import os
import secrets
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone

from .validators import validate_photo, validate_profile_photo


class Profile(models.Model):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        STAFF = "staff", "Staff"
        ADMIN = "admin", "Administrator"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.STUDENT)
    student_id = models.CharField(max_length=9, unique=True, null=True, blank=True)
    contact_number = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(
        upload_to="profile-photos/%Y/%m/", validators=[validate_profile_photo], blank=True, null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Category(models.Model):
    """Item category, managed by administrators. Required on every post."""
    name = models.CharField(max_length=60, unique=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class ItemPost(models.Model):
    class Type(models.TextChoices):
        LOST = "LOST", "Lost"
        FOUND = "FOUND", "Found"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open for Claim"
        CLAIM_IN_PROGRESS = "CLAIM_IN_PROGRESS", "Claim in Progress"
        TURNED_OVER = "TURNED_OVER", "At Guard House"
        RETURNED = "RETURNED", "Returned"
        CLAIMED = "CLAIMED", "Claimed"
        CLOSED = "CLOSED", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="item_posts")
    post_type = models.CharField(max_length=5, choices=Type.choices)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, null=True, blank=True, related_name="posts",
        help_text="Required for new posts. Older rows may be blank until edited.",
    )
    # Session 1 location: DORMANT. Kept in the database for the future campus-map
    # (DOrSU map cut into segments). It is not shown, collected or filtered while
    # settings.FINDIT_LOCATION_ENABLED is False (the default).
    location = models.CharField(
        max_length=120, blank=True,
        help_text="Dormant future feature (campus map segment). Not collected while FINDIT_LOCATION_ENABLED is off.",
    )
    title = models.CharField(max_length=120, blank=True)
    description = models.TextField(max_length=1600, blank=True)
    approximate_date = models.DateField(null=True, blank=True)
    # Session 2: optional like approximate_date, so older posts stay valid.
    approximate_time = models.TimeField(
        "approximate time lost/found", null=True, blank=True,
        help_text="Enter the estimated time when the item was lost or found.",
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN)
    returned_application = models.ForeignKey(
        "ClaimApplication", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="returned_posts",
    )
    claimed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="items_claimed",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    turned_over_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_reason = models.CharField(max_length=240, blank=True)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    is_shared = models.BooleanField(
        default=False,
        help_text="Turned on the first time someone signed in presses Copy link. Shared posts are viewable "
                  "without signing in until the post is permanently deleted.",
    )
    shared_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_archived", "-created_at"], name="itempost_browse_idx"),
            models.Index(fields=["post_type", "status"], name="itempost_type_status_idx"),
        ]

    def __str__(self):
        return self.display_title

    @property
    def is_resolved(self):
        return self.status in {self.Status.CLAIMED, self.Status.CLOSED}

    @property
    def display_title(self):
        """Title is optional; fall back to the category so lists stay readable."""
        if self.title:
            return self.title
        if self.category_id:
            return f"{self.get_post_type_display()} {self.category.name.lower()}"
        return f"{self.get_post_type_display()} item"

    @property
    def has_approximate_when(self):
        return bool(self.approximate_date or self.approximate_time)

    @property
    def cover_photo(self):
        photos = getattr(self, "_prefetched_objects_cache", {}).get("photos")
        if photos is not None:
            return photos[0] if photos else None
        return self.photos.order_by("order", "pk").first()

    @property
    def can_accept_claims(self):
        return (
            self.post_type == self.Type.FOUND
            and self.status in {self.Status.OPEN, self.Status.CLAIM_IN_PROGRESS}
            and not self.is_archived
        )

    @property
    def author_name(self):
        return self.author.get_full_name() or self.author.username


class PostShare(models.Model):
    """Who pressed Copy link on a post (one row per person)."""
    post = models.ForeignKey(ItemPost, on_delete=models.CASCADE, related_name="shares")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="post_shares")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["post", "user"], name="unique_post_share")]


class PostPhoto(models.Model):
    """One of 1-20 photos attached to a post. Photos are required; video is not allowed."""
    post = models.ForeignKey(ItemPost, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="item-photos/%Y/%m/", validators=[validate_photo])
    order = models.PositiveSmallIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return f"Photo {self.order} for {self.post}"


class AnswerType(models.TextChoices):
    CHOICE = "CHOICE", "Choose from a list"
    TEXT = "TEXT", "Free text"


class QuestionTemplate(models.Model):
    """A preset ownership question in the admin-managed question bank.

    Finders pick from these instead of typing questions. A question is either
    general (offered for every category) or tied to specific categories.
    Default questions fill a post up to the minimum of three.
    """
    text = models.CharField(max_length=240)
    answer_type = models.CharField(max_length=8, choices=AnswerType.choices, default=AnswerType.TEXT)
    choices = models.JSONField(default=list, blank=True, help_text="Answer options for list questions.")
    categories = models.ManyToManyField(Category, blank=True, related_name="question_templates")
    is_general = models.BooleanField(default=True, help_text="Offer this question for every category.")
    is_default = models.BooleanField(default=False, help_text="Used automatically when a finder picks fewer than three.")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "text"]

    def __str__(self):
        return self.text


class VerificationQuestion(models.Model):
    """The questions attached to one found post. Text, type and choices are
    copied from the question bank so later bank edits never change what an
    earlier claimant answered."""
    post = models.ForeignKey(ItemPost, on_delete=models.CASCADE, related_name="verification_questions")
    order = models.PositiveSmallIntegerField()
    text = models.CharField(max_length=240)
    template = models.ForeignKey(
        QuestionTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="post_questions"
    )
    answer_type = models.CharField(max_length=8, choices=AnswerType.choices, default=AnswerType.TEXT)
    choices = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["post", "order"], name="unique_post_question_order")
        ]

    def __str__(self):
        return f"{self.post.title} — question {self.order}"


class ClaimApplication(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        DECLINED = "DECLINED", "Declined"
        RETURNED = "RETURNED", "Returned to claimant"
        COMPLETED = "COMPLETED", "Completed"
        CLOSED = "CLOSED", "Closed"
        EXPIRED = "EXPIRED", "Expired"

    ACTIVE_STATUSES = ("SUBMITTED", "APPROVED", "RETURNED")
    RANKED_STATUSES = ("APPROVED", "RETURNED", "COMPLETED")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(ItemPost, on_delete=models.CASCADE, related_name="claims")
    claimant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="claims")
    finder = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="finder_claims",
        help_text="LOST posts only: the person who found the item and is verifying the owner.",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_claims"
    )
    declined_at = models.DateTimeField(null=True, blank=True)
    declined_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="declined_claims"
    )
    decline_reason = models.CharField(max_length=500, blank=True)
    reapply_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="reapplications"
    )
    description = models.TextField(
        max_length=1500, blank=True,
        help_text="Required free-text description written by the claimant (blank only on older claims).",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUBMITTED)
    submitted_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Claim by {self.claimant} for {self.post}"

    @property
    def is_open(self):
        return self.status in self.ACTIVE_STATUSES

    @property
    def is_lost_report(self):
        return self.finder_id is not None

    @property
    def finder_user(self):
        """Who verifies the claimant: the FOUND post's author, or the LOST post's finder."""
        return self.finder if self.finder_id else self.post.author

    @property
    def approval_rank(self):
        """1 for the first approved claim on the post, 2 for the next, and so on."""
        if self.status not in self.RANKED_STATUSES or not self.approved_at:
            return None
        return self.post.claims.filter(
            status__in=self.RANKED_STATUSES, approved_at__lt=self.approved_at,
        ).count() + 1


class ClaimAnswer(models.Model):
    claim = models.ForeignKey(ClaimApplication, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(VerificationQuestion, on_delete=models.CASCADE, related_name="answers")
    answer_text = models.TextField(max_length=1200)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["claim", "question"], name="one_answer_per_claim_question")
        ]

    def __str__(self):
        return f"Answer for {self.question}"


class Comment(models.Model):
    class Moderation(models.TextChoices):
        VISIBLE = "VISIBLE", "Visible"
        HIDDEN = "HIDDEN", "Hidden"
        REMOVED = "REMOVED", "Removed"

    post = models.ForeignKey(ItemPost, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comments")
    text = models.CharField(max_length=1000)
    moderation_status = models.CharField(max_length=10, choices=Moderation.choices, default=Moderation.VISIBLE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.author}"


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(ItemPost, on_delete=models.CASCADE, related_name="conversations")
    claim = models.OneToOneField(
        ClaimApplication, on_delete=models.CASCADE, null=True, blank=True, related_name="conversation"
    )
    initiator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="started_conversations")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_conversations")
    is_paused = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)
    pause_reason = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["post", "initiator", "recipient"],
                condition=models.Q(claim__isnull=True),
                name="unique_lost_post_conversation",
            )
        ]

    def __str__(self):
        return f"Conversation about {self.post}"

    def includes(self, user):
        return user.pk in {self.initiator_id, self.recipient_id}


class ChatMessage(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_messages")
    text = models.CharField(max_length=2000)
    client_id = models.CharField(max_length=64, blank=True, help_text="Browser-generated id so a resent message is saved once.")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sent_at"]
        indexes = [models.Index(fields=["conversation", "sent_at"], name="chatmessage_conv_time_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "client_id"], condition=~models.Q(client_id=""),
                name="unique_chat_message_client_id",
            )
        ]

    def __str__(self):
        return f"Message from {self.sender}"


class ChatQuestion(models.Model):
    """A question card the finder sends inside a chat; the claimant/owner answers it.
    Answers are read and judged by a person, never checked automatically."""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveSmallIntegerField()
    template = models.ForeignKey(QuestionTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    text = models.CharField(max_length=240)
    answer_type = models.CharField(max_length=8, choices=AnswerType.choices, default=AnswerType.TEXT)
    choices = models.JSONField(default=list, blank=True)
    asked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="asked_chat_questions")
    asked_at = models.DateTimeField(auto_now_add=True)
    answer_text = models.TextField(max_length=1200, blank=True)
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="answered_chat_questions"
    )
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["conversation", "order"], name="unique_chat_question_order"),
        ]

    @property
    def is_answered(self):
        return self.answered_at is not None


class IdempotencyKey(models.Model):
    """One-time form keys: a repeated submit with the same key is ignored."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    key = models.CharField(max_length=64)
    path = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "key"], name="unique_user_idempotency_key")]


class PostStatusEvent(models.Model):
    post = models.ForeignKey(ItemPost, on_delete=models.CASCADE, related_name="status_events")
    previous_status = models.CharField(max_length=24, blank=True)
    new_status = models.CharField(max_length=24, choices=ItemPost.Status.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="post_status_events"
    )
    related_claim = models.ForeignKey(ClaimApplication, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class InAppNotification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="findit_notifications")
    post = models.ForeignKey(ItemPost, on_delete=models.CASCADE, related_name="notifications")
    claim = models.ForeignKey(ClaimApplication, on_delete=models.SET_NULL, null=True, blank=True)
    text = models.CharField(max_length=240)
    is_priority = models.BooleanField(default=False, help_text="Shown as a red badge on Messages until read.")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read_at"], name="notification_unread_idx")]


class ReportStatus(models.TextChoices):
    """Shared status set for chat safety reports and general reports."""
    SUBMITTED = "SUBMITTED", "Submitted"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    RESOLVED = "RESOLVED", "Resolved"
    DISMISSED = "DISMISSED", "Dismissed"


OPEN_REPORT_STATUSES = (ReportStatus.SUBMITTED, ReportStatus.UNDER_REVIEW)
CLOSED_REPORT_STATUSES = (ReportStatus.RESOLVED, ReportStatus.DISMISSED)


def generate_reference(model, prefix):
    """Unique, human-readable reference such as CSR-20261127-4F9A2C."""
    while True:
        reference = f"{prefix}-{timezone.localdate():%Y%m%d}-{secrets.token_hex(3).upper()}"
        if not model.objects.filter(reference=reference).exists():
            return reference


def private_report_storage():
    """Report attachments live outside MEDIA_ROOT and are only served through a permission-checked view."""
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)


def general_report_attachment_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()[:6]
    return f"report-attachments/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{extension}"


class AbuseReport(models.Model):
    """Chat safety report about a user or messages in a private conversation."""

    Status = ReportStatus

    class Reason(models.TextChoices):
        HARASSMENT = "HARASSMENT", "Harassment or bullying"
        THREATS = "THREATS", "Threats or intimidation"
        SCAM = "SCAM", "Scam or suspicious behavior"
        INAPPROPRIATE = "INAPPROPRIATE", "Inappropriate messages"
        SPAM = "SPAM", "Spam"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=24, unique=True, editable=False)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="submitted_reports")
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    reported_message = models.ForeignKey(
        ChatMessage, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports",
    )
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports_about")
    reason = models.CharField("category", max_length=16, choices=Reason.choices)
    details = models.TextField("description", max_length=1500, blank=True)
    status = models.CharField(max_length=16, choices=ReportStatus.choices, default=ReportStatus.SUBMITTED, db_index=True)
    admin_note = models.TextField("internal remarks", max_length=1500, blank=True)
    assigned_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_chat_reports",
    )
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_reports")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = generate_reference(AbuseReport, "CSR")
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status in OPEN_REPORT_STATUSES


class GeneralReport(models.Model):
    """Item listing or system issue report, kept separate from chat safety reports."""

    Status = ReportStatus

    class Category(models.TextChoices):
        SUSPICIOUS_LISTING = "SUSPICIOUS_LISTING", "Suspicious or fraudulent item listing"
        INCORRECT_INFO = "INCORRECT_INFO", "Incorrect item information"
        DUPLICATE = "DUPLICATE", "Duplicate item listing"
        INAPPROPRIATE = "INAPPROPRIATE", "Inappropriate item content or image"
        SCAM = "SCAM", "Suspected scam"
        TECHNICAL = "TECHNICAL", "Technical or system issue"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=24, unique=True, editable=False)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="general_reports")
    category = models.CharField(max_length=20, choices=Category.choices)
    post = models.ForeignKey(
        ItemPost, on_delete=models.SET_NULL, null=True, blank=True, related_name="general_reports",
        verbose_name="related listing",
    )
    description = models.TextField(max_length=2000)
    attachment = models.FileField(
        upload_to=general_report_attachment_path, storage=private_report_storage, blank=True, null=True,
    )
    status = models.CharField(max_length=16, choices=ReportStatus.choices, default=ReportStatus.SUBMITTED, db_index=True)
    internal_remarks = models.TextField(max_length=1500, blank=True)
    assigned_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_general_reports",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_general_reports",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = generate_reference(GeneralReport, "GRP")
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status in OPEN_REPORT_STATUSES


class ReportStatusEvent(models.Model):
    """Review history for either kind of report. Notes are internal to reviewers."""

    chat_report = models.ForeignKey(AbuseReport, on_delete=models.CASCADE, null=True, blank=True, related_name="events")
    general_report = models.ForeignKey(GeneralReport, on_delete=models.CASCADE, null=True, blank=True, related_name="events")
    previous_status = models.CharField(max_length=16, blank=True)
    new_status = models.CharField(max_length=16, choices=ReportStatus.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="report_events")
    note = models.TextField(max_length=1500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def previous_status_label(self):
        return dict(ReportStatus.choices).get(self.previous_status, self.previous_status)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(chat_report__isnull=False, general_report__isnull=True)
                    | models.Q(chat_report__isnull=True, general_report__isnull=False)
                ),
                name="report_event_has_exactly_one_report",
            )
        ]


class ModeratorVerification(models.Model):
    """Administrator authorization for a Staff account to use moderator functions.

    This is not a separate role and does not verify university employment.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"
        REVOKED = "REVOKED", "Revoked"

    staff = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="moderator_verification")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="moderator_requests_made",
    )
    requested_at = models.DateTimeField(default=timezone.now)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="moderator_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    remarks = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["status", "staff__first_name"]

    def __str__(self):
        return f"{self.staff} — {self.get_status_display()}"


class ModeratorVerificationEvent(models.Model):
    verification = models.ForeignKey(ModeratorVerification, on_delete=models.CASCADE, related_name="events")
    previous_status = models.CharField(max_length=10, blank=True)
    new_status = models.CharField(max_length=10, choices=ModeratorVerification.Status.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="moderator_events")
    remarks = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def previous_status_label(self):
        return dict(ModeratorVerification.Status.choices).get(self.previous_status, "Not requested")


class SystemSettings(models.Model):
    """A single configurable settings row. Blank timers mean disabled."""
    guardhouse_grace_days = models.PositiveSmallIntegerField(null=True, blank=True)
    posts_per_hour = models.PositiveSmallIntegerField(
        default=10, help_text="Most new posts one account can create in an hour.",
    )
    archive_purge_days = models.PositiveSmallIntegerField(null=True, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Find-IT system settings"


class StaffAuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="staff_audit_events")
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=60)
    target_id = models.CharField(max_length=80)
    details = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def action_label(self):
        return self.action.replace("_", " ").capitalize()


def _new_turn_in_code():
    import secrets
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, easy to type
    return "".join(secrets.choice(alphabet) for _ in range(8))


class TurnInTicket(models.Model):
    """The QR / short code a finder shows at the guard house.

    FOUND posts get one automatically when posted. On LOST posts, the finder
    gets one when they choose to bring the item to the guard house.
    """
    code = models.CharField(max_length=12, unique=True, default=_new_turn_in_code, editable=False)
    post = models.ForeignKey(ItemPost, on_delete=models.CASCADE, related_name="turn_in_tickets")
    finder = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="turn_in_tickets")
    claim = models.ForeignKey(ClaimApplication, on_delete=models.SET_NULL, null=True, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True, help_text="When the finder said they are bringing it.")
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["post", "finder"], name="one_ticket_per_post_finder")]

    def __str__(self):
        return f"Turn-in {self.code}"


class GuardhouseIntake(models.Model):
    """Staff confirmation that an item physically arrived at the guard house."""

    class Method(models.TextChoices):
        QR = "QR", "QR scan"
        CODE = "CODE", "Code typed in"
        MANUAL = "MANUAL", "Manual (from the post page)"
        WALK_IN = "WALK_IN", "Walk-in item (posted by staff)"

    post = models.OneToOneField(ItemPost, on_delete=models.CASCADE, related_name="intake")
    ticket = models.ForeignKey(TurnInTicket, on_delete=models.SET_NULL, null=True, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="guardhouse_intakes")
    received_at = models.DateTimeField(default=timezone.now)
    handed_over_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="handed_over_items"
    )
    handed_over_by_name = models.CharField(max_length=120, blank=True, help_text="For people without an account.")
    method = models.CharField(max_length=8, choices=Method.choices)

    @property
    def handed_over_by_label(self):
        if self.handed_over_by_user_id:
            user = self.handed_over_by_user
            return user.get_full_name() or user.username
        return self.handed_over_by_name or "Not recorded"


class StatusChangeRequest(models.Model):
    """While an item is at the guard house the finder cannot change its status
    directly; they ask staff instead. A reason is required, a photo optional."""

    class Requested(models.TextChoices):
        CLOSED = "CLOSED", "Close the listing"
        OPEN = "OPEN", "Take the item back from the guard house"

    class Decision(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    post = models.ForeignKey(ItemPost, on_delete=models.CASCADE, related_name="status_requests")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="status_requests")
    requested_status = models.CharField(max_length=8, choices=Requested.choices)
    reason = models.TextField(max_length=1000)
    photo = models.ImageField(upload_to="status-requests/%Y/%m/", validators=[validate_photo], blank=True, null=True)
    decision = models.CharField(max_length=8, choices=Decision.choices, default=Decision.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_status_requests"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["decision", "-created_at"]
