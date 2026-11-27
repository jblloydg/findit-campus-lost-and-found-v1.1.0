"""Integration v1.1.0 — session 2 (approximate time) on top of session 4."""
from datetime import timedelta

from django.utils import timezone

from .base import FindItTestCase, photo


class ApproximateTimeTests(FindItTestCase):
    def post(self, **extra):
        data = {"post_type": "LOST", "category": self.category.pk, "photos": [photo()]}
        data.update(extra)
        return self.client_for(self.alice).post("/posts/new/", data)

    def test_time_saved_and_shown(self):
        today = timezone.localdate() - timedelta(days=1)
        self.post(approximate_date=today.isoformat(), approximate_time="14:30")
        post = self.alice.items.latest("created_at") if hasattr(self.alice, "items") else None
        from core.models import ItemPost
        post = ItemPost.objects.filter(author=self.alice).latest("created_at")
        self.assertEqual(post.approximate_time.strftime("%H:%M"), "14:30")
        page = self.client_for(self.alice).get(f"/p/{post.pk}/")
        self.assertContains(page, "2:30 PM")

    def test_time_needs_a_date_and_no_future(self):
        r = self.post(approximate_time="10:00")
        self.assertContains(r, "Add the approximate date as well")
        future = timezone.localdate() + timedelta(days=2)
        r = self.post(approximate_date=future.isoformat())
        self.assertContains(r, "cannot be in the future")

    def test_only_author_or_admin_see_edit(self):
        from core.models import ItemPost
        self.post()
        post = ItemPost.objects.filter(author=self.alice).latest("created_at")
        self.assertNotContains(self.client_for(self.staff).get(f"/p/{post.pk}/"), "Edit post")
        self.assertContains(self.client_for(self.alice).get(f"/p/{post.pk}/"), "Edit post")
