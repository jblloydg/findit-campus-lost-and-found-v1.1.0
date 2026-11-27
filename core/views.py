from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    AdminReviewForm, ClaimAnswerForm, CloseReasonForm, CommentForm,
    FindItLoginForm, ItemPostForm, ReportForm, SignupForm, StaffAccountForm,
    SystemSettingsForm,
)
from .models import (
    AbuseReport, ClaimAnswer, ClaimApplication, Comment, Conversation,
    InAppNotification, ItemPost, PostStatusEvent, Profile, StaffAuditLog,
    SystemSettings, VerificationQuestion,
)
from .permissions import is_admin, is_staff_or_admin, role_of
from .services import (
    archive_post, audit, close_claim, close_post, confirm_claimed,
    create_claim_conversation, create_lost_post_conversation, notify_user, record_status,
    return_to_claimant, turn_over_to_guardhouse,
)

User = get_user_model()


def _safe_next(request, fallback="home"):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}):
        return target
    return reverse(fallback)


def landing(request):
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "core/landing.html", {"login_form": FindItLoginForm()})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))
    form = FindItLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect(_safe_next(request))
    return render(request, "core/login.html", {"form": form, "next": request.GET.get("next", "")})


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Your demo account is ready.")
        return redirect(_safe_next(request))
    return render(request, "core/signup.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("landing")


@login_required
def home(request):
    posts = ItemPost.objects.filter(is_archived=False).select_related("author", "author__profile")
    q = request.GET.get("q", "").strip()
    post_type = request.GET.get("type", "").strip()
    status = request.GET.get("status", "").strip()
    if q:
        posts = posts.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if post_type in {ItemPost.Type.LOST, ItemPost.Type.FOUND}:
        posts = posts.filter(post_type=post_type)
    if status in dict(ItemPost.Status.choices):
        posts = posts.filter(status=status)
    return render(request, "core/home.html", {
        "posts": posts[:100],
        "q": q,
        "selected_type": post_type,
        "selected_status": status,
        "status_choices": ItemPost.Status.choices,
    })


def _can_view_archived(post, user):
    # Soft removal hides the listing from active search but preserves direct links.
    return True


def _conversation_for_post(post, user):
    if post.is_archived or post.status in {
        ItemPost.Status.TURNED_OVER, ItemPost.Status.CLAIMED, ItemPost.Status.CLOSED
    }:
        return None
    if post.post_type == ItemPost.Type.FOUND:
        claim = post.claims.filter(
            claimant=user,
            status__in=[ClaimApplication.Status.SUBMITTED, ClaimApplication.Status.RETURNED],
        ).first()
        if claim:
            try:
                return claim.conversation
            except Conversation.DoesNotExist:
                return create_claim_conversation(claim)
    return create_lost_post_conversation(post, user)


def post_detail(request, post_id):
    post = get_object_or_404(ItemPost.objects.select_related("author"), pk=post_id)
    if not _can_view_archived(post, request.user):
        raise Http404

    resume = request.GET.get("resume", "")
    if request.user.is_authenticated and resume == "message" and request.user.pk != post.author_id:
        conversation = _conversation_for_post(post, request.user)
        if conversation:
            return redirect("chat-room", conversation_id=conversation.pk)
        messages.info(request, "This listing is no longer accepting new online conversations.")

    comments = post.comments.filter(moderation_status=Comment.Moderation.VISIBLE).select_related("author")
    user_claim = None
    claim_form = None
    if request.user.is_authenticated and post.post_type == ItemPost.Type.FOUND:
        user_claim = post.claims.filter(
            claimant=request.user,
            status__in=[ClaimApplication.Status.SUBMITTED, ClaimApplication.Status.RETURNED],
        ).first()
        if post.can_accept_claims and request.user.pk != post.author_id and not user_claim:
            claim_form = ClaimAnswerForm(questions=post.verification_questions.all())

    can_manage = request.user.is_authenticated and (
        request.user.pk == post.author_id or is_staff_or_admin(request.user)
    )
    can_moderate = request.user.is_authenticated and is_staff_or_admin(request.user)
    # Matches the rule in edit_post: only the author or an administrator.
    can_edit = request.user.is_authenticated and (
        request.user.pk == post.author_id or is_admin(request.user)
    )
    can_interact = (
        not post.is_archived
        and post.status not in {
            ItemPost.Status.TURNED_OVER, ItemPost.Status.CLAIMED, ItemPost.Status.CLOSED
        }
    )
    applications = []
    account_list = []
    if can_manage:
        applications = list(post.claims.select_related("claimant").order_by("-submitted_at"))
    if can_moderate and post.status == ItemPost.Status.TURNED_OVER:
        account_list = User.objects.filter(profile__role=Profile.Role.STUDENT, is_active=True).order_by("first_name")
    context = {
        "post": post,
        "comments": comments,
        "comment_form": CommentForm() if request.user.is_authenticated else None,
        "claim_form": claim_form,
        "user_claim": user_claim,
        "can_manage": can_manage,
        "can_edit": can_edit,
        "can_moderate": can_moderate,
        "can_interact": can_interact,
        "applications": applications,
        "account_list": account_list,
        "resume": resume,
        "direct_link": request.build_absolute_uri(),
    }
    return render(request, "core/post_detail.html", context)


@login_required
def create_post(request):
    form = ItemPostForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        post.save()
        if post.post_type == ItemPost.Type.FOUND:
            for order, text in enumerate(form.question_texts(), start=1):
                VerificationQuestion.objects.create(post=post, order=order, text=text)
        PostStatusEvent.objects.create(
            post=post,
            previous_status="",
            new_status=post.status,
            actor=request.user,
            note="Listing created.",
        )
        messages.success(request, "Your post is live.")
        return redirect("post-detail", post_id=post.pk)
    return render(request, "core/post_form.html", {"form": form})


@login_required
def edit_post(request, post_id):
    post = get_object_or_404(ItemPost, pk=post_id)
    if post.author_id != request.user.pk and not is_admin(request.user):
        return HttpResponseForbidden("Only the post author or an administrator may edit this post.")
    form = ItemPostForm(request.POST or None, request.FILES or None, instance=post)
    if request.method == "POST" and form.is_valid():
        updated = form.save()
        if not post.claims.exists():
            if updated.post_type == ItemPost.Type.FOUND:
                updated.verification_questions.all().delete()
                for order, text in enumerate(form.question_texts(), start=1):
                    VerificationQuestion.objects.create(post=updated, order=order, text=text)
            else:
                updated.verification_questions.all().delete()
        messages.success(request, "Your post was updated.")
        return redirect("post-detail", post_id=post.pk)
    existing_questions = list(post.verification_questions.order_by("order"))
    if post.claims.exists():
        form.fields["post_type"].disabled = True
    for index, question in enumerate(existing_questions, start=1):
        form.fields[f"question_{index}"].initial = question.text
        if post.claims.exists():
            form.fields[f"question_{index}"].disabled = True
            form.fields[f"question_{index}"].help_text = "Locked after a claim is submitted so earlier answers stay attached to their questions."
    return render(request, "core/post_form.html", {"form": form, "editing": True, "post": post})


@login_required
@require_POST
def submit_claim(request, post_id):
    post = get_object_or_404(ItemPost, pk=post_id)
    if post.author_id == request.user.pk:
        messages.error(request, "You cannot claim your own post.")
        return redirect("post-detail", post_id=post.pk)
    if not post.can_accept_claims:
        messages.error(request, "This item is not accepting online claims.")
        return redirect("post-detail", post_id=post.pk)
    if post.claims.filter(
        claimant=request.user,
        status__in=[ClaimApplication.Status.SUBMITTED, ClaimApplication.Status.RETURNED],
    ).exists():
        messages.info(request, "You already have a claim for this item.")
        return redirect("my-claims")

    questions = list(post.verification_questions.order_by("order"))
    if len(questions) != 5:
        messages.error(request, "This post is missing its five private verification questions. Please contact staff.")
        return redirect("post-detail", post_id=post.pk)
    form = ClaimAnswerForm(request.POST, questions=questions)
    if not form.is_valid():
        messages.error(request, "Please answer all five private questions.")
        return redirect(f"{reverse('post-detail', args=[post.pk])}?resume=claim#claim-form")

    with transaction.atomic():
        claim = ClaimApplication.objects.create(post=post, claimant=request.user)
        for question in questions:
            ClaimAnswer.objects.create(
                claim=claim,
                question=question,
                answer_text=form.cleaned_data[f"answer_{question.pk}"].strip(),
            )
        create_claim_conversation(claim)
        if post.status == ItemPost.Status.OPEN:
            record_status(post, ItemPost.Status.CLAIM_IN_PROGRESS, request.user, "A claim was submitted.", claim)
        claim.last_activity_at = timezone.now()
        claim.save(update_fields=["last_activity_at"])
        notify_user(post.author, post, "A new private claim form was submitted for your found-item post.", claim)
    messages.success(request, "Your private claim application was submitted.")
    return redirect("my-claims")


@login_required
@require_POST
def add_comment(request, post_id):
    post = get_object_or_404(ItemPost, pk=post_id)
    if post.is_archived or post.status in {
        ItemPost.Status.TURNED_OVER, ItemPost.Status.CLAIMED, ItemPost.Status.CLOSED
    }:
        messages.error(request, "Comments are closed for this listing.")
        return redirect("post-detail", post_id=post.pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        Comment.objects.create(post=post, author=request.user, text=form.cleaned_data["text"].strip())
        messages.success(request, "Comment added.")
    else:
        messages.error(request, "Add a comment of up to 1,000 characters.")
    return redirect(f"{reverse('post-detail', args=[post.pk])}#comments")


@login_required
def my_posts(request):
    posts = ItemPost.objects.filter(author=request.user).order_by("-created_at")
    return render(request, "core/my_posts.html", {"posts": posts})


@login_required
def my_claims(request):
    claims = ClaimApplication.objects.filter(claimant=request.user).select_related("post", "post__author")
    return render(request, "core/my_claims.html", {"claims": claims})


@login_required
def claim_review(request, claim_id):
    claim = get_object_or_404(
        ClaimApplication.objects.select_related("post", "claimant"),
        pk=claim_id,
    )
    if claim.post.author_id != request.user.pk and not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Only the finder or authorized staff may review this private form.")
    if is_staff_or_admin(request.user) and claim.post.author_id != request.user.pk:
        audit(request.user, "viewed_claim_form", claim, "Staff opened private ownership answers.")
    answers = claim.answers.select_related("question").order_by("question__order")
    return render(request, "core/claim_review.html", {"claim": claim, "answers": answers})


@login_required
@require_POST
def close_claim_view(request, claim_id):
    claim = get_object_or_404(ClaimApplication.objects.select_related("post", "post__author"), pk=claim_id)
    if request.user.pk not in {claim.post.author_id, claim.claimant_id} and not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Only the claim participants or staff can close this claim.")
    reason_form = CloseReasonForm(request.POST)
    if reason_form.is_valid():
        close_claim(claim, request.user, reason_form.cleaned_data.get("reason") or "Closed by participant.")
        messages.success(request, "The claim was closed. The listing can remain open for other claimants.")
    return redirect("post-detail", post_id=claim.post_id)


@login_required
@require_POST
def turnover_view(request, post_id):
    post = get_object_or_404(ItemPost, pk=post_id)
    if request.user.pk != post.author_id and not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Only the finder or authorized staff can record guard-house turnover.")
    if post.post_type != ItemPost.Type.FOUND or post.status in {ItemPost.Status.CLAIMED, ItemPost.Status.CLOSED}:
        messages.error(request, "This item cannot be turned over in its current state.")
        return redirect("post-detail", post_id=post.pk)
    turn_over_to_guardhouse(post, request.user)
    messages.success(request, "The item is now listed as at the guard house. Existing claims were notified and closed.")
    return redirect("post-detail", post_id=post.pk)


@login_required
@require_POST
def returned_view(request, post_id):
    post = get_object_or_404(ItemPost, pk=post_id)
    if post.author_id != request.user.pk:
        return HttpResponseForbidden("Only the finder can record a return.")
    claim = get_object_or_404(ClaimApplication, pk=request.POST.get("claim_id"), post=post)
    try:
        return_to_claimant(post, claim, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    except PermissionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Return recorded. The claimant can confirm receipt.")
    return redirect("staff-dashboard" if is_staff_or_admin(request.user) else "my-posts")


@login_required
@require_POST
def claimed_view(request, post_id):
    post = get_object_or_404(ItemPost, pk=post_id)
    claim = post.returned_application
    witnessed = False
    recipient = None
    if post.status == ItemPost.Status.TURNED_OVER:
        if not is_staff_or_admin(request.user):
            return HttpResponseForbidden("Only staff can record an in-person guard-house pickup.")
        claim = None
        recipient = get_object_or_404(
            User, pk=request.POST.get("recipient_id"), profile__role=Profile.Role.STUDENT
        )
        witnessed = True
    elif not claim:
        messages.error(request, "The finder has not recorded a return for this item.")
        return redirect("post-detail", post_id=post.pk)
    elif is_staff_or_admin(request.user):
        witnessed = True
    try:
        confirm_claimed(post, request.user, claim=claim, witnessed=witnessed, recipient=recipient)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))
    messages.success(request, "The claim is complete. The item is archived for history.")
    return redirect("post-detail", post_id=post.pk)


@login_required
@require_POST
def close_post_view(request, post_id):
    post = get_object_or_404(ItemPost, pk=post_id)
    if request.user.pk != post.author_id and not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Only the author or staff can close this listing.")
    form = CloseReasonForm(request.POST)
    reason = form.cleaned_data.get("reason", "") if form.is_valid() else ""
    close_post(post, request.user, reason)
    messages.success(request, "The listing is closed and retained in history.")
    return redirect("post-detail", post_id=post.pk)


@login_required
@require_POST
def remove_post_view(request, post_id):
    post = get_object_or_404(ItemPost, pk=post_id)
    if request.user.pk != post.author_id and not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Only the author or staff can remove this listing.")
    archive_post(post, request.user)
    messages.success(request, "The post was removed from active listings. Its claims and chats remain in history.")
    return redirect("my-posts" if request.user.pk == post.author_id else "staff-dashboard")


@login_required
def chat_room(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.select_related("post", "initiator", "recipient"),
        pk=conversation_id,
    )
    staff_view = is_staff_or_admin(request.user) and not conversation.includes(request.user)
    if not conversation.includes(request.user) and not staff_view:
        return HttpResponseForbidden("This conversation is private to its participants and authorized staff.")
    if is_staff_or_admin(request.user):
        audit(request.user, "reviewed_chat", conversation, "Staff opened private chat history.")
    messages_qs = conversation.messages.select_related("sender").all()
    return render(request, "core/chat_room.html", {
        "conversation": conversation,
        "chat_messages": messages_qs,
        "staff_view": staff_view,
        "can_send": conversation.includes(request.user) and not conversation.is_closed and not conversation.is_paused,
    })


@login_required
@require_POST
def pause_chat(request, conversation_id):
    if not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Only staff can pause a conversation.")
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    reason = request.POST.get("reason", "").strip()[:240] or "Paused for staff review."
    conversation.is_paused = True
    conversation.pause_reason = reason
    conversation.save(update_fields=["is_paused", "pause_reason", "updated_at"])
    audit(request.user, "paused_chat", conversation, reason)
    for participant in {conversation.initiator, conversation.recipient}:
        notify_user(participant, conversation.post, "A staff member paused this conversation for review.", conversation.claim)
    messages.success(request, "Chat paused. The participants can still read its history.")
    return redirect("chat-room", conversation_id=conversation.pk)


@login_required
@require_POST
def unpause_chat(request, conversation_id):
    if not is_admin(request.user):
        return HttpResponseForbidden("Only an administrator can restore a paused conversation.")
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    if conversation.is_closed:
        messages.error(request, "A closed claim chat cannot be reopened.")
        return redirect("chat-room", conversation_id=conversation.pk)
    conversation.is_paused = False
    conversation.pause_reason = ""
    conversation.save(update_fields=["is_paused", "pause_reason", "updated_at"])
    audit(request.user, "resumed_chat", conversation, "Administrator restored messaging.")
    for participant in {conversation.initiator, conversation.recipient}:
        notify_user(participant, conversation.post, "An administrator restored messaging in this conversation.", conversation.claim)
    messages.success(request, "Chat restored.")
    return redirect("chat-room", conversation_id=conversation.pk)


@login_required
@require_POST
def report_chat(request, conversation_id):
    if not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Only staff can submit reports for administrator review.")
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    form = ReportForm(request.POST)
    if form.is_valid():
        target_id = request.POST.get("target_user_id") or None
        if target_id and str(target_id) not in {str(conversation.initiator_id), str(conversation.recipient_id)}:
            return HttpResponseForbidden("The reported account must be a participant in this conversation.")
        report = form.save(commit=False)
        report.reporter = request.user
        report.conversation = conversation
        report.target_user_id = target_id
        report.save()
        conversation.is_paused = True
        conversation.pause_reason = "Reported for administrator review."
        conversation.save(update_fields=["is_paused", "pause_reason", "updated_at"])
        audit(request.user, "reported_chat", report, "Sent to administrators.")
        messages.success(request, "Report submitted to administrators; chat paused for review.")
    else:
        messages.error(request, "Choose a report reason.")
    return redirect("chat-room", conversation_id=conversation.pk)


@login_required
def notifications(request):
    rows = InAppNotification.objects.filter(recipient=request.user).select_related("post", "claim")
    unread_ids = list(rows.filter(read_at__isnull=True).values_list("pk", flat=True)[:200])
    if unread_ids:
        InAppNotification.objects.filter(pk__in=unread_ids).update(read_at=timezone.now())
    return render(request, "core/notifications.html", {"notifications": rows[:200]})


@login_required
def messages_inbox(request):
    conversations = Conversation.objects.filter(
        Q(initiator=request.user) | Q(recipient=request.user)
    ).select_related("post", "initiator", "recipient").prefetch_related("messages")
    return render(request, "core/messages.html", {"conversations": conversations[:100]})


@login_required
def staff_dashboard(request):
    if not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Staff access is required.")
    posts = ItemPost.objects.filter(is_archived=False).select_related("author").prefetch_related("claims")
    conversations = Conversation.objects.select_related("post", "initiator", "recipient")[:100]
    return render(request, "core/staff_dashboard.html", {
        "posts": posts[:100],
        "conversations": conversations,
        "recent_reports": AbuseReport.objects.filter(status=AbuseReport.Status.PENDING)[:20],
        "is_admin": is_admin(request.user),
    })


@login_required
def staff_accounts(request):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    form = StaffAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        audit(request.user, "created_staff_account", user, "Staff account created by administrator.")
        messages.success(request, f"Staff account for {user.get_full_name()} was created.")
        return redirect("staff-accounts")
    staff_users = User.objects.filter(profile__role=Profile.Role.STAFF).order_by("first_name")
    return render(request, "core/staff_accounts.html", {"form": form, "staff_users": staff_users})


@login_required
def admin_settings(request):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    settings_row = SystemSettings.current()
    form = SystemSettingsForm(request.POST or None, instance=settings_row)
    if request.method == "POST" and form.is_valid():
        setting = form.save(commit=False)
        setting.updated_by = request.user
        setting.save()
        audit(request.user, "updated_system_timers", setting, "Guard-house grace and archive purge timers changed.")
        messages.success(request, "Timer settings saved. Blank values keep the timers disabled.")
        return redirect("admin-settings")
    return render(request, "core/admin_settings.html", {"form": form, "settings_row": settings_row})


@login_required
def admin_reports(request):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    reports = AbuseReport.objects.select_related("reporter", "target_user", "conversation", "conversation__post", "reviewed_by")
    return render(request, "core/admin_reports.html", {"reports": reports[:200]})


@login_required
@require_POST
def review_report(request, report_id):
    if not is_admin(request.user):
        return HttpResponseForbidden("Only administrators can decide account restrictions.")
    report = get_object_or_404(AbuseReport.objects.select_related("target_user"), pk=report_id)
    form = AdminReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose an administrator action.")
        return redirect("admin-reports")
    action = form.cleaned_data["action"]
    if action == "suspend" and report.target_user:
        report.target_user.is_active = False
        report.target_user.save(update_fields=["is_active"])
        report.status = AbuseReport.Status.ACTION_TAKEN
        decision = "Account suspended."
    elif action == "restore" and report.target_user:
        report.target_user.is_active = True
        report.target_user.save(update_fields=["is_active"])
        report.status = AbuseReport.Status.ACTION_TAKEN
        decision = "Account restored."
    else:
        report.status = AbuseReport.Status.RESOLVED
        decision = "Report resolved without account action."
    report.admin_note = form.cleaned_data["admin_note"]
    report.reviewed_by = request.user
    report.resolved_at = timezone.now()
    report.save(update_fields=["status", "admin_note", "reviewed_by", "resolved_at"])
    audit(request.user, "reviewed_report", report, decision)
    messages.success(request, decision)
    return redirect("admin-reports")


@login_required
@require_POST
def staff_moderate_comment(request, comment_id):
    if not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Staff access is required.")
    comment = get_object_or_404(Comment, pk=comment_id)
    action = request.POST.get("action")
    if action not in {Comment.Moderation.VISIBLE, Comment.Moderation.HIDDEN, Comment.Moderation.REMOVED}:
        return HttpResponseForbidden("Unknown moderation action.")
    comment.moderation_status = action
    comment.save(update_fields=["moderation_status"])
    audit(request.user, f"comment_{action.lower()}", comment, "Comment moderation action.")
    messages.success(request, "Comment moderation updated.")
    return redirect("post-detail", post_id=comment.post_id)
