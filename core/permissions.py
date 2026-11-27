from .models import ModeratorVerification, Profile


def role_of(user):
    if not getattr(user, "is_authenticated", False):
        return None
    # v1.1.1: being a Django superuser no longer makes someone an administrator.
    # Roles come only from the profile; the Developer role is set by create_developer.
    try:
        return user.profile.role
    except Profile.DoesNotExist:
        return Profile.Role.STUDENT


ADMIN_ROLES = {Profile.Role.ADMIN, Profile.Role.DEVELOPER}
STAFF_ROLES = {Profile.Role.STAFF, Profile.Role.ADMIN, Profile.Role.DEVELOPER}


def is_staff_or_admin(user):
    return role_of(user) in STAFF_ROLES


def is_admin(user):
    """Administrators and the Developer (who can do everything an administrator can)."""
    return role_of(user) in ADMIN_ROLES


def is_developer(user):
    return bool(getattr(user, "is_active", False)) and role_of(user) == Profile.Role.DEVELOPER


def is_unverified_student(user):
    """Signed-in students who have not confirmed their email. They get lower limits."""
    if role_of(user) != Profile.Role.STUDENT:
        return False
    return user.profile.email_verified_at is None


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
