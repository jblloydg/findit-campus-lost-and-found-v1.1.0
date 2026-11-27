from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def verified_mark(user):
    """✔ Verified badge for verified students; nothing for unverified students.
    Staff and administrators are created by an administrator, so they always show it."""
    try:
        profile = user.profile
    except Exception:
        return ""
    if profile.is_verified:
        return format_html('<span class="verified-badge" title="Verified Find-IT account">✔ Verified</span>')
    if profile.role == "student":
        return format_html('<span class="unverified-badge" title="This account has not verified its email">Not verified</span>')
    return ""
