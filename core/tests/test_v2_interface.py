"""DES-003: Find-IT v2.0.0 interface (sidebar shell, dashboard, landing)."""
from django.test import Client

from core.models import ClaimApplication, ItemPost

from .base import FindItTestCase


class V2InterfaceTests(FindItTestCase):
    def test_signed_in_pages_have_sidebar_and_top_bar(self):
        response = self.client_for(self.finder).get("/home/")
        self.assertContains(response, 'class="sidebar"')
        self.assertContains(response, 'class="app-topbar"')
        self.assertContains(response, "Report lost item")
        self.assertNotContains(response, "Staff workspace")
        self.assertNotContains(response, "Admin dashboard")

    def test_sidebar_sections_follow_the_role(self):
        staff_page = self.client_for(self.staff).get("/home/")
        self.assertContains(staff_page, "Staff workspace")
        self.assertContains(staff_page, "Scan turn-in QR")
        self.assertNotContains(staff_page, "Moderator verification")
        admin_page = self.client_for(self.admin).get("/home/")
        for label in ["Staff workspace", "Admin dashboard", "Moderator verification", "System settings", "Backups"]:
            self.assertContains(admin_page, label)

    def test_dashboard_counts(self):
        post = self.create_post(user=self.finder)
        self.claim(post, self.alice)
        finder_page = self.client_for(self.finder).get("/home/")
        self.assertEqual(finder_page.context["dashboard"]["active_posts"], 1)
        alice_page = self.client_for(self.alice).get("/home/")
        self.assertEqual(alice_page.context["dashboard"]["open_claims"],
                         ClaimApplication.objects.filter(claimant=self.alice).count())
        self.assertContains(alice_page, "Hello, ")

    def test_lost_and_found_pages(self):
        client = self.client_for(self.finder)
        self.assertContains(client.get("/home/?type=LOST"), "Lost <em>items</em>", html=False)
        self.assertContains(client.get("/home/?type=FOUND"), "Found <em>items</em>", html=False)

    def test_report_lost_item_preselects_the_type(self):
        client = self.client_for(self.finder)
        self.assertEqual(client.get("/posts/new/?type=LOST").context["form"].initial.get("post_type"), ItemPost.Type.LOST)
        self.assertEqual(client.get("/posts/new/?type=FOUND").context["form"].initial.get("post_type"), ItemPost.Type.FOUND)
        self.assertFalse(client.get("/posts/new/?type=nonsense").context["form"].initial)

    def test_landing_page_sections_and_safe_example_id(self):
        response = Client().get("/")
        for text in ["Campus community, connected", "How it works", "Privacy by design", "Keep proof private."]:
            self.assertContains(response, text)
        self.assertContains(response, 'placeholder="2020-0001"')

    def test_owner_real_id_is_never_shown(self):
        # CLAUDE.md decision 10: the old starter example ID is the owner's real account.
        real_id = "2024-" + "0122"
        pages = [Client().get(url) for url in ["/", "/login/", "/signup/", "/password-reset/"]]
        pages.append(self.client_for(self.finder).get("/home/"))
        for response in pages:
            self.assertNotContains(response, real_id)
