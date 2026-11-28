import re

from django import forms
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from captcha.fields import CaptchaField
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .models import (
    CLOSED_REPORT_STATUSES, AbuseReport, AnswerType, Category, GeneralReport, ItemPost, PostPhoto, Profile,
    QuestionTemplate, ReportStatus, StatusChangeRequest, SystemSettings,
)
from .validators import validate_photo, validate_profile_photo, validate_report_attachment

User = get_user_model()
STUDENT_ID_PATTERN = re.compile(r"^\d{4}-\d{4}$")
MAX_POST_PHOTOS = 20
HUMAN_CHECK_PHOTO_THRESHOLD = 10
MIN_POST_QUESTIONS = 3
MAX_POST_QUESTIONS = 5


PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 -]{5,18}[0-9]$")


def email_in_use(email, exclude_user=None):
    """Email addresses are unique across all accounts, ignoring letter case."""
    users = User.objects.filter(email__iexact=email)
    if exclude_user is not None:
        users = users.exclude(pk=exclude_user.pk)
    return users.exists()


def _check_password_strength(form, field, password, candidate):
    try:
        validate_password(password, candidate)
    except ValidationError as exc:
        form.add_error(field, exc)


class FindItLoginForm(AuthenticationForm):
    """v1.1.1: students sign in with their email (or their verified Student ID);
    staff and administrators use their assigned username."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": (
            "Incorrect email / username or password. Passwords are case-sensitive. "
            "Students sign in with their email; a Student ID works only after it is verified. "
            "If your account was suspended, contact a Find-IT administrator."
        ),
    }

    username = forms.CharField(
        label="Email (students) or staff username",
        max_length=254,
        widget=forms.TextInput(attrs={"autocomplete": "username", "placeholder": "you@example.com", "autofocus": True}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Your password", "data-password-toggle": "true"}),
    )

    def clean_username(self):
        return self.cleaned_data["username"].strip()


class SignupForm(forms.Form):
    """Student self-registration. The role is always Student and cannot be chosen."""

    first_name = forms.CharField(max_length=60, label="First name", widget=forms.TextInput(attrs={"autocomplete": "given-name", "placeholder": "Juan"}))
    last_name = forms.CharField(max_length=60, label="Last name", widget=forms.TextInput(attrs={"autocomplete": "family-name", "placeholder": "Cruz"}))
    student_id = forms.CharField(
        max_length=9, label="Student ID", help_text="Format: YYYY-NNNN, such as 2020-0001. Once you verify your email, this ID is locked to your account.",
        widget=forms.TextInput(attrs={"placeholder": "2020-0001", "autocomplete": "username"}),
    )
    email = forms.EmailField(max_length=254, label="Email address", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    password1 = forms.CharField(
        label="Password", strip=False,
        help_text="At least 8 characters. Avoid common passwords, passwords that are only numbers, or anything close to your name or ID.",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "data-password-toggle": "true"}),
    )
    password2 = forms.CharField(
        label="Confirm password", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "data-password-toggle": "true"}),
    )

    def clean_first_name(self):
        return self.cleaned_data["first_name"].strip()

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip()

    id_is_mine = forms.BooleanField(
        required=False,
        label="This is my Student ID. The verified account using it is not me (impostor), or I lost access to it.",
        help_text="Your account is created without a Student ID and you are taken to the ID review form.",
    )

    def clean_student_id(self):
        value = self.cleaned_data["student_id"].strip()
        if not STUDENT_ID_PATTERN.fullmatch(value):
            raise ValidationError("Use the Student ID format YYYY-NNNN, such as 2020-0001.")
        # v1.1.1: unverified accounts may share an ID; only a verified (locked) ID is blocked.
        self.id_locked = Profile.objects.filter(student_id=value, student_id_locked=True).exists()
        return value

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if email_in_use(value):
            raise ValidationError("That email address is already used by another account.")
        return value

    def clean(self):
        cleaned = super().clean()
        if getattr(self, "id_locked", False) and not cleaned.get("id_is_mine"):
            self.add_error("student_id", (
                "That Student ID is verified by another account. If it is really yours, tick the box below "
                "to request an ID review."
            ))
        password1, password2 = cleaned.get("password1"), cleaned.get("password2")
        if password1 and password2:
            if password1 != password2:
                self.add_error("password2", "The passwords do not match.")
            else:
                candidate = User(
                    username=cleaned.get("student_id", ""), email=cleaned.get("email", ""),
                    first_name=cleaned.get("first_name", ""), last_name=cleaned.get("last_name", ""),
                )
                _check_password_strength(self, "password1", password1, candidate)
        return cleaned

    @property
    def wants_id_review(self):
        return bool(getattr(self, "id_locked", False) and self.cleaned_data.get("id_is_mine"))

    @transaction.atomic
    def save(self):
        import secrets
        from .models import StudentIdRecord
        # The sign-in name is the email; the username is an internal unique handle.
        while True:
            username = f"student-{secrets.token_hex(5)}"
            if not User.objects.filter(username=username).exists():
                break
        user = User.objects.create_user(
            username=username,
            email=self.cleaned_data["email"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            password=self.cleaned_data["password1"],
        )
        # Role is assigned here, never taken from the submitted form.
        user.profile.role = Profile.Role.STUDENT
        if not self.wants_id_review:
            user.profile.student_id = self.cleaned_data["student_id"]
            StudentIdRecord.objects.create(
                user=user, student_id=self.cleaned_data["student_id"], source=StudentIdRecord.Source.SIGNUP,
            )
        user.profile.save(update_fields=["role", "student_id"])
        return user


class VerifyCodeForm(forms.Form):
    code = forms.CharField(
        label="6-digit code", max_length=12,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "placeholder": "123456"}),
    )


class StudentIdChangeForm(forms.Form):
    student_id = forms.CharField(
        max_length=9, label="Student ID", help_text="Format: YYYY-NNNN, such as 2020-0001.",
        widget=forms.TextInput(attrs={"placeholder": "2020-0001"}),
    )
    confirm = forms.BooleanField(label="I understand: an account that uses three different Student IDs is disabled.")

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_student_id(self):
        value = self.cleaned_data["student_id"].strip()
        if not STUDENT_ID_PATTERN.fullmatch(value):
            raise ValidationError("Use the Student ID format YYYY-NNNN, such as 2020-0001.")
        if Profile.objects.filter(student_id=value, student_id_locked=True).exclude(user=self.user).exists():
            raise ValidationError("That Student ID is verified by another account. If it is yours, request an ID review.")
        return value


class IdReviewForm(forms.Form):
    student_id = forms.CharField(
        max_length=9, label="Student ID you are asking about",
        widget=forms.TextInput(attrs={"placeholder": "2020-0001"}),
    )
    message = forms.CharField(
        label="Explain briefly (required)", max_length=1000,
        help_text="For example: 'I never made that account', or 'I lost access to my old email'. "
                  "Do not type passwords or other people's private details.",
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": 1000}),
    )
    captcha = CaptchaField(label="Captcha")

    def clean_student_id(self):
        value = self.cleaned_data["student_id"].strip()
        if not STUDENT_ID_PATTERN.fullmatch(value):
            raise ValidationError("Use the Student ID format YYYY-NNNN, such as 2020-0001.")
        return value

    def clean_message(self):
        value = self.cleaned_data["message"].strip()
        if not value:
            raise ValidationError("Write a short explanation.")
        return value


class IdReviewDecisionForm(forms.Form):
    decision = forms.ChoiceField(label="Decision", choices=[
        ("keep", "Keep the ID with the verified account"),
        ("transfer", "Move the ID to the person who asked"),
    ])
    note = forms.CharField(label="Note to the person who asked (optional)", max_length=500, required=False,
                           widget=forms.Textarea(attrs={"rows": 2, "maxlength": 500}))


class ReportBlockForm(forms.Form):
    reason = forms.ChoiceField(
        label="Reason (optional)", required=False,
        choices=[("", "No reason (just block)")] + [
            (value, label) for value, label in AbuseReport.Reason.choices if value != AbuseReport.Reason.BLOCK
        ],
    )
    details = forms.CharField(
        label="Details (optional)", max_length=1500, required=False,
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": 1500}),
    )


class StaffAccountForm(forms.Form):
    """Administrator-only form. Always creates a Staff role account."""

    first_name = forms.CharField(max_length=60, label="First name")
    last_name = forms.CharField(max_length=60, label="Last name", required=False)
    username = forms.RegexField(
        regex=r"^[A-Za-z][A-Za-z0-9._-]{2,31}$",
        label="Staff username",
        help_text="3–32 letters, numbers, dots, dashes, or underscores, starting with a letter. Not a student ID.",
        error_messages={"invalid": "Use 3–32 letters, numbers, dots, dashes, or underscores, starting with a letter."},
    )
    email = forms.EmailField(max_length=254, label="Email address", required=False)
    password = forms.CharField(
        label="Temporary password", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "data-password-toggle": "true"}),
    )
    password_confirm = forms.CharField(
        label="Confirm temporary password", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "data-password-toggle": "true"}),
    )

    def clean_username(self):
        value = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=value).exists():
            raise ValidationError("That username is already in use.")
        return value

    def clean_email(self):
        value = self.cleaned_data.get("email", "").strip().lower()
        if value and email_in_use(value):
            raise ValidationError("That email address is already used by another account.")
        return value

    def clean(self):
        cleaned = super().clean()
        password, confirm = cleaned.get("password"), cleaned.get("password_confirm")
        if password and confirm:
            if password != confirm:
                self.add_error("password_confirm", "The passwords do not match.")
            else:
                candidate = User(
                    username=cleaned.get("username", ""), email=cleaned.get("email", ""),
                    first_name=cleaned.get("first_name", ""), last_name=cleaned.get("last_name", ""),
                )
                _check_password_strength(self, "password", password, candidate)
        return cleaned

    @transaction.atomic
    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data.get("email", ""),
            first_name=self.cleaned_data["first_name"].strip(),
            last_name=self.cleaned_data.get("last_name", "").strip(),
            password=self.cleaned_data["password"],
        )
        user.profile.role = Profile.Role.STAFF
        user.profile.student_id = None
        user.profile.save(update_fields=["role", "student_id"])
        return user


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    """Accepts several images in one input. Each file is checked by Pillow and validate_photo."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/jpeg,image/png,image/webp", "multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            files = [single_clean(item, initial) for item in data if item]
        elif data:
            files = [single_clean(data, initial)]
        else:
            files = []
        for item in files:
            validate_photo(item)
        return files
class ProfileForm(forms.Form):
    """Fields a signed-in user may change on their own profile.

    Student ID, username, role, and account status are deliberately absent.
    """

    first_name = forms.CharField(max_length=60, label="First name", widget=forms.TextInput(attrs={"autocomplete": "given-name"}))
    last_name = forms.CharField(max_length=60, label="Last name", required=False, widget=forms.TextInput(attrs={"autocomplete": "family-name"}))
    email = forms.EmailField(max_length=254, label="Email address", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    contact_number = forms.CharField(
        max_length=20, label="Contact number", required=False,
        help_text="Optional. Digits, spaces, or dashes, such as 0917 123 4567 or +63 917 123 4567.",
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
    )
    photo = forms.ImageField(
        label="Profile picture", required=False,
        help_text="Optional. JPG, PNG, or WebP; up to 2 MB.",
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )
    remove_photo = forms.BooleanField(label="Remove my current profile picture", required=False)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        profile = user.profile
        kwargs.setdefault("initial", {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "contact_number": profile.contact_number,
        })
        super().__init__(*args, **kwargs)

    def clean_first_name(self):
        value = self.cleaned_data["first_name"].strip()
        if not value:
            raise ValidationError("Enter your first name.")
        return value

    def clean_last_name(self):
        return self.cleaned_data.get("last_name", "").strip()

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if email_in_use(value, exclude_user=self.user):
            raise ValidationError("That email address is already used by another account.")
        return value

    def clean_contact_number(self):
        value = " ".join(self.cleaned_data.get("contact_number", "").split())
        if not value:
            return ""
        digits = re.sub(r"\D", "", value)
        if not PHONE_PATTERN.fullmatch(value) or not 7 <= len(digits) <= 15:
            raise ValidationError("Enter a valid contact number using digits, spaces, or dashes.")
        return value

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo:
            validate_profile_photo(photo)
        return photo

    @transaction.atomic
    def save(self):
        user, profile = self.user, self.user.profile
        email_changed = (user.email or "").lower() != (self.cleaned_data["email"] or "").lower()
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        user.save(update_fields=["first_name", "last_name", "email"])
        if email_changed and profile.role == Profile.Role.STUDENT and profile.email_verified_at:
            # A new email must be confirmed again. A locked Student ID stays locked to this account.
            profile.email_verified_at = None
            profile.save(update_fields=["email_verified_at"])
            self.verification_removed = True
        profile.contact_number = self.cleaned_data["contact_number"]
        old_photo_name = profile.photo.name if profile.photo else ""
        new_photo = self.cleaned_data.get("photo")
        if new_photo:
            profile.photo = new_photo
        elif self.cleaned_data.get("remove_photo"):
            profile.photo = None
        profile.save(update_fields=["contact_number", "photo"])
        if old_photo_name and old_photo_name != (profile.photo.name if profile.photo else ""):
            storage = Profile._meta.get_field("photo").storage
            transaction.on_commit(lambda: storage.delete(old_photo_name))
        return user


class FindItPasswordResetForm(PasswordResetForm):
    """v1.1.1: the Developer password can only be reset with `create_developer --reset-password`
    on the computer itself, never by email, so a stolen mailbox cannot take over the Developer."""

    def get_users(self, email):
        return (user for user in super().get_users(email)
                if getattr(getattr(user, "profile", None), "role", "") != Profile.Role.DEVELOPER)


class FindItSetPasswordForm(SetPasswordForm):
    """Used by the emailed password-reset link."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "New password"
        self.fields["new_password2"].label = "Confirm new password"
        for name in ("new_password1", "new_password2"):
            self.fields[name].widget.attrs["data-password-toggle"] = "true"
        self.fields["new_password1"].help_text = (
            "At least 8 characters. Avoid common passwords, passwords that are only numbers, "
            "or anything close to your name, ID, or email."
        )


class FindItPasswordChangeForm(PasswordChangeForm):
    """Django's secure password change form with Find-IT labels and show/hide toggles."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "old_password": "Current password",
            "new_password1": "New password",
            "new_password2": "Confirm new password",
        }
        for name, label in labels.items():
            self.fields[name].label = label
            self.fields[name].widget.attrs["data-password-toggle"] = "true"
        self.fields["new_password1"].help_text = (
            "At least 8 characters. Avoid common passwords, passwords that are only numbers, "
            "or anything close to your name, ID, or email."
        )


class ItemPostForm(forms.ModelForm):
    """Create/edit a post. Photos (1-20) and a category are required; title and
    description are optional, like a social-media post."""

    photos = MultipleImageField(
        required=False,
        label="Photos",
        help_text=f"Add 1 to {MAX_POST_PHOTOS} photos (JPG, PNG or WebP, up to 5 MB each). No video.",
    )
    remove_photos = forms.ModelMultipleChoiceField(
        queryset=PostPhoto.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple, label="Remove photos",
    )
    captcha = CaptchaField(
        label="Captcha",
        help_text="Needed only when a post has more than 10 photos. Type the letters, or solve the sum, shown in the image.",
    )
    questions = forms.ModelMultipleChoiceField(
        queryset=QuestionTemplate.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Ownership questions",
        help_text=(
            f"Pick up to {MAX_POST_QUESTIONS}. If you pick fewer than {MIN_POST_QUESTIONS}, "
            "default questions are added for you."
        ),
    )

    class Meta:
        model = ItemPost
        fields = ["post_type", "category", "title", "description", "approximate_date", "approximate_time", "location"]
        widgets = {
            "location": forms.TextInput(attrs={"placeholder": "Optional: a broad place, such as Library 2nd floor", "maxlength": 120}),
            "post_type": forms.Select(attrs={"data-post-type": "true"}),
            "category": forms.Select(attrs={"data-category": "true"}),
            "title": forms.TextInput(attrs={"placeholder": "Optional: a broad name, such as blue water bottle"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Optional: describe visible details without revealing private identifiers."}),
            "approximate_date": forms.DateInput(attrs={"type": "date"}),
            # format="%H:%M" so the browser time picker shows the saved value when editing.
            "approximate_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }
        labels = {
            "title": "Title (optional)", "description": "Description (optional)",
            "approximate_date": "Approximate date lost/found",
            "approximate_time": "Approximate time lost/found",
        }
        help_texts = {"approximate_time": "Enter the estimated time when the item was lost or found."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound and not self._captcha_needed():
            # Only uploads that bring a post above 10 photos are checked.
            del self.fields["captcha"]
        if not getattr(settings, "FINDIT_LOCATION_ENABLED", False):
            # Location is DORMANT (owner decision 8): not shown or collected unless the setting is on.
            del self.fields["location"]
        else:
            self.fields["location"].required = False
            self.fields["location"].label = "Where (optional)"
            self.fields["location"].help_text = "A broad place on the main campus. Keep exact spots for the private claim form."
        categories = Category.objects.filter(is_active=True)
        if self.instance.pk and self.instance.category_id:
            categories = Category.objects.filter(Q(is_active=True) | Q(pk=self.instance.category_id))
        self.fields["category"].queryset = categories
        self.fields["category"].required = True
        self.fields["category"].empty_label = "Choose a category"
        if self.instance.pk:
            self.fields["remove_photos"].queryset = self.instance.photos.all()
        self.fields["questions"].queryset = QuestionTemplate.objects.filter(is_active=True).prefetch_related("categories")
        if self.instance.pk:
            self.fields["questions"].initial = [
                q.template_id for q in self.instance.verification_questions.all() if q.template_id
            ]

    def _captcha_needed(self):
        new = len([f for f in self.files.getlist("photos") if f]) if self.files else 0
        removing = len(self.data.getlist("remove_photos")) if hasattr(self.data, "getlist") else 0
        return new > 0 and self.existing_photo_count() - removing + new > HUMAN_CHECK_PHOTO_THRESHOLD

    def existing_photo_count(self):
        return self.instance.photos.count() if self.instance.pk else 0

    def clean(self):
        cleaned = super().clean()
        new_photos = cleaned.get("photos") or []
        removing = cleaned.get("remove_photos") or []
        total = self.existing_photo_count() - len(removing) + len(new_photos)
        if total < 1:
            self.add_error("photos", "Add at least one photo of the item.")
        elif total > MAX_POST_PHOTOS:
            self.add_error("photos", f"A post can have at most {MAX_POST_PHOTOS} photos. You selected {total}.")
        self._clean_approximate_when(cleaned)
        picked = cleaned.get("questions") or []
        if len(picked) > MAX_POST_QUESTIONS:
            self.add_error("questions", f"Pick at most {MAX_POST_QUESTIONS} questions.")
        return cleaned

    def _clean_approximate_when(self, cleaned):
        """Session 2 rules: a time needs a date; neither may be in the future."""
        date = cleaned.get("approximate_date")
        time = cleaned.get("approximate_time")
        if time and not date and not self.has_error("approximate_date"):
            self.add_error("approximate_date", "Add the approximate date as well, so the time has a day to go with it.")
            return
        if not date:
            return
        now = timezone.localtime()
        if date > now.date():
            self.add_error("approximate_date", "The approximate date cannot be in the future.")
        elif time and date == now.date() and time.replace(second=0, microsecond=0) > now.time().replace(second=0, microsecond=0):
            self.add_error("approximate_time", "The approximate time cannot be later than now.")

    def picked_questions(self):
        return list(self.cleaned_data.get("questions") or [])

    def save_photos(self, post):
        """Apply photo removals and additions after the post itself is saved."""
        for photo in self.cleaned_data.get("remove_photos") or []:
            photo.delete()  # its files are removed by the post_delete signal
        next_order = (post.photos.aggregate(models.Max("order"))["order__max"] or 0) + 1
        for offset, upload in enumerate(self.cleaned_data.get("photos") or []):
            PostPhoto.objects.create(post=post, image=upload, order=next_order + offset)


class CommentForm(forms.Form):
    text = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Add a public comment"}),
    )


class ClaimAnswerForm(forms.Form):
    """Private claim: one answer per post question plus a required description."""

    def __init__(self, *args, questions=None, **kwargs):
        super().__init__(*args, **kwargs)
        for question in questions or []:
            name = f"answer_{question.pk}"
            if question.answer_type == AnswerType.CHOICE and question.choices:
                self.fields[name] = forms.ChoiceField(
                    label=question.text,
                    choices=[("", "Choose an answer")] + [(c, c) for c in question.choices],
                )
            else:
                self.fields[name] = forms.CharField(
                    label=question.text,
                    max_length=1200,
                    widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Your private answer"}),
                )
        self.fields["description"] = forms.CharField(
            label="Describe the item in your own words",
            max_length=1500,
            help_text="Required. Mention details only the owner would know. Only the finder and staff can read this.",
            widget=forms.Textarea(attrs={"rows": 4, "placeholder": "For example: what it looks like, what was inside, how you lost it"}),
        )

    def answer_fields(self):
        return [field for field in self if field.name.startswith("answer_")]


class QuestionTemplateForm(forms.ModelForm):
    choices_text = forms.CharField(
        required=False,
        label="Answer options (one per line)",
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="Only for 'Choose from a list'. Add at least two options; consider including “Not sure”.",
    )

    class Meta:
        model = QuestionTemplate
        fields = ["text", "answer_type", "categories", "is_general", "is_default", "is_active", "sort_order"]
        widgets = {
            "text": forms.TextInput(),
            "categories": forms.CheckboxSelectMultiple,
        }
        labels = {
            "text": "Question",
            "is_general": "General (offer for every category)",
            "is_default": "Default (auto-added when a finder picks fewer than three)",
            "is_active": "Active",
            "sort_order": "Display order (lower shows first)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categories"].queryset = Category.objects.all()
        self.fields["categories"].required = False
        if self.instance.pk and self.instance.choices:
            self.fields["choices_text"].initial = "\n".join(self.instance.choices)

    def clean(self):
        cleaned = super().clean()
        options = []
        for line in (cleaned.get("choices_text") or "").splitlines():
            line = line.strip()
            if line and line.casefold() not in {o.casefold() for o in options}:
                options.append(line[:120])
        if cleaned.get("answer_type") == AnswerType.CHOICE:
            if len(options) < 2:
                self.add_error("choices_text", "A list question needs at least two answer options.")
        else:
            options = []
        cleaned["choices"] = options
        if not cleaned.get("is_general") and not cleaned.get("categories"):
            self.add_error("categories", "Choose at least one category, or mark the question as general.")
        if cleaned.get("is_default") and not cleaned.get("is_general"):
            self.add_error("is_default", "Default questions must be general so they fit every category.")
        will_be_default = bool(cleaned.get("is_default")) and bool(cleaned.get("is_active"))
        if not will_be_default:
            others = QuestionTemplate.objects.filter(is_default=True, is_active=True)
            if self.instance.pk:
                others = others.exclude(pk=self.instance.pk)
            if others.count() < MIN_POST_QUESTIONS:
                self.add_error(
                    "is_default",
                    f"Keep at least {MIN_POST_QUESTIONS} active default questions so every post has enough questions.",
                )
        return cleaned

    def save(self, commit=True):
        self.instance.choices = self.cleaned_data.get("choices", [])
        return super().save(commit=commit)


class ReportForm(forms.ModelForm):
    """Chat safety report submitted from a conversation by a participant or an authorized reviewer."""

    target_user = forms.TypedChoiceField(label="Account being reported", coerce=int, empty_value=None)
    reported_message = forms.TypedChoiceField(
        label="Specific message (optional)", coerce=int, empty_value=None, required=False,
    )

    class Meta:
        model = AbuseReport
        fields = ["reason", "details"]
        labels = {"reason": "Category", "details": "What happened?"}
        widgets = {"details": forms.Textarea(attrs={"rows": 4, "maxlength": 1500})}

    def __init__(self, *args, conversation, reporter, **kwargs):
        super().__init__(*args, **kwargs)
        self.conversation = conversation
        self.reporter = reporter
        participants = [conversation.initiator, conversation.recipient]
        choices = [(u.pk, u.get_full_name() or u.username) for u in participants if u.pk != reporter.pk]
        self.fields["target_user"].choices = [("", "Choose account")] + choices
        if len(choices) == 1:
            self.fields["target_user"].initial = choices[0][0]
        recent = conversation.messages.exclude(sender=reporter).select_related("sender").order_by("-sent_at")[:30]
        self.fields["reported_message"].choices = [("", "Not a specific message")] + [
            (m.pk, f"{m.sender.first_name or m.sender.username}, {timezone.localtime(m.sent_at):%b %d %H:%M}: {m.text[:60]}")
            for m in recent
        ]
        self.fields["details"].required = True
        self.fields["reason"].choices = [("", "Choose a category")] + list(AbuseReport.Reason.choices)

    def clean_details(self):
        value = self.cleaned_data["details"].strip()
        if len(value) < 10:
            raise ValidationError("Describe what happened in at least 10 characters.")
        return value

    def clean_target_user(self):
        value = self.cleaned_data["target_user"]
        if value not in {self.conversation.initiator_id, self.conversation.recipient_id} or value == self.reporter.pk:
            raise ValidationError("Choose the other participant in this conversation.")
        return value

    def clean_reported_message(self):
        value = self.cleaned_data.get("reported_message")
        if value and not self.conversation.messages.filter(pk=value).exclude(sender=self.reporter).exists():
            raise ValidationError("Choose a message from this conversation.")
        return value


class GeneralReportForm(forms.ModelForm):
    class Meta:
        model = GeneralReport
        fields = ["category", "description", "attachment"]
        labels = {"description": "Describe the issue", "attachment": "Screenshot or attachment (optional)"}
        help_texts = {"attachment": "JPG, PNG, WebP, or PDF; up to 5 MB. Only you and authorized reviewers can open it."}
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5, "maxlength": 2000}),
            "attachment": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp,application/pdf"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [("", "Choose a category")] + list(GeneralReport.Category.choices)

    def clean_description(self):
        value = self.cleaned_data["description"].strip()
        if len(value) < 10:
            raise ValidationError("Describe the issue in at least 10 characters.")
        return value

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        if attachment and hasattr(attachment, "content_type"):
            validate_report_attachment(attachment)
        return attachment


class ReportReviewForm(forms.Form):
    """Reviewer action on a chat safety report or general report."""

    ACTION_NOTE = "NOTE"
    action = forms.ChoiceField(label="Action", choices=[
        (ACTION_NOTE, "Add remarks only (keep status)"),
        (ReportStatus.UNDER_REVIEW, "Mark as Under Review"),
        (ReportStatus.RESOLVED, "Resolve"),
        (ReportStatus.DISMISSED, "Dismiss (no action needed)"),
    ])
    remarks = forms.CharField(
        label="Internal remarks", max_length=1500, required=False,
        help_text="Only administrators and verified moderators can see these remarks.",
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": 1500}),
    )
    account_action = forms.ChoiceField(label="Account decision (administrators only)", required=False, choices=[
        ("", "No account change"),
        ("suspend", "Suspend the reported account"),
        ("restore", "Restore the reported account"),
    ])

    def __init__(self, *args, report, allow_account_action=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.report = report
        if not allow_account_action:
            del self.fields["account_action"]

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get("action")
        status = self.report.status
        if action == self.ACTION_NOTE and not cleaned.get("remarks", "").strip():
            self.add_error("remarks", "Write the remarks to add.")
        if action == ReportStatus.UNDER_REVIEW and status != ReportStatus.SUBMITTED and status not in CLOSED_REPORT_STATUSES:
            self.add_error("action", "This report is already under review.")
        if action in CLOSED_REPORT_STATUSES and status in CLOSED_REPORT_STATUSES:
            self.add_error("action", "This report is already closed. Reopen it as Under Review first.")
        if action == ReportStatus.DISMISSED and cleaned.get("account_action"):
            self.add_error("account_action", "A dismissed report cannot change an account.")
        if cleaned.get("account_action") and action != ReportStatus.RESOLVED:
            self.add_error("account_action", "Account decisions are recorded when resolving a report.")
        return cleaned


class AdminAccountForm(forms.Form):
    """Administrator edit of another account's details, role, and status."""

    first_name = forms.CharField(max_length=60, label="First name")
    last_name = forms.CharField(max_length=60, label="Last name", required=False)
    email = forms.EmailField(max_length=254, label="Email address", required=False)
    contact_number = forms.CharField(max_length=20, label="Contact number", required=False)
    role = forms.ChoiceField(label="Role", choices=[
        (value, label) for value, label in Profile.Role.choices if value != Profile.Role.DEVELOPER
    ])
    is_active = forms.TypedChoiceField(
        label="Account status", coerce=lambda v: v == "1", choices=[("1", "Active"), ("0", "Inactive (suspended)")],
    )

    def __init__(self, *args, account, acting_admin, **kwargs):
        self.account = account
        self.acting_admin = acting_admin
        kwargs.setdefault("initial", {
            "first_name": account.first_name, "last_name": account.last_name, "email": account.email,
            "contact_number": account.profile.contact_number, "role": account.profile.role,
            "is_active": "1" if account.is_active else "0",
        })
        super().__init__(*args, **kwargs)
        self.locked_reason = ""
        acting_is_developer = acting_admin.profile.role == Profile.Role.DEVELOPER
        if not acting_is_developer:
            # Only the Developer can create or remove administrators.
            self.fields["role"].choices = [
                (value, label) for value, label in self.fields["role"].choices if value != Profile.Role.ADMIN
            ] if account.profile.role != Profile.Role.ADMIN else self.fields["role"].choices
        if account.pk == acting_admin.pk:
            self.locked_reason = "You cannot change your own role or status. Another administrator must do it."
        elif account.profile.role == Profile.Role.DEVELOPER:
            self.locked_reason = "The Developer account can only be changed with the create_developer command."
        elif account.profile.role == Profile.Role.ADMIN and not acting_is_developer:
            self.locked_reason = "Only the Developer can change an administrator's role or status."
        if self.locked_reason:
            for name in ("role", "is_active"):
                self.fields[name].disabled = True
        if not account.profile.student_id:
            self.fields["role"].help_text = "Student role needs a Student ID, so it is only available for accounts that registered as students."

    def clean_first_name(self):
        value = self.cleaned_data["first_name"].strip()
        if not value:
            raise ValidationError("Enter a first name.")
        return value

    def clean_last_name(self):
        return self.cleaned_data.get("last_name", "").strip()

    def clean_email(self):
        value = self.cleaned_data.get("email", "").strip().lower()
        if value and email_in_use(value, exclude_user=self.account):
            raise ValidationError("That email address is already used by another account.")
        return value

    clean_contact_number = ProfileForm.clean_contact_number

    def clean(self):
        cleaned = super().clean()
        role, active = cleaned.get("role"), cleaned.get("is_active")
        if role == Profile.Role.STUDENT and not self.account.profile.student_id:
            self.add_error("role", "This account has no Student ID, so it cannot become a Student.")
        acting_is_developer = self.acting_admin.profile.role == Profile.Role.DEVELOPER
        if not self.locked_reason and role == Profile.Role.ADMIN and self.account.profile.role != Profile.Role.ADMIN \
                and not acting_is_developer:
            self.add_error("role", "Only the Developer can make someone an administrator.")
        currently_admin = self.account.profile.role == Profile.Role.ADMIN and self.account.is_active
        if currently_admin and (role != Profile.Role.ADMIN or active is False):
            other_admins = User.objects.filter(
                is_active=True, profile__role__in=[Profile.Role.ADMIN, Profile.Role.DEVELOPER],
            ).exclude(pk=self.account.pk)
            if not other_admins.exists():
                raise ValidationError("At least one active administrator must remain.")
        return cleaned

    @transaction.atomic
    def save(self):
        account, profile = self.account, self.account.profile
        changes = []
        old_role, old_active = profile.role, account.is_active
        account.first_name = self.cleaned_data["first_name"]
        account.last_name = self.cleaned_data["last_name"]
        account.email = self.cleaned_data["email"]
        account.is_active = self.cleaned_data["is_active"]
        account.save(update_fields=["first_name", "last_name", "email", "is_active"])
        profile.contact_number = self.cleaned_data["contact_number"]
        profile.role = self.cleaned_data["role"]
        profile.save(update_fields=["contact_number", "role"])
        if old_role != profile.role:
            changes.append(f"role {old_role} → {profile.role}")
        if old_active != account.is_active:
            changes.append("activated" if account.is_active else "deactivated")
        return changes


class ModeratorDecisionForm(forms.Form):
    action = forms.ChoiceField(choices=[
        ("request", "Select for moderator verification"),
        ("approve", "Approve (Verified)"),
        ("reject", "Reject"),
        ("revoke", "Revoke authorization"),
    ])
    remarks = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 2, "maxlength": 500}))


class SystemSettingsForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = [
            "guardhouse_grace_days", "archive_purge_days", "posts_per_hour",
            "unverified_max_open_claims", "unverified_claim_expiry_days", "unverified_posts_per_day",
            "unverified_chat_messages", "unverified_chat_window_minutes", "unverified_chat_max_chars",
            "id_conflict_grace_days",
        ]
        widgets = {
            "posts_per_hour": forms.NumberInput(attrs={"min": 1, "max": 500}),
            "guardhouse_grace_days": forms.NumberInput(attrs={"min": 1, "placeholder": "Disabled"}),
            "archive_purge_days": forms.NumberInput(attrs={"min": 1, "placeholder": "Disabled"}),
        }

    LIMIT_RANGES = {
        "unverified_max_open_claims": (1, 50), "unverified_claim_expiry_days": (1, 7),
        "unverified_posts_per_day": (1, 100), "unverified_chat_messages": (1, 500),
        "unverified_chat_window_minutes": (1, 1440), "unverified_chat_max_chars": (20, 2000),
        "id_conflict_grace_days": (1, 90),
    }

    def clean(self):
        cleaned = super().clean()
        for name, (low, high) in self.LIMIT_RANGES.items():
            value = cleaned.get(name)
            if value is None or value < low or value > high:
                self.add_error(name, f"Choose a number from {low} to {high}.")
        return cleaned

    def clean_guardhouse_grace_days(self):
        return self._clean_timer("guardhouse_grace_days")

    def clean_archive_purge_days(self):
        return self._clean_timer("archive_purge_days")

    def clean_posts_per_hour(self):
        value = self.cleaned_data.get("posts_per_hour")
        if not value or value < 1 or value > 500:
            raise ValidationError("Choose between 1 and 500 posts per hour.")
        return value

    def _clean_timer(self, field):
        value = self.cleaned_data.get(field)
        if value is not None and value < 1:
            raise ValidationError("Leave blank to keep this timer disabled, or enter at least one day.")
        if value is not None and value > 3650:
            raise ValidationError("Choose a value of 3650 days or less.")
        return value


class CloseReasonForm(forms.Form):
    reason = forms.CharField(max_length=240, required=False, label="Reason (optional)")


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "sort_order", "is_active"]
        labels = {"sort_order": "Display order (lower shows first)", "is_active": "Active (shown on the post form)"}

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = Category.objects.filter(name__iexact=name)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError("A category with that name already exists.")
        return name

    def clean_is_active(self):
        active = self.cleaned_data["is_active"]
        if not active and self.instance.pk and self.instance.is_active:
            if Category.objects.filter(is_active=True).exclude(pk=self.instance.pk).count() == 0:
                raise ValidationError("Keep at least one category active.")
        return active


class CaptchaOnlyForm(forms.Form):
    """Renders a fresh captcha on the post form; ItemPostForm validates it when needed."""
    captcha = CaptchaField(label="Captcha")


class StatusChangeRequestForm(forms.Form):
    requested_status = forms.ChoiceField(label="What should staff do?", choices=StatusChangeRequest.Requested.choices)
    reason = forms.CharField(label="Reason (required)", max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))
    photo = forms.ImageField(label="Photo (optional)", required=False, validators=[validate_photo])
