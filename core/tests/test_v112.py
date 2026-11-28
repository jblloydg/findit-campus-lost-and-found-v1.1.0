"""v1.1.2 tests: bug fixes for v1.1.1 (BUG-008, ...). All people here are fictional."""
from django.test import override_settings
from django.urls import reverse

from core.models import Category, InAppNotification, ItemPost
from core.security import is_own_site_path
from core.verification import notify_account

from .base import FindItTestCase


class PostDetailTagLineTests(FindItTestCase):
    """BUG-008: category link uses the id and shows the name; location stays dormant."""

    def test_category_link_uses_id_and_shows_name(self):
        post = self.create_post()
        html = self.client_for(self.alice).get(reverse("post-detail", args=[post.pk])).content.decode()
        self.assertIn(f'href="{reverse("home")}?category={self.category.pk}">{self.category.name}</a>', html)

    def test_category_link_filters_browse(self):
        post = self.create_post()
        other_category = Category.objects.exclude(pk=self.category.pk).first()
        other = self.create_post(category=other_category.pk)
        response = self.client_for(self.alice).get(f"{reverse('home')}?category={self.category.pk}")
        self.assertContains(response, reverse("post-detail", args=[post.pk]))
        self.assertNotContains(response, reverse("post-detail", args=[other.pk]))

    @override_settings(FINDIT_LOCATION_ENABLED=False)
    def test_dormant_location_hidden(self):
        post = self.create_post()
        ItemPost.objects.filter(pk=post.pk).update(location="Library 2nd floor")
        response = self.client_for(self.alice).get(reverse("post-detail", args=[post.pk]))
        self.assertNotContains(response, "Library 2nd floor")

    @override_settings(FINDIT_LOCATION_ENABLED=True)
    def test_location_shown_when_enabled(self):
        post = self.create_post()
        ItemPost.objects.filter(pk=post.pk).update(location="Library 2nd floor")
        response = self.client_for(self.alice).get(reverse("post-detail", args=[post.pk]))
        self.assertContains(response, "📍 Library 2nd floor")

    def test_post_without_category_has_no_empty_link(self):
        post = self.create_post()
        ItemPost.objects.filter(pk=post.pk).update(category=None)
        response = self.client_for(self.alice).get(reverse("post-detail", args=[post.pk]))
        self.assertNotContains(response, 'class="category-tag"')


class NotificationLinkTests(FindItTestCase):
    """SEC-002: tapping a notice never leaves Find-IT."""

    UNSAFE = [
        "https://evil.example.com/", "http://evil.example.com", "//evil.example.com/", "/\\evil.example.com",
        "/\\/evil.example.com", "\\\\evil.example.com", "javascript:alert(1)", "/\t/evil.example.com",
        "/%0a/evil.example.com\n", "evil.example.com", " /home/",
    ]

    def open_notice(self, link):
        notice = InAppNotification.objects.create(recipient=self.alice, text="Test notice", link=link)
        return self.client_for(self.alice).get(f"{reverse('notifications')}?open={notice.pk}")

    def test_own_page_link_opens(self):
        response = self.open_notice(reverse("my-profile"))
        self.assertRedirects(response, reverse("my-profile"), fetch_redirect_response=False)

    def test_other_website_links_never_redirect_away(self):
        for link in self.UNSAFE:
            with self.subTest(link=link):
                self.assertFalse(is_own_site_path(link))
                response = self.open_notice(link)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], reverse("notifications"))

    def test_unsafe_link_is_not_stored(self):
        notice = notify_account(self.alice, "Hello", link="//evil.example.com/")
        self.assertEqual(notice.link, "")
        notice = notify_account(self.alice, "Hello again", link=reverse("home"))
        self.assertEqual(notice.link, reverse("home"))
