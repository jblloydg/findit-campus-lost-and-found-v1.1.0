from django.contrib.auth import views as auth_views
from django.urls import path

from .forms import FindItSetPasswordForm

from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("health/", views.health, name="health"),
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.my_profile, name="my-profile"),
    path("profile/edit/", views.edit_profile, name="edit-profile"),
    path("profile/password/", views.change_password, name="change-password"),
    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="core/password_reset_form.html",
        email_template_name="core/email/password_reset_email.txt",
        subject_template_name="core/email/password_reset_subject.txt",
    ), name="password_reset"),
    path("password-reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="core/password_reset_done.html",
    ), name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="core/password_reset_confirm.html", form_class=FindItSetPasswordForm,
    ), name="password_reset_confirm"),
    path("password-reset/complete/", auth_views.PasswordResetCompleteView.as_view(
        template_name="core/password_reset_complete.html",
    ), name="password_reset_complete"),
    path("home/", views.home, name="home"),
    path("p/<uuid:post_id>/", views.post_detail, name="post-detail"),
    path("posts/new/", views.create_post, name="create-post"),
    path("posts/<uuid:post_id>/edit/", views.edit_post, name="edit-post"),
    path("posts/<uuid:post_id>/claim/", views.submit_claim, name="submit-claim"),
    path("posts/<uuid:post_id>/comment/", views.add_comment, name="add-comment"),
    path("posts/<uuid:post_id>/turn-over/", views.turnover_view, name="turnover"),
    path("posts/<uuid:post_id>/returned/", views.returned_view, name="returned"),
    path("posts/<uuid:post_id>/claimed/", views.claimed_view, name="claimed"),
    path("posts/<uuid:post_id>/close/", views.close_post_view, name="close-post"),
    path("posts/<uuid:post_id>/remove/", views.remove_post_view, name="remove-post"),
    path("my-posts/", views.my_posts, name="my-posts"),
    path("my-claims/", views.my_claims, name="my-claims"),
    path("claims/<uuid:claim_id>/form/", views.claim_review, name="claim-review"),
    path("claims/<uuid:claim_id>/close/", views.close_claim_view, name="close-claim"),
    path("conversations/<uuid:conversation_id>/", views.chat_room, name="chat-room"),
    path("conversations/<uuid:conversation_id>/pause/", views.pause_chat, name="pause-chat"),
    path("conversations/<uuid:conversation_id>/unpause/", views.unpause_chat, name="unpause-chat"),
    path("conversations/<uuid:conversation_id>/report/", views.report_chat, name="report-chat"),
    path("reports/new/", views.general_report_create, name="general-report-create"),
    path("reports/general/<uuid:report_id>/attachment/", views.general_report_attachment, name="general-report-attachment"),
    path("my-reports/", views.my_reports, name="my-reports"),
    path("notifications/", views.notifications, name="notifications"),
    path("messages/", views.messages_inbox, name="messages"),
    path("staff/", views.staff_dashboard, name="staff-dashboard"),
    path("staff/accounts/", views.staff_accounts, name="staff-accounts"),
    path("staff/accounts/<int:user_id>/status/", views.staff_account_status, name="staff-account-status"),
    path("staff/accounts/<int:user_id>/edit/", views.edit_account, name="edit-account"),
    path("staff/admin/", views.admin_dashboard, name="admin-dashboard"),
    path("staff/admin/backups/", views.backup_status, name="backup-status"),
    path("staff/moderators/", views.moderator_verifications, name="moderator-verifications"),
    path("staff/moderators/<int:user_id>/decide/", views.moderator_verification_action, name="moderator-verification-action"),
    path("staff/general-reports/", views.general_reports, name="general-reports"),
    path("staff/general-reports/<uuid:report_id>/", views.general_report_detail, name="general-report-detail"),
    path("staff/settings/", views.admin_settings, name="admin-settings"),
    path("staff/reports/", views.admin_reports, name="admin-reports"),
    path("staff/reports/<uuid:report_id>/", views.review_report, name="review-report"),
    path("staff/comments/<int:comment_id>/moderate/", views.staff_moderate_comment, name="moderate-comment"),
]
