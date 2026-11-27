import logging
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from .forms import (
    AdminAccountForm, ClaimAnswerForm, GeneralReportForm, ModeratorDecisionForm, ReportReviewForm, CloseReasonForm, CommentForm,
    FindItLoginForm, FindItPasswordChangeForm, ItemPostForm, ProfileForm, ReportForm, SignupForm, StaffAccountForm,
    SystemSettingsForm,
)
from .models import (
    OPEN_REPORT_STATUSES, AbuseReport, ChatMessage, ClaimAnswer, ClaimApplication, Comment, Conversation, GeneralReport,
    InAppNotification, ItemPost, ModeratorVerification, ModeratorVerificationEvent, ReportStatus, PostStatusEvent, Profile, StaffAuditLog,
    SystemSettings, VerificationQuestion,
)
from .security import clear_login_failures, client_ip, login_is_locked, record_login_failure
from .permissions import (
    can_review_private_chats, can_review_reports, is_admin, is_staff_or_admin, role_of,
)
from .services import (
    archive_post, audit, close_claim, close_post, confirm_claimed,
    create_claim_conversation, create_lost_post_conversation, notify_user, record_status,
    return_to_claimant, turn_over_to_guardhouse,
    ModeratorTransitionError, change_moderator_verification, record_report_submission,
    review_report_status, revoke_moderator_if_not_staff,
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


def _role_home(user):
    """Default landing page after sign-in when no safe ?next= page was requested."""
    return "staff-dashboard" if is_staff_or_admin(user) else "home"


@sensitive_post_parameters("password")
@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request, fallback=_role_home(request.user)))
    form = FindItLoginForm(request, data=request.POST or None)
    if request.method == "POST":
        username = request.POST.get("username", "")
        ip = client_ip(request)
        if login_is_locked(username, ip):
            minutes = max(1, settings.LOGIN_LOCKOUT_SECONDS // 60)
            form = FindItLoginForm(request)
            form.initial["username"] = username.strip()[:150]
            messages.error(
                request,
                f"Too many failed sign-in attempts. Wait {minutes} minutes and try again, or reset your password.",
            )
            return render(request, "core/login.html", {"form": form, "next": request.POST.get("next", "")}, status=429)
        if form.is_valid():
            user = form.get_user()
            clear_login_failures(username, ip)
            login(request, user)  # Rotates the session key to prevent session fixation.
            messages.success(request, f"Welcome back, {user.first_name or user.username}.")
            return redirect(_safe_next(request, fallback=_role_home(user)))
        record_login_failure(username, ip)
        messages.error(request, "Sign-in failed. Check the details below.")
    return render(request, "core/login.html", {
        "form": form,
        "next": request.POST.get("next") or request.GET.get("next", ""),
    })


@sensitive_post_parameters("password1", "password2")
def signup_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = SignupForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, "Your student account was created and you are now signed in.")
            return redirect(_safe_next(request))
        messages.error(request, "Your account was not created. Fix the highlighted fields and try again.")
    return render(request, "core/signup.html", {"form": form})


@never_cache
@login_required
def my_profile(request):
    user = User.objects.select_related("profile").get(pk=request.user.pk)
    return render(request, "core/profile.html", {"profile_user": user, "profile": user.profile})


@login_required
def edit_profile(request):
    # Always the signed-in user's own record: there is no user id in the URL to tamper with.
    user = User.objects.select_related("profile").get(pk=request.user.pk)
    form = ProfileForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        user=user,
    )
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile was updated.")
            return redirect("my-profile")
        messages.error(request, "Your profile was not saved. Fix the highlighted fields and try again.")
    return render(request, "core/profile_edit.html", {"form": form, "profile": user.profile})


@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@never_cache
@login_required
def change_password(request):
    form = FindItPasswordChangeForm(request.user, request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keep this session; other sessions are signed out.
            messages.success(request, "Your password was changed.")
            return redirect("my-profile")
        messages.error(request, "Your password was not changed. Fix the highlighted fields and try again.")
    return render(request, "core/change_password.html", {"form": form})


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
    category = request.GET.get("category", "").strip()
    location = request.GET.get("location", "").strip()[:120]
    if q:
        posts = posts.filter(
            Q(title__icontains=q) | Q(description__icontains=q) | Q(location__icontains=q)
        )
    if post_type in {ItemPost.Type.LOST, ItemPost.Type.FOUND}:
        posts = posts.filter(post_type=post_type)
    if status in dict(ItemPost.Status.choices):
        posts = posts.filter(status=status)
    if category in dict(ItemPost.Category.choices):
        posts = posts.filter(category=category)
    else:
        category = ""
    if location:
        posts = posts.filter(location__icontains=location)
    page_obj = _paginate(request, posts, 24)
    return render(request, "core/home.html", {
        "posts": page_obj,
        "page_obj": page_obj,
        "querystring": _querystring_without_page(request),
        "q": q,
        "selected_type": post_type,
        "selected_status": status,
        "selected_category": category,
        "location": location,
        "status_choices": ItemPost.Status.choices,
        "category_choices": ItemPost.Category.choices,
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
    posts = ItemPost.objects.filter(author=request.user).annotate(claim_count=Count("claims")).order_by("-created_at")
    return render(request, "core/my_posts.html", {"posts": posts})


@never_cache
@login_required
def my_claims(request):
    claims = ClaimApplication.objects.filter(claimant=request.user).select_related("post", "post__author", "conversation")
    return render(request, "core/my_claims.html", {"claims": claims})


@never_cache
@login_required
def claim_review(request, claim_id):
    """Private ownership answers.

    Visible to: the claimant (their own answers, read-only), the finder who wrote the
    questions, and Staff/Admin accounts handling claims. Everyone else gets 403.
    """
    claim = get_object_or_404(
        ClaimApplication.objects.select_related("post", "post__author", "claimant"),
        pk=claim_id,
    )
    is_claimant = claim.claimant_id == request.user.pk
    is_finder = claim.post.author_id == request.user.pk
    staff_access = is_staff_or_admin(request.user)
    if not (is_claimant or is_finder or staff_access):
        return HttpResponseForbidden("Only the claimant, the finder, or authorized staff may view this private form.")
    if staff_access and not (is_claimant or is_finder):
        audit(request.user, "viewed_claim_form", claim, "Staff opened private ownership answers.")
    answers = claim.answers.select_related("question").order_by("question__order")
    return render(request, "core/claim_review.html", {
        "claim": claim, "answers": answers, "viewer_is_claimant": is_claimant,
    })


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


@never_cache
@login_required
def chat_room(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.select_related("post", "initiator", "recipient"),
        pk=conversation_id,
    )
    reviewer = can_review_private_chats(request.user)
    staff_view = reviewer and not conversation.includes(request.user)
    if not conversation.includes(request.user) and not staff_view:
        return HttpResponseForbidden("This conversation is private to its participants and authorized reviewers.")
    if staff_view:
        audit(request.user, "reviewed_chat", conversation, "Authorized reviewer opened private chat history.")
    messages_qs = conversation.messages.select_related("sender").all()
    return render(request, "core/chat_room.html", {
        "conversation": conversation,
        "chat_messages": messages_qs,
        "staff_view": staff_view,
        "can_send": conversation.includes(request.user) and not conversation.is_closed and not conversation.is_paused,
        "is_reviewer": reviewer,
        "can_report": conversation.includes(request.user) or reviewer,
    })


@login_required
@require_POST
def pause_chat(request, conversation_id):
    if not can_review_private_chats(request.user):
        return HttpResponseForbidden("Only administrators and verified moderators can pause a conversation.")
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    reason = request.POST.get("reason", "").strip()[:240] or "Paused for staff review."
    conversation.is_paused = True
    conversation.pause_reason = reason
    conversation.save(update_fields=["is_paused", "pause_reason", "updated_at"])
    audit(request.user, "paused_chat", conversation, reason)
    for participant in {conversation.initiator, conversation.recipient}:
        notify_user(participant, conversation.post, "An authorized reviewer paused this conversation for review.", conversation.claim)
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
def report_chat(request, conversation_id):
    """Participants report the other person; authorized reviewers can also file a report."""
    conversation = get_object_or_404(Conversation.objects.select_related("post", "initiator", "recipient"), pk=conversation_id)
    is_participant = conversation.includes(request.user)
    reviewer = can_review_private_chats(request.user)
    if not is_participant and not reviewer:
        return HttpResponseForbidden("Only participants and authorized reviewers can report this conversation.")
    form = ReportForm(
        request.POST if request.method == "POST" else None, conversation=conversation, reporter=request.user,
    )
    if request.method == "POST":
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.conversation = conversation
            report.target_user_id = form.cleaned_data["target_user"]
            report.reported_message_id = form.cleaned_data.get("reported_message")
            report.save()
            record_report_submission(report, request.user)
            if reviewer and not is_participant:
                conversation.is_paused = True
                conversation.pause_reason = "Reported for safety review."
                conversation.save(update_fields=["is_paused", "pause_reason", "updated_at"])
            audit(request.user, "reported_chat", report, report.reference)
            messages.success(
                request,
                f"Report {report.reference} was submitted for review. No account is restricted until an authorized reviewer decides.",
            )
            return redirect("chat-room", conversation_id=conversation.pk)
        messages.error(request, "Your report was not submitted. Fix the highlighted fields and try again.")
    return render(request, "core/chat_report_form.html", {"form": form, "conversation": conversation})


@login_required
def notifications(request):
    rows = InAppNotification.objects.filter(recipient=request.user).select_related("post", "claim")
    unread_ids = list(rows.filter(read_at__isnull=True).values_list("pk", flat=True)[:200])
    if unread_ids:
        InAppNotification.objects.filter(pk__in=unread_ids).update(read_at=timezone.now())
    return render(request, "core/notifications.html", {"notifications": rows[:200]})


@login_required
def messages_inbox(request):
    # Only the newest message per conversation is loaded (sliced prefetch), not every message.
    conversations = Conversation.objects.filter(
        Q(initiator=request.user) | Q(recipient=request.user)
    ).select_related("post", "initiator", "recipient").prefetch_related(
        Prefetch(
            "messages",
            queryset=ChatMessage.objects.select_related("sender").order_by("-sent_at")[:1],
            to_attr="latest_messages",
        )
    )
    return render(request, "core/messages.html", {"conversations": conversations[:100]})


@login_required
def staff_dashboard(request):
    if not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Staff access is required.")
    posts = ItemPost.objects.filter(is_archived=False).select_related("author").annotate(claim_count=Count("claims"))
    conversations = Conversation.objects.select_related("post", "initiator", "recipient")[:100]
    reviewer = can_review_reports(request.user)
    return render(request, "core/staff_dashboard.html", {
        "posts": posts[:100],
        "conversations": conversations if reviewer else [],
        "recent_reports": AbuseReport.objects.filter(status__in=OPEN_REPORT_STATUSES).select_related("reporter")[:20] if reviewer else [],
        "open_general_count": GeneralReport.objects.filter(status__in=OPEN_REPORT_STATUSES).count() if reviewer else 0,
        "is_admin": is_admin(request.user),
        "is_reviewer": reviewer,
        "moderator_status": ModeratorVerification.objects.filter(staff=request.user).first(),
    })


def _paginate(request, queryset, per_page=20):
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


def _querystring_without_page(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


@sensitive_post_parameters("password", "password_confirm")
@login_required
def staff_accounts(request):
    """Administrator account management: create staff, search, filter, and open any account."""
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    form = StaffAccountForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            audit(request.user, "created_staff_account", user, "Staff account created by administrator.")
            messages.success(request, f"Staff account for {user.get_full_name() or user.username} was created.")
            return redirect("staff-accounts")
        messages.error(request, "The staff account was not created. Fix the highlighted fields and try again.")
    staff_users = (
        User.objects.filter(profile__role=Profile.Role.STAFF)
        .select_related("profile", "moderator_verification").order_by("first_name", "username")
    )
    accounts = User.objects.select_related("profile").order_by("profile__role", "first_name", "username")
    q = request.GET.get("q", "").strip()[:80]
    role_filter = request.GET.get("role", "").strip()
    status_filter = request.GET.get("status", "").strip()
    if q:
        accounts = accounts.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
    if role_filter in dict(Profile.Role.choices):
        accounts = accounts.filter(profile__role=role_filter)
    else:
        role_filter = ""
    if status_filter in {"active", "inactive"}:
        accounts = accounts.filter(is_active=status_filter == "active")
    else:
        status_filter = ""
    return render(request, "core/staff_accounts.html", {
        "form": form,
        "staff_users": staff_users,
        "page_obj": _paginate(request, accounts, 20),
        "querystring": _querystring_without_page(request),
        "q": q,
        "role_filter": role_filter,
        "status_filter": status_filter,
        "role_choices": Profile.Role.choices,
    })


def _account_lock_reason(account, admin_user):
    if account.pk == admin_user.pk:
        return "You cannot change your own role or status."
    if account.is_superuser:
        return "Django superusers are managed in Django administration."
    return ""


def _is_last_active_admin(account):
    if not (account.is_active and role_of(account) == Profile.Role.ADMIN):
        return False
    return not User.objects.filter(is_active=True).filter(
        Q(profile__role=Profile.Role.ADMIN) | Q(is_superuser=True)
    ).exclude(pk=account.pk).exists()


@login_required
@require_POST
def staff_account_status(request, user_id):
    """Administrators activate or deactivate accounts. Roles are never changed here."""
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    target = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
    lock = _account_lock_reason(target, request.user)
    if lock:
        return HttpResponseForbidden(lock)
    action = request.POST.get("action")
    if action not in {"suspend", "activate"}:
        messages.error(request, "Choose activate or deactivate.")
        return redirect(_safe_next(request, fallback="staff-accounts"))
    if action == "suspend" and _is_last_active_admin(target):
        messages.error(request, "At least one active administrator must remain.")
        return redirect(_safe_next(request, fallback="staff-accounts"))
    target.is_active = action == "activate"
    target.save(update_fields=["is_active"])
    name = target.get_full_name() or target.username
    audit(request.user, f"{action}_account", target, f"{role_of(target)} account {'activated' if target.is_active else 'deactivated'} by administrator.")
    messages.success(request, f"{name} was {'activated' if target.is_active else 'deactivated and can no longer sign in'}.")
    return redirect(_safe_next(request, fallback="staff-accounts"))


@never_cache
@login_required
def edit_account(request, user_id):
    """Administrator edit of any account. Superusers and the admin's own role/status are locked."""
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    account = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
    form = AdminAccountForm(
        request.POST if request.method == "POST" else None, account=account, acting_admin=request.user,
    )
    if request.method == "POST":
        if form.is_valid():
            changes = form.save()
            revoke_moderator_if_not_staff(account, request.user)
            audit(request.user, "edited_account", account, "; ".join(["details updated", *changes]))
            messages.success(request, f"Account {account.username} was updated.")
            return redirect("edit-account", user_id=account.pk)
        messages.error(request, "The account was not saved. Fix the highlighted fields and try again.")
    verification = ModeratorVerification.objects.filter(staff=account).first()
    return render(request, "core/account_edit.html", {
        "form": form, "account": account, "verification": verification,
        "recent_activity": StaffAuditLog.objects.filter(target_type="User", target_id=str(account.pk))[:10],
    })


@login_required
def admin_dashboard(request):
    """Administrator overview. Every number is counted from the database on each visit."""
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    users = User.objects.all()
    admin_q = Q(profile__role=Profile.Role.ADMIN) | Q(is_superuser=True)
    account_counts = users.aggregate(
        total=Count("pk"),
        students=Count("pk", filter=Q(profile__role=Profile.Role.STUDENT, is_superuser=False)),
        staff=Count("pk", filter=Q(profile__role=Profile.Role.STAFF, is_superuser=False)),
        admins=Count("pk", filter=admin_q),
        active=Count("pk", filter=Q(is_active=True)),
        inactive=Count("pk", filter=Q(is_active=False)),
    )
    verification_counts = {
        value: ModeratorVerification.objects.filter(status=value).count()
        for value in ModeratorVerification.Status.values
    }

    def report_counts(model):
        counts = {value: 0 for value in ReportStatus.values}
        for row in model.objects.values("status").annotate(n=Count("pk")):
            counts[row["status"]] = row["n"]
        counts["TOTAL"] = sum(counts.values())
        return counts

    return render(request, "core/admin_dashboard.html", {
        "account_counts": account_counts,
        "verification_counts": verification_counts,
        "chat_counts": report_counts(AbuseReport),
        "general_counts": report_counts(GeneralReport),
        "pending_verifications": ModeratorVerification.objects.filter(
            status=ModeratorVerification.Status.PENDING).select_related("staff")[:5],
        "recent_verification_events": ModeratorVerificationEvent.objects.select_related(
            "verification__staff", "actor")[:5],
        "open_chat_reports": AbuseReport.objects.filter(status__in=OPEN_REPORT_STATUSES).select_related("reporter", "target_user")[:5],
        "open_general_reports": GeneralReport.objects.filter(status__in=OPEN_REPORT_STATUSES).select_related("reporter", "post")[:5],
        "report_status_choices": ReportStatus.choices,
    })


@never_cache
@login_required
def backup_status(request):
    """Read-only backup information for administrators. Backups cannot be downloaded or
    restored from the website; restore is a command-line procedure (docs/OPERATIONS.md)."""
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    from .backup import BackupError, status_summary
    try:
        info = status_summary()
    except (BackupError, OSError) as exc:
        info = {"error": str(exc)}
    return render(request, "core/backup_status.html", {"info": info})


@login_required
def moderator_verifications(request):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    staff_users = (
        User.objects.filter(profile__role=Profile.Role.STAFF, is_superuser=False)
        .select_related("profile", "moderator_verification", "moderator_verification__reviewed_by")
        .order_by("first_name", "username")
    )
    status_filter = request.GET.get("status", "").strip()
    if status_filter == "NONE":
        staff_users = staff_users.filter(moderator_verification__isnull=True)
    elif status_filter in ModeratorVerification.Status.values:
        staff_users = staff_users.filter(moderator_verification__status=status_filter)
    else:
        status_filter = ""
    history = ModeratorVerificationEvent.objects.select_related("verification__staff", "actor")
    return render(request, "core/moderator_verifications.html", {
        "staff_users": staff_users,
        "status_filter": status_filter,
        "status_choices": ModeratorVerification.Status.choices,
        "counts": {value: ModeratorVerification.objects.filter(status=value).count() for value in ModeratorVerification.Status.values},
        "unrequested_count": User.objects.filter(
            profile__role=Profile.Role.STAFF, is_superuser=False, moderator_verification__isnull=True).count(),
        "history_page": _paginate(request, history, 15),
        "querystring": _querystring_without_page(request),
    })


@login_required
@require_POST
def moderator_verification_action(request, user_id):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    staff_user = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
    form = ModeratorDecisionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a valid moderator action.")
        return redirect("moderator-verifications")
    try:
        verification = change_moderator_verification(
            staff_user, request.user, form.cleaned_data["action"], form.cleaned_data["remarks"],
        )
    except ModeratorTransitionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, f"Moderator status for {staff_user.get_full_name() or staff_user.username} is now {verification.get_status_display()}.",
        )
    return redirect(_safe_next(request, fallback="moderator-verifications"))


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


def _filtered_reports(request, queryset, category_field, category_choices, search_fields):
    """Shared search, category, status, and date filters for report lists."""
    filters = {
        "q": request.GET.get("q", "").strip()[:80],
        "category": request.GET.get("category", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "date_from": request.GET.get("date_from", "").strip(),
        "date_to": request.GET.get("date_to", "").strip(),
    }
    if filters["q"]:
        query = Q()
        for field in search_fields:
            query |= Q(**{f"{field}__icontains": filters["q"]})
        queryset = queryset.filter(query)
    if filters["category"] in dict(category_choices):
        queryset = queryset.filter(**{category_field: filters["category"]})
    else:
        filters["category"] = ""
    if filters["status"] == "OPEN":
        queryset = queryset.filter(status__in=OPEN_REPORT_STATUSES)
    elif filters["status"] in ReportStatus.values:
        queryset = queryset.filter(status=filters["status"])
    else:
        filters["status"] = ""
    for key, lookup in (("date_from", "created_at__date__gte"), ("date_to", "created_at__date__lte")):
        parsed = parse_date(filters[key]) if filters[key] else None
        if parsed:
            queryset = queryset.filter(**{lookup: parsed})
        else:
            filters[key] = ""
    return queryset, filters


def _report_list_context(request, queryset, filters, category_choices, **extra):
    return {
        "page_obj": _paginate(request, queryset, 20),
        "querystring": _querystring_without_page(request),
        "filters": filters,
        "category_choices": category_choices,
        "status_choices": ReportStatus.choices,
        **extra,
    }


@login_required
def admin_reports(request):
    """Chat safety report queue for administrators and verified moderators."""
    if not can_review_reports(request.user):
        return HttpResponseForbidden("Administrator or verified moderator access is required.")
    reports = AbuseReport.objects.select_related(
        "reporter", "target_user", "conversation", "conversation__post", "assigned_reviewer", "reviewed_by",
    )
    reports, filters = _filtered_reports(
        request, reports, "reason", AbuseReport.Reason.choices,
        ["reference", "details", "reporter__username", "reporter__first_name", "target_user__username", "target_user__first_name"],
    )
    return render(request, "core/admin_reports.html", _report_list_context(
        request, reports, filters, AbuseReport.Reason.choices,
    ))


@never_cache
@login_required
def review_report(request, report_id):
    """Chat safety report detail and review form."""
    if not can_review_reports(request.user):
        return HttpResponseForbidden("Administrator or verified moderator access is required.")
    report = get_object_or_404(AbuseReport.objects.select_related(
        "reporter", "target_user", "conversation", "conversation__post", "reported_message",
        "reported_message__sender", "assigned_reviewer", "reviewed_by",
    ), pk=report_id)
    admin_user = is_admin(request.user)
    can_change_account = (
        admin_user and report.target_user is not None and not report.target_user.is_superuser
        and report.target_user_id != request.user.pk and role_of(report.target_user) != Profile.Role.ADMIN
    )
    form = ReportReviewForm(
        request.POST if request.method == "POST" else None, report=report, allow_account_action=can_change_account,
    )
    if request.method == "POST":
        if form.is_valid():
            action = form.cleaned_data["action"]
            remarks = form.cleaned_data["remarks"]
            account_action = form.cleaned_data.get("account_action")
            if account_action:
                report.target_user.is_active = account_action == "restore"
                report.target_user.save(update_fields=["is_active"])
                decision = "Account suspended." if account_action == "suspend" else "Account restored."
                audit(request.user, f"{account_action}_account", report.target_user, f"Decision on {report.reference}.")
                remarks = f"{decision} {remarks}".strip()
            review_report_status(report, request.user, action, remarks)
            messages.success(request, f"Report {report.reference} updated: {report.get_status_display()}.")
            return redirect("review-report", report_id=report.pk)
        messages.error(request, "The review was not saved. Check the highlighted fields.")
    else:
        audit(request.user, "viewed_chat_report", report, report.reference)
    return render(request, "core/chat_report_detail.html", {
        "report": report,
        "form": form,
        "events": report.events.select_related("actor"),
        "context_messages": _messages_around(report),
    })


def _messages_around(report):
    """A few messages before and after the reported one, for reviewer context."""
    if not report.reported_message_id or not report.conversation_id:
        return []
    message = report.reported_message
    qs = report.conversation.messages.select_related("sender")
    before = list(qs.filter(sent_at__lt=message.sent_at).order_by("-sent_at")[:3])[::-1]
    after = list(qs.filter(sent_at__gt=message.sent_at).order_by("sent_at")[:3])
    return before + [message] + after


@login_required
def general_report_create(request):
    post = None
    post_id = request.GET.get("post") or request.POST.get("post")
    if post_id:
        try:
            post = ItemPost.objects.filter(pk=post_id).first()
        except (ValueError, ValidationError):
            post = None
    form = GeneralReportForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
    )
    if post is None:
        form.fields["category"].initial = GeneralReport.Category.TECHNICAL
    if request.method == "POST":
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.post = post
            report.save()
            record_report_submission(report, request.user)
            messages.success(request, f"Report {report.reference} was submitted. You can follow its status under My reports.")
            return redirect("my-reports")
        messages.error(request, "Your report was not submitted. Fix the highlighted fields and try again.")
    return render(request, "core/general_report_form.html", {"form": form, "post": post})


@login_required
def general_reports(request):
    if not can_review_reports(request.user):
        return HttpResponseForbidden("Administrator or verified moderator access is required.")
    reports = GeneralReport.objects.select_related("reporter", "post", "assigned_reviewer", "reviewed_by")
    reports, filters = _filtered_reports(
        request, reports, "category", GeneralReport.Category.choices,
        ["reference", "description", "reporter__username", "reporter__first_name", "post__title"],
    )
    return render(request, "core/general_reports.html", _report_list_context(
        request, reports, filters, GeneralReport.Category.choices,
    ))


@never_cache
@login_required
def general_report_detail(request, report_id):
    if not can_review_reports(request.user):
        return HttpResponseForbidden("Administrator or verified moderator access is required.")
    report = get_object_or_404(GeneralReport.objects.select_related(
        "reporter", "post", "post__author", "assigned_reviewer", "reviewed_by",
    ), pk=report_id)
    form = ReportReviewForm(request.POST if request.method == "POST" else None, report=report)
    if request.method == "POST":
        if form.is_valid():
            review_report_status(report, request.user, form.cleaned_data["action"], form.cleaned_data["remarks"])
            messages.success(request, f"Report {report.reference} updated: {report.get_status_display()}.")
            return redirect("general-report-detail", report_id=report.pk)
        messages.error(request, "The review was not saved. Check the highlighted fields.")
    return render(request, "core/general_report_detail.html", {
        "report": report, "form": form, "events": report.events.select_related("actor"),
    })


@never_cache
@login_required
def general_report_attachment(request, report_id):
    """Serve a report attachment only to its reporter and authorized reviewers."""
    report = get_object_or_404(GeneralReport, pk=report_id)
    if report.reporter_id != request.user.pk and not can_review_reports(request.user):
        return HttpResponseForbidden("You cannot open this attachment.")
    if not report.attachment:
        raise Http404
    try:
        handle = report.attachment.open("rb")
    except FileNotFoundError:
        raise Http404
    name = os.path.basename(report.attachment.name)
    is_pdf = name.lower().endswith(".pdf")
    response = FileResponse(handle, as_attachment=is_pdf, filename=f"{report.reference}{os.path.splitext(name)[1]}")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; sandbox"
    return response


@never_cache
@login_required
def my_reports(request):
    """A user's own submitted reports. Internal remarks are never shown here."""
    return render(request, "core/my_reports.html", {
        "chat_reports": AbuseReport.objects.filter(reporter=request.user).select_related("target_user", "conversation__post"),
        "general_reports": GeneralReport.objects.filter(reporter=request.user).select_related("post"),
    })


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


def csrf_failure(request, reason=""):
    """Friendly page for expired or missing CSRF tokens (settings.CSRF_FAILURE_VIEW)."""
    return render(request, "core/csrf_failure.html", status=403)


@never_cache
@transaction.non_atomic_requests  # must answer even when a transaction cannot be opened
def health(request):
    """Uptime check for monitoring services. Reports only ok/error, never details."""
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        database = "ok"
    except Exception:  # noqa: BLE001 - any failure means "not healthy"
        logging.getLogger("findit.errors").exception("Health check database failure")
        database = "error"
    healthy = database == "ok"
    return JsonResponse({"status": "ok" if healthy else "error", "database": database}, status=200 if healthy else 503)
