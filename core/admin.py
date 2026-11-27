from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    AbuseReport, ClaimAnswer, ClaimApplication, ChatMessage, Comment, Conversation,
    InAppNotification, ItemPost, PostStatusEvent, Profile, StaffAuditLog,
    SystemSettings, VerificationQuestion,
    GeneralReport, ModeratorVerification, ModeratorVerificationEvent, ReportStatusEvent,
)

User = get_user_model()
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0
    fields = ("role", "student_id", "contact_number", "photo")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "first_name", "last_name", "email", "account_role", "is_active", "is_staff", "is_superuser")
    list_filter = ("profile__role", "is_active", "is_staff", "is_superuser")

    @admin.display(description="Find-IT role")
    def account_role(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.get_role_display() if profile else "—"


class VerificationQuestionInline(admin.TabularInline):
    model = VerificationQuestion
    extra = 0


@admin.register(ItemPost)
class ItemPostAdmin(admin.ModelAdmin):
    list_display = ("title", "post_type", "category", "location", "status", "author", "is_archived", "created_at")
    list_filter = ("post_type", "category", "status", "is_archived")
    search_fields = ("title", "description", "location", "author__username")
    readonly_fields = (
        "status", "returned_application", "claimed_by_user", "turned_over_at",
        "claimed_at", "closed_at", "is_archived", "archived_at", "created_at", "updated_at",
    )
    inlines = [VerificationQuestionInline]

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ClaimApplication)
class ClaimApplicationAdmin(admin.ModelAdmin):
    list_display = ("post", "claimant", "status", "submitted_at", "last_activity_at")
    list_filter = ("status",)
    search_fields = ("post__title", "claimant__username")
    readonly_fields = ("status", "submitted_at", "last_activity_at", "closed_at", "close_reason")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AbuseReport)
class AbuseReportAdmin(admin.ModelAdmin):
    list_display = ("reference", "reason", "status", "reporter", "target_user", "assigned_reviewer", "created_at")
    list_filter = ("status", "reason")
    readonly_fields = ("reporter", "conversation", "target_user", "details", "created_at")

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ("guardhouse_grace_days", "archive_purge_days", "updated_by", "updated_at")

    def has_add_permission(self, request):
        return not SystemSettings.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


class ProtectedHistoryAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in [Comment, Conversation, ChatMessage, ClaimAnswer, PostStatusEvent, InAppNotification, StaffAuditLog]:
    admin.site.register(model, ProtectedHistoryAdmin)



# Read-only views for the moderator verification and report features. Decisions are made in the
# Find-IT pages so that history and permission checks are always applied.
class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GeneralReport)
class GeneralReportAdmin(ReadOnlyAdmin):
    list_display = ("reference", "category", "status", "reporter", "post", "assigned_reviewer", "created_at")
    list_filter = ("status", "category")
    search_fields = ("reference", "description", "reporter__username")
    exclude = ("attachment",)


@admin.register(ModeratorVerification)
class ModeratorVerificationAdmin(ReadOnlyAdmin):
    list_display = ("staff", "status", "reviewed_by", "decided_at")
    list_filter = ("status",)


@admin.register(ModeratorVerificationEvent)
class ModeratorVerificationEventAdmin(ReadOnlyAdmin):
    list_display = ("verification", "previous_status", "new_status", "actor", "created_at")


@admin.register(ReportStatusEvent)
class ReportStatusEventAdmin(ReadOnlyAdmin):
    list_display = ("chat_report", "general_report", "previous_status", "new_status", "actor", "created_at")
