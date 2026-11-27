from django.conf import settings

from .mail import test_inbox_enabled
from .models import InAppNotification, Profile
from .permissions import is_admin, is_developer, is_staff_or_admin, role_of


def site_context(request):
    # Decision 8: location stays dormant unless FINDIT_LOCATION_ENABLED=1 (every page can check it).
    location_enabled = getattr(settings, "FINDIT_LOCATION_ENABLED", False)
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0, "current_role": None, "priority_message_count": 0,
                "location_enabled": location_enabled}
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        profile = None
    return {
        "location_enabled": location_enabled,
        "current_is_staff": is_staff_or_admin(request.user),
        "current_is_admin": is_admin(request.user),
        "current_is_developer": is_developer(request.user),
        "current_unverified": bool(profile and profile.role == Profile.Role.STUDENT and not profile.email_verified_at),
        "current_sign_in_name": profile.sign_in_name if profile else request.user.username,
        "test_inbox_enabled": test_inbox_enabled(),
        "unread_notification_count": InAppNotification.objects.filter(
            recipient=request.user, read_at__isnull=True
        ).count(),
        "current_role": role_of(request.user),
        "priority_message_count": InAppNotification.objects.filter(
            recipient=request.user, read_at__isnull=True, is_priority=True
        ).count(),
        "role_labels": dict(Profile.Role.choices),
        "current_role_label": dict(Profile.Role.choices).get(role_of(request.user), "Student"),
    }
