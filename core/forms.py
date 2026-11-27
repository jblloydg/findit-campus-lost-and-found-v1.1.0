import re

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.core.exceptions import ValidationError

from .models import ItemPost, SystemSettings, AbuseReport, Profile
from .validators import validate_photo

User = get_user_model()
STUDENT_ID_PATTERN = re.compile(r"^\d{4}-\d{4}$")


class FindItLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="School ID or staff username",
        widget=forms.TextInput(attrs={"autocomplete": "username", "placeholder": "2024-0122"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Your password"}),
    )


class SignupForm(forms.Form):
    display_name = forms.CharField(max_length=80, label="Name")
    student_id = forms.CharField(max_length=9, label="School ID", help_text="Format: YYYY-NNNN")
    password1 = forms.CharField(label="Create password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def clean_student_id(self):
        value = self.cleaned_data["student_id"].strip()
        if not STUDENT_ID_PATTERN.fullmatch(value):
            raise ValidationError("Use the school ID format YYYY-NNNN.")
        if User.objects.filter(username=value).exists():
            raise ValidationError("That school ID already has an account.")
        if Profile.objects.filter(student_id=value).exists():
            raise ValidationError("That school ID already has an account.")
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") and cleaned.get("password2"):
            if cleaned["password1"] != cleaned["password2"]:
                self.add_error("password2", "The passwords do not match.")
            else:
                candidate = User(username=cleaned.get("student_id", ""), first_name=cleaned.get("display_name", ""))
                try:
                    from django.contrib.auth.password_validation import validate_password
                    validate_password(cleaned["password1"], candidate)
                except ValidationError as exc:
                    self.add_error("password1", exc)
        return cleaned

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data["student_id"],
            first_name=self.cleaned_data["display_name"].strip(),
            password=self.cleaned_data["password1"],
        )
        user.profile.student_id = self.cleaned_data["student_id"]
        user.profile.save(update_fields=["student_id"])
        return user


class StaffAccountForm(forms.Form):
    display_name = forms.CharField(max_length=80)
    username = forms.RegexField(
        regex=r"^[A-Za-z0-9._-]{3,32}$",
        help_text="Use a staff username, not a student ID.",
    )
    password = forms.CharField(widget=forms.PasswordInput, min_length=10)

    def clean_username(self):
        value = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=value).exists():
            raise ValidationError("That username is already in use.")
        return value

    def clean_password(self):
        password = self.cleaned_data["password"]
        candidate = User(username=self.cleaned_data.get("username", ""), first_name=self.cleaned_data.get("display_name", ""))
        from django.contrib.auth.password_validation import validate_password
        validate_password(password, candidate)
        return password

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            first_name=self.cleaned_data["display_name"].strip(),
            password=self.cleaned_data["password"],
        )
        user.profile.role = Profile.Role.STAFF
        user.profile.student_id = None
        user.profile.save(update_fields=["role", "student_id"])
        return user


class ItemPostForm(forms.ModelForm):
    question_1 = forms.CharField(max_length=240, required=False, label="Private question 1")
    question_2 = forms.CharField(max_length=240, required=False, label="Private question 2")
    question_3 = forms.CharField(max_length=240, required=False, label="Private question 3")
    question_4 = forms.CharField(max_length=240, required=False, label="Private question 4")
    question_5 = forms.CharField(max_length=240, required=False, label="Private question 5")

    class Meta:
        model = ItemPost
        fields = ["post_type", "title", "category", "description", "approximate_date", "photo"]
        widgets = {
            "post_type": forms.Select(attrs={"data-post-type": "true"}),
            "title": forms.TextInput(attrs={"placeholder": "A broad name, such as blue water bottle"}),
            "category": forms.Select(),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Describe visible details without revealing private identifiers."}),
            "approximate_date": forms.DateInput(attrs={"type": "date"}),
            "photo": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo:
            validate_photo(photo)
        return photo

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("post_type") == ItemPost.Type.FOUND:
            questions = [cleaned.get(f"question_{n}", "").strip() for n in range(1, 6)]
            if any(not question for question in questions):
                raise ValidationError("A found-item post needs exactly five private verification questions.")
            if len({q.casefold() for q in questions}) != 5:
                raise ValidationError("Use five different private questions.")
        return cleaned

    def question_texts(self):
        return [self.cleaned_data[f"question_{n}"].strip() for n in range(1, 6)]


class CommentForm(forms.Form):
    text = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Add a public comment"}),
    )


class ClaimAnswerForm(forms.Form):
    def __init__(self, *args, questions=None, **kwargs):
        super().__init__(*args, **kwargs)
        for question in questions or []:
            self.fields[f"answer_{question.pk}"] = forms.CharField(
                label=question.text,
                max_length=1200,
                widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Your private answer"}),
            )


class ReportForm(forms.ModelForm):
    class Meta:
        model = AbuseReport
        fields = ["reason", "details"]
        widgets = {"details": forms.Textarea(attrs={"rows": 4})}


class SystemSettingsForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = ["guardhouse_grace_days", "archive_purge_days"]
        widgets = {
            "guardhouse_grace_days": forms.NumberInput(attrs={"min": 1, "placeholder": "Disabled"}),
            "archive_purge_days": forms.NumberInput(attrs={"min": 1, "placeholder": "Disabled"}),
        }

    def clean_guardhouse_grace_days(self):
        return self._clean_timer("guardhouse_grace_days")

    def clean_archive_purge_days(self):
        return self._clean_timer("archive_purge_days")

    def _clean_timer(self, field):
        value = self.cleaned_data.get(field)
        if value is not None and value < 1:
            raise ValidationError("Leave blank to keep this timer disabled, or enter at least one day.")
        if value is not None and value > 3650:
            raise ValidationError("Choose a value of 3650 days or less.")
        return value


class AdminReviewForm(forms.Form):
    action = forms.ChoiceField(choices=[
        ("resolve", "Resolve with no account action"),
        ("suspend", "Suspend reported account"),
        ("restore", "Restore account"),
    ])
    admin_note = forms.CharField(max_length=1500, required=False, widget=forms.Textarea(attrs={"rows": 3}))


class CloseReasonForm(forms.Form):
    reason = forms.CharField(max_length=240, required=False, label="Reason (optional)")
