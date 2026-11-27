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


class BugFixTests(FindItTestCase):
    def test_bug_002_damaged_claim_id_does_not_crash(self):
        post = self.create_post(self.finder)
        client = self.client_for(self.finder)
        self.assertEqual(client.post(f"/posts/{post.pk}/returned/", {"claim_id": "not-a-uuid"}).status_code, 404)
        ItemPost.objects.filter(pk=post.pk).update(status=ItemPost.Status.TURNED_OVER)
        staff = self.client_for(self.staff)
        self.assertEqual(staff.post(f"/posts/{post.pk}/claimed/", {"claim_id": "bad"}).status_code, 404)
        self.assertEqual(staff.post(f"/posts/{post.pk}/claimed/", {"recipient_id": "abc"}).status_code, 302)

    def test_bug_003_impossible_report_dates_do_not_crash(self):
        client = self.client_for(self.admin)
        for url in ("/staff/reports/", "/staff/general-reports/"):
            self.assertEqual(client.get(url, {"date_from": "2026-99-99", "date_to": "abc"}).status_code, 200)


class SocketHelpers:
    def setUp(self):
        super().setUp()
        from core.consumers import ConversationConsumer
        ConversationConsumer.DB_THREAD_SENSITIVE = True  # TestCase data lives in one unsaved transaction
        self.addCleanup(setattr, ConversationConsumer, "DB_THREAD_SENSITIVE", False)

    def _communicator(self, user, conversation):
        from channels.routing import URLRouter
        from channels.testing import WebsocketCommunicator
        from django.urls import path
        from core.consumers import ConversationConsumer
        app = URLRouter([path("ws/conversations/<uuid:conversation_id>/", ConversationConsumer.as_asgi())])
        communicator = WebsocketCommunicator(app, f"/ws/conversations/{conversation.pk}/")
        communicator.scope["user"] = user
        return communicator

    def _run(self, coro):
        from asgiref.sync import async_to_sync
        return async_to_sync(coro)()


class ChatQueueTests(SocketHelpers, FindItTestCase):
    """CHG-003: messages carry a one-time id, so a message re-sent from the browser's
    queue after a dropped connection is saved once and never counted twice."""

    def test_resend_after_reconnect_is_saved_once(self):
        post = self.create_post(self.finder)
        self.claim(post, self.alice)
        conversation = Conversation.objects.get(claim__claimant=self.alice)

        async def scenario():
            first = self._communicator(self.alice, conversation)
            await first.connect()
            await first.receive_json_from()  # connection notice
            await first.send_json_to({"message": "Is it still there?", "client_id": "queue-1"})
            await first.send_json_to({"message": "Is it still there?", "client_id": "queue-1"})  # double press
            a = await first.receive_json_from()
            b = await first.receive_json_from()
            await first.disconnect()
            # Connection dropped before the browser saw the reply: the queue sends it again.
            second = self._communicator(self.alice, conversation)
            await second.connect()
            await second.receive_json_from()
            await second.send_json_to({"message": "Is it still there?", "client_id": "queue-1"})
            c = await second.receive_json_from()
            await second.disconnect()
            return a, b, c

        a, b, c = self._run(scenario)
        self.assertEqual({a["type"], b["type"], c["type"]}, {"message"})
        self.assertEqual(a["id"], c["id"])
        self.assertEqual(ChatMessage.objects.filter(conversation=conversation, client_id="queue-1").count(), 1)

    def test_resend_is_not_blocked_by_unverified_limit(self):
        casey = self.make_user("2026-0005", verified=False)
        post = self.create_post(self.finder)
        self.claim(post, casey)
        conversation = Conversation.objects.get(claim__claimant=casey)
        for i in range(9):
            ChatMessage.objects.create(conversation=conversation, sender=casey, text=f"m{i}", client_id=f"old-{i}")

        async def scenario():
            ws = self._communicator(casey, conversation)
            await ws.connect()
            await ws.receive_json_from()
            await ws.send_json_to({"message": "tenth", "client_id": "q-10"})
            first = await ws.receive_json_from()
            await ws.send_json_to({"message": "tenth", "client_id": "q-10"})  # resend from the queue
            again = await ws.receive_json_from()
            await ws.send_json_to({"message": "eleventh", "client_id": "q-11"})
            refused = await ws.receive_json_from()
            await ws.disconnect()
            return first, again, refused

        first, again, refused = self._run(scenario)
        self.assertEqual(first["type"], "message")
        self.assertEqual(again["type"], "message")
        self.assertEqual(refused["type"], "error")
        self.assertEqual(refused["client_id"], "q-11")
        self.assertEqual(ChatMessage.objects.filter(conversation=conversation, sender=casey).count(), 10)

    def test_someone_elses_message_id_cannot_be_reused(self):
        post = self.create_post(self.finder)
        self.claim(post, self.alice)
        conversation = Conversation.objects.get(claim__claimant=self.alice)
        ChatMessage.objects.create(conversation=conversation, sender=self.finder, text="from finder", client_id="shared-id")

        async def scenario():
            ws = self._communicator(self.alice, conversation)
            await ws.connect()
            await ws.receive_json_from()
            await ws.send_json_to({"message": "fake", "client_id": "shared-id"})
            reply = await ws.receive_json_from()
            await ws.disconnect()
            return reply

        self.assertEqual(self._run(scenario)["type"], "error")


class NotificationQueueTests(SocketHelpers, FindItTestCase):
    """CHG-004 / BUG-004 / BUG-005."""

    def _notice_communicator(self, user):
        from channels.routing import URLRouter
        from channels.testing import WebsocketCommunicator
        from django.urls import path
        from core.consumers import NotificationConsumer
        communicator = WebsocketCommunicator(URLRouter([path("ws/notifications/", NotificationConsumer.as_asgi())]), "/ws/notifications/")
        communicator.scope["user"] = user
        return communicator

    def test_reconnect_gets_true_counts_and_missed_notices(self):
        from core.services import notify_user
        post = self.create_post(self.finder)
        InAppNotification.objects.filter(recipient=self.alice).update(read_at=timezone.now())
        notify_user(self.alice, post, "first notice")
        before = InAppNotification.objects.filter(recipient=self.alice).latest("pk").pk
        notify_user(self.alice, post, "missed while offline", priority=True)

        async def scenario():
            ws = self._notice_communicator(self.alice)
            await ws.connect()
            sync = await ws.receive_json_from()
            await ws.send_json_to({"type": "since", "after_id": before})
            missed = await ws.receive_json_from()
            await ws.send_json_to([1, 2])           # junk is ignored, not a crash
            await ws.send_to(text_data="not json")
            await ws.send_json_to({"type": "since", "after_id": "abc"})
            nothing = await ws.receive_nothing(timeout=0.3)
            await ws.send_json_to({"type": "sync"})  # BUG-006: periodic re-check
            resync = await ws.receive_json_from()
            assert resync["type"] == "sync" and resync["unread"] == 2
            await ws.disconnect()
            return sync, missed, nothing

        sync, missed, nothing = self._run(scenario)
        self.assertEqual(sync["type"], "sync")
        self.assertEqual(sync["unread"], 2)
        self.assertEqual(sync["priority"], 1)
        self.assertEqual(missed["text"], "missed while offline")
        self.assertTrue(missed["catch_up"])
        self.assertTrue(nothing)

    def test_live_push_waits_for_the_save(self):
        from core.services import notify_user
        post = self.create_post(self.finder)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            notify_user(self.alice, post, "pushed after commit")
        self.assertEqual(len(callbacks), 1)  # BUG-004: the push is queued until the save is final

    def test_bug_005_non_object_json_does_not_crash_chat(self):
        post = self.create_post(self.finder)
        self.claim(post, self.alice)
        conversation = Conversation.objects.get(claim__claimant=self.alice)

        async def scenario():
            ws = self._communicator(self.alice, conversation)
            await ws.connect()
            await ws.receive_json_from()
            replies = []
            for junk in ([1], "hello", 5, None):
                await ws.send_json_to(junk)
                replies.append(await ws.receive_json_from())
            await ws.send_json_to({"message": "still works", "client_id": "ok-1"})
            replies.append(await ws.receive_json_from())
            await ws.disconnect()
            return replies

        replies = self._run(scenario)
        self.assertEqual([r["type"] for r in replies], ["error"] * 4 + ["message"])


from django.test import TransactionTestCase


class ChatWorkerThreadTests(SocketHelpers, TransactionTestCase):
    """PERF-002: the real path, with chat saves in their own worker thread and saved data."""
    serialized_rollback = True

    def setUp(self):
        TransactionTestCase.setUp(self)  # keep the real worker threads (no SocketHelpers switch)
        from core.models import Category
        self.finder = FindItTestCase.make_user(self, "2026-0001")
        self.alice = FindItTestCase.make_user(self, "2026-0002")
        post = ItemPost.objects.create(author=self.finder, post_type="LOST", category=Category.objects.first())
        self.conversation = Conversation.objects.create(post=post, initiator=self.alice, recipient=self.finder)

    def test_message_saved_once_through_worker_thread(self):
        async def scenario():
            ws = self._communicator(self.alice, self.conversation)
            await ws.connect()
            await ws.receive_json_from()
            replies = []
            for _ in range(3):
                await ws.send_json_to({"message": "hello", "client_id": "thread-1"})
                replies.append(await ws.receive_json_from())
            await ws.disconnect()
            return replies

        replies = self._run(scenario)
        self.assertEqual({r["type"] for r in replies}, {"message"})
        self.assertEqual(ChatMessage.objects.filter(client_id="thread-1").count(), 1)


class CompressedPhotoTests(FindItTestCase):
    """PERF-003: originals are never stored; a compressed photo + small preview are."""

    def big_upload(self):
        import io
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        image = Image.effect_noise((2600, 1900), 60).convert("RGB")
        exif = Image.Exif()
        exif[0x8825] = {2: (7.0, 5.0, 0.0)}  # GPS block, like a phone photo
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=90, exif=exif)
        self.assertGreater(buffer.tell(), 1_000_000)
        return SimpleUploadedFile("phone.jpg", buffer.getvalue(), content_type="image/jpeg")

    def test_upload_is_compressed_and_original_not_kept(self):
        from PIL import Image
        from core.models import PostPhoto
        response = self.client_for(self.finder).post("/posts/new/", {
            "post_type": "FOUND", "category": self.category.pk, "photos": [self.big_upload()],
        })
        self.assertEqual(response.status_code, 302)
        photo = PostPhoto.objects.latest("pk")
        self.assertLessEqual(photo.image.size, 300 * 1024)
        self.assertLessEqual(photo.preview.size, 40 * 1024)
        with Image.open(photo.image.path) as full, Image.open(photo.preview.path) as small:
            self.assertLessEqual(max(full.size), 1600)
            self.assertLessEqual(max(small.size), 480)
            self.assertNotIn(0x8825, full.getexif())  # GPS removed
        self.assertTrue(photo.image.name.endswith(".jpg"))
        self.assertNotIn("phone", photo.image.name)  # the original upload was not saved

    def test_transparent_png_and_file_cleanup(self):
        import io, os
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        from core.models import PostPhoto
        buffer = io.BytesIO()
        Image.new("RGBA", (800, 600), (0, 0, 0, 0)).save(buffer, "PNG")
        self.create_post(self.finder, photos=[SimpleUploadedFile("t.png", buffer.getvalue(), content_type="image/png")])
        photo = PostPhoto.objects.latest("pk")
        paths = [photo.image.path, photo.preview.path]
        self.assertTrue(all(os.path.exists(p) for p in paths))
        with self.captureOnCommitCallbacks(execute=True):
            photo.delete()
        self.assertFalse(any(os.path.exists(p) for p in paths))

    def test_lists_use_previews(self):
        post = self.create_post(self.finder)
        html = self.client_for(self.alice).get("/home/").content.decode()
        self.assertIn(post.cover_photo.preview.url, html)
        self.assertIn('loading="lazy"', html)


class ChatHistoryTests(FindItTestCase):
    """CHG-005: pages sized by bytes, older/newer/around, search, rate limits."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()
        post = self.create_post(self.finder)
        self.claim(post, self.alice)
        self.conversation = Conversation.objects.get(claim__claimant=self.alice)
        ChatMessage.objects.bulk_create([
            ChatMessage(conversation=self.conversation, sender=self.alice if i % 2 else self.finder,
                        text=("long " * 200 if i % 10 == 0 else f"short message {i}"))
            for i in range(300)
        ])
        ChatMessage.objects.create(conversation=self.conversation, sender=self.finder, text="The umbrella is BLUE with a strap")
        self.url = f"/conversations/{self.conversation.pk}/messages/"
        self.client_a = self.client_for(self.alice)

    def test_pages_are_sized_by_bytes(self):
        from core.chat_history import MAX_MESSAGES, OVERHEAD_BYTES, PAGE_BYTES
        data = self.client_a.get(self.url, {"latest": "1"}).json()
        size = sum(len(m["text"].encode()) + OVERHEAD_BYTES for m in data["messages"])
        self.assertLessEqual(size, PAGE_BYTES + 1100)  # one long message may cross the line
        self.assertLessEqual(len(data["messages"]), MAX_MESSAGES)
        self.assertTrue(data["has_older"])
        ids = [m["id"] for m in data["messages"]]
        self.assertEqual(ids, sorted(ids))
        older = self.client_a.get(self.url, {"before": ids[0]}).json()
        self.assertTrue(older["messages"])
        self.assertLess(older["messages"][-1]["id"], ids[0])
        newer = self.client_a.get(self.url, {"after": older["messages"][0]["id"]}).json()
        self.assertEqual(newer["messages"][0]["id"], older["messages"][1]["id"])

    def test_whole_history_can_be_read_back_without_gaps(self):
        seen, before = [], None
        data = self.client_a.get(self.url, {"latest": "1"}).json()
        while True:
            seen = [m["id"] for m in data["messages"]] + seen
            if not data["has_older"]:
                break
            data = self.client_a.get(self.url, {"before": seen[0]}).json()
        self.assertEqual(seen, list(self.conversation.messages.order_by("pk").values_list("pk", flat=True)))

    def test_search_and_open_result(self):
        data = self.client_a.get(self.url, {"q": "blue"}).json()
        self.assertEqual(len(data["results"]), 1)
        self.assertIn("BLUE", data["results"][0]["snippet"])
        around = self.client_a.get(self.url, {"around": data["results"][0]["id"]}).json()
        self.assertIn(data["results"][0]["id"], [m["id"] for m in around["messages"]])
        self.assertTrue(self.client_a.get(self.url, {"q": "b"}).json()["too_short"])
        self.assertEqual(self.client_a.get(self.url, {"q": "' OR 1=1 --"}).json()["results"], [])
        self.assertEqual(len(self.client_a.get(self.url, {"q": "short"}).json()["results"]), 30)

    def test_strangers_cannot_read_or_search(self):
        self.assertEqual(self.client_for(self.bob).get(self.url, {"q": "blue"}).status_code, 403)
        self.assertEqual(self.client_for(self.bob).get(self.url, {"latest": "1"}).status_code, 403)
        other = Conversation.objects.create(post=self.conversation.post, initiator=self.bob, recipient=self.finder)
        self.assertEqual(self.client_a.get(f"/conversations/{other.pk}/messages/", {"around": "1"}).status_code, 403)

    def test_search_and_paging_are_rate_limited(self):
        from core.chat_history import PAGES_PER_MINUTE, SEARCHES_PER_MINUTE
        codes = [self.client_a.get(self.url, {"q": "blue"}).status_code for _ in range(SEARCHES_PER_MINUTE + 1)]
        self.assertEqual(codes[-1], 429)
        codes = [self.client_a.get(self.url, {"latest": "1"}).status_code for _ in range(PAGES_PER_MINUTE + 1)]
        self.assertEqual(codes[-1], 429)

    def test_bad_values_do_not_crash(self):
        for params in ({"before": "abc"}, {"after": "-1"}, {"around": "99999999"}, {"q": "x" * 5000}, {}):
            self.assertIn(self.client_a.get(self.url, params).status_code, {200, 404})


import tempfile as _tempfile

PRIVATE_DIR = _tempfile.mkdtemp(prefix="findit-test-private-")


def _ffmpeg_exe():
    from core.chat_media import _ffmpeg
    return _ffmpeg()


def make_video(seconds=3, size="640x360", audio=True):
    import subprocess, os
    from django.core.files.uploadedfile import SimpleUploadedFile
    path = os.path.join(_tempfile.mkdtemp(), "clip.mp4")
    cmd = [_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=24:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if audio else []) + ["-shortest", path]
    subprocess.run(cmd, check=True, capture_output=True)
    with open(path, "rb") as handle:
        return SimpleUploadedFile("clip.mp4", handle.read(), content_type="video/mp4")


@override_settings(PRIVATE_MEDIA_ROOT=PRIVATE_DIR)
class ChatMediaTests(FindItTestCase):
    """CHG-006: photos/videos in chats are re-encoded, private, limited and duplicate-safe."""

    def setUp(self):
        super().setUp()
        post = self.create_post(self.finder)
        self.claim(post, self.alice)
        self.conversation = Conversation.objects.get(claim__claimant=self.alice)
        self.upload_url = f"/conversations/{self.conversation.pk}/attachments/"

    def send(self, user, upload, client_id="c1"):
        return self.client_for(user).post(self.upload_url, {"file": upload, "client_id": client_id})

    def jpeg_with_hidden_payload(self, size=(1200, 900)):
        import io
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        buffer = io.BytesIO()
        Image.effect_noise(size, 50).convert("RGB").save(buffer, "JPEG", quality=90)
        payload = b"PK\x03\x04TROJAN-PAYLOAD-" + b"X" * 2000  # a zip hidden after the picture
        return SimpleUploadedFile("photo.jpg", buffer.getvalue() + payload, content_type="image/jpeg")

    def test_photo_is_reencoded_private_and_payload_removed(self):
        from core.models import ChatAttachment
        reply = self.send(self.alice, self.jpeg_with_hidden_payload()).json()
        self.assertEqual(reply["status"], "READY")
        attachment = ChatAttachment.objects.get()
        self.assertFalse(attachment.upload)                      # received file deleted
        with attachment.file.open("rb") as handle:
            data = handle.read()
        self.assertNotIn(b"TROJAN-PAYLOAD", data)
        self.assertTrue(data.startswith(b"\xff\xd8"))            # a real JPEG
        self.assertTrue(attachment.message_id)
        url = reply["attachment"]["url"]
        ok = self.client_for(self.finder).get(url)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.client_for(self.bob).get(url).status_code, 404)   # strangers: nothing
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 404)
        history = self.client_for(self.finder).get(f"/conversations/{self.conversation.pk}/messages/", {"latest": "1"}).json()
        self.assertEqual(history["messages"][-1]["attachment"]["kind"], "PHOTO")

    def test_same_upload_twice_is_saved_once(self):
        from core.models import ChatAttachment, ChatMessage
        self.send(self.alice, self.jpeg_with_hidden_payload(), "same")
        self.send(self.alice, self.jpeg_with_hidden_payload(), "same")
        self.assertEqual(ChatAttachment.objects.count(), 1)
        self.assertEqual(ChatMessage.objects.filter(client_id="att-same").count(), 1)

    def test_video_is_compressed_to_mp4_with_ranges(self):
        from core.chat_media import run_pending
        from core.models import ChatAttachment
        reply = self.send(self.alice, make_video()).json()
        self.assertEqual(reply["status"], "PROCESSING")
        run_pending()
        attachment = ChatAttachment.objects.get()
        self.assertEqual(attachment.status, "READY", attachment.error)
        self.assertLessEqual(max(attachment.width, attachment.height), 1280)
        self.assertTrue(attachment.preview)
        self.assertAlmostEqual(attachment.duration_seconds, 3, delta=0.6)
        url = f"/chat-media/{attachment.pk}/file/"
        part = self.client_for(self.finder).get(url, HTTP_RANGE="bytes=0-99")
        self.assertEqual(part.status_code, 206)
        self.assertEqual(len(b"".join(part.streaming_content)), 100)
        self.assertEqual(part["Content-Type"], "video/mp4")

    def test_fake_files_are_refused(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.chat_media import run_pending
        from core.models import ChatAttachment
        fake_photo = SimpleUploadedFile("evil.jpg", b"MZ\x90\x00 this is a program, not a photo", content_type="image/jpeg")
        self.assertEqual(self.send(self.alice, fake_photo, "p").json()["status"], "FAILED")
        fake_video = SimpleUploadedFile("evil.mp4", b"#!/bin/sh\necho not a video\n" * 50, content_type="video/mp4")
        self.send(self.alice, fake_video, "v")
        run_pending()
        self.assertEqual(ChatAttachment.objects.get(client_id="v").status, "FAILED")
        exe = SimpleUploadedFile("setup.exe", b"MZ", content_type="application/octet-stream")
        self.assertEqual(self.send(self.alice, exe, "e").status_code, 400)
        self.assertFalse(ChatAttachment.objects.filter(client_id="e").exists())
        self.assertFalse(any(a.file for a in ChatAttachment.objects.all()))

    def test_unverified_limits(self):
        from core.models import ChatAttachment
        casey = self.make_user("2026-0005", verified=False)
        post = self.create_post(self.finder)
        self.claim(post, casey)
        conversation = Conversation.objects.get(claim__claimant=casey)
        url = f"/conversations/{conversation.pk}/attachments/"
        client = self.client_for(casey)
        big = self.jpeg_with_hidden_payload(size=(3000, 2200))
        self.assertGreater(big.size, 2 * 1024 * 1024)
        self.assertEqual(client.post(url, {"file": big, "client_id": "big"}).status_code, 400)
        for i in range(3):
            self.assertEqual(client.post(url, {"file": self.jpeg_with_hidden_payload(), "client_id": f"ok{i}"}).status_code, 200)
        refused = client.post(url, {"file": self.jpeg_with_hidden_payload(), "client_id": "fourth"})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("3 photos or videos per chat", refused.json()["error"])
        self.assertEqual(ChatAttachment.objects.filter(uploader=casey).count(), 3)

    def test_unverified_video_length_limit(self):
        from core.chat_media import run_pending
        from core.models import ChatAttachment
        casey = self.make_user("2026-0005", verified=False)
        post = self.create_post(self.finder)
        self.claim(post, casey)
        conversation = Conversation.objects.get(claim__claimant=casey)
        self.client_for(casey).post(f"/conversations/{conversation.pk}/attachments/",
                                    {"file": make_video(seconds=22, size="320x240", audio=False), "client_id": "long"})
        run_pending()
        attachment = ChatAttachment.objects.get(client_id="long")
        self.assertEqual(attachment.status, "FAILED")
        self.assertIn("20 seconds", attachment.error)

    def test_heavy_flood_is_quietly_slowed_not_refused(self):
        from core.models import ChatAttachment
        for i in range(12):
            ChatAttachment.objects.create(conversation=self.conversation, uploader=self.alice, client_id=f"old{i}",
                                          kind="VIDEO", status="READY", uploaded_bytes=10 * 1024 * 1024)
        reply = self.send(self.alice, self.jpeg_with_hidden_payload(), "heavy")
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply.json()["status"], "PROCESSING")            # looks like it is just slow
        attachment = ChatAttachment.objects.get(client_id="heavy")
        self.assertGreater(attachment.not_before, timezone.now())
        from core.chat_media import next_job
        self.assertIsNone(next_job())                                      # not processed yet

    def test_files_deleted_with_the_post(self):
        import os
        from core.models import ChatAttachment
        self.send(self.alice, self.jpeg_with_hidden_payload(), "gone")
        attachment = ChatAttachment.objects.get(client_id="gone")
        paths = [attachment.file.path, attachment.preview.path]
        self.assertTrue(all(os.path.exists(p) for p in paths))
        with self.captureOnCommitCallbacks(execute=True):
            self.conversation.post.delete()
        self.assertFalse(any(os.path.exists(p) for p in paths))

    def test_closed_or_blocked_chat_refuses_uploads(self):
        self.conversation.is_closed = True
        self.conversation.save()
        self.assertEqual(self.send(self.alice, self.jpeg_with_hidden_payload()).status_code, 400)
        self.assertEqual(self.send(self.bob, self.jpeg_with_hidden_payload(), "x").status_code, 403)
