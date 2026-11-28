"""v1.1.2 tests: bug fixes for v1.1.1 (BUG-008, ...). All people here are fictional."""
from django.test import override_settings
from django.urls import reverse

from core.models import Category, ItemPost

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
