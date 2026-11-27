from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    AbuseReport, ClaimAnswer, ClaimApplication, ChatMessage, Comment, Conversation,
    InAppNotification, ItemPost, PostStatusEvent, Profile, StaffAuditLog,
    SystemSettings, VerificationQuestion,
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
    fields = ("role", "student_id")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "first_name", "is_active", "is_staff", "is_superuser")


class VerificationQuestionInline(admin.TabularInline):
    model = VerificationQuestion
    extra = 0


@admin.register(ItemPost)
class ItemPostAdmin(admin.ModelAdmin):
    list_display = ("title", "post_type", "category", "status", "author", "is_archived", "created_at")
    list_filter = ("post_type", "category", "status", "is_archived")
    search_fields = ("title", "description", "author__username")
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
    list_display = ("reason", "status", "reporter", "target_user", "created_at")
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