"""v1.1.1 tests: V2-I verification, Student ID rules, ID reviews, unverified limits,
report & block, Developer role, test inbox and SQL-injection attempts.
All people here are fictional (example Student ID 2020-0001)."""
from datetime import timedelta

from django.contrib.auth import SESSION_KEY, get_user_model
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    AbuseReport, ChatMessage, ClaimApplication, Conversation, EmailVerificationCode, IdReviewCase, InAppNotification,
    ItemPost, Profile, StudentIdRecord, TestEmail, UserBlock,
)
from core.services import process_due_actions
from core.verification import chat_limit_message, issue_code, mark_verified

from .base import PASSWORD, FindItTestCase

User = get_user_model()


def signup(client, student_id="2020-0001", email="juan.cruz@example.com", **extra):
    data = {
        "first_name": "Juan", "last_name": "Cruz", "student_id": student_id, "email": email,
        "password1": PASSWORD, "password2": PASSWORD,
    }
    data.update(extra)
    return client.post(reverse("signup"), data)


class SignupAndSignInTests(FindItTestCase):
    def test_signup_uses_email_sign_in_and_sends_three_welcome_messages(self):
        response = signup(self.client)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="juan.cruz@example.com")
        self.assertNotEqual(user.username, "2020-0001")
        self.assertEqual(user.profile.student_id, "2020-0001")
        self.assertIsNone(user.profile.email_verified_at)
        notices = list(InAppNotification.objects.filter(recipient=user).order_by("pk"))
        self.assertEqual(len(notices), 3)
        self.assertTrue(any(n.link == reverse("verify-email") for n in notices))
        self.assertEqual(len(mail.outbox), 3)
        self.assertIn("verification code", mail.outbox[1].body)
        # Sign in with email works; the Student ID does not work until it is verified.
        self.client.logout()
        bad = self.client.post(reverse("login"), {"username": "2020-0001", "password": PASSWORD})
        self.assertEqual(bad.status_code, 200)
        good = self.client.post(reverse("login"), {"username": "JUAN.CRUZ@example.com", "password": PASSWORD})
        self.assertEqual(good.status_code, 302)

    def test_notification_click_opens_its_page(self):
        signup(self.client)
        user = User.objects.get(email="juan.cruz@example.com")
        notice = InAppNotification.objects.get(recipient=user, link=reverse("verify-email"))
        response = self.client.get(reverse("notifications") + f"?open={notice.pk}")
        self.assertRedirects(response, reverse("verify-email"))
        notice.refresh_from_db()
        self.assertIsNotNone(notice.read_at)

    def test_student_cannot_sign_in_with_internal_username(self):
        signup(self.client)
        user = User.objects.get(email="juan.cruz@example.com")
        self.client.logout()
        response = self.client.post(reverse("login"), {"username": user.username, "password": PASSWORD})
        self.assertEqual(response.status_code, 200)


class VerificationTests(FindItTestCase):
    def setUp(self):
        super().setUp()
        signup(self.client)
        self.user = User.objects.get(email="juan.cruz@example.com")

    def _code(self):
        mail.outbox.clear()
        EmailVerificationCode.objects.all().delete()
        return issue_code(self.user)

    def test_wrong_code_counts_and_right_code_verifies_and_locks(self):
        code = self._code()
        wrong = "000000" if code != "000000" else "111111"
        self.client.post(reverse("verify-email"), {"code": wrong})
        self.user.profile.refresh_from_db()
        self.assertIsNone(self.user.profile.email_verified_at)
        self.client.post(reverse("verify-email"), {"code": code})
        self.user.profile.refresh_from_db()
        self.assertIsNotNone(self.user.profile.email_verified_at)
        self.assertTrue(self.user.profile.student_id_locked)
        self.client.logout()
        response = self.client.post(reverse("login"), {"username": "2020-0001", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)

    def test_code_stops_after_five_wrong_tries_and_expires(self):
        code = self._code()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.client.post(reverse("verify-email"), {"code": wrong})
        self.client.post(reverse("verify-email"), {"code": code})
        self.user.profile.refresh_from_db()
        self.assertIsNone(self.user.profile.email_verified_at)
        code = self._code()
        EmailVerificationCode.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.client.post(reverse("verify-email"), {"code": code})
        self.user.profile.refresh_from_db()
        self.assertIsNone(self.user.profile.email_verified_at)

    def test_code_requests_are_rate_limited(self):
        EmailVerificationCode.objects.all().delete()
        self.client.post(reverse("verify-email"), {"action": "send"})
        self.client.post(reverse("verify-email"), {"action": "send"})  # within 60 seconds: refused
        self.assertEqual(EmailVerificationCode.objects.filter(user=self.user).count(), 1)

    def test_changing_email_removes_verified_badge(self):
        mark_verified(self.user)
        self.client.post(reverse("edit-profile"), {"first_name": "Juan", "last_name": "Cruz", "email": "new@example.com"})
        self.user.profile.refresh_from_db()
        self.assertIsNone(self.user.profile.email_verified_at)
        self.assertTrue(self.user.profile.student_id_locked)

    def test_code_is_stored_hashed(self):
        code = self._code()
        row = EmailVerificationCode.objects.get(user=self.user)
        self.assertNotIn(code, row.code_hash)


class StudentIdRuleTests(FindItTestCase):
    def make_unverified(self, email, student_id="2020-0001"):
        from django.test import Client
        client = Client()
        signup(client, student_id=student_id, email=email)
        return User.objects.get(email=email), client

    def test_duplicates_allowed_until_verified_then_grace_and_clear(self):
        a, _ = self.make_unverified("a@example.com")
        b, b_client = self.make_unverified("b@example.com")
        self.assertEqual(Profile.objects.filter(student_id="2020-0001").count(), 2)
        mark_verified(a)
        b.profile.refresh_from_db()
        self.assertIsNotNone(b.profile.id_conflict_deadline)
        self.assertGreater(b.profile.id_conflict_deadline, timezone.now() + timedelta(days=13))
        # A new sign-up with the locked ID is refused.
        response = signup(self.client, email="c@example.com")
        self.assertContains(response, "verified by another account")
        # After the grace period the timer runner clears B's ID; B must set a new one.
        Profile.objects.filter(user=b).update(id_conflict_deadline=timezone.now() - timedelta(minutes=1))
        process_due_actions()
        b.profile.refresh_from_db()
        self.assertIsNone(b.profile.student_id)
        self.assertRedirects(b_client.get(reverse("home")), reverse("change-student-id"))
        b_client.post(reverse("change-student-id"), {"student_id": "2020-0002", "confirm": "on"})
        b.profile.refresh_from_db()
        self.assertEqual(b.profile.student_id, "2020-0002")

    def test_open_appeal_pauses_the_deadline(self):
        a, _ = self.make_unverified("a@example.com")
        b, b_client = self.make_unverified("b@example.com")
        mark_verified(a)
        b_client.get(reverse("id-review-new"))
        case = IdReviewCase.objects.create(kind="APPEAL", requester=b, student_id="2020-0001", holder=a, message="x")
        Profile.objects.filter(user=b).update(id_conflict_deadline=timezone.now() - timedelta(minutes=1))
        process_due_actions()
        b.profile.refresh_from_db()
        self.assertEqual(b.profile.student_id, "2020-0001")
        self.assertTrue(case.is_open)

    def test_third_different_student_id_disables_account(self):
        user, client = self.make_unverified("a@example.com")
        client.post(reverse("change-student-id"), {"student_id": "2020-0002", "confirm": "on"})
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        client.post(reverse("change-student-id"), {"student_id": "2020-0003", "confirm": "on"})
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertIsNotNone(user.profile.flagged_at)
        self.assertEqual(StudentIdRecord.objects.filter(user=user).count(), 3)

    def test_locked_id_cannot_be_changed_by_owner(self):
        response = self.client_for(self.finder).post(reverse("change-student-id"), {"student_id": "2020-0009", "confirm": "on"})
        self.assertEqual(response.status_code, 200)
        self.finder.profile.refresh_from_db()
        self.assertEqual(self.finder.profile.student_id, "2026-0001")


class IdReviewTests(FindItTestCase):
    @staticmethod
    def captcha():
        from captcha.models import CaptchaStore
        key = CaptchaStore.generate_key()
        return {"captcha_0": key, "captcha_1": CaptchaStore.objects.get(hashkey=key).response}

    def test_impostor_signup_review_and_transfer(self):
        # finder (2026-0001) is verified and holds the ID. A newcomer says it is theirs.
        response = signup(self.client, student_id="2026-0001", email="real.owner@example.com", id_is_mine="on")
        self.assertRedirects(response, reverse("id-review-new"), fetch_redirect_response=False)
        newcomer = User.objects.get(email="real.owner@example.com")
        self.assertIsNone(newcomer.profile.student_id)
        # The captcha is required: a wrong answer sends nothing.
        self.client.post(reverse("id-review-new"), {
            "student_id": "2026-0001", "message": "I never made that account.", "captcha_0": "x", "captcha_1": "no",
        })
        self.assertFalse(IdReviewCase.objects.exists())
        self.client.post(reverse("id-review-new"), {
            "student_id": "2026-0001", "message": "I never made that account.", **self.captcha(),
        })
        case = IdReviewCase.objects.get(requester=newcomer)
        self.assertEqual(case.kind, IdReviewCase.Kind.IMPOSTOR)
        # Only one open case per account.
        self.client.post(reverse("id-review-new"), {"student_id": "2026-0001", "message": "again", **self.captcha()})
        self.assertEqual(IdReviewCase.objects.filter(requester=newcomer).count(), 1)
        # Plain staff cannot decide; admins and verified moderators can.
        self.assertEqual(self.client_for(self.staff).get(reverse("id-reviews")).status_code, 403)
        admin = self.client_for(self.admin)
        self.assertContains(admin.get(reverse("id-reviews")), "2026-0001")
        admin.post(reverse("id-review-detail", args=[case.pk]), {"decision": "transfer", "note": "Checked school ID."})
        newcomer.profile.refresh_from_db()
        self.finder.profile.refresh_from_db()
        self.assertEqual(newcomer.profile.student_id, "2026-0001")
        self.assertTrue(newcomer.profile.student_id_locked)
        self.assertIsNone(self.finder.profile.student_id)

    def test_keep_decision(self):
        newcomer = self.make_user("2026-0099", verified=False)
        case = IdReviewCase.objects.create(kind="IMPOSTOR", requester=newcomer, student_id="2026-0001",
                                           holder=self.finder, message="mine")
        self.client_for(self.admin).post(reverse("id-review-detail", args=[case.pk]), {"decision": "keep"})
        case.refresh_from_db()
        self.assertEqual(case.status, IdReviewCase.Status.KEPT)
        self.finder.profile.refresh_from_db()
        self.assertEqual(self.finder.profile.student_id, "2026-0001")


class UnverifiedLimitTests(FindItTestCase):
    def setUp(self):
        super().setUp()
        self.casey = self.make_user("2026-0005", verified=False)

    def test_one_post_per_day(self):
        self.create_post(self.casey, post_type="LOST")
        from .base import photo
        response = self.client_for(self.casey).post("/posts/new/", {
            "post_type": "LOST", "category": self.category.pk, "photos": [photo()],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ItemPost.objects.filter(author=self.casey).count(), 1)

    def test_three_open_claims_at_most(self):
        posts = [self.create_post(self.finder) for _ in range(4)]
        for post in posts:
            self.claim(post, self.casey)
        self.assertEqual(ClaimApplication.objects.filter(claimant=self.casey).count(), 3)

    def test_chat_length_and_rate_limits(self):
        self.assertIsNotNone(chat_limit_message(self.casey, "x" * 101))
        self.assertIsNone(chat_limit_message(self.casey, "hello"))
        self.assertIsNone(chat_limit_message(self.alice, "x" * 500))  # verified: normal limits
        post = self.create_post(self.finder)
        self.claim(post, self.casey)
        conversation = Conversation.objects.get(claim__claimant=self.casey)
        for i in range(10):
            ChatMessage.objects.create(conversation=conversation, sender=self.casey, text=f"m{i}")
        self.assertIsNotNone(chat_limit_message(self.casey, "one more"))

    def test_claims_expire_after_three_idle_days(self):
        post = self.create_post(self.finder)
        self.claim(post, self.casey)
        self.claim(post, self.alice)
        ClaimApplication.objects.update(last_activity_at=timezone.now() - timedelta(days=4))
        process_due_actions()
        self.assertEqual(ClaimApplication.objects.get(claimant=self.casey).status, "EXPIRED")
        self.assertEqual(ClaimApplication.objects.get(claimant=self.alice).status, "SUBMITTED")

    def test_warning_shown_to_others_not_to_self(self):
        post = self.create_post(self.casey, post_type="LOST")
        warning = "this user is not yet verified"
        self.assertContains(self.client_for(self.alice).get(f"/p/{post.pk}/"), warning)
        self.assertNotContains(self.client_for(self.casey).get(f"/p/{post.pk}/"), warning)
        self.assertContains(self.client_for(self.alice).get(f"/p/{post.pk}/"), "Not verified")


class ReportBlockTests(FindItTestCase):
    def test_block_closes_claim_and_keeps_apart(self):
        post = self.create_post(self.finder)
        self.claim(post, self.alice)
        claim = ClaimApplication.objects.get(claimant=self.alice)
        conversation = claim.conversation
        response = self.client_for(self.finder).post(
            reverse("report-block", args=[self.alice.pk]) + f"?conversation={conversation.pk}",
            {"reason": "", "details": "", "next": f"/p/{post.pk}/"},
        )
        self.assertEqual(response.status_code, 302)
        claim.refresh_from_db()
        conversation.refresh_from_db()
        self.assertEqual(claim.status, "CLOSED")
        self.assertTrue(conversation.is_closed)
        report = AbuseReport.objects.get(reporter=self.finder)
        self.assertEqual(report.reason, AbuseReport.Reason.BLOCK)
        self.assertEqual(report.conversation, conversation)
        # Alice cannot claim again or comment on the finder's posts.
        self.claim(post, self.alice)
        self.assertEqual(ClaimApplication.objects.filter(claimant=self.alice).count(), 1)
        self.client_for(self.alice).post(f"/posts/{post.pk}/comment/", {"text": "hi"})
        self.assertFalse(post.comments.exists())
        # Unblock from the profile.
        self.client_for(self.finder).post(reverse("blocked-people"), {"user_id": self.alice.pk})
        self.assertFalse(UserBlock.objects.exists())

    def test_reason_given_uses_that_category(self):
        post = self.create_post(self.finder)
        self.client_for(self.alice).post(reverse("report-block", args=[self.finder.pk]), {"reason": "SPAM"})
        self.assertEqual(AbuseReport.objects.get().reason, "SPAM")
        self.assertTrue(UserBlock.objects.filter(blocker=self.alice, blocked=self.finder).exists())
        self.assertTrue(post)

    def test_staff_cannot_be_blocked_and_strangers_cannot_block(self):
        self.client_for(self.alice).post(reverse("report-block", args=[self.staff.pk]), {})
        response = self.client_for(self.alice).post(reverse("report-block", args=[self.bob.pk]), {})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(UserBlock.objects.exists())


class DeveloperRoleTests(FindItTestCase):
    def setUp(self):
        super().setUp()
        self.developer = self.make_user("dev.test", role=Profile.Role.DEVELOPER)
        self.developer.is_staff = self.developer.is_superuser = True
        self.developer.save()

    def edit(self, actor, account, role):
        return self.client_for(actor).post(reverse("edit-account", args=[account.pk]), {
            "first_name": account.first_name or "X", "last_name": "", "email": account.email, "contact_number": "",
            "role": role, "is_active": "1",
        })

    def test_only_developer_can_make_admins(self):
        self.edit(self.admin, self.staff, "admin")
        self.staff.profile.refresh_from_db()
        self.assertEqual(self.staff.profile.role, Profile.Role.STAFF)
        self.edit(self.developer, self.staff, "admin")
        self.staff.profile.refresh_from_db()
        self.assertEqual(self.staff.profile.role, Profile.Role.ADMIN)

    def test_admin_cannot_change_admin_or_see_developer(self):
        other_admin = self.make_user("admin.two", role=Profile.Role.ADMIN)
        self.edit(self.admin, other_admin, "staff")
        other_admin.profile.refresh_from_db()
        self.assertEqual(other_admin.profile.role, Profile.Role.ADMIN)
        self.assertEqual(self.client_for(self.admin).get(reverse("edit-account", args=[self.developer.pk])).status_code, 404)
        response = self.client_for(self.admin).post(reverse("staff-account-status", args=[self.developer.pk]), {"action": "suspend"})
        self.assertEqual(response.status_code, 403)
        listing = self.client_for(self.admin).get(reverse("staff-accounts"))
        self.assertNotIn(self.developer, list(listing.context["page_obj"]))

    def test_django_admin_is_developer_only(self):
        self.admin.is_staff = self.admin.is_superuser = True
        self.admin.save()
        self.assertEqual(self.client_for(self.admin).get("/django-admin/").status_code, 302)
        self.assertEqual(self.client_for(self.developer).get("/django-admin/").status_code, 200)

    def test_superuser_is_not_admin_automatically(self):
        user = User.objects.create_superuser("root.test", "root@example.com", PASSWORD)
        self.assertEqual(user.profile.role, Profile.Role.STUDENT)
        from core.permissions import is_admin
        self.assertFalse(is_admin(user))

    def test_developer_password_never_reset_by_email(self):
        self.developer.email = "dev@example.com"
        self.developer.save()
        self.client.post(reverse("password_reset"), {"email": "dev@example.com"})
        self.assertEqual(len(mail.outbox), 0)

    def test_developer_command_refuses_without_terminal(self):
        with self.assertRaises(CommandError):
            call_command("create_developer")

    def test_seed_demo_refuses_on_online_site(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo")  # tests run with DEBUG off, like an online site


class TestInboxTests(FindItTestCase):
    @override_settings(FINDIT_TEST_INBOX=True)
    def test_each_person_sees_only_their_own_emails(self):
        self.alice.email = "alice@example.com"
        self.alice.save()
        TestEmail.objects.create(recipient=self.alice, to="alice@example.com", subject="Alice code", body="111111")
        TestEmail.objects.create(recipient=self.bob, to="bob@example.com", subject="Bob code", body="222222")
        response = self.client_for(self.alice).get(reverse("test-inbox"))
        self.assertContains(response, "Alice code")
        self.assertNotContains(response, "Bob code")

    @override_settings(FINDIT_TEST_INBOX=False)
    def test_inbox_off_online(self):
        self.assertEqual(self.client_for(self.alice).get(reverse("test-inbox")).status_code, 404)


class SqlInjectionTests(FindItTestCase):
    """What people type is always sent to the database as a separate value (parameterized
    query), so these classic attacks are treated as plain text and do nothing."""
    ATTACKS = ["' OR '1'='1", "' OR 1=1 --", "admin'--", "\"; DROP TABLE core_itempost; --", "2026-0001' OR 'x'='x"]

    def test_login_attacks_fail(self):
        for attack in self.ATTACKS:
            response = self.client.post(reverse("login"), {"username": attack, "password": attack})
            self.assertIn(response.status_code, {200, 429})
            self.assertNotIn(SESSION_KEY, self.client.session)

    def test_signup_and_search_attacks_are_plain_text(self):
        post = self.create_post(self.finder)
        for attack in self.ATTACKS:
            response = signup(self.client, student_id=attack, email="x@example.com")
            self.assertEqual(response.status_code, 200)
            response = self.client_for(self.alice).get(reverse("home"), {"q": attack, "category": attack, "type": attack})
            self.assertEqual(response.status_code, 200)
        self.assertTrue(ItemPost.objects.filter(pk=post.pk).exists())
        self.assertFalse(User.objects.filter(email="x@example.com").exists())
