"""Possible LOST <-> FOUND matches (session 3, adapted in v1.1.0).

For a LOST post, open FOUND posts are scored by: same category (30 points),
title similarity (up to 40) and description similarity (up to 30). Matches
scoring 40 or more are shown to the LOST post's author and staff only.
Titles and descriptions are optional since session 4, so empty text simply
adds no points. No location data is used.
"""
from difflib import SequenceMatcher

from .models import ItemPost

MIN_SCORE = 40


def _similarity(a, b):
    a, b = (a or "").lower().strip(), (b or "").lower().strip()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def find_possible_matches(lost_post, limit=10):
    if lost_post.post_type != ItemPost.Type.LOST:
        return []
    found_posts = (
        ItemPost.objects.filter(post_type=ItemPost.Type.FOUND, status=ItemPost.Status.OPEN, is_archived=False)
        .exclude(pk=lost_post.pk)
        .select_related("category")
        .prefetch_related("photos")
    )
    matches = []
    for found_post in found_posts:
        score = 0.0
        if lost_post.category_id and lost_post.category_id == found_post.category_id:
            score += 30
        score += _similarity(lost_post.title, found_post.title) * 40
        score += _similarity(lost_post.description, found_post.description) * 30
        if score >= MIN_SCORE:
            matches.append({"post": found_post, "score": round(score)})
    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches[:limit]
