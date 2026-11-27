from .models import ModeratorVerification, Profile


def role_of(user):
    if not getattr(user, "is_authenticated", False):
        return None
    if user.is_superuser:
        return Profile.Role.ADMIN
    try:
        return user.profile.role
    except Profile.DoesNotExist:
        return Profile.Role.STUDENT


def is_staff_or_admin(user):
    return role_of(user) in {Profile.Role.STAFF, Profile.Role.ADMIN}


def is_admin(user):
    return role_of(user) == Profile.Role.ADMIN


def can_manage_any_post(user):
    return is_staff_or_admin(user)


def is_verified_moderator(user):
    """A Staff account that an administrator has verified for moderator functions.

    Moderator is an extra authorization on a Staff account, not a separate role.
    Pending, rejected, and revoked verifications grant nothing.
    """
    if role_of(user) != Profile.Role.STAFF or not user.is_active:
        return False
    return ModeratorVerification.objects.filter(
        staff_id=user.pk, status=ModeratorVerification.Status.VERIFIED,
    ).exists()


def can_review_reports(user):
    """Administrators and verified moderators review safety and general reports."""
    return is_admin(user) or is_verified_moderator(user)


def can_review_private_chats(user):
    """Reading other people's private chats is limited to report reviewers."""
    return can_review_reports(user)
