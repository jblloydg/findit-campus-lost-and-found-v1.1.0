"""Integration v1.1.0 — session 3 (date filters, possible matches) on top of session 4."""
from datetime import timedelta

from django.utils import timezone

from core.models import ItemPost

from .base import FindItTestCase


class Session3Tests(FindItTestCase):
    def test_possible_matches_shown_to_lost_author_only(self):
        self.create_post(self.finder, "FOUND", title="Blue water bottle", description="metal bottle with sticker")
        lost = self.create_post(self.alice, "LOST", title="Blue water bottle", description="metal bottle with a sticker")
        page = self.client_for(self.alice).get(f"/p/{lost.pk}/")
        self.assertContains(page, "Possible matches")
        self.assertContains(page, "match score")
        self.assertNotContains(self.client_for(self.bob).get(f"/p/{lost.pk}/"), "Possible matches")

    def test_date_range_filter(self):
        old = self.create_post(self.alice, "LOST", approximate_date=(timezone.localdate() - timedelta(days=10)).isoformat())
        new = self.create_post(self.alice, "LOST", approximate_date=timezone.localdate().isoformat())
        frm = (timezone.localdate() - timedelta(days=2)).isoformat()
        r = self.client_for(self.alice).get(f"/home/?date_from={frm}")
        ids = {p.pk for p in r.context["posts"]}
        self.assertIn(new.pk, ids)
        self.assertNotIn(old.pk, ids)
        self.assertContains(r, "Clear filters")
