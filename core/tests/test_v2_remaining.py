"""v2.0.0 list items that had a backend but no page yet (DES-004 … DES-012)."""
from datetime import timedelta
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import Client, override_settings
from django.utils import timezone

from core.forms import ItemPostForm
from core.models import ChatAttachment, IdReviewCase, Profile, StaffAuditLog, StudentIdRecord
from core.services import audit

from .base import FindItTestCase


class AccountVerificationPagesTests(FindItTestCase):
    def flag(self, user):
        user.profile.flagged_at = timezone.now()
        user.profile.flag_reason = "Used 3 different Student IDs."
        user.profile.save()

    def test_edit_account_shows_verification_details(self):
        StudentIdRecord.objects.create(user=self.alice, student_id="2026-0002", source="SIGNUP")
        self.alice.profile.id_conflict_deadline = timezone.now() + timedelta(days=14)
        self.alice.profile.save()
        response = self.client_for(self.admin).get(f"/staff/accounts/{self.alice.pk}/edit/")
        self.assertContains(response, "Verification details")
        self.assertContains(response, "Email verified")
        self.assertContains(response, "Student ID history")
        self.assertContains(response, "2026-0002")
        self.assertContains(response, "Student ID conflict")

    def test_red_flagged_filter_and_panel(self):
        self.flag(self.bob)
        response = self.client_for(self.admin).get("/staff/accounts/?verify=flagged")
        self.assertContains(response, "Red-flagged accounts")
        accounts = list(response.context["page_obj"])
        self.assertEqual(accounts, [self.bob])
        self.assertEqual(response.context["flagged_count"], 1)
        # A made-up filter value is ignored, not an error.
        self.assertEqual(self.client_for(self.admin).get("/staff/accounts/?verify=<script>").status_code, 200)

    def test_verified_and_unverified_filters(self):
        casey = self.make_user("2026-0009", verified=False)
        client = self.client_for(self.admin)
        self.assertIn(casey, list(client.get("/staff/accounts/?verify=unverified").context["page_obj"]))
        self.assertNotIn(casey, list(client.get("/staff/accounts/?verify=verified").context["page_obj"]))

    def test_developer_view(self):
        developer = self.make_user("dev.test", role=Profile.Role.DEVELOPER)
        page = self.client_for(developer).get(f"/staff/accounts/{self.alice.pk}/edit/")
        self.assertContains(page, "Developer view")
        self.assertIn(Profile.Role.ADMIN, [value for value, _ in page.context["form"].fields["role"].choices])
        admin_page = self.client_for(self.admin).get(f"/staff/accounts/{self.alice.pk}/edit/")
        self.assertNotContains(admin_page, "Developer view")
        self.assertNotIn(Profile.Role.ADMIN, [value for value, _ in admin_page.context["form"].fields["role"].choices])

    def test_admin_dashboard_numbers(self):
        self.flag(self.bob)
        IdReviewCase.objects.create(kind="IMPOSTOR", requester=self.alice, student_id="2026-0003", message="Mine.")
        response = self.client_for(self.admin).get("/staff/admin/")
        self.assertContains(response, "Verified students")
        self.assertContains(response, "Red-flagged accounts")
        self.assertContains(response, "Open ID reviews")
        self.assertEqual(response.context["account_counts"]["flagged"], 1)
        self.assertEqual(response.context["open_id_reviews"], 1)


class WithdrawIdReviewTests(FindItTestCase):
    def setUp(self):
        super().setUp()
        self.case = IdReviewCase.objects.create(kind="IMPOSTOR", requester=self.alice, student_id="2026-0003", message="Mine.")

    def test_requester_withdraws_open_review(self):
        client = self.client_for(self.alice)
        self.assertContains(client.get("/profile/"), f"/id-review/{self.case.pk}/withdraw/")
        response = client.post(f"/id-review/{self.case.pk}/withdraw/")
        self.assertRedirects(response, "/profile/")
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, IdReviewCase.Status.WITHDRAWN)
        self.assertTrue(StaffAuditLog.objects.filter(action="withdrew_id_review").exists())
        self.assertNotContains(client.get("/profile/"), f"/id-review/{self.case.pk}/withdraw/")

    def test_only_the_requester_and_only_when_open(self):
        self.assertEqual(self.client_for(self.bob).post(f"/id-review/{self.case.pk}/withdraw/").status_code, 404)
        self.assertEqual(self.client_for(self.alice).get(f"/id-review/{self.case.pk}/withdraw/").status_code, 405)
        self.case.status = IdReviewCase.Status.KEPT
        self.case.save()
        self.client_for(self.alice).post(f"/id-review/{self.case.pk}/withdraw/")
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, IdReviewCase.Status.KEPT)


class AuditAndStatusPagesTests(FindItTestCase):
    def test_audit_log_for_admins_only(self):
        audit(self.admin, "edited_account", self.alice, "details updated")
        audit(self.staff, "confirmed_turn_in", self.alice, "guard house")
        page = self.client_for(self.admin).get("/staff/admin/audit/")
        self.assertContains(page, "Edited account")
        filtered = self.client_for(self.admin).get("/staff/admin/audit/?action=confirmed_turn_in")
        self.assertEqual([e.action for e in filtered.context["page_obj"]], ["confirmed_turn_in"])
        for user in (self.alice, self.staff):
            self.assertEqual(self.client_for(user).get("/staff/admin/audit/").status_code, 403)
        self.assertEqual(Client().get("/staff/admin/audit/").status_code, 302)

    def test_system_status_for_admins_only(self):
        page = self.client_for(self.admin).get("/staff/admin/status/")
        self.assertContains(page, "Database")
        self.assertContains(page, "Daily backup")
        self.assertContains(page, "Chat photos and videos queue")
        self.assertTrue(page.context["checks"][0]["ok"])
        for user in (self.alice, self.staff):
            self.assertEqual(self.client_for(user).get("/staff/admin/status/").status_code, 403)


class LocationAndVideoBadgeTests(FindItTestCase):
    def test_location_input_is_dormant_by_default(self):
        self.assertNotIn("location", ItemPostForm().fields)
        self.assertNotContains(self.client_for(self.finder).get("/posts/new/"), 'name="location"')

    @override_settings(FINDIT_LOCATION_ENABLED=True)
    def test_location_input_when_enabled(self):
        self.assertIn("location", ItemPostForm().fields)
        self.assertFalse(ItemPostForm().fields["location"].required)
        self.assertContains(self.client_for(self.finder).get("/posts/new/"), 'name="location"')

    def test_video_badge(self):
        video = ChatAttachment(kind="VIDEO", status="READY", duration_seconds=42.4, stored_bytes=3_250_000, width=1280, height=720)
        video.pk = 99
        self.assertEqual(video.duration_label, "0:42")
        html = render_to_string("core/includes/chat_attachment.html", {"message": SimpleNamespace(attachment=video)})
        self.assertIn("media-badge", html)
        self.assertIn("0:42", html)
        self.assertIn("3.1", html)
