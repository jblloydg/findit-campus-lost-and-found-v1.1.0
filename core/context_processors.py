from .models import InAppNotification, Profile
from .permissions import role_of


def site_context(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0, "current_role": None}
    return {
        "unread_notification_count": InAppNotification.objects.filter(
            recipient=request.user, read_at__isnull=True
        ).count(),
        "current_role": role_of(request.user),
        "role_labels": dict(Profile.Role.choices),
        "current_role_label": dict(Profile.Role.choices).get(role_of(request.user), "Student"),
    }
