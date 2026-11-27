
from difflib import SequenceMatcher

from .models import ItemPost


def find_possible_matches(lost_post, limit=10):
    """
    Find possible FOUND posts that match a LOST post.
    """

    if lost_post.post_type != ItemPost.Type.LOST:
        return []

    found_posts = ItemPost.objects.filter(
        post_type=ItemPost.Type.FOUND,
        status=ItemPost.Status.OPEN,
        is_archived=False,
    ).exclude(pk=lost_post.pk)

    matches = []

    lost_title = lost_post.title.lower()
    lost_description = lost_post.description.lower()

    for found_post in found_posts:
        score = 0

        # Compare categories
        if lost_post.category == found_post.category:
            score += 30

        # Compare titles
        title_similarity = SequenceMatcher(
            None,
            lost_title,
            found_post.title.lower()
        ).ratio()

        score += title_similarity * 40

        # Compare descriptions
        description_similarity = SequenceMatcher(
            None,
            lost_description,
            found_post.description.lower()
        ).ratio()

        score += description_similarity * 30

        if score >= 40:
            matches.append({
                "post": found_post,
                "score": round(score),
            })

    matches.sort(key=lambda item: item["score"], reverse=True)

    return matches[:limit]