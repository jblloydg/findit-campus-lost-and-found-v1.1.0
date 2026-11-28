"""v1.1.1 — V2-I account verification, Student ID rules, unverified limits, report & block.

Plain summary
-------------
* Verifying is optional. A signed-in student asks for a 6-digit code, it is
  emailed (printed + Test inbox on a local PC), they type it in -> Verified.
* Until someone verifies a Student ID, several accounts may use it. When one
  verifies, the ID is locked to them; the others get `id_conflict_grace_days`
  to change their ID or appeal, then the ID is cleared from their account.
* An account that has used three different Student IDs is red-flagged and disabled.
* Somebody whose ID is locked by another account can open an ID review case.
  Verified moderators and administrators decide it.
* Unverified students get lower limits (claims, posts, chat).
* "Report & block" keeps two people apart and files a report for moderators.

All state changes for these features go through this module.
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, models, transaction
from django.urls import reverse
from django.utils import timezone

from .mail import send_findit_email
from .models import (
    AbuseReport, ChatMessage, ClaimApplication, Conversation, EmailVerificationCode, IdReviewCase, InAppNotification,
    ItemPost, Profile, StudentIdRecord, SystemSettings, UserBlock,
)

User = get_user_model()

CODE_LIFETIME_MINUTES = 15
CODES_PER_DAY = 5
CODE_RESEND_SECONDS = 60
CODE_MAX_ATTEMPTS = 5
MAX_STUDENT_IDS = 3
ID_CASES_PER_30_DAYS = 3
ID_CASES_PER_IP_PER_DAY = 5


# ---------------------------------------------------------------------------
# Notifications that are not about a post
# ---------------------------------------------------------------------------

def notify_account(user, text, link="", priority=False):
    text = text[:240]
    recent = InAppNotification.objects.filter(
        recipient=user, post__isnull=True, text=text, created_at__gte=timezone.now() - timedelta(seconds=60),
    ).first()
    if recent:
        return recent
    notification = InAppNotification.objects.create(
        recipient=user, post=None, link=link[:200], text=text, is_priority=priority,
    )
    from .services import push_notification
    push_notification(notification)
    return notification


def _site_url(path):
    return f"{settings.FINDIT_SITE_URL.rstrip('/')}{path}" if getattr(settings, "FINDIT_SITE_URL", "") else path


# ---------------------------------------------------------------------------
# Email verification codes
# ---------------------------------------------------------------------------

def _hash_code(user, code):
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"{user.pk}:{code}".encode(), hashlib.sha256).hexdigest()


def _new_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def code_send_wait(user):
    """Seconds until a new code may be sent (0 = now), or None if today's limit is used up."""
    now = timezone.now()
    sent_today = EmailVerificationCode.objects.filter(user=user, created_at__gte=now - timedelta(days=1))
    if sent_today.count() >= CODES_PER_DAY:
        return None
    last = sent_today.order_by("-created_at").first()
    if last:
        wait = CODE_RESEND_SECONDS - int((now - last.created_at).total_seconds())
        if wait > 0:
            return wait
    return 0


def issue_code(user):
    """Create and store a new code. Returns the plain code (only ever put in the email)."""
    EmailVerificationCode.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())
    code = _new_code()
    EmailVerificationCode.objects.create(
        user=user, email=user.email, code_hash=_hash_code(user, code),
        expires_at=timezone.now() + timedelta(minutes=CODE_LIFETIME_MINUTES),
    )
    return code


def send_verification_code(user):
    """Returns (ok, message)."""
    profile = user.profile
    if profile.email_verified_at:
        return False, "Your email is already verified."
    if not user.email:
        return False, "Add an email address to your profile first."
    wait = code_send_wait(user)
    if wait is None:
        return False, f"You can ask for {CODES_PER_DAY} codes a day. Please try again tomorrow."
    if wait:
        return False, f"Please wait {wait} seconds before asking for another code."
    code = issue_code(user)
    send_findit_email(user, "Find-IT: your verification code", _code_email_body(user, code))
    return True, f"We sent a 6-digit code to {user.email}. It works for {CODE_LIFETIME_MINUTES} minutes."


def _code_email_body(user, code):
    return (
        f"Hi {user.first_name or 'there'},\n\n"
        f"Your Find-IT verification code is: {code}\n\n"
        f"Enter it on the Verify page: {_site_url(reverse('verify-email'))}\n"
        f"The code works for {CODE_LIFETIME_MINUTES} minutes. If you did not ask for it, ignore this email.\n\n"
        "— Find-IT, Davao Oriental State University\n"
    )


def check_code(user, code):
    """Returns (ok, message). Wrong codes count; after five tries the code stops working."""
    code = (code or "").strip().replace(" ", "")
    if user.profile.email_verified_at:
        return True, "Your email is already verified."
    with transaction.atomic():
        row = (
            EmailVerificationCode.objects.select_for_update()
            .filter(user=user, used_at__isnull=True).order_by("-created_at").first()
        )
        if row is None or row.expires_at < timezone.now():
            return False, "That code has expired. Ask for a new code."
        if row.email.lower() != (user.email or "").lower():
            row.used_at = timezone.now()
            row.save(update_fields=["used_at"])
            return False, "Your email changed after the code was sent. Ask for a new code."
        if not (len(code) == 6 and code.isdigit()) or not hmac.compare_digest(row.code_hash, _hash_code(user, code)):
            row.attempts += 1
            if row.attempts >= CODE_MAX_ATTEMPTS:
                row.used_at = timezone.now()
            row.save(update_fields=["attempts", "used_at"])
            if row.used_at:
                return False, "Too many wrong tries. That code no longer works; ask for a new code."
            return False, f"That code is not right. {CODE_MAX_ATTEMPTS - row.attempts} tries left."
        row.used_at = timezone.now()
        row.save(update_fields=["used_at"])
    return mark_verified(user)


def locked_holder(student_id, exclude_user=None):
    rows = Profile.objects.filter(student_id=student_id, student_id_locked=True).select_related("user")
    if exclude_user is not None:
        rows = rows.exclude(user=exclude_user)
    return rows.first()


def mark_verified(user):
    """Email confirmed. Lock the Student ID if no other account holds it locked."""
    message = "Your email is verified. Your account now shows ✔ Verified."
    with transaction.atomic():
        profile = Profile.objects.select_for_update().get(user=user)
        profile.email_verified_at = profile.email_verified_at or timezone.now()
        profile.save(update_fields=["email_verified_at"])
        if profile.student_id and not profile.student_id_locked:
            if locked_holder(profile.student_id, exclude_user=user):
                message += (
                    f" Your Student ID {profile.student_id} is already locked to another verified account, so it was "
                    "not locked to you. Change your Student ID or request an ID review from your profile."
                )
            else:
                try:
                    with transaction.atomic():
                        profile.student_id_locked = True
                        profile.id_conflict_deadline = None
                        profile.save(update_fields=["student_id_locked", "id_conflict_deadline"])
                except IntegrityError:
                    profile.student_id_locked = False
                else:
                    start_conflicts(profile.student_id, holder=user)
                    message += f" Student ID {profile.student_id} is now locked to your account."
    return True, message


def start_conflicts(student_id, holder):
    """Other accounts that use a newly locked Student ID get a deadline to change it or appeal."""
    days = SystemSettings.current().id_conflict_grace_days or 14
    deadline = timezone.now() + timedelta(days=days)
    others = Profile.objects.filter(student_id=student_id, student_id_locked=False).exclude(user=holder)
    for other in others.select_related("user"):
        if other.id_conflict_deadline is None:
            other.id_conflict_deadline = deadline
            other.save(update_fields=["id_conflict_deadline"])
        notify_account(
            other.user,
            f"Another account verified Student ID {student_id}. Change your Student ID or appeal "
            f"by {timezone.localtime(other.id_conflict_deadline):%b %d, %Y}, or it will be cleared.",
            link=reverse("my-profile"), priority=True,
        )


# ---------------------------------------------------------------------------
# Welcome messages
# ---------------------------------------------------------------------------

def welcome_new_account(user):
    """Three notices (each also sent as an email): welcome, verify, start posting/browsing."""
    name = user.first_name or "there"
    notify_account(user, "Welcome to Find-IT, the DOrSU campus lost and found.", link=reverse("home"))
    notify_account(
        user, "Verify your email to get ✔ Verified and higher limits. Tap here to verify.",
        link=reverse("verify-email"), priority=True,
    )
    notify_account(user, "Start posting and browsing: see what has been lost and found on campus.", link=reverse("home"))
    send_findit_email(user, "Welcome to Find-IT", (
        f"Hi {name},\n\nWelcome to Find-IT, the campus lost-and-found for Davao Oriental State University.\n"
        "Hand-offs must always happen within school premises.\n\n— Find-IT\n"
    ))
    code = issue_code(user)
    send_findit_email(user, "Find-IT: verify your email", (
        f"Hi {name},\n\nVerifying is optional but gives you ✔ Verified and higher limits.\n\n"
        f"Your verification code is: {code}\n"
        f"Verify here: {_site_url(reverse('verify-email'))}\n"
        f"The code works for {CODE_LIFETIME_MINUTES} minutes; you can ask for a new one on that page.\n\n— Find-IT\n"
    ))
    send_findit_email(user, "Find-IT: start posting and browsing", (
        f"Hi {name},\n\nSee lost and found items: {_site_url(reverse('home'))}\n"
        f"Post something you lost or found: {_site_url(reverse('create-post'))}\n\n— Find-IT\n"
    ))


# ---------------------------------------------------------------------------
# Student IDs
# ---------------------------------------------------------------------------

def distinct_student_ids(user):
    return StudentIdRecord.objects.filter(user=user).count()


def would_be_flagged(user, new_id):
    if StudentIdRecord.objects.filter(user=user, student_id=new_id).exists():
        return False
    return distinct_student_ids(user) + 1 >= MAX_STUDENT_IDS


def record_student_id(user, student_id, source):
    StudentIdRecord.objects.get_or_create(user=user, student_id=student_id, defaults={"source": source})


def flag_and_disable(user, reason):
    profile = user.profile
    profile.flagged_at = timezone.now()
    profile.flag_reason = reason[:240]
    profile.save(update_fields=["flagged_at", "flag_reason"])
    user.is_active = False
    user.save(update_fields=["is_active"])


@transaction.atomic
def change_student_id(user, new_id):
    """Returns (ok, message, disabled). Locked (verified) IDs cannot be changed here."""
    profile = Profile.objects.select_for_update().get(user=user)
    if profile.role != Profile.Role.STUDENT:
        return False, "Only student accounts have a Student ID.", False
    if profile.student_id_locked:
        return False, "Your Student ID is verified and locked. Ask for an ID review to change it.", False
    if profile.student_id == new_id:
        return False, "That is already your Student ID.", False
    if locked_holder(new_id, exclude_user=user):
        return False, "That Student ID is locked to a verified account. If it is yours, request an ID review.", False
    record_student_id(user, new_id, StudentIdRecord.Source.CHANGE)
    profile.student_id = new_id
    profile.id_conflict_deadline = None
    profile.save(update_fields=["student_id", "id_conflict_deadline"])
    if distinct_student_ids(user) >= MAX_STUDENT_IDS:
        flag_and_disable(user, f"Used {MAX_STUDENT_IDS} different Student IDs.")
        return True, "This account used three different Student IDs, so it was red-flagged and disabled.", True
    if profile.email_verified_at and not locked_holder(new_id, exclude_user=user):
        try:
            with transaction.atomic():
                profile.student_id_locked = True
                profile.save(update_fields=["student_id_locked"])
        except IntegrityError:
            profile.student_id_locked = False
        else:
            start_conflicts(new_id, holder=user)
    return True, f"Your Student ID is now {new_id}.", False


def needs_student_id(user):
    """A student without a Student ID (cleared after a conflict) must set one, unless a review is open."""
    if not getattr(user, "is_authenticated", False):
        return False
    try:
        profile = user.profile
    except Profile.DoesNotExist:
        return False
    if profile.role != Profile.Role.STUDENT or profile.student_id:
        return False
    return not IdReviewCase.objects.filter(requester=user, status=IdReviewCase.Status.OPEN).exists()


def clear_expired_id_conflicts():
    """Called by the timer runner: clear IDs whose grace period ended (paused while an appeal is open)."""
    now = timezone.now()
    due = Profile.objects.filter(
        id_conflict_deadline__lt=now, student_id_locked=False, student_id__isnull=False,
    ).select_related("user")
    cleared = 0
    for profile in due:
        if IdReviewCase.objects.filter(requester=profile.user, status=IdReviewCase.Status.OPEN).exists():
            continue
        old = profile.student_id
        profile.student_id = None
        profile.id_conflict_deadline = None
        profile.save(update_fields=["student_id", "id_conflict_deadline"])
        notify_account(
            profile.user, f"Student ID {old} was cleared from your account because another account verified it. "
            "Set your own Student ID.", link=reverse("change-student-id"), priority=True,
        )
        cleared += 1
    return cleared


# ---------------------------------------------------------------------------
# ID review cases (manual review, protected against floods of requests)
# ---------------------------------------------------------------------------

class ReviewLimitError(Exception):
    pass


def _ip_key(ip):
    return "findit:id-review-ip:" + hashlib.sha256((ip or "unknown").encode()).hexdigest()


def id_review_block_reason(user, ip=""):
    """Why this person cannot open a case right now (None = allowed)."""
    if IdReviewCase.objects.filter(requester=user, status=IdReviewCase.Status.OPEN).exists():
        return "You already have an ID review waiting. Please wait for its decision."
    since = timezone.now() - timedelta(days=30)
    if IdReviewCase.objects.filter(requester=user, created_at__gte=since).count() >= ID_CASES_PER_30_DAYS:
        return f"You can open {ID_CASES_PER_30_DAYS} ID reviews every 30 days. Please try again later."
    if ip and cache.get(_ip_key(ip), 0) >= ID_CASES_PER_IP_PER_DAY:
        return "Too many ID reviews were sent from this network today. Please try again tomorrow."
    return None


@transaction.atomic
def open_id_review(requester, student_id, message, ip=""):
    reason = id_review_block_reason(requester, ip)
    if reason:
        raise ReviewLimitError(reason)
    holder = locked_holder(student_id, exclude_user=requester)
    if holder is None:
        raise ReviewLimitError("That Student ID is not locked to another account, so no review is needed. "
                               "You can set it as your Student ID from your profile.")
    profile = requester.profile
    kind = IdReviewCase.Kind.APPEAL if (profile.id_conflict_deadline and profile.student_id == student_id) else IdReviewCase.Kind.IMPOSTOR
    case = IdReviewCase.objects.create(
        kind=kind, requester=requester, student_id=student_id, holder=holder.user, message=message.strip()[:1000],
    )
    if ip:
        key = _ip_key(ip)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, 60 * 60 * 24)
    notify_account(requester, f"ID review {case.reference} was sent. A moderator will decide it.",
                   link=reverse("my-profile"))
    return case


@transaction.atomic
def decide_id_review(case, actor, transfer, note=""):
    case = IdReviewCase.objects.select_for_update().select_related("requester__profile", "holder__profile").get(pk=case.pk)
    if case.status != IdReviewCase.Status.OPEN:
        raise ValueError("This review was already decided.")
    note = (note or "").strip()[:500]
    case.reviewed_by = actor
    case.decided_at = timezone.now()
    case.decision_note = note
    if transfer:
        holder_profile = Profile.objects.select_for_update().filter(
            student_id=case.student_id, student_id_locked=True,
        ).exclude(user=case.requester).first()
        if holder_profile:
            holder_profile.student_id = None
            holder_profile.student_id_locked = False
            holder_profile.save(update_fields=["student_id", "student_id_locked"])
            notify_account(holder_profile.user, f"After an ID review, Student ID {case.student_id} was removed from "
                           "your account. Set your own Student ID.", link=reverse("change-student-id"), priority=True)
        profile = Profile.objects.select_for_update().get(user=case.requester)
        record_student_id(case.requester, case.student_id, StudentIdRecord.Source.REVIEW)
        profile.student_id = case.student_id
        profile.student_id_locked = True
        profile.id_conflict_deadline = None
        profile.save(update_fields=["student_id", "student_id_locked", "id_conflict_deadline"])
        start_conflicts(case.student_id, holder=case.requester)
        case.status = IdReviewCase.Status.TRANSFERRED
        notify_account(case.requester, f"ID review {case.reference}: Student ID {case.student_id} is now locked to "
                       "your account.", link=reverse("my-profile"), priority=True)
    else:
        case.status = IdReviewCase.Status.KEPT
        notify_account(case.requester, f"ID review {case.reference}: the Student ID stays with the verified account."
                       + (f" Note: {note}" if note else ""), link=reverse("my-profile"), priority=True)
    case.save(update_fields=["status", "reviewed_by", "decided_at", "decision_note"])
    from .services import audit
    audit(actor, "decided_id_review", case, f"{case.get_status_display()} · {note}")
    return case


@transaction.atomic
def withdraw_id_review(case, user):
    """v2.0.0: the student who asked for an ID review can take it back while it is still open."""
    case = IdReviewCase.objects.select_for_update().get(pk=case.pk)
    if case.requester_id != user.pk:
        raise PermissionError("Only the person who asked for this review can withdraw it.")
    if case.status != IdReviewCase.Status.OPEN:
        raise ValueError("This review was already decided or withdrawn.")
    case.status = IdReviewCase.Status.WITHDRAWN
    case.decided_at = timezone.now()
    case.decision_note = "Withdrawn by the student who asked."
    case.save(update_fields=["status", "decided_at", "decision_note"])
    from .services import audit
    audit(user, "withdrew_id_review", case, f"{case.reference} withdrawn by the requester")
    return case


# ---------------------------------------------------------------------------
# Limits for unverified students
# ---------------------------------------------------------------------------

def _is_unverified(user):
    from .permissions import is_unverified_student
    return is_unverified_student(user)


def claim_limit_message(user):
    if not _is_unverified(user):
        return None
    limit = SystemSettings.current().unverified_max_open_claims or 3
    open_claims = ClaimApplication.objects.filter(
        claimant=user, status__in=ClaimApplication.ACTIVE_STATUSES, finder__isnull=True,
    ).count()
    if open_claims >= limit:
        return (f"Unverified accounts can have {limit} open claims at a time. Close one, or verify your email "
                "to remove this limit.")
    return None


def posting_limit_message(user):
    """Unverified students: N posts per 24 hours. Others: None (the per-hour limit still applies)."""
    if not _is_unverified(user):
        return None
    limit = SystemSettings.current().unverified_posts_per_day or 1
    since = timezone.now() - timedelta(days=1)
    if ItemPost.objects.filter(author=user, created_at__gte=since).count() >= limit:
        return (f"Unverified accounts can create {limit} post{'s' if limit != 1 else ''} per day. "
                "Verify your email to post more.")
    return None


def chat_limit_message(user, text):
    if not _is_unverified(user):
        return None
    row = SystemSettings.current()
    max_chars = row.unverified_chat_max_chars or 100
    if len(text) > max_chars:
        return f"Unverified accounts can send up to {max_chars} characters per message. Verify your email to send longer messages."
    window = row.unverified_chat_window_minutes or 10
    limit = row.unverified_chat_messages or 10
    since = timezone.now() - timedelta(minutes=window)
    if ChatMessage.objects.filter(sender=user, sent_at__gte=since).count() >= limit:
        return f"Unverified accounts can send {limit} messages every {window} minutes. Please wait, or verify your email."
    return None


def claim_expiry_days(claimant):
    if _is_unverified(claimant):
        return SystemSettings.current().unverified_claim_expiry_days or 3
    return 7


# ---------------------------------------------------------------------------
# Report & block
# ---------------------------------------------------------------------------

def blocked_between(a, b):
    if not a or not b or not getattr(a, "pk", None) or not getattr(b, "pk", None) or a.pk == b.pk:
        return False
    return UserBlock.objects.filter(
        models.Q(blocker_id=a.pk, blocked_id=b.pk) | models.Q(blocker_id=b.pk, blocked_id=a.pk)
    ).exists()


def conversations_between(a, b):
    return Conversation.objects.filter(
        models.Q(initiator=a, recipient=b) | models.Q(initiator=b, recipient=a)
    )


def has_relationship(a, b):
    """Only people who met on Find-IT (a post, a claim or a chat) can block each other."""
    return (
        conversations_between(a, b).exists()
        or ClaimApplication.objects.filter(
            models.Q(claimant=a, post__author=b) | models.Q(claimant=b, post__author=a)
            | models.Q(claimant=a, finder=b) | models.Q(claimant=b, finder=a)
        ).exists()
        or ItemPost.objects.filter(author=b).exists()
    )


@transaction.atomic
def block_user(blocker, blocked, reason="", details="", conversation=None):
    """One action: file a report (reason optional) and keep the two people apart."""
    from .services import close_claim, close_conversation, record_report_submission
    if blocker.pk == blocked.pk:
        raise ValueError("You cannot block yourself.")
    if blocked.profile.role != Profile.Role.STUDENT:
        raise ValueError("Staff accounts cannot be blocked. Use Report a problem instead.")
    if conversation is None:
        conversation = conversations_between(blocker, blocked).order_by("-updated_at").first()
    reason = reason if reason in AbuseReport.Reason.values else ""
    details = (details or "").strip()[:1500]
    report = AbuseReport(
        reporter=blocker, conversation=conversation, target_user=blocked,
        reason=reason or AbuseReport.Reason.BLOCK, details=details,
    )
    report.save()
    record_report_submission(report, blocker)
    block, created = UserBlock.objects.get_or_create(blocker=blocker, blocked=blocked, defaults={"report": report})
    if not created:
        block.report = report
        block.save(update_fields=["report"])
    note = "Closed: one person blocked the other."
    for convo in conversations_between(blocker, blocked):
        if not convo.is_closed:
            close_conversation(convo, note)
    claims = ClaimApplication.objects.filter(status__in=ClaimApplication.ACTIVE_STATUSES).filter(
        models.Q(claimant=blocked, post__author=blocker) | models.Q(claimant=blocker, post__author=blocked)
        | models.Q(claimant=blocked, finder=blocker) | models.Q(claimant=blocker, finder=blocked)
    )
    for claim in claims:
        close_claim(claim, None, note)
    return report


def unblock_user(blocker, blocked_id):
    return UserBlock.objects.filter(blocker=blocker, blocked_id=blocked_id).delete()[0] > 0
