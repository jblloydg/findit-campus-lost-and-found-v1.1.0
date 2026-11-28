"""Sign-in rules (v1.1.1).

* Students sign in with their **email address**. A student whose Student ID is
  verified (locked to their account) may also type that Student ID.
* Staff, administrators and the Developer sign in with their assigned username.

Every lookup goes through Django's ORM, which sends what the person typed to the
database as a separate value (a parameterized query), never as part of the SQL
text, so typed text cannot change the query (no SQL injection).
"""
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .models import Profile

STUDENT_ID_PATTERN = re.compile(r"^\d{4}-\d{4}$")


class FindItBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        identifier = (username or kwargs.get(User.USERNAME_FIELD) or "").strip()
        if not identifier or password is None:
            return None
        user = self._find(User, identifier)
        if user is None:
            # Same work as a real check so the response time does not reveal whether the account exists.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    @staticmethod
    def _find(User, identifier):
        if "@" in identifier:
            matches = list(User.objects.filter(email__iexact=identifier).select_related("profile")[:2])
            return matches[0] if len(matches) == 1 else None
        if STUDENT_ID_PATTERN.fullmatch(identifier):
            profile = Profile.objects.filter(
                student_id=identifier, student_id_locked=True, email_verified_at__isnull=False,
                role=Profile.Role.STUDENT,
            ).select_related("user").first()
            return profile.user if profile else None
        user = User.objects.filter(username=identifier).select_related("profile").first()
        if user is None:
            # BUG-024: staff usernames are not case-sensitive ("Security.Demo" = "security.demo"),
            # but only when exactly one account matches.
            matches = list(User.objects.filter(username__iexact=identifier).select_related("profile")[:2])
            user = matches[0] if len(matches) == 1 else None
        if user is None:
            return None
        try:
            if user.profile.role == Profile.Role.STUDENT:
                return None  # students never sign in with the internal username
        except Profile.DoesNotExist:
            return None
        return user
