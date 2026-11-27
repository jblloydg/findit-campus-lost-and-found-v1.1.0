"""Create (or reset the password of) the Find-IT Developer account.

The Developer is the only role that can make or remove administrators and open the
Django back-office (/django-admin/). It cannot be created, edited or seen through any
web page. There is no password in the code or the repository: you type it here, and
only a scrambled (hashed) version is saved in the database.

Run it on the computer that holds the database (your PC now, the online server later):

    python manage.py create_developer
    python manage.py create_developer --reset-password      # forgot the password

Moving to a new database later (v3.0.0): a backup made with backup_now and loaded with
restore_backup carries this account over, or simply run this command again there.
"""
import getpass
import sys

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Profile, StaffAuditLog

MIN_LENGTH = 12


class Command(BaseCommand):
    help = "Create the Find-IT Developer account (or reset its password). Asks for the password privately."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Developer sign-in name (asked if not given).")
        parser.add_argument("--email", help="Developer email (asked if not given).")
        parser.add_argument("--reset-password", action="store_true", help="Set a new password for an existing Developer.")

    def handle(self, *args, **options):
        if not sys.stdin.isatty():
            raise CommandError("Run this command yourself in a terminal window so the password can be typed privately.")
        User = get_user_model()
        if options["reset_password"]:
            return self._reset(User, options)

        username = (options["username"] or input("Developer username (letters, numbers, . _ -): ")).strip()
        if not username or "@" in username or len(username) > 150:
            raise CommandError("Choose a username without @, up to 150 characters.")
        if User.objects.filter(username__iexact=username).exists():
            raise CommandError("That username already exists. Use --reset-password to change a Developer's password.")
        email = (options["email"] or input("Developer email: ")).strip().lower()
        if "@" not in email:
            raise CommandError("Enter a valid email address.")
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("That email is already used by another account.")
        candidate = User(username=username, email=email)
        password = self._ask_password(candidate)
        with transaction.atomic():
            user = User.objects.create_user(username=username, email=email, password=password)
            user.is_staff = True        # needed for /django-admin/
            user.is_superuser = True    # full rights inside /django-admin/
            user.save(update_fields=["is_staff", "is_superuser"])
            profile = user.profile
            profile.role = Profile.Role.DEVELOPER
            profile.email_verified_at = timezone.now()
            profile.save(update_fields=["role", "email_verified_at"])
            StaffAuditLog.objects.create(
                actor=user, action="created_developer", target_type="User", target_id=str(user.pk),
                details="Developer account created with the create_developer command.",
            )
        self.stdout.write(self.style.SUCCESS(
            f"Developer account '{username}' was created. Sign in at /login/ with this username. "
            "Keep the password private; it is not stored anywhere except as a hash in the database."
        ))

    def _reset(self, User, options):
        username = (options["username"] or input("Developer username: ")).strip()
        user = User.objects.filter(username=username, profile__role=Profile.Role.DEVELOPER).first()
        if user is None:
            raise CommandError("No Developer account with that username.")
        password = self._ask_password(user)
        user.set_password(password)
        user.is_active = True
        user.save(update_fields=["password", "is_active"])
        StaffAuditLog.objects.create(
            actor=user, action="reset_developer_password", target_type="User", target_id=str(user.pk),
            details="Password reset with the create_developer command.",
        )
        self.stdout.write(self.style.SUCCESS("The Developer password was changed. Any place still signed in "
                                             "with the old password is signed out automatically."))

    def _ask_password(self, candidate):
        for _ in range(3):
            first = getpass.getpass(f"Password (at least {MIN_LENGTH} characters, typing is hidden): ")
            second = getpass.getpass("Type the password again: ")
            if first != second:
                self.stderr.write("The passwords do not match. Try again.")
                continue
            if len(first) < MIN_LENGTH:
                self.stderr.write(f"Use at least {MIN_LENGTH} characters.")
                continue
            try:
                validate_password(first, candidate)
            except ValidationError as exc:
                self.stderr.write(" ".join(exc.messages))
                continue
            return first
        raise CommandError("No password was set.")
