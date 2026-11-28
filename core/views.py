import logging
import os
import re
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.db.models.functions import Coalesce, TruncDate
from django.utils.dateparse import parse_date
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from .forms import (
    AdminAccountForm, CaptchaOnlyForm, CategoryForm, ClaimAnswerForm, CloseReasonForm, CommentForm,
    FindItLoginForm, FindItPasswordChangeForm, GeneralReportForm, IdReviewDecisionForm, IdReviewForm, ItemPostForm,
    ModeratorDecisionForm, ProfileForm, QuestionTemplateForm, ReportBlockForm, ReportForm, ReportReviewForm,
    SignupForm, StaffAccountForm, StatusChangeRequestForm, StudentIdChangeForm, SystemSettingsForm, VerifyCodeForm,
)
from .models import (
    OPEN_REPORT_STATUSES, AbuseReport, Category, ChatMessage, ChatQuestion, ClaimAnswer, ClaimApplication, Comment,
    Conversation, GeneralReport, GuardhouseIntake, InAppNotification, ItemPost, ModeratorVerification,
    ModeratorVerificationEvent, PostShare, PostStatusEvent, Profile, QuestionTemplate, ReportStatus, StaffAuditLog,
    StatusChangeRequest, SystemSettings, TurnInTicket, VerificationQuestion,
    IdReviewCase, StudentIdRecord, TestEmail, UserBlock, ChatAttachment,
)
from .mail import test_inbox_enabled
from .verification import (
    ReviewLimitError, block_user, blocked_between, check_code, change_student_id, claim_limit_message,
    code_send_wait, decide_id_review, distinct_student_ids, has_relationship, id_review_block_reason,
    locked_holder, open_id_review, posting_limit_message, send_verification_code, unblock_user, withdraw_id_review,
    welcome_new_account, would_be_flagged,
)
from .matching import find_possible_matches
from .security import clear_login_failures, client_ip, is_own_site_path, login_is_locked, record_login_failure
from .permissions import (
    can_review_private_chats, can_review_reports, is_admin, is_developer, is_staff_or_admin, is_unverified_student,
    role_of,
)
from .services import (
    archive_post, audit, close_claim, close_post, confirm_claimed,
    answer_chat_question, apply_post_questions, approve_claim, ask_chat_questions, can_decide_claim,
    chat_questions_ready, chat_roles, claim_counts, create_claim_conversation, create_lost_post_conversation,
    current_round_questions, decline_claim, notify_user, reapply_status, record_status, reopen_lost_report,
    request_guardhouse, request_status_change, return_to_claimant, review_status_change, ticket_for,
    turn_over_to_guardhouse,
    ModeratorTransitionError, change_moderator_verification, record_report_submission,
    review_report_status, revoke_moderator_if_not_staff,
)

User = get_user_model()


from .auth import STUDENT_ID_PATTERN  # noqa: E402  (BUG-024 sign-in hint)


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
        if STUDENT_ID_PATTERN.fullmatch(username.strip()):
            # BUG-024: the team typed a Student ID on new (not yet verified) accounts and only saw
            # "Sign-in failed". Shown for every Student ID, so it does not reveal whether an account exists.
            messages.error(request, "Sign-in failed. A Student ID only works after your email is verified, "
                                    "so sign in with your email address instead.")
        else:
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
            wants_review = form.wants_id_review
            user = form.save()
            login(request, user, backend="core.auth.FindItBackend")
            welcome_new_account(user)
            if wants_review:
                request.session["id_review_student_id"] = form.cleaned_data["student_id"]
                messages.success(request, "Your account was created without a Student ID. Send the ID review below.")
                return redirect("id-review-new")
            messages.success(
                request,
                "Your student account was created and you are now signed in. Sign in next time with your email. "
                "Check Updates to verify your email (optional).",
            )
            return redirect(_safe_next(request))
        messages.error(request, "Your account was not created. Fix the highlighted fields and try again.")
    return render(request, "core/signup.html", {"form": form})


@never_cache
@login_required
def my_profile(request):
    user = User.objects.select_related("profile").get(pk=request.user.pk)
    profile = user.profile
    return render(request, "core/profile.html", {
        "profile_user": user, "profile": profile,
        "id_cases": IdReviewCase.objects.filter(requester=user).order_by("-created_at")[:5],
        "id_count": distinct_student_ids(user),
        "blocked_count": UserBlock.objects.filter(blocker=user).count(),
        "locked_by_other": bool(profile.student_id and not profile.student_id_locked
                                and locked_holder(profile.student_id, exclude_user=user)),
    })


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
            if getattr(form, "verification_removed", False):
                messages.info(request, "Your email changed, so verify the new email to get ✔ Verified back.")
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


def _parse_filter_date(value):
    """Session 3: a date from a YYYY-MM-DD query value, or None if blank or invalid."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return parse_date(value)
    except ValueError:
        return None


@login_required
def home(request):
    posts = (
        ItemPost.objects.filter(is_archived=False)
        .select_related("author", "author__profile", "category")
        .prefetch_related("photos")
    )
    q = request.GET.get("q", "").strip()
    post_type = request.GET.get("type", "").strip()
    status = request.GET.get("status", "").strip()
    category = request.GET.get("category", "").strip()
    # Session 1 location filter: dormant until settings.FINDIT_LOCATION_ENABLED is turned on.
    location_enabled = getattr(settings, "FINDIT_LOCATION_ENABLED", False)
    location = request.GET.get("location", "").strip()[:120] if location_enabled else ""
    if q:
        text_match = Q(title__icontains=q) | Q(description__icontains=q) | Q(category__name__icontains=q)
        if location_enabled:
            text_match |= Q(location__icontains=q)
        posts = posts.filter(
            text_match
        )
    if post_type in {ItemPost.Type.LOST, ItemPost.Type.FOUND}:
        posts = posts.filter(post_type=post_type)
    if status in dict(ItemPost.Status.choices):
        posts = posts.filter(status=status)
    if category.isdigit():
        posts = posts.filter(category_id=int(category))
    else:
        category = ""
    if location:
        posts = posts.filter(location__icontains=location)
    date_from = _parse_filter_date(request.GET.get("date_from"))
    date_to = _parse_filter_date(request.GET.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    if date_from or date_to:
        # Session 3: the item date is the approximate date; posts without one use the day they were posted.
        posts = posts.annotate(item_date=Coalesce("approximate_date", TruncDate("created_at")))
        if date_from:
            posts = posts.filter(item_date__gte=date_from)
        if date_to:
            posts = posts.filter(item_date__lte=date_to)
    page_obj = _paginate(request, posts, 24)  # session 1: pagination
    # v2.0.0 dashboard tiles (read-only counts for the signed-in person).
    dashboard = {
        "active_posts": ItemPost.objects.filter(author=request.user, is_archived=False).exclude(
            status__in=[ItemPost.Status.CLOSED, ItemPost.Status.CLAIMED, ItemPost.Status.RETURNED]
        ).count(),
        "open_claims": ClaimApplication.objects.filter(
            claimant=request.user, status__in=[ClaimApplication.Status.SUBMITTED, ClaimApplication.Status.APPROVED]
        ).count(),
    }
    return render(request, "core/home.html", {
        "dashboard": dashboard,
        "posts": page_obj,
        "page_obj": page_obj,
        "querystring": _querystring_without_page(request),
        "q": q,
        "selected_type": post_type,
        "selected_status": status,
        "selected_category": category,
        "status_choices": ItemPost.Status.choices,
        "categories": Category.objects.filter(is_active=True),
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "filters_active": bool(q or post_type or status or category or date_from or date_to or location),
        "location": location,
        "location_enabled": location_enabled,
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
        claim = post.claims.filter(claimant=user, status__in=ClaimApplication.ACTIVE_STATUSES).first()
        if claim:
            try:
                return claim.conversation
            except Conversation.DoesNotExist:
                return create_claim_conversation(claim)
    return create_lost_post_conversation(post, user)


def post_detail(request, post_id):
    post = get_object_or_404(
        ItemPost.objects.select_related("author", "category").prefetch_related("photos"), pk=post_id
    )
    if not _can_view_archived(post, request.user):
        raise Http404
    if not request.user.is_authenticated and not post.is_shared:
        # Not shared yet: the link only works for signed-in users.
        from urllib.parse import quote
        return redirect(f"{reverse('login')}?next={quote(request.get_full_path())}")

    resume = request.GET.get("resume", "")
    is_blocked = request.user.is_authenticated and blocked_between(request.user, post.author)
    if request.user.is_authenticated and resume == "message" and request.user.pk != post.author_id and is_blocked:
        messages.error(request, "You cannot message this person because one of you blocked the other.")
        resume = ""
    if request.user.is_authenticated and resume == "message" and request.user.pk != post.author_id:
        conversation = _conversation_for_post(post, request.user)
        if conversation:
            return redirect("chat-room", conversation_id=conversation.pk)
        messages.info(request, "This listing is no longer accepting new online conversations.")

    comments = post.comments.filter(moderation_status=Comment.Moderation.VISIBLE).select_related("author")
    user_claim = None
    latest_claim = None
    claim_form = None
    reapply_from = None
    if request.user.is_authenticated and post.post_type == ItemPost.Type.FOUND:
        mine = post.claims.filter(claimant=request.user).order_by("-submitted_at")
        user_claim = mine.filter(status__in=ClaimApplication.ACTIVE_STATUSES).first()
        latest_claim = user_claim or mine.first()
        if post.can_accept_claims and request.user.pk != post.author_id and not user_claim and not is_blocked:
            can_apply, reapply_from = reapply_status(post, request.user)
            if can_apply:
                saved = request.session.get("claim_form_data") or {}
                data = saved.get("data") if saved.get("post") == str(post.pk) else None
                claim_form = ClaimAnswerForm(data, questions=post.verification_questions.all())

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
        applications = list(post.claims.select_related("claimant", "finder").order_by("-submitted_at"))
    elif request.user.is_authenticated and post.post_type == ItemPost.Type.LOST:
        applications = list(post.claims.filter(finder=request.user).select_related("claimant", "finder"))
    for application in applications:
        application.can_decide = can_decide_claim(request.user, application)
        application.rank = application.approval_rank
    show_matches = (
        can_manage
        and post.post_type == ItemPost.Type.LOST
        and not post.is_archived
        and post.status not in {ItemPost.Status.CLAIMED, ItemPost.Status.CLOSED, ItemPost.Status.RETURNED}
    )
    possible_matches = find_possible_matches(post) if show_matches else []
    my_ticket = None
    if request.user.is_authenticated:
        my_ticket = post.turn_in_tickets.filter(finder=request.user).first()
    panel_conversation = None
    if request.user.is_authenticated and request.user.pk != post.author_id:
        if post.post_type == ItemPost.Type.FOUND and latest_claim is not None:
            panel_conversation = getattr(latest_claim, "conversation", None)
        if panel_conversation is None:  # LOST post, or a FOUND post's "Message poster" chat (DES-007)
            panel_conversation = post.conversations.filter(initiator=request.user, claim__isnull=True).first()
    # BUG-023: the author sees the chats about this post (or why there are none yet).
    author_chats = []
    if request.user.is_authenticated and request.user.pk == post.author_id:
        author_chats = list(
            post.conversations.filter(Q(initiator=request.user) | Q(recipient=request.user))
            .select_related("initiator", "recipient").order_by("-updated_at")[:10]
        )
        for chat in author_chats:
            chat.other_person = chat.initiator if chat.recipient_id == request.user.pk else chat.recipient
    if can_moderate and post.status == ItemPost.Status.TURNED_OVER:
        account_list = User.objects.filter(profile__role=Profile.Role.STUDENT, is_active=True).order_by("first_name")
    for application in applications:
        application.claimant_unverified = is_unverified_student(application.claimant)
    viewer_is_student_other = request.user.is_authenticated and request.user.pk != post.author_id
    context = {
        "chat_char_limit": (
            SystemSettings.current().unverified_chat_max_chars
            if request.user.is_authenticated and is_unverified_student(request.user) else 2000
        ),
        "is_blocked": is_blocked,
        "unverified_warning": viewer_is_student_other and is_unverified_student(post.author),
        "author_verified": post.author.profile.is_verified,
        "can_block_author": bool(
            viewer_is_student_other and not is_blocked and role_of(post.author) == Profile.Role.STUDENT
        ),
        "post": post,
        "comments": comments,
        "comment_form": CommentForm() if request.user.is_authenticated else None,
        "claim_form": claim_form,
        "user_claim": user_claim,
        "latest_claim": latest_claim,
        "reapply_from": reapply_from,
        "claim_counts": claim_counts(post),
        "can_manage": can_manage,
        "can_edit": can_edit,
        "can_moderate": can_moderate,
        "can_interact": can_interact,
        "applications": applications,
        "account_list": account_list,
        "resume": resume,
        "direct_link": request.build_absolute_uri(reverse("post-detail", args=[post.pk])),
        "shared_by_author": post.shares.filter(user_id=post.author_id).exists(),
        "share_count": post.shares.count(),
        "panel_conversation": panel_conversation,
        "author_chats": author_chats,
        "show_matches": show_matches,
        "possible_matches": possible_matches,
        "my_ticket": my_ticket,
        "my_ticket_qr": _qr_svg(request, my_ticket) if my_ticket else "",
        "intake": getattr(post, "intake", None) if post.status == ItemPost.Status.TURNED_OVER else None,
        "is_ticket_finder": bool(my_ticket),
        "status_request_form": StatusChangeRequestForm() if my_ticket and post.status == ItemPost.Status.TURNED_OVER else None,
        "my_pending_request": post.status_requests.filter(requester=request.user, decision="PENDING").first() if request.user.is_authenticated else None,
        "pending_status_requests": post.status_requests.filter(decision="PENDING").select_related("requester") if can_moderate else [],
        "panel_can_send": bool(
            panel_conversation and panel_conversation.includes(request.user)
            and not panel_conversation.is_closed and not panel_conversation.is_paused
        ),
        # BUG-008: location is dormant; only show it when the feature is turned on.
        "location_enabled": getattr(settings, "FINDIT_LOCATION_ENABLED", False),
    }
    return render(request, "core/post_detail.html", context)


def _question_options(form):
    """Question bank rows for the picker, with selection state and category ids."""
    raw = form["questions"].value() or []
    selected = {str(v) for v in raw}
    options = []
    for template in form.fields["questions"].queryset:
        options.append({
            "template": template,
            "selected": str(template.pk) in selected,
            "category_ids": " ".join(str(c.pk) for c in template.categories.all()),
        })
    return options


def _posts_per_hour():
    return SystemSettings.current().posts_per_hour or 10


def _posting_rate_limited(user):
    since = timezone.now() - timedelta(hours=1)
    return ItemPost.objects.filter(author=user, created_at__gte=since).count() >= _posts_per_hour()


@login_required
def create_post(request):
    # v2.0.0: "Report lost item" / "Report found item" open the form with the type already chosen.
    preset_type = request.GET.get("type", "")
    initial = {"post_type": preset_type} if preset_type in {ItemPost.Type.LOST, ItemPost.Type.FOUND} else None
    form = ItemPostForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST":
        daily_limit = posting_limit_message(request.user)
        if daily_limit:
            messages.error(request, daily_limit)
            return redirect("my-posts")
        if _posting_rate_limited(request.user):
            messages.error(request, f"You can create up to {_posts_per_hour()} posts per hour. Please try again later.")
            return redirect("my-posts")
        if form.is_valid():
            with transaction.atomic():
                post = form.save(commit=False)
                post.author = request.user
                post.save()
                form.save_photos(post)
                apply_post_questions(post, form.picked_questions())
                PostStatusEvent.objects.create(
                    post=post,
                    previous_status="",
                    new_status=post.status,
                    actor=request.user,
                    note="Listing created.",
                )
            messages.success(request, "Your post is live.")
            if post.post_type == ItemPost.Type.LOST:
                match_count = len(find_possible_matches(post))
                if match_count:
                    messages.info(
                        request,
                        f"We found {match_count} possible match{'es' if match_count != 1 else ''} among found items. "
                        "See Possible matches on your post.",
                    )
            return redirect("post-detail", post_id=post.pk)
    return render(request, "core/post_form.html", {
        "form": form, "captcha_form": CaptchaOnlyForm(), "question_options": _question_options(form),
    })


@login_required
def edit_post(request, post_id):
    post = get_object_or_404(ItemPost, pk=post_id)
    if post.author_id != request.user.pk and not is_admin(request.user):
        return HttpResponseForbidden("Only the post author or an administrator may edit this post.")
    form = ItemPostForm(request.POST or None, request.FILES or None, instance=post)
    if post.claims.exists():
        form.fields["post_type"].disabled = True
        form.fields["questions"].disabled = True
        form.fields["questions"].help_text = "Locked after a claim is submitted so earlier answers stay attached to their questions."
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            updated = form.save()
            form.save_photos(updated)
            if not post.claims.exists():
                apply_post_questions(updated, form.picked_questions())
        messages.success(request, "Your post was updated.")
        return redirect("post-detail", post_id=post.pk)
    return render(request, "core/post_form.html", {
        "form": form, "editing": True, "post": post, "captcha_form": CaptchaOnlyForm(),
        "question_options": _question_options(form), "questions_locked": post.claims.exists(),
        "locked_questions": post.verification_questions.all(),
    })


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
    if post.claims.filter(claimant=request.user, status__in=ClaimApplication.ACTIVE_STATUSES).exists():
        messages.info(request, "You already have a claim for this item.")
        return redirect("my-claims")
    if blocked_between(request.user, post.author):
        messages.error(request, "You cannot claim this item because one of you blocked the other.")
        return redirect("post-detail", post_id=post.pk)
    limit = claim_limit_message(request.user)
    if limit:
        messages.error(request, limit)
        return redirect("my-claims")
    can_apply, reapply_from = reapply_status(post, request.user)
    if not can_apply:
        messages.error(request, "You have already used your one re-application for this item.")
        return redirect("my-claims")

    questions = list(post.verification_questions.order_by("order"))
    if len(questions) < 3:
        messages.error(request, "This post is missing its private ownership questions. Please contact staff.")
        return redirect("post-detail", post_id=post.pk)
    form = ClaimAnswerForm(request.POST, questions=questions)
    if not form.is_valid():
        request.session["claim_form_data"] = {"post": str(post.pk), "data": request.POST.dict()}
        messages.error(request, "Please answer every question and write a description of the item.")
        return redirect(f"{reverse('post-detail', args=[post.pk])}?resume=claim#claim-form")
    request.session.pop("claim_form_data", None)

    with transaction.atomic():
        claim = ClaimApplication.objects.create(
            post=post, claimant=request.user, description=form.cleaned_data["description"].strip(),
            reapply_of=reapply_from,
        )
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
    if blocked_between(request.user, post.author):
        messages.error(request, "You cannot comment here because one of you blocked the other.")
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
    posts = (
        ItemPost.objects.filter(author=request.user)
        .select_related("category").prefetch_related("photos", "claims")
        .order_by("-created_at")
    )
    return render(request, "core/my_posts.html", {"posts": posts})


@never_cache
@login_required
def my_claims(request):
    claims = list(
        ClaimApplication.objects.filter(claimant=request.user)
        .select_related("post", "post__author", "post__category", "finder", "conversation")
        .prefetch_related("post__photos")
    )
    for claim in claims:
        claim.rank = claim.approval_rank
        if claim.status == ClaimApplication.Status.DECLINED:
            can_apply, linked = reapply_status(claim.post, request.user)
            claim.can_reapply = can_apply and linked is not None and linked.pk == claim.pk and claim.post.can_accept_claims
            if claim.is_lost_report:
                claim.can_reapply = not claim.reapply_of_id and not claim.reapplications.exists()
    active = [c for c in claims if c.status in ClaimApplication.ACTIVE_STATUSES]
    declined = [c for c in claims if c.status == ClaimApplication.Status.DECLINED]
    history = [c for c in claims if c not in active and c not in declined]
    return render(request, "core/my_claims.html", {"active": active, "declined": declined, "history": history})


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
        "unverified_warning": (not is_claimant) and is_unverified_student(claim.claimant),
        "can_block_claimant": is_finder and not blocked_between(request.user, claim.claimant),
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
    """Finder: "I'm bringing it to the guard house" (status unchanged until staff
    receive it). Staff: confirm it was received, from the post page."""
    post = get_object_or_404(ItemPost, pk=post_id)
    if is_staff_or_admin(request.user):
        handed_user = None
        if request.POST.get("handed_over_by") == "finder":
            ticket = post.turn_in_tickets.filter(requested_at__isnull=False).first() or post.turn_in_tickets.first()
            handed_user = ticket.finder if ticket else post.author
        try:
            turn_over_to_guardhouse(
                post, request.user, handed_over_by_user=handed_user,
                handed_over_by_name=request.POST.get("handed_over_by_name", "").strip(),
                method=GuardhouseIntake.Method.MANUAL,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Received at the guard house. Claims stay open; approved claimants pick it up in person.")
        return redirect("post-detail", post_id=post.pk)
    ticket = post.turn_in_tickets.filter(finder=request.user).first()
    if ticket is None:
        return HttpResponseForbidden("Only the finder can bring this item to the guard house.")
    try:
        request_guardhouse(ticket, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Staff were told you're on your way. Show turn-in code {ticket.code} (or its QR) at the guard house.")
    return redirect("post-detail", post_id=post.pk)


@login_required
@require_POST
def lost_guardhouse_view(request, conversation_id):
    """A finder on a LOST post chooses to bring the item to the guard house."""
    conversation = get_object_or_404(Conversation.objects.select_related("post", "claim"), pk=conversation_id)
    post = conversation.post
    finder, _owner = chat_roles(conversation)
    if post.post_type != ItemPost.Type.LOST or finder is None or finder.pk != request.user.pk:
        return HttpResponseForbidden("Only the finder in this chat can do this.")
    ticket = ticket_for(post, request.user, conversation.claim)
    try:
        request_guardhouse(ticket, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Staff were told you're on your way. Show turn-in code {ticket.code} (or its QR) at the guard house.")
        notify_user(post.author, post, "A finder is bringing your item to the guard house.", conversation.claim, priority=True)
    return redirect("chat-room", conversation_id=conversation.pk)


def _turn_in_url(request, ticket):
    from django.conf import settings as django_settings
    path = reverse("turn-in", args=[ticket.code])
    base = getattr(django_settings, "FINDIT_SITE_URL", "")
    return f"{base}{path}" if base else request.build_absolute_uri(path)


def _qr_svg(request, ticket):
    import segno
    return segno.make(_turn_in_url(request, ticket), error="m").svg_inline(scale=4, dark="#17344f", light="#ffffff")


@login_required
def ticket_qr(request, code):
    ticket = get_object_or_404(TurnInTicket, code=code.upper())
    if request.user.pk != ticket.finder_id and not is_staff_or_admin(request.user):
        return HttpResponseForbidden("This QR code is private to the finder and staff.")
    from django.http import HttpResponse
    import segno
    import io
    buffer = io.BytesIO()
    segno.make(_turn_in_url(request, ticket), error="m").save(
        buffer, kind="svg", scale=8, dark="#17344f", border=4,
    )
    response = HttpResponse(buffer.getvalue(), content_type="image/svg+xml")
    response["Content-Disposition"] = f'attachment; filename="find-it-turn-in-{ticket.code}.svg"'
    return response


@login_required
def staff_scan(request):
    if not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Staff access is required.")
    return render(request, "core/staff_scan.html")


def turn_in_view(request, code):
    """Where a scanned QR (or a typed code) lands.

    The QR is a plain link anyone can open. Non-staff (and signed-out people)
    only see a basic info page. Signed-in staff/admin also get the one-tap
    'Confirm turned in' prompt; the server re-checks their role on every confirm.
    """
    is_staff_user = request.user.is_authenticated and is_staff_or_admin(request.user)
    ticket = TurnInTicket.objects.select_related("post", "post__category", "finder").filter(code=code.strip().upper()).first()
    if ticket is None:
        return render(request, "core/turn_in_confirm.html", {
            "code": code.strip().upper(), "ticket": None, "is_staff_user": is_staff_user,
        }, status=404)
    post = ticket.post
    if not is_staff_user:
        if request.method == "POST":
            return HttpResponseForbidden("Only signed-in guard-house staff can confirm a turn-in.")
        return render(request, "core/turn_in_public.html", {"ticket": ticket, "post": post})
    if request.method == "POST":
        method = GuardhouseIntake.Method.QR if request.POST.get("via") == "qr" else GuardhouseIntake.Method.CODE
        handed_user = ticket.finder if request.POST.get("handed_over_by") != "other" else None
        try:
            turn_over_to_guardhouse(
                post, request.user, ticket=ticket, handed_over_by_user=handed_user,
                handed_over_by_name=request.POST.get("handed_over_by_name", "").strip(), method=method,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Turn-in {ticket.code} confirmed. The item is now listed as at the guard house.")
        return redirect("turn-in", code=ticket.code)
    return render(request, "core/turn_in_confirm.html", {
        "code": ticket.code, "ticket": ticket, "post": post,
        "intake": getattr(post, "intake", None), "via": request.GET.get("via", "code"),
    })


@login_required
def walk_in_view(request):
    """Staff post an item someone handed in directly at the guard house."""
    if not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Staff access is required.")
    data = request.POST.copy() if request.method == "POST" else None
    if data is not None:
        data["post_type"] = ItemPost.Type.FOUND
    form = ItemPostForm(data, request.FILES or None, initial={"post_type": ItemPost.Type.FOUND})
    form.fields["post_type"].disabled = True
    form.fields["post_type"].initial = ItemPost.Type.FOUND
    handed_name = (request.POST.get("handed_over_by_name") or "").strip() if request.method == "POST" else ""
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            post = form.save(commit=False)
            post.author = request.user
            post.post_type = ItemPost.Type.FOUND
            post.save()
            form.save_photos(post)
            apply_post_questions(post, form.picked_questions())
            PostStatusEvent.objects.create(post=post, previous_status="", new_status=post.status, actor=request.user, note="Walk-in item posted by staff.")
            turn_over_to_guardhouse(post, request.user, handed_over_by_name=handed_name or "Walk-in (name not given)", method=GuardhouseIntake.Method.WALK_IN)
        messages.success(request, "Walk-in item posted and recorded as at the guard house.")
        return redirect("post-detail", post_id=post.pk)
    return render(request, "core/post_form.html", {
        "form": form, "walk_in": True, "handed_over_by_name": handed_name,
        "captcha_form": CaptchaOnlyForm(), "question_options": _question_options(form),
    })


@login_required
@require_POST
def status_request_view(request, post_id):
    post = get_object_or_404(ItemPost, pk=post_id)
    form = StatusChangeRequestForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Choose a request and write a reason. " + " ".join(e for errs in form.errors.values() for e in errs))
        return redirect("post-detail", post_id=post.pk)
    try:
        request_status_change(post, request.user, form.cleaned_data["requested_status"], form.cleaned_data["reason"], form.cleaned_data.get("photo"))
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Request sent to guard-house staff.")
    return redirect("post-detail", post_id=post.pk)


@login_required
@require_POST
def review_status_request_view(request, request_id):
    if not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Staff access is required.")
    row = get_object_or_404(StatusChangeRequest, pk=request_id)
    review_status_change(row, request.user, request.POST.get("decision") == "approve", request.POST.get("note", ""))
    messages.success(request, "Status request reviewed.")
    return redirect(_safe_next(request, "staff-dashboard"))


@login_required
@require_POST
def returned_view(request, post_id):
    post = get_object_or_404(ItemPost, pk=post_id)
    claim_id = request.POST.get("claim_id", "")
    if not _is_uuid(claim_id):
        raise Http404  # BUG-002: a damaged form value used to crash the page
    claim = get_object_or_404(ClaimApplication.objects.select_related("post", "finder"), pk=claim_id, post=post)
    if request.user.pk != claim.finder_user.pk:
        return HttpResponseForbidden("Only the finder can record a return.")
    try:
        return_to_claimant(post, claim, request.user)
    except (ValueError, PermissionError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Return recorded. The claimant can confirm receipt.")
    return redirect("post-detail", post_id=post.pk)


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
        witnessed = True
        if request.POST.get("claim_id"):
            if not _is_uuid(request.POST.get("claim_id")):
                raise Http404
            claim = get_object_or_404(ClaimApplication, pk=request.POST.get("claim_id"), post=post, status=ClaimApplication.Status.APPROVED)
        else:
            claim = None
            recipient_id = request.POST.get("recipient_id", "")
            if not recipient_id.isdigit():
                messages.error(request, "Choose the student who collected the item.")
                return redirect("post-detail", post_id=post.pk)
            recipient = get_object_or_404(
                User, pk=int(recipient_id), profile__role=Profile.Role.STUDENT
            )
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
    if post.status == ItemPost.Status.TURNED_OVER and not is_staff_or_admin(request.user):
        messages.error(request, "The item is at the guard house. Send a status request to staff instead.")
        return redirect("post-detail", post_id=post.pk)
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
    if post.status == ItemPost.Status.TURNED_OVER and not is_staff_or_admin(request.user):
        messages.error(request, "The item is at the guard house. Send a status request to staff instead.")
        return redirect("post-detail", post_id=post.pk)
    archive_post(post, request.user)
    messages.success(request, "The post was removed from active listings. Its claims and chats remain in history.")
    return redirect("my-posts" if request.user.pk == post.author_id else "staff-dashboard")




def _message_json(message):
    from .chat_media import attachment_json
    return {
        "id": message.pk, "sender": message.sender.first_name or message.sender.username,
        "sender_id": message.sender_id, "text": message.text, "sent_at": message.sent_at.isoformat(),
        "client_id": message.client_id,
        "attachment": attachment_json(getattr(message, "attachment", None)) if _has_attachment(message) else None,
    }


def _media_limits(user, conversation):
    from . import chat_media
    limits = chat_media.limits_for(user)
    left = None
    if limits["per_chat"] is not None:
        used = ChatAttachment.objects.filter(conversation=conversation, uploader=user).exclude(
            status=ChatAttachment.Status.FAILED).count()
        left = max(0, limits["per_chat"] - used)
    return {"photo_mb": limits["photo_bytes"] // chat_media.MB, "video_mb": limits["video_bytes"] // chat_media.MB,
            "video_seconds": limits["video_seconds"], "left": left}


def _has_attachment(message):
    try:
        return message.attachment is not None
    except ChatAttachment.DoesNotExist:
        return False


def _chat_reader(request, conversation):
    return conversation.includes(request.user) or can_review_private_chats(request.user)


@login_required
@require_POST
def chat_upload(request, conversation_id):
    """CHG-006: receive one photo or video for a chat. Re-encoded before anyone sees it."""
    from . import chat_media
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    if not conversation.includes(request.user):
        return JsonResponse({"error": "Only the people in this chat can send files."}, status=403)
    limits = chat_media.limits_for(request.user)
    biggest = max(limits["photo_bytes"], limits["video_bytes"])
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length > biggest + 512 * 1024:
        return JsonResponse({"error": f"Files can be up to {biggest // chat_media.MB} MB."}, status=413)
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse({"error": "Choose a photo or video."}, status=400)
    try:
        attachment = chat_media.accept_upload(conversation, request.user, uploaded, request.POST.get("client_id", ""))
    except chat_media.MediaRefused as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(_attachment_status(attachment))


def _attachment_status(attachment):
    from .chat_media import attachment_json
    return {
        "client_id": attachment.client_id, "status": attachment.status, "error": attachment.error,
        "message_id": attachment.message_id, "attachment": attachment_json(attachment),
    }


@never_cache
@login_required
def chat_upload_status(request, conversation_id):
    """Status of my uploads in this chat: ?ids=a,b,c (used after a reload or when the live push was missed)."""
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    if not conversation.includes(request.user):
        return JsonResponse({"error": "Not your chat."}, status=403)
    ids = [i[:64] for i in request.GET.get("ids", "").split(",") if i][:20]
    rows = ChatAttachment.objects.filter(conversation=conversation, uploader=request.user, client_id__in=ids)
    return JsonResponse({"uploads": [_attachment_status(a) for a in rows]})


def chat_media_file(request, attachment_id, part):
    """Private chat photo/video. Only for the two people in the chat and authorized reviewers.
    Supports byte ranges so videos can be skipped forward without downloading everything."""
    if not request.user.is_authenticated:
        raise Http404
    attachment = get_object_or_404(ChatAttachment.objects.select_related("conversation"), pk=attachment_id)
    if not _chat_reader(request, attachment.conversation) or attachment.status != ChatAttachment.Status.READY:
        raise Http404
    field = attachment.preview if part == "preview" else attachment.file
    if not field:
        raise Http404
    content_type = "image/jpeg" if (part == "preview" or attachment.kind == ChatAttachment.Kind.PHOTO) else "video/mp4"
    try:
        size = field.size
        handle = field.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404
    status, start, end = 200, 0, size - 1
    match = re.match(r"bytes=(\d*)-(\d*)$", request.headers.get("Range", ""))
    if match and size:
        if match.group(1):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else size - 1
        elif match.group(2):
            start = max(0, size - int(match.group(2)))
        end = min(end, size - 1)
        if start > end:
            handle.close()
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        status = 206
    handle.seek(start)
    length = end - start + 1

    def stream(remaining=length, chunk=64 * 1024):
        try:
            while remaining > 0:
                data = handle.read(min(chunk, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data
        finally:
            handle.close()

    response = StreamingHttpResponse(stream(), status=status, content_type=content_type)
    response["Content-Length"] = str(length)
    response["Accept-Ranges"] = "bytes"
    if status == 206:
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Content-Disposition"] = "inline"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=86400"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@never_cache
@login_required
def chat_messages_json(request, conversation_id):
    """CHG-005: chat history pages sized by bytes, plus search inside the conversation.
    ?latest=1 · ?before=ID · ?after=ID · ?around=ID · ?q=text. Rate-limited per person."""
    from . import chat_history
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    if not (conversation.includes(request.user) or can_review_private_chats(request.user)):
        return HttpResponseForbidden("This conversation is private to its participants and authorized reviewers.")
    rows = conversation.messages.select_related("sender", "attachment")
    get = request.GET
    if "q" in get:
        if chat_history.over_rate_limit(request.user, "search", chat_history.SEARCHES_PER_MINUTE):
            return JsonResponse({"error": "Too many searches. Wait a moment and try again."}, status=429)
        query = get.get("q", "")
        return JsonResponse({
            "results": chat_history.search(rows, query),
            "too_short": len(query.strip()) < chat_history.SEARCH_MIN_CHARS,
        })
    if chat_history.over_rate_limit(request.user, "page", chat_history.PAGES_PER_MINUTE):
        return JsonResponse({"error": "Loading too fast. Wait a moment."}, status=429)
    payload = {"has_older": False, "has_newer": False}
    if get.get("around", "").isdigit():
        found = chat_history.around_page(rows, int(get["around"]))
        if found is None:
            return JsonResponse({"error": "That message is no longer in this chat."}, status=404)
        page, payload["has_older"], payload["has_newer"] = found
    elif get.get("before", "").isdigit():
        page, payload["has_older"] = chat_history.older_page(rows, int(get["before"]))
        payload["has_newer"] = True
    elif get.get("after", "").isdigit():
        page, payload["has_newer"] = chat_history.newer_page(rows, int(get["after"]))
        payload["has_older"] = True
    elif get.get("latest") == "1":
        page, payload["has_older"] = chat_history.latest_page(rows)
    else:
        return JsonResponse({"messages": [], **payload})
    payload["messages"] = [_message_json(m) for m in page]
    payload["more"] = payload["has_newer"] if "after" in get else payload["has_older"]  # older clients
    return JsonResponse(payload)


def _is_embedded(request):
    """DES-007: the chat page is being shown inside the chat window over a post page.
    Browsers say so with Sec-Fetch-Dest: iframe (also after a form inside the window redirects);
    ?embed=1 is the fallback for older browsers."""
    return request.GET.get("embed") == "1" or request.headers.get("Sec-Fetch-Dest") == "iframe"


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
    # PERF-001 / CHG-005: only the newest ~8 KB of messages are put in the page;
    # older ones load by themselves when the reader scrolls up.
    from .chat_history import latest_page
    messages_qs, has_older = latest_page(conversation.messages.select_related("sender", "attachment"))
    asker, answerer = chat_roles(conversation)
    claim = conversation.claim
    questions = list(conversation.questions.all())
    InAppNotification.objects.filter(
        recipient=request.user, post=conversation.post, is_priority=True, read_at__isnull=True,
    ).update(read_at=timezone.now())
    can_send = conversation.includes(request.user) and not conversation.is_closed and not conversation.is_paused
    is_asker = bool(asker and asker.pk == request.user.pk)
    is_answerer = bool(answerer and answerer.pk == request.user.pk)
    question_bank = []
    round_count = 0
    if is_asker and can_send and (claim is None or claim.status in {"SUBMITTED", "APPROVED"}):
        round_count = current_round_questions(conversation).count()  # CHG-011: also counts chats without a claim
        if round_count < 5:
            question_bank = list(QuestionTemplate.objects.filter(is_active=True).prefetch_related("categories"))
    can_decide = bool(claim and can_decide_claim(request.user, claim))
    lost_ticket = None
    if is_asker and conversation.post.post_type == ItemPost.Type.LOST:
        lost_ticket = conversation.post.turn_in_tickets.filter(finder=request.user).first()
    other = None
    if conversation.includes(request.user):
        other = conversation.recipient if conversation.initiator_id == request.user.pk else conversation.initiator
    embedded = _is_embedded(request)
    return render(request, "core/chat_room.html", {
        "base_template": "core/chat_embed_base.html" if embedded else "core/base.html",
        "embedded": embedded,
        "other_person": other,
        "unverified_warning": bool(other and is_unverified_student(other)),
        "other_verified": bool(other and other.profile.is_verified),
        "can_block_other": bool(
            other and role_of(other) == Profile.Role.STUDENT and not blocked_between(request.user, other)
        ),
        "is_unverified_sender": is_unverified_student(request.user),
        "chat_char_limit": SystemSettings.current().unverified_chat_max_chars if is_unverified_student(request.user) else 2000,
        "media_limits": _media_limits(request.user, conversation),
        "lost_ticket": lost_ticket,
        "lost_ticket_qr": _qr_svg(request, lost_ticket) if lost_ticket else "",
        "conversation": conversation,
        "chat_messages": messages_qs,
        "has_older_messages": has_older,
        "staff_view": staff_view,
        "can_send": can_send,
        "is_reviewer": reviewer,
        "can_report": conversation.includes(request.user) or reviewer,
        "questions": questions,
        "is_asker": is_asker,
        "is_answerer": is_answerer,
        "question_bank": question_bank,
        "questions_left": 5 - round_count,
        "claim": claim,
        "claim_rank": claim.approval_rank if claim else None,
        "can_decide": can_decide,
        "lost_ready": chat_questions_ready(claim) if claim and claim.is_lost_report else True,
        "can_reverify": bool(
            claim and claim.is_lost_report and claim.status == "DECLINED" and request.user.pk == claim.claimant_id
            and not claim.reapply_of_id and not claim.reapplications.exists()
        ),
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
    open_id = request.GET.get("open", "")
    if open_id.isdigit():
        # Tapping a notice marks it read and opens its page (only safe local paths are stored).
        notice = rows.filter(pk=int(open_id)).first()
        if notice:
            if notice.read_at is None:
                notice.read_at = timezone.now()
                notice.save(update_fields=["read_at"])
            if is_own_site_path(notice.link):
                return redirect(notice.link)
            if notice.post_id:
                return redirect("post-detail", post_id=notice.post_id)
        return redirect("notifications")
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
            queryset=ChatMessage.objects.select_related("sender", "attachment").order_by("-sent_at")[:1],
            to_attr="latest_messages",
        )
    )
    return render(request, "core/messages.html", {"conversations": conversations[:100]})


@login_required
def staff_dashboard(request):
    if not is_staff_or_admin(request.user):
        return HttpResponseForbidden("Staff access is required.")
    posts = ItemPost.objects.filter(is_archived=False).select_related("author", "category").annotate(claim_count=Count("claims"))
    conversations = Conversation.objects.select_related("post", "post__category", "initiator", "recipient")[:100]
    reviewer = can_review_reports(request.user)
    return render(request, "core/staff_dashboard.html", {
        "posts": posts[:100],
        "conversations": conversations if reviewer else [],
        "recent_reports": AbuseReport.objects.filter(status__in=OPEN_REPORT_STATUSES).select_related("reporter")[:20] if reviewer else [],
        "open_general_count": GeneralReport.objects.filter(status__in=OPEN_REPORT_STATUSES).count() if reviewer else 0,
        "is_admin": is_admin(request.user),
        "incoming": TurnInTicket.objects.filter(requested_at__isnull=False, received_at__isnull=True)
            .exclude(post__status__in=["TURNED_OVER", "CLAIMED", "CLOSED"]).select_related("post", "post__category", "finder")[:50],
        "at_guardhouse": ItemPost.objects.filter(status=ItemPost.Status.TURNED_OVER).select_related("intake", "category")[:100],
        "status_requests": StatusChangeRequest.objects.filter(decision="PENDING").select_related("post", "post__category", "requester")[:50],
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
    if not is_developer(request.user):
        accounts = accounts.exclude(profile__role=Profile.Role.DEVELOPER)
    q = request.GET.get("q", "").strip()[:80]
    role_filter = request.GET.get("role", "").strip()
    status_filter = request.GET.get("status", "").strip()
    if q:
        accounts = accounts.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
            | Q(profile__student_id__icontains=q)
        )
    if role_filter in dict(Profile.Role.choices):
        accounts = accounts.filter(profile__role=role_filter)
    else:
        role_filter = ""
    if status_filter in {"active", "inactive"}:
        accounts = accounts.filter(is_active=status_filter == "active")
    else:
        status_filter = ""
    # v2.0.0: verification filter (red-flagged accounts, verified / not verified students, ID conflicts).
    verify_filter = request.GET.get("verify", "").strip()
    verify_filters = {
        "flagged": Q(profile__flagged_at__isnull=False),
        "verified": Q(profile__role=Profile.Role.STUDENT, profile__email_verified_at__isnull=False),
        "unverified": Q(profile__role=Profile.Role.STUDENT, profile__email_verified_at__isnull=True),
        "conflict": Q(profile__id_conflict_deadline__isnull=False),
    }
    if verify_filter in verify_filters:
        accounts = accounts.filter(verify_filters[verify_filter])
    else:
        verify_filter = ""
    flagged_accounts = (
        User.objects.filter(profile__flagged_at__isnull=False).select_related("profile").order_by("-profile__flagged_at")
    )
    return render(request, "core/staff_accounts.html", {
        "verify_filter": verify_filter,
        "flagged_accounts": flagged_accounts[:5],
        "flagged_count": flagged_accounts.count(),
        "acting_is_developer": is_developer(request.user),
        "form": form,
        "staff_users": staff_users,
        "page_obj": _paginate(request, accounts, 20),
        "querystring": _querystring_without_page(request),
        "q": q,
        "role_filter": role_filter,
        "status_filter": status_filter,
        "role_choices": [c for c in Profile.Role.choices if c[0] != Profile.Role.DEVELOPER or is_developer(request.user)],
    })


def _account_lock_reason(account, admin_user):
    if account.pk == admin_user.pk:
        return "You cannot change your own role or status."
    if role_of(account) == Profile.Role.DEVELOPER:
        return "The Developer account can only be changed with the create_developer command."
    if role_of(account) == Profile.Role.ADMIN and not is_developer(admin_user):
        return "Only the Developer can change an administrator account."
    return ""


def _is_last_active_admin(account):
    if not (account.is_active and role_of(account) in {Profile.Role.ADMIN, Profile.Role.DEVELOPER}):
        return False
    return not User.objects.filter(
        is_active=True, profile__role__in=[Profile.Role.ADMIN, Profile.Role.DEVELOPER],
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
    if role_of(account) == Profile.Role.DEVELOPER and not is_developer(request.user):
        raise Http404
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
        # v2.0.0: verification details (verified date, locked ID, ID history, conflict deadline, red flag).
        "id_records": StudentIdRecord.objects.filter(user=account),
        "id_cases": IdReviewCase.objects.filter(Q(requester=account) | Q(holder=account)).select_related(
            "requester", "holder").order_by("-created_at")[:10],
        "acting_is_developer": is_developer(request.user),
        "recent_activity": StaffAuditLog.objects.filter(target_type="User", target_id=str(account.pk))[:10],
    })


@login_required
def admin_dashboard(request):
    """Administrator overview. Every number is counted from the database on each visit."""
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    users = User.objects.all()
    admin_q = Q(profile__role__in=[Profile.Role.ADMIN, Profile.Role.DEVELOPER])
    account_counts = users.aggregate(
        total=Count("pk"),
        students=Count("pk", filter=Q(profile__role=Profile.Role.STUDENT)),
        verified_students=Count("pk", filter=Q(profile__role=Profile.Role.STUDENT, profile__email_verified_at__isnull=False)),
        flagged=Count("pk", filter=Q(profile__flagged_at__isnull=False)),
        staff=Count("pk", filter=Q(profile__role=Profile.Role.STAFF)),
        admins=Count("pk", filter=admin_q),
        active=Count("pk", filter=Q(is_active=True)),
        inactive=Count("pk", filter=Q(is_active=False)),
    )
    account_counts["unverified_students"] = account_counts["students"] - account_counts["verified_students"]
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
        "open_id_reviews": IdReviewCase.objects.filter(status=IdReviewCase.Status.OPEN).count(),
    })


@never_cache
@login_required
def backup_status(request):
    """Read-only backup information for administrators (session 1 page, session 4 backup engine).
    Backups cannot be downloaded or restored from the website; restore is a command."""
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    from .backups import last_status, list_backups
    backups = list_backups()
    return render(request, "core/backup_status.html", {
        "status": last_status(), "backups": backups, "keep_days": settings.BACKUP_KEEP_DAYS,
    })


@never_cache
@login_required
def audit_log(request):
    """v2.0.0: the full staff audit log for administrators (read-only, newest first)."""
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    entries = StaffAuditLog.objects.select_related("actor")
    q = request.GET.get("q", "").strip()[:80]
    action = request.GET.get("action", "").strip()[:80]
    actions = list(StaffAuditLog.objects.order_by("action").values_list("action", flat=True).distinct())
    if q:
        entries = entries.filter(
            Q(details__icontains=q) | Q(target_id__icontains=q) | Q(target_type__icontains=q)
            | Q(actor__username__icontains=q) | Q(actor__first_name__icontains=q) | Q(actor__last_name__icontains=q)
        )
    if action in actions:
        entries = entries.filter(action=action)
    else:
        action = ""
    return render(request, "core/audit_log.html", {
        "page_obj": _paginate(request, entries, 50),
        "querystring": _querystring_without_page(request),
        "q": q, "action": action,
        "action_choices": [(a, a.replace("_", " ").capitalize()) for a in actions],
    })


@never_cache
@login_required
def system_status(request):
    """v2.0.0: a readable version of /health/ for administrators, plus a few safe checks."""
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    import time
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from .backups import last_status

    checks = []
    started = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        ms = (time.perf_counter() - started) * 1000
        checks.append({"name": "Database", "ok": True, "detail": f"Answered in {ms:.0f} ms ({connection.vendor})."})
    except Exception:  # noqa: BLE001 - shown as a failed check, details stay in the log
        logging.getLogger("findit.errors").exception("Status page database failure")
        checks.append({"name": "Database", "ok": False, "detail": "The database did not answer. See the error log."})
    try:
        executor = MigrationExecutor(connection)
        pending = len(executor.migration_plan(executor.loader.graph.leaf_nodes()))
        checks.append({"name": "Database updates (migrations)", "ok": pending == 0,
                       "detail": "All applied." if pending == 0 else f"{pending} not applied. Run python manage.py migrate."})
    except Exception:  # noqa: BLE001
        checks.append({"name": "Database updates (migrations)", "ok": False, "detail": "Could not be checked."})
    status = last_status() or {}
    if not status:
        checks.append({"name": "Daily backup (made by the timer runner)", "ok": False,
                       "detail": "No backup yet. Start the timer runner or run python manage.py backup_now."})
    elif not status.get("ok"):
        checks.append({"name": "Daily backup (made by the timer runner)", "ok": False,
                       "detail": "The last backup failed. Open Backups for details."})
    else:
        from datetime import datetime
        try:
            age_hours = (timezone.now() - datetime.fromisoformat(status.get("at", ""))).total_seconds() / 3600
        except (TypeError, ValueError):
            age_hours = None
        fresh = age_hours is not None and age_hours <= 26
        checks.append({"name": "Daily backup (made by the timer runner)", "ok": fresh,
                       "detail": (f"Last backup {age_hours:.0f} hours ago." if age_hours is not None else "Last backup time unknown.")
                       + ("" if fresh else " Older than a day: is the timer runner (process_due --loop) running?")})
    waiting = ChatAttachment.objects.filter(status=ChatAttachment.Status.PROCESSING)
    oldest = waiting.order_by("created_at").values_list("created_at", flat=True).first()
    stuck = oldest is not None and (timezone.now() - oldest).total_seconds() > 15 * 60
    checks.append({"name": "Chat photos and videos queue", "ok": not stuck,
                   "detail": f"{waiting.count()} waiting" + (" (the oldest for over 15 minutes: is the media worker running?)" if stuck else ".")})
    return render(request, "core/system_status.html", {
        "checks": checks, "all_ok": all(c["ok"] for c in checks), "checked_at": timezone.now(),
        "open_queues": {
            "chat_reports": AbuseReport.objects.filter(status__in=OPEN_REPORT_STATUSES).count(),
            "general_reports": GeneralReport.objects.filter(status__in=OPEN_REPORT_STATUSES).count(),
            "id_reviews": IdReviewCase.objects.filter(status=IdReviewCase.Status.OPEN).count(),
        },
    })


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
        parsed = _parse_filter_date(filters[key])  # BUG-003: "2026-99-99" used to crash the page
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


@login_required
def admin_categories(request):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    form = CategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        category = form.save()
        audit(request.user, "created_category", category, category.name)
        messages.success(request, f"Category “{category.name}” added.")
        return redirect("admin-categories")
    categories = Category.objects.annotate(post_count=Count("posts")).order_by("sort_order", "name")
    return render(request, "core/admin_categories.html", {"form": form, "categories": categories})


@login_required
def admin_category_edit(request, category_id):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    category = get_object_or_404(Category, pk=category_id)
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request.user, "updated_category", category, f"{category.name} · active={category.is_active}")
        messages.success(request, "Category saved.")
        return redirect("admin-categories")
    return render(request, "core/admin_category_edit.html", {"form": form, "category": category})


@login_required
def admin_questions(request):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    q = request.GET.get("q", "").strip()
    templates = QuestionTemplate.objects.prefetch_related("categories").annotate(use_count=Count("post_questions"))
    if q:
        templates = templates.filter(text__icontains=q)
    return render(request, "core/admin_questions.html", {"templates": templates, "q": q})


@login_required
def admin_question_edit(request, template_id=None):
    if not is_admin(request.user):
        return HttpResponseForbidden("Administrator access is required.")
    template = get_object_or_404(QuestionTemplate, pk=template_id) if template_id else None
    form = QuestionTemplateForm(request.POST or None, instance=template)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        audit(request.user, "updated_question" if template else "created_question", saved, saved.text[:200])
        messages.success(request, "Question saved. Posts that already use it keep their original wording.")
        return redirect("admin-questions")
    return render(request, "core/admin_question_edit.html", {"form": form, "template": template})


# ---------------------------------------------------------------------------
# Approve / decline / re-verify / chat questions
# ---------------------------------------------------------------------------

def _back_to(request, claim):
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}):
        return redirect(target)
    return redirect("post-detail", post_id=claim.post_id)


@login_required
@require_POST
def approve_claim_view(request, claim_id):
    claim = get_object_or_404(ClaimApplication.objects.select_related("post", "finder"), pk=claim_id)
    try:
        approve_claim(claim, request.user)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Claim approved. The claimant was notified of their place in the approval order.")
    return _back_to(request, claim)


@login_required
@require_POST
def decline_claim_view(request, claim_id):
    claim = get_object_or_404(ClaimApplication.objects.select_related("post", "finder"), pk=claim_id)
    try:
        decline_claim(claim, request.user, request.POST.get("reason", ""))
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Claim declined. Its chat is now read-only.")
    return _back_to(request, claim)


@login_required
@require_POST
def reverify_view(request, conversation_id):
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    try:
        reopen_lost_report(conversation, request.user)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "You asked the finder to verify you again. This was your one re-application.")
    return redirect("chat-room", conversation_id=conversation.pk)


@login_required
@require_POST
def ask_questions_view(request, conversation_id):
    conversation = get_object_or_404(Conversation.objects.select_related("post", "claim"), pk=conversation_id)
    ids = [v for v in request.POST.getlist("questions") if v.isdigit()]
    templates = list(QuestionTemplate.objects.filter(pk__in=ids, is_active=True))
    if not templates:
        messages.error(request, "Pick at least one question to send.")
        return redirect("chat-room", conversation_id=conversation.pk)
    try:
        created = ask_chat_questions(conversation, request.user, templates)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Sent {len(created)} question(s). You'll get a notification when they're answered.")
    return redirect("chat-room", conversation_id=conversation.pk)


@login_required
@require_POST
def answer_question_view(request, question_id):
    question = get_object_or_404(ChatQuestion.objects.select_related("conversation"), pk=question_id)
    try:
        answer_chat_question(question, request.user, request.POST.get("answer", ""))
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))
    except ValueError as exc:
        messages.error(request, str(exc))
    if request.headers.get("x-requested-with") == "fetch":
        question.refresh_from_db()
        return JsonResponse({"ok": question.is_answered, "answer": question.answer_text})
    return redirect(f"{reverse('chat-room', args=[question.conversation_id])}#question-{question.pk}")


@login_required
@require_POST
def share_post(request, post_id):
    """Copy link: turns on public (signed-out) viewing for this post, permanently."""
    post = get_object_or_404(ItemPost, pk=post_id)
    PostShare.objects.get_or_create(post=post, user=request.user)
    if not post.is_shared:
        ItemPost.objects.filter(pk=post.pk, is_shared=False).update(is_shared=True, shared_at=timezone.now())
    link = request.build_absolute_uri(reverse("post-detail", args=[post.pk]))
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({
            "url": link,
            "shared_by_author": post.shares.filter(user_id=post.author_id).exists(),
            "share_count": post.shares.count(),
        })
    messages.success(request, f"Link ready to share: {link}")
    return redirect("post-detail", post_id=post.pk)
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


# ---------------------------------------------------------------------------
# v1.1.1 — email verification, Student ID, ID reviews, report & block, test inbox
# ---------------------------------------------------------------------------

@never_cache
@login_required
def verify_email(request):
    profile = request.user.profile
    form = VerifyCodeForm(request.POST if request.method == "POST" and "code" in request.POST else None)
    if request.method == "POST":
        if request.POST.get("action") == "send":
            ok, text = send_verification_code(request.user)
            (messages.success if ok else messages.error)(request, text)
            return redirect("verify-email")
        if form.is_valid():
            ok, text = check_code(request.user, form.cleaned_data["code"])
            if ok:
                messages.success(request, text)
                return redirect("my-profile")
            messages.error(request, text)
            return redirect("verify-email")
        messages.error(request, "Type the 6-digit code from the email.")
    wait = code_send_wait(request.user)
    return render(request, "core/verify_email.html", {
        "form": form, "profile": profile, "send_wait": wait, "test_inbox": test_inbox_enabled(),
        "is_student": profile.role == Profile.Role.STUDENT,
    })


@never_cache
@login_required
def change_student_id_view(request):
    profile = request.user.profile
    if profile.role != Profile.Role.STUDENT:
        return HttpResponseForbidden("Only student accounts have a Student ID.")
    form = StudentIdChangeForm(request.POST if request.method == "POST" else None, user=request.user)
    if request.method == "POST" and not profile.student_id_locked and form.is_valid():
        ok, text, disabled = change_student_id(request.user, form.cleaned_data["student_id"])
        if disabled:
            logout(request)
            messages.error(request, text + " Contact a Find-IT administrator.")
            return redirect("login")
        (messages.success if ok else messages.error)(request, text)
        if ok:
            return redirect("my-profile")
    preview = form.data.get("student_id", "").strip() if form.is_bound else ""
    return render(request, "core/student_id_change.html", {
        "form": form, "profile": profile, "id_count": distinct_student_ids(request.user),
        "max_ids": 3, "warn_flag": bool(preview and would_be_flagged(request.user, preview)),
        "must_set": not profile.student_id,
    })


@never_cache
@login_required
def id_review_new(request):
    if role_of(request.user) != Profile.Role.STUDENT:
        return HttpResponseForbidden("ID reviews are for student accounts.")
    ip = client_ip(request)
    initial = {"student_id": request.session.get("id_review_student_id") or request.user.profile.student_id or ""}
    form = IdReviewForm(request.POST if request.method == "POST" else None, initial=initial)
    blocked_reason = id_review_block_reason(request.user, ip)
    if request.method == "POST" and not blocked_reason and form.is_valid():
        try:
            case = open_id_review(request.user, form.cleaned_data["student_id"], form.cleaned_data["message"], ip)
        except ReviewLimitError as exc:
            messages.error(request, str(exc))
        else:
            request.session.pop("id_review_student_id", None)
            messages.success(request, f"ID review {case.reference} was sent. You will get an update when it is decided.")
            return redirect("my-profile")
    elif request.method == "POST" and blocked_reason:
        messages.error(request, blocked_reason)
    return render(request, "core/id_review_form.html", {"form": form, "blocked_reason": blocked_reason})


@login_required
@require_POST
def id_review_withdraw(request, case_id):
    """v2.0.0: the student who asked can withdraw an open ID review."""
    case = get_object_or_404(IdReviewCase, pk=case_id, requester=request.user)
    try:
        withdraw_id_review(case, request.user)
    except (ValueError, PermissionError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"ID review {case.reference} was withdrawn.")
    return redirect("my-profile")


@never_cache
@login_required
def id_reviews(request):
    if not can_review_reports(request.user):
        return HttpResponseForbidden("Only administrators and verified moderators review Student ID cases.")
    status = request.GET.get("status", "OPEN")
    if status not in IdReviewCase.Status.values:
        status = "OPEN"
    cases = IdReviewCase.objects.filter(status=status).select_related("requester", "holder")
    q = request.GET.get("q", "").strip()[:20]
    if q:
        cases = cases.filter(Q(student_id__icontains=q) | Q(reference__icontains=q))
    # One row per Student ID for open cases, so many repeated requests cannot flood the queue.
    groups = []
    if status == "OPEN":
        seen = {}
        for case in cases.order_by("created_at"):
            if case.student_id in seen:
                seen[case.student_id]["count"] += 1
                continue
            seen[case.student_id] = {"case": case, "count": 1}
            groups.append(seen[case.student_id])
    return render(request, "core/id_reviews.html", {
        "groups": groups, "page_obj": _paginate(request, cases.order_by("-created_at"), 25) if status != "OPEN" else None,
        "status": status, "status_choices": IdReviewCase.Status.choices, "q": q,
    })


@never_cache
@login_required
def id_review_detail(request, case_id):
    if not can_review_reports(request.user):
        return HttpResponseForbidden("Only administrators and verified moderators review Student ID cases.")
    case = get_object_or_404(IdReviewCase.objects.select_related("requester__profile", "holder__profile"), pk=case_id)
    form = IdReviewDecisionForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            decide_id_review(case, request.user, form.cleaned_data["decision"] == "transfer", form.cleaned_data["note"])
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"ID review {case.reference} was decided.")
            return redirect("id-reviews")
    related = IdReviewCase.objects.filter(student_id=case.student_id).exclude(pk=case.pk).select_related("requester")[:20]
    holder_now = locked_holder(case.student_id)
    return render(request, "core/id_review_detail.html", {
        "case": case, "form": form, "related": related, "holder_now": holder_now.user if holder_now else None,
        "requester_ids": StudentIdRecord.objects.filter(user=case.requester),
        "holder_ids": StudentIdRecord.objects.filter(user=holder_now.user) if holder_now else [],
    })


@never_cache
@login_required
def report_block(request, user_id):
    """One button: report (reason optional) + block. Keeps the two people apart."""
    target = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
    back = _safe_next(request, fallback="home")
    if target.pk == request.user.pk or role_of(target) != Profile.Role.STUDENT:
        messages.error(request, "This account cannot be blocked. Use Report a problem instead.")
        return redirect(back)
    if not has_relationship(request.user, target):
        return HttpResponseForbidden("You can only block someone you met through a post, claim or chat.")
    conversation = None
    conversation_id = request.GET.get("conversation") or request.POST.get("conversation")
    if conversation_id:
        conversation = Conversation.objects.filter(pk=conversation_id).first() if _is_uuid(conversation_id) else None
        if conversation and not (conversation.includes(request.user) and conversation.includes(target)):
            conversation = None
    form = ReportBlockForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            report = block_user(request.user, target, form.cleaned_data["reason"], form.cleaned_data["details"], conversation)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(back)
        messages.success(request, (
            f"{target.first_name or 'This person'} is blocked and report {report.reference} was sent to moderators. "
            "Your chats and claims with them are now closed. You can unblock them from My profile."
        ))
        return redirect(back)
    return render(request, "core/report_block.html", {
        "form": form, "target": target, "conversation": conversation, "next": back,
    })


def _is_uuid(value):
    import uuid
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


@never_cache
@login_required
def blocked_people(request):
    if request.method == "POST":
        user_id = request.POST.get("user_id", "")
        if user_id.isdigit() and unblock_user(request.user, int(user_id)):
            messages.success(request, "Unblocked. Closed chats and claims stay closed.")
        return redirect("blocked-people")
    return render(request, "core/blocked_people.html", {
        "blocks": UserBlock.objects.filter(blocker=request.user).select_related("blocked"),
    })


@never_cache
@login_required
def test_inbox(request):
    """Local-only page: copies of the emails Find-IT printed instead of sending."""
    if not test_inbox_enabled():
        raise Http404
    rows = TestEmail.objects.all() if is_developer(request.user) else TestEmail.objects.filter(
        Q(recipient=request.user) | Q(to__iexact=request.user.email or "-")
    )
    return render(request, "core/test_inbox.html", {"emails": rows[:50]})


def server_error(request):
    """DES-005: the 500 page with only the version label added. No database, no request context,
    so it still works when something else in Find-IT is failing."""
    from django.http import HttpResponseServerError
    from django.template import loader
    from .version import FINDIT_VERSION
    return HttpResponseServerError(loader.get_template("500.html").render({"findit_version": FINDIT_VERSION}))
