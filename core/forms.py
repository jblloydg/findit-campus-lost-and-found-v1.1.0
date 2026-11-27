import re

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.core.exceptions import ValidationError

from captcha.fields import CaptchaField
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .models import (
    AbuseReport, AnswerType, Category, ItemPost, PostPhoto, Profile, QuestionTemplate, StatusChangeRequest,
    SystemSettings,
)
from .validators import validate_photo

User = get_user_model()
STUDENT_ID_PATTERN = re.compile(r"^\d{4}-\d{4}$")
MAX_POST_PHOTOS = 20
HUMAN_CHECK_PHOTO_THRESHOLD = 10
MIN_POST_QUESTIONS = 3
MAX_POST_QUESTIONS = 5


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
        fields = ["post_type", "category", "title", "description", "approximate_date", "approximate_time"]
        widgets = {
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
            photo.image.delete(save=False)
            photo.delete()
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
    class Meta:
        model = AbuseReport
        fields = ["reason", "details"]
        widgets = {"details": forms.Textarea(attrs={"rows": 4})}


class SystemSettingsForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = ["guardhouse_grace_days", "archive_purge_days", "posts_per_hour"]
        widgets = {
            "posts_per_hour": forms.NumberInput(attrs={"min": 1, "max": 500}),
            "guardhouse_grace_days": forms.NumberInput(attrs={"min": 1, "placeholder": "Disabled"}),
            "archive_purge_days": forms.NumberInput(attrs={"min": 1, "placeholder": "Disabled"}),
        }

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


class AdminReviewForm(forms.Form):
    action = forms.ChoiceField(choices=[
        ("resolve", "Resolve with no account action"),
        ("suspend", "Suspend reported account"),
        ("restore", "Restore account"),
    ])
    admin_note = forms.CharField(max_length=1500, required=False, widget=forms.Textarea(attrs={"rows": 3}))


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
