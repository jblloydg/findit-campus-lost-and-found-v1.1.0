from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone

from .models import (
    CLOSED_REPORT_STATUSES, OPEN_REPORT_STATUSES, AbuseReport, ChatQuestion, ClaimApplication, Conversation,
    GeneralReport, GuardhouseIntake, InAppNotification, ItemPost, ModeratorVerification, ModeratorVerificationEvent,
    PostStatusEvent, Profile, QuestionTemplate, ReportStatus, ReportStatusEvent, StaffAuditLog, StatusChangeRequest,
    SystemSettings, TurnInTicket, VerificationQuestion,
)
from .permissions import is_staff_or_admin

User = get_user_model()


def actor_name(user):
    return user.get_full_name() or user.username if user else "Find-IT"


def audit(actor, action, target, details=""):
    return StaffAuditLog.objects.create(
        actor=actor,
        action=action[:80],
        target_type=target.__class__.__name__,
        target_id=str(target.pk),
        details=details[:500],
    )


def record_status(post, new_status, actor=None, note="", related_claim=None):
    old_status = post.status
    if old_status == new_status:
        return None
    post.status = new_status
    post.save(update_fields=["status", "updated_at"])
    return PostStatusEvent.objects.create(
        post=post,
        previous_status=old_status,
        new_status=new_status,
        actor=actor,
        note=note[:240],
        related_claim=related_claim,
    )


MIN_POST_QUESTIONS = 3
MAX_POST_QUESTIONS = 5


def resolve_post_questions(picked):
    """Return 3-5 question templates: the finder's picks (max 5) topped up with
    active default questions until there are at least three."""
    chosen = list(picked)[:MAX_POST_QUESTIONS]
    if len(chosen) < MIN_POST_QUESTIONS:
        chosen_ids = {q.pk for q in chosen}
        defaults = QuestionTemplate.objects.filter(is_default=True, is_active=True).exclude(pk__in=chosen_ids)
        for template in defaults:
            if len(chosen) >= MIN_POST_QUESTIONS:
                break
            chosen.append(template)
    if len(chosen) < MIN_POST_QUESTIONS:
        fallback = QuestionTemplate.objects.filter(is_active=True, is_general=True).exclude(pk__in={q.pk for q in chosen})
        for template in fallback:
            if len(chosen) >= MIN_POST_QUESTIONS:
                break
            chosen.append(template)
    return chosen


def apply_post_questions(post, picked):
    """Replace a found post's questions with snapshots of the chosen templates.
    Callers must not do this once a claim exists."""
    post.verification_questions.all().delete()
    if post.post_type != ItemPost.Type.FOUND:
        return []
    created = []
    for order, template in enumerate(resolve_post_questions(picked), start=1):
        created.append(VerificationQuestion.objects.create(
            post=post,
            order=order,
            text=template.text,
            template=template,
            answer_type=template.answer_type,
            choices=list(template.choices or []),
        ))
    return created


def notify_user(user, post, text, claim=None, priority=False):
    text = text[:240]
    recent = InAppNotification.objects.filter(
        recipient=user, post=post, claim=claim, text=text,
        created_at__gte=timezone.now() - timedelta(seconds=60),
    ).first()
    if recent:
        # Identical notice within a minute (double click, retry): merge instead of duplicating.
        if priority and not recent.is_priority:
            recent.is_priority = True
            recent.save(update_fields=["is_priority"])
        return recent
    notification = InAppNotification.objects.create(
        recipient=user, post=post, claim=claim, text=text, is_priority=priority,
    )
    push_notification(notification)
    return notification


def push_notification(notification):
    """Live 'new notification' push. BUG-004: sent only after the database has saved it,
    so nobody sees (or opens) a notice that a failed save later removed."""
    def send():
        layer = get_channel_layer()
        if layer:
            try:
                async_to_sync(layer.group_send)(
                    f"notifications_{notification.recipient_id}",
                    {"type": "notification.created", "text": notification.text, "id": notification.pk,
                     "priority": notification.is_priority},
                )
            except Exception:  # the live push is a bonus; the notice is saved either way
                pass
    transaction.on_commit(send)


def notify_claimants(post, text, include_open=True):
    claims = post.claims.select_related("claimant").all()
    if not include_open:
        claims = claims.filter(status__in=ClaimApplication.ACTIVE_STATUSES)
    for claim in claims:
        notify_user(claim.claimant, post, text, claim)


def create_claim_conversation(claim):
    return Conversation.objects.get_or_create(
        claim=claim,
        defaults={
            "post": claim.post,
            "initiator": claim.claimant,
            "recipient": claim.finder_user,
        },
    )[0]


def create_lost_post_conversation(post, finder):
    return Conversation.objects.get_or_create(
        post=post,
        claim=None,
        initiator=finder,
        recipient=post.author,
    )[0]


def close_conversation(conversation, reason=""):
    conversation.is_closed = True
    conversation.pause_reason = reason[:240]
    conversation.save(update_fields=["is_closed", "pause_reason", "updated_at"])


@transaction.atomic
def close_claim(claim, actor=None, reason="Closed by participant"):
    claim = ClaimApplication.objects.select_for_update().select_related("post", "claimant").get(pk=claim.pk)
    if claim.status not in ClaimApplication.ACTIVE_STATUSES:
        return claim
    claim.status = ClaimApplication.Status.CLOSED
    claim.closed_at = timezone.now()
    claim.close_reason = reason[:240]
    claim.save(update_fields=["status", "closed_at", "close_reason"])
    if claim.post.returned_application_id == claim.pk:
        claim.post.returned_application = None
        claim.post.save(update_fields=["returned_application", "updated_at"])
        record_status(claim.post, ItemPost.Status.OPEN, actor, "The selected claim was closed; the item is available again.")
    if hasattr(claim, "conversation"):
        close_conversation(claim.conversation, reason)
    reopen_if_no_active_claims(claim.post, actor)
    notify_user(claim.claimant, claim.post, "Your claim was closed.", claim)
    if claim.finder_user.pk != claim.claimant_id:
        notify_user(claim.finder_user, claim.post, "A claim was closed.", claim)
    if actor and is_staff_or_admin(actor):
        audit(actor, "closed_claim", claim, reason)
    return claim


def staff_users():
    return User.objects.filter(is_active=True).filter(
        profile__role__in=[Profile.Role.STAFF, Profile.Role.ADMIN, Profile.Role.DEVELOPER]
    ).distinct()


def ticket_for(post, finder, claim=None):
    ticket, _ = TurnInTicket.objects.get_or_create(post=post, finder=finder, defaults={"claim": claim})
    if claim and ticket.claim_id != claim.pk:
        ticket.claim = claim
        ticket.save(update_fields=["claim"])
    return ticket


def can_turn_in(post):
    return post.status not in {ItemPost.Status.TURNED_OVER, ItemPost.Status.CLAIMED, ItemPost.Status.CLOSED} and not post.is_archived


@transaction.atomic
def request_guardhouse(ticket, actor):
    """Finder says they are bringing the item. Status changes only when staff receive it."""
    ticket = TurnInTicket.objects.select_for_update().select_related("post").get(pk=ticket.pk)
    if actor.pk != ticket.finder_id:
        raise PermissionError("Only the finder can say they are bringing this item.")
    if not can_turn_in(ticket.post):
        raise ValueError("This item can't be turned in right now.")
    if ticket.requested_at:
        return ticket
    ticket.requested_at = timezone.now()
    ticket.save(update_fields=["requested_at"])
    for staff in staff_users():
        notify_user(staff, ticket.post, f"Item on its way to the guard house. Turn-in code {ticket.code}.")
    return ticket


@transaction.atomic
def turn_over_to_guardhouse(post, actor, ticket=None, handed_over_by_user=None, handed_over_by_name="", method=GuardhouseIntake.Method.MANUAL):
    """Staff confirm the item physically arrived. Claims and chats stay open; the
    admin's guard-house grace days decide when the listing (and its chats) close."""
    if not is_staff_or_admin(actor):
        raise PermissionError("Only guard-house staff can confirm that an item was received.")
    post = ItemPost.objects.select_for_update().get(pk=post.pk)
    if post.status == ItemPost.Status.TURNED_OVER:
        return post
    if not can_turn_in(post):
        raise ValueError("This item can't be turned in in its current state.")
    if ticket is None:
        finder = handed_over_by_user or post.author
        ticket = TurnInTicket.objects.filter(post=post, finder=finder).first()
    if handed_over_by_user is None and not handed_over_by_name and ticket:
        handed_over_by_user = ticket.finder
    record_status(post, ItemPost.Status.TURNED_OVER, actor, "Received at the guard house.")
    post.turned_over_at = timezone.now()
    post.returned_application = None
    post.save(update_fields=["turned_over_at", "returned_application", "updated_at"])
    GuardhouseIntake.objects.create(
        post=post, ticket=ticket, received_by=actor, received_at=timezone.now(),
        handed_over_by_user=handed_over_by_user, handed_over_by_name=(handed_over_by_name or "")[:120], method=method,
    )
    if ticket:
        ticket.received_at = timezone.now()
        ticket.save(update_fields=["received_at"])
    # A recorded hand-off that never completed goes back to Approved.
    post.claims.filter(status=ClaimApplication.Status.RETURNED).update(status=ClaimApplication.Status.APPROVED)
    settings_row = SystemSettings.current()
    window = (
        f" Chats stay open for {settings_row.guardhouse_grace_days} day(s)."
        if settings_row.guardhouse_grace_days else ""
    )
    notify_claimants(post, "Status update: this item is now at the guard house. Approved claimants pick it up in person." + window)
    if ticket and ticket.finder_id != actor.pk:
        notify_user(ticket.finder, post, "The guard house confirmed it received the item. Thank you!")
    if post.author_id not in {actor.pk, ticket.finder_id if ticket else None}:
        notify_user(post.author, post, "This item is now at the guard house.")
    audit(actor, "guardhouse_intake", post, f"Method {method}; handed over by {handed_over_by_user or handed_over_by_name or 'unknown'}.")
    return post


@transaction.atomic
def request_status_change(post, actor, requested_status, reason, photo=None):
    post = ItemPost.objects.select_for_update().get(pk=post.pk)
    if post.status != ItemPost.Status.TURNED_OVER:
        raise ValueError("Status requests are only needed while the item is at the guard house.")
    if actor.pk != post.author_id and not post.turn_in_tickets.filter(finder=actor).exists():
        raise PermissionError("Only the finder can request a status change.")
    if not (reason or "").strip():
        raise ValueError("Write a reason for the request.")
    if post.status_requests.filter(requester=actor, decision=StatusChangeRequest.Decision.PENDING).exists():
        raise ValueError("You already have a pending request for this item.")
    request_row = StatusChangeRequest.objects.create(
        post=post, requester=actor, requested_status=requested_status, reason=reason.strip()[:1000], photo=photo or None,
    )
    for staff in staff_users():
        notify_user(staff, post, "A finder asked staff to change the status of an item at the guard house.")
    return request_row


@transaction.atomic
def review_status_change(request_row, actor, approve, note=""):
    if not is_staff_or_admin(actor):
        raise PermissionError("Only staff can review status requests.")
    request_row = StatusChangeRequest.objects.select_for_update().select_related("post").get(pk=request_row.pk)
    if request_row.decision != StatusChangeRequest.Decision.PENDING:
        return request_row
    post = request_row.post
    request_row.decision = StatusChangeRequest.Decision.APPROVED if approve else StatusChangeRequest.Decision.REJECTED
    request_row.reviewed_by = actor
    request_row.reviewed_at = timezone.now()
    request_row.review_note = (note or "").strip()[:500]
    request_row.save(update_fields=["decision", "reviewed_by", "reviewed_at", "review_note"])
    if approve and post.status == ItemPost.Status.TURNED_OVER:
        if request_row.requested_status == StatusChangeRequest.Requested.CLOSED:
            close_post(post, actor, f"Closed at the finder's request: {request_row.reason[:150]}")
        else:
            active = post.claims.filter(status__in=["SUBMITTED", "APPROVED"]).exists()
            new_status = ItemPost.Status.CLAIM_IN_PROGRESS if active else ItemPost.Status.OPEN
            record_status(post, new_status, actor, "Item taken back from the guard house at the finder's request.")
            post.turned_over_at = None
            post.save(update_fields=["turned_over_at", "updated_at"])
            GuardhouseIntake.objects.filter(post=post).delete()
            post.turn_in_tickets.update(requested_at=None, received_at=None)
    audit(actor, "approved_status_request" if approve else "rejected_status_request", request_row, request_row.review_note)
    verdict = "approved" if approve else "rejected"
    notify_user(
        request_row.requester, post,
        f"Staff {verdict} your status request." + (f" Note: {request_row.review_note}" if request_row.review_note else ""),
        priority=True,
    )
    return request_row


@transaction.atomic
def return_to_claimant(post, claim, actor):
    post = ItemPost.objects.select_for_update().get(pk=post.pk)
    claim = ClaimApplication.objects.select_for_update().select_related("claimant").get(pk=claim.pk, post=post)
    if claim.status != ClaimApplication.Status.APPROVED:
        raise ValueError("Approve this claim before recording the return.")
    if post.status in {ItemPost.Status.CLAIMED, ItemPost.Status.CLOSED, ItemPost.Status.RETURNED}:
        raise ValueError("This item has already been returned or closed.")
    if post.status == ItemPost.Status.TURNED_OVER:
        raise ValueError("This item is at the guard house; staff record the release there.")
    record_status(post, ItemPost.Status.RETURNED, actor, "Finder recorded the hand-off.", claim)
    post.returned_application = claim
    post.save(update_fields=["returned_application", "updated_at"])
    claim.status = ClaimApplication.Status.RETURNED
    claim.last_activity_at = timezone.now()
    claim.save(update_fields=["status", "last_activity_at"])
    for other in post.claims.exclude(pk=claim.pk).filter(status__in=["SUBMITTED", "APPROVED"]):
        other.status = ClaimApplication.Status.CLOSED
        other.closed_at = timezone.now()
        other.close_reason = "The item was returned to another claimant."
        other.save(update_fields=["status", "closed_at", "close_reason"])
        if hasattr(other, "conversation"):
            close_conversation(other.conversation, "The item was returned.")
        notify_user(other.claimant, post, "Status update: this item has been returned. Other claimant details are private.", other)
    notify_user(claim.claimant, post, "The finder recorded that the item was returned to you. Confirm receipt when you have it.", claim, priority=True)
    if hasattr(claim, "conversation"):
        claim.conversation.is_closed = False
        claim.conversation.save(update_fields=["is_closed", "updated_at"])
    return claim


@transaction.atomic
def confirm_claimed(post, actor, claim=None, witnessed=False, recipient=None):
    post = ItemPost.objects.select_for_update().get(pk=post.pk)
    if claim is None:
        if not witnessed or not is_staff_or_admin(actor):
            raise PermissionError("A staff member must witness a guard-house pickup.")
        recipient_user = recipient
        related_claim = None
    else:
        claim = ClaimApplication.objects.select_for_update().select_related("claimant").get(pk=claim.pk, post=post)
        if post.status == ItemPost.Status.CLAIMED:
            return post
        guardhouse_release = (
            post.status == ItemPost.Status.TURNED_OVER and witnessed and is_staff_or_admin(actor)
            and claim.status == ClaimApplication.Status.APPROVED
        )
        if post.returned_application_id != claim.pk and not guardhouse_release:
            raise PermissionError("Only the selected claimant can confirm this hand-off.")
        if actor.pk != claim.claimant_id and not (witnessed and is_staff_or_admin(actor)):
            raise PermissionError("Only the claimant can confirm receipt.")
        recipient_user = claim.claimant
        related_claim = claim
    post.claimed_by_user = recipient_user
    post.claimed_at = timezone.now()
    post.closed_at = timezone.now()
    post.closed_reason = "Claim completed."
    record_status(post, ItemPost.Status.CLAIMED, actor, "Receipt confirmed.", related_claim)
    post.is_archived = True
    post.archived_at = timezone.now()
    post.save(update_fields=["claimed_by_user", "claimed_at", "closed_at", "closed_reason", "is_archived", "archived_at", "updated_at"])
    if claim:
        claim.status = ClaimApplication.Status.COMPLETED
        claim.closed_at = timezone.now()
        claim.save(update_fields=["status", "closed_at"])
    for other in post.claims.exclude(status__in=[ClaimApplication.Status.CLOSED, ClaimApplication.Status.EXPIRED, ClaimApplication.Status.COMPLETED]):
        other.status = ClaimApplication.Status.CLOSED
        other.closed_at = timezone.now()
        other.close_reason = "The item has been claimed."
        other.save(update_fields=["status", "closed_at", "close_reason"])
    for conversation in post.conversations.all():
        close_conversation(conversation, "The claim is complete.")
    notify_claimants(post, "Status update: this item has been claimed. Other claimant details are private.")
    if witnessed:
        audit(actor, "witnessed_guardhouse_pickup", post, f"Claimed by account {recipient_user.pk}.")
    return post


@transaction.atomic
def close_post(post, actor, reason=""):
    post = ItemPost.objects.select_for_update().get(pk=post.pk)
    record_status(post, ItemPost.Status.CLOSED, actor, reason or "Listing closed.")
    post.closed_at = timezone.now()
    post.closed_reason = reason[:240]
    post.is_archived = True
    post.archived_at = timezone.now()
    post.save(update_fields=["closed_at", "closed_reason", "is_archived", "archived_at", "updated_at"])
    for claim in post.claims.filter(status__in=ClaimApplication.ACTIVE_STATUSES):
        claim.status = ClaimApplication.Status.CLOSED
        claim.closed_at = timezone.now()
        claim.close_reason = reason[:240] or "Listing closed."
        claim.save(update_fields=["status", "closed_at", "close_reason"])
        if hasattr(claim, "conversation"):
            close_conversation(claim.conversation, "Listing closed.")
    for conversation in post.conversations.all():
        close_conversation(conversation, "Listing closed.")
    notify_claimants(post, "Status update: this listing is closed.")
    if is_staff_or_admin(actor):
        audit(actor, "closed_post", post, reason)
    return post


def archive_post(post, actor):
    if not post.is_archived:
        post.is_archived = True
        post.archived_at = timezone.now()
        post.save(update_fields=["is_archived", "archived_at", "updated_at"])
    if is_staff_or_admin(actor):
        audit(actor, "archived_post", post, "Removed from active listings; history retained.")
    return post


def prune_idempotency_keys():
    from .models import IdempotencyKey
    IdempotencyKey.objects.filter(created_at__lt=timezone.now() - timedelta(days=2)).delete()


def process_due_actions():
    prune_idempotency_keys()
    now = timezone.now()
    settings_row = SystemSettings.current()
    # v1.1.1: claims by unverified students expire sooner (System settings, default 3 days).
    from .verification import claim_expiry_days, clear_expired_id_conflicts
    shortest = min(7, settings_row.unverified_claim_expiry_days or 3)
    candidates = ClaimApplication.objects.filter(
        status__in=ClaimApplication.ACTIVE_STATUSES,
        last_activity_at__lt=now - timedelta(days=shortest),
    ).select_related("post", "claimant", "claimant__profile")
    for claim in candidates:
        days = claim_expiry_days(claim.claimant)
        if claim.last_activity_at >= now - timedelta(days=days):
            continue
        idle_text = "seven days" if days == 7 else f"{days} day{'s' if days != 1 else ''}"
        was_selected_return = claim.post.returned_application_id == claim.pk
        claim.status = ClaimApplication.Status.EXPIRED
        claim.closed_at = now
        claim.close_reason = f"No activity for {idle_text}."
        claim.save(update_fields=["status", "closed_at", "close_reason"])
        if was_selected_return:
            claim.post.returned_application = None
            claim.post.save(update_fields=["returned_application", "updated_at"])
            record_status(claim.post, ItemPost.Status.OPEN, None, "The selected claim expired; the item is available again.")
        if hasattr(claim, "conversation"):
            close_conversation(claim.conversation, f"No activity for {idle_text}.")
        notify_user(claim.claimant, claim.post, f"Your claim closed after {idle_text} without activity.", claim)
        notify_user(claim.finder_user, claim.post, f"A claim on your post closed after {idle_text} without activity.", claim)
        reopen_if_no_active_claims(claim.post, None)

    clear_expired_id_conflicts()
    from .chat_media import fail_stuck_uploads
    fail_stuck_uploads()

    if settings_row.guardhouse_grace_days:
        cutoff = now - timedelta(days=settings_row.guardhouse_grace_days)
        for post in ItemPost.objects.filter(status=ItemPost.Status.TURNED_OVER, turned_over_at__lt=cutoff):
            close_post(post, None, "Guard-house grace period ended.")

    if settings_row.archive_purge_days:
        cutoff = now - timedelta(days=settings_row.archive_purge_days)
        eligible = ItemPost.objects.filter(is_archived=True, archived_at__lt=cutoff)
        for post in eligible:
            has_open_report = AbuseReport.objects.filter(
                status__in=OPEN_REPORT_STATUSES,
                conversation__post=post,
            ).exists() or GeneralReport.objects.filter(
                status__in=OPEN_REPORT_STATUSES,
                post=post,
            ).exists()
            if not has_open_report:
                post.delete()


# ---------------------------------------------------------------------------
# Approve / decline / re-apply
# ---------------------------------------------------------------------------

def reopen_if_no_active_claims(post, actor):
    post.refresh_from_db(fields=["status"])
    if post.status == ItemPost.Status.CLAIM_IN_PROGRESS:
        if not post.claims.filter(status__in=["SUBMITTED", "APPROVED"]).exists():
            record_status(post, ItemPost.Status.OPEN, actor, "No active claims remain.")


def can_decide_claim(user, claim):
    """FOUND posts: the post author or staff. LOST posts: the finder in that chat or staff."""
    if not getattr(user, "is_authenticated", False):
        return False
    return user.pk == claim.finder_user.pk or is_staff_or_admin(user)


def claim_counts(post):
    claims = post.claims.all()
    return {
        "claiming": claims.filter(status__in=ClaimApplication.ACTIVE_STATUSES).count(),
        "approved": claims.filter(status__in=["APPROVED", "RETURNED"]).count(),
    }


def current_round_questions(conversation):
    """Questions asked for the conversation's current claim (a re-application starts a new round)."""
    questions = conversation.questions.all()
    if conversation.claim_id:
        questions = questions.filter(asked_at__gte=conversation.claim.submitted_at)
    return questions


def chat_questions_ready(claim):
    """LOST reports need at least three answered question cards (none pending) before approval."""
    conversation = getattr(claim, "conversation", None)
    if conversation is None:
        return False
    questions = current_round_questions(conversation)
    answered = questions.filter(answered_at__isnull=False).count()
    return answered >= MIN_POST_QUESTIONS and answered == questions.count()


@transaction.atomic
def approve_claim(claim, actor):
    claim = ClaimApplication.objects.select_for_update().select_related("post", "claimant", "finder").get(pk=claim.pk)
    if not can_decide_claim(actor, claim):
        raise PermissionError("Only the finder or authorized staff can approve this claim.")
    if claim.status == ClaimApplication.Status.APPROVED:
        return claim
    if claim.status != ClaimApplication.Status.SUBMITTED:
        raise ValueError("Only a submitted claim can be approved.")
    if claim.post.status in {ItemPost.Status.CLAIMED, ItemPost.Status.CLOSED}:
        raise ValueError("This listing is already resolved.")
    if claim.is_lost_report and not chat_questions_ready(claim):
        raise ValueError("Send at least three questions and wait until all of them are answered before approving.")
    claim.status = ClaimApplication.Status.APPROVED
    claim.approved_at = timezone.now()
    claim.approved_by = actor
    claim.last_activity_at = timezone.now()
    claim.save(update_fields=["status", "approved_at", "approved_by", "last_activity_at"])
    rank = claim.approval_rank
    notify_user(
        claim.claimant, claim.post,
        f"Your claim was approved. You are #{rank} in the approval order. Coordinate the hand-off in the chat.",
        claim, priority=True,
    )
    if is_staff_or_admin(actor) and actor.pk != claim.finder_user.pk:
        audit(actor, "approved_claim", claim, f"Approval #{rank}.")
        notify_user(claim.finder_user, claim.post, "Staff approved a claim on this item.", claim)
    return claim


@transaction.atomic
def decline_claim(claim, actor, reason=""):
    claim = ClaimApplication.objects.select_for_update().select_related("post", "claimant", "finder").get(pk=claim.pk)
    if not can_decide_claim(actor, claim):
        raise PermissionError("Only the finder or authorized staff can decline this claim.")
    if claim.status == ClaimApplication.Status.DECLINED:
        return claim
    if claim.status not in {ClaimApplication.Status.SUBMITTED, ClaimApplication.Status.APPROVED}:
        raise ValueError("This claim can no longer be declined.")
    reason = (reason or "").strip()[:500]
    claim.status = ClaimApplication.Status.DECLINED
    claim.declined_at = timezone.now()
    claim.declined_by = actor
    claim.decline_reason = reason
    claim.closed_at = timezone.now()
    claim.close_reason = "Declined."
    claim.save(update_fields=["status", "declined_at", "declined_by", "decline_reason", "closed_at", "close_reason"])
    if hasattr(claim, "conversation"):
        close_conversation(claim.conversation, "This claim was declined. The chat is read-only.")
    reopen_if_no_active_claims(claim.post, actor)
    text = "Your claim was declined." + (f" Reason: {reason}" if reason else "")
    if not claim.reapply_of_id:
        text += " You may re-apply once from My Claims."
    notify_user(claim.claimant, claim.post, text, claim, priority=True)
    if is_staff_or_admin(actor) and actor.pk != claim.finder_user.pk:
        audit(actor, "declined_claim", claim, reason or "No reason given.")
        notify_user(claim.finder_user, claim.post, "Staff declined a claim on this item.", claim)
    return claim


def reapply_status(post, user):
    """Return (can_apply, declined_claim_to_link). Declined claimants may re-apply once."""
    mine = post.claims.filter(claimant=user)
    if mine.filter(status__in=ClaimApplication.ACTIVE_STATUSES).exists():
        return False, None
    declined = mine.filter(status=ClaimApplication.Status.DECLINED).order_by("-declined_at")
    if not declined.exists():
        return True, None
    if mine.filter(reapply_of__isnull=False).exists():
        return False, None
    return True, declined.first()


# ---------------------------------------------------------------------------
# Chat question cards (FOUND claim chats and LOST finder chats)
# ---------------------------------------------------------------------------

def chat_roles(conversation):
    """(asker, answerer): the finder side asks, the claimant/owner side answers.

    Owner's rule (v2.1.0, CHG-011): whoever is the finder in a chat can send ownership questions.
    - LOST post: the person who messaged the author is the finder; the author (owner) answers.
    - FOUND post, claim chat: the claim's finder asks; the claimant answers.
    - FOUND post, chat without a claim ("Message poster"): the author is the finder and asks;
      the other person answers.
    """
    post = conversation.post
    if post.post_type == ItemPost.Type.LOST:
        finder = conversation.initiator if conversation.recipient_id == post.author_id else conversation.recipient
        return finder, post.author
    claim = conversation.claim
    if claim is None:
        if post.author_id not in (conversation.initiator_id, conversation.recipient_id):
            return None, None
        other = conversation.initiator if conversation.recipient_id == post.author_id else conversation.recipient
        return post.author, other
    return claim.finder_user, claim.claimant


def broadcast_conversation(conversation, payload):
    def send():
        layer = get_channel_layer()
        if layer:
            async_to_sync(layer.group_send)(f"conversation_{conversation.pk.hex}", {"type": "chat.event", "payload": payload})
    transaction.on_commit(send)  # BUG-004: only after the change is saved


def question_payload(question):
    return {
        "event": "question",
        "id": question.pk,
        "order": question.order,
        "text": question.text,
        "answer_type": question.answer_type,
        "choices": question.choices,
        "answered": question.is_answered,
        "answer": question.answer_text,
    }


@transaction.atomic
def ask_chat_questions(conversation, actor, templates):
    conversation = Conversation.objects.select_for_update().select_related("post", "claim").get(pk=conversation.pk)
    asker, answerer = chat_roles(conversation)
    if asker is None or actor.pk != asker.pk:
        raise PermissionError("Only the finder in this chat can send ownership questions.")
    if conversation.is_closed or conversation.is_paused:
        raise ValueError("This chat is read-only.")
    claim = conversation.claim
    if claim is not None and claim.status not in {"SUBMITTED", "APPROVED"}:
        raise ValueError("Questions can only be sent while the claim is being reviewed.")
    if conversation.post.post_type == ItemPost.Type.LOST and claim is None:
        claim = open_lost_report(conversation, actor)
    round_questions = current_round_questions(conversation)
    existing_ids = set(round_questions.values_list("template_id", flat=True))
    room = MAX_POST_QUESTIONS - round_questions.count()
    new = []
    for template in templates:
        if template.pk not in existing_ids and template not in new:
            new.append(template)
    new = new[:max(room, 0)]
    if not new:
        raise ValueError(f"Each round can hold at most {MAX_POST_QUESTIONS} different questions.")
    next_order = (conversation.questions.aggregate(m=models.Max("order"))["m"] or 0) + 1
    created = []
    for offset, template in enumerate(new):
        created.append(ChatQuestion.objects.create(
            conversation=conversation, order=next_order + offset, template=template, text=template.text,
            answer_type=template.answer_type, choices=list(template.choices or []), asked_by=actor,
        ))
    if claim:
        ClaimApplication.objects.filter(pk=claim.pk).update(last_activity_at=timezone.now())
    notify_user(answerer, conversation.post, f"{len(created)} ownership question(s) are waiting for you in the chat.", claim, priority=True)
    for question in created:
        broadcast_conversation(conversation, question_payload(question))
    return created


@transaction.atomic
def answer_chat_question(question, actor, answer):
    question = ChatQuestion.objects.select_for_update().select_related("conversation", "conversation__post", "conversation__claim").get(pk=question.pk)
    conversation = question.conversation
    asker, answerer = chat_roles(conversation)
    if answerer is None or actor.pk != answerer.pk:
        raise PermissionError("Only the claimant can answer these questions.")
    if conversation.is_closed or conversation.is_paused:
        raise ValueError("This chat is read-only.")
    if question.is_answered:
        return question
    answer = (answer or "").strip()
    if not answer:
        raise ValueError("Write or choose an answer.")
    if question.answer_type == "CHOICE" and question.choices and answer not in question.choices:
        raise ValueError("Choose one of the listed answers.")
    question.answer_text = answer[:1200]
    question.answered_by = actor
    question.answered_at = timezone.now()
    question.save(update_fields=["answer_text", "answered_by", "answered_at"])
    if conversation.claim_id:
        ClaimApplication.objects.filter(pk=conversation.claim_id).update(last_activity_at=timezone.now())
    remaining = conversation.questions.filter(answered_at__isnull=True).count()
    text = "All ownership questions were answered. Review them in the chat." if remaining == 0 else "An ownership question was answered."
    notify_user(asker, conversation.post, text, conversation.claim, priority=True)
    broadcast_conversation(conversation, question_payload(question))
    return question


def open_lost_report(conversation, finder):
    """The first question a finder sends on a LOST post opens a verification record
    (a ClaimApplication with the owner as claimant and this finder as verifier)."""
    post = conversation.post
    claim = ClaimApplication.objects.create(
        post=post, claimant=post.author, finder=finder, description="",
    )
    conversation.claim = claim
    conversation.save(update_fields=["claim", "updated_at"])
    if post.status == ItemPost.Status.OPEN:
        record_status(post, ItemPost.Status.CLAIM_IN_PROGRESS, finder, "A finder started verifying the owner.", claim)
    return claim


@transaction.atomic
def reopen_lost_report(conversation, owner):
    """LOST re-apply: the owner asks the finder to verify them once more."""
    conversation = Conversation.objects.select_for_update().select_related("post", "claim").get(pk=conversation.pk)
    old = conversation.claim
    if old is None or old.status != ClaimApplication.Status.DECLINED or owner.pk != old.claimant_id:
        raise PermissionError("Only a declined owner can ask to be verified again.")
    if old.reapply_of_id or old.reapplications.exists():
        raise ValueError("You have already used your one re-application.")
    claim = ClaimApplication.objects.create(
        post=old.post, claimant=owner, finder=old.finder, reapply_of=old, description="",
    )
    conversation.claim = claim
    conversation.is_closed = False
    conversation.pause_reason = ""
    conversation.save(update_fields=["claim", "is_closed", "pause_reason", "updated_at"])
    if old.post.status == ItemPost.Status.OPEN:
        record_status(old.post, ItemPost.Status.CLAIM_IN_PROGRESS, owner, "Owner asked to be verified again.", claim)
    notify_user(old.finder, old.post, "The owner asked to be verified again. Send new questions in the chat.", claim, priority=True)
    return claim


# ---------------------------------------------------------------------------
# Report review and moderator verification (session 1)
# ---------------------------------------------------------------------------

def record_report_submission(report, reporter):
    """First history row for a newly submitted chat or general report."""
    kwargs = {"chat_report": report} if isinstance(report, AbuseReport) else {"general_report": report}
    ReportStatusEvent.objects.create(previous_status="", new_status=report.status, actor=reporter, **kwargs)


@transaction.atomic
def review_report_status(report, actor, action, remarks=""):
    """Apply a reviewer decision to an AbuseReport or GeneralReport and record it in the history.

    action is a ReportStatus value, or "NOTE" to add remarks without changing status.
    """
    now = timezone.now()
    previous = report.status
    remarks = (remarks or "").strip()
    remarks_field = "admin_note" if isinstance(report, AbuseReport) else "internal_remarks"
    fields = []
    if action != "NOTE":
        report.status = action
        fields.append("status")
        if action == ReportStatus.UNDER_REVIEW:
            report.assigned_reviewer = actor
            report.resolved_at = None
            fields += ["assigned_reviewer", "resolved_at"]
        if action in CLOSED_REPORT_STATUSES:
            report.resolved_at = now
            fields.append("resolved_at")
            if not report.assigned_reviewer_id:
                report.assigned_reviewer = actor
                fields.append("assigned_reviewer")
    if remarks:
        setattr(report, remarks_field, remarks)
        fields.append(remarks_field)
    report.reviewed_by = actor
    report.reviewed_at = now
    fields += ["reviewed_by", "reviewed_at"]
    report.save(update_fields=fields)
    kwargs = {"chat_report": report} if isinstance(report, AbuseReport) else {"general_report": report}
    ReportStatusEvent.objects.create(
        previous_status=previous, new_status=report.status, actor=actor, note=remarks, **kwargs,
    )
    audit(actor, f"report_{action.lower()}", report, f"{report.reference}: {previous} → {report.status}")
    return report


MODERATOR_TRANSITIONS = {
    # action: (allowed current statuses, new status). None means "no verification record yet".
    "request": ({None, ModeratorVerification.Status.REJECTED, ModeratorVerification.Status.REVOKED},
                ModeratorVerification.Status.PENDING),
    "approve": ({ModeratorVerification.Status.PENDING}, ModeratorVerification.Status.VERIFIED),
    "reject": ({ModeratorVerification.Status.PENDING}, ModeratorVerification.Status.REJECTED),
    "revoke": ({ModeratorVerification.Status.VERIFIED, ModeratorVerification.Status.PENDING},
               ModeratorVerification.Status.REVOKED),
}


class ModeratorTransitionError(Exception):
    pass


@transaction.atomic
def change_moderator_verification(staff_user, actor, action, remarks=""):
    if action not in MODERATOR_TRANSITIONS:
        raise ModeratorTransitionError("Unknown moderator action.")
    if staff_user.profile.role != Profile.Role.STAFF or staff_user.is_superuser:
        raise ModeratorTransitionError("Moderator authorization can only be given to Staff accounts.")
    verification = ModeratorVerification.objects.select_for_update().filter(staff=staff_user).first()
    current = verification.status if verification else None
    allowed, new_status = MODERATOR_TRANSITIONS[action]
    if current not in allowed:
        raise ModeratorTransitionError("That change is not allowed from the current verification status.")
    now = timezone.now()
    remarks = (remarks or "").strip()[:500]
    if verification is None:
        verification = ModeratorVerification(staff=staff_user)
    verification.status = new_status
    verification.remarks = remarks
    if action == "request":
        verification.requested_by = actor
        verification.requested_at = now
        verification.reviewed_by = None
        verification.decided_at = None
    else:
        verification.reviewed_by = actor
        verification.decided_at = now
    verification.save()
    ModeratorVerificationEvent.objects.create(
        verification=verification, previous_status=current or "", new_status=new_status, actor=actor, remarks=remarks,
    )
    audit(actor, f"moderator_{action}", verification, f"{staff_user.username}: {current or 'none'} → {new_status}")
    return verification


def revoke_moderator_if_not_staff(user, actor):
    """Called after a role change: only Staff accounts can keep moderator authorization."""
    verification = ModeratorVerification.objects.filter(staff=user).first()
    if user.profile.role == Profile.Role.STAFF or verification is None:
        return
    if verification.status in {ModeratorVerification.Status.VERIFIED, ModeratorVerification.Status.PENDING}:
        previous = verification.status
        verification.status = ModeratorVerification.Status.REVOKED
        verification.reviewed_by = actor
        verification.decided_at = timezone.now()
        verification.remarks = "Automatically revoked because the account is no longer Staff."
        verification.save()
        ModeratorVerificationEvent.objects.create(
            verification=verification, previous_status=previous, new_status=verification.status,
            actor=actor, remarks=verification.remarks,
        )


# ---- CHG-019 (v2.1.0): Contact staff — one shared staff inbox ----
MAX_OPEN_HELP_REQUESTS = 5


def _staff_team():
    from .permissions import STAFF_ROLES
    return get_user_model().objects.filter(is_active=True, profile__role__in=STAFF_ROLES)


@transaction.atomic
def open_staff_help(requester, subject, text, post=None):
    """A student asks the staff team for help. Every staff member and administrator is told."""
    from django.urls import reverse
    from .models import StaffHelpMessage, StaffHelpThread
    from .verification import notify_account
    subject, text = (subject or "").strip()[:120], (text or "").strip()[:2000]
    if not text:
        raise ValueError("Write what you need help with.")
    open_count = StaffHelpThread.objects.filter(requester=requester).exclude(status=StaffHelpThread.Status.RESOLVED).count()
    if open_count >= MAX_OPEN_HELP_REQUESTS:
        raise ValueError(f"You already have {open_count} open requests. Add to one of them, or wait until staff resolve one.")
    if not subject:
        subject = f"About: {post.display_title}" if post else "Help request"
    thread = StaffHelpThread.objects.create(requester=requester, post=post, subject=subject)
    StaffHelpMessage.objects.create(thread=thread, sender=requester, text=text)
    link = reverse("staff-help-thread", args=[thread.pk])
    for member in _staff_team().exclude(pk=requester.pk):
        notify_account(member, f"New request in the staff inbox: {subject}", link=link, priority=True)
    audit(requester, "opened_staff_help", thread, subject)
    return thread


@transaction.atomic
def add_staff_help_message(thread, sender, text):
    from django.urls import reverse
    from .models import StaffHelpMessage, StaffHelpThread
    from .permissions import is_staff_or_admin
    from .verification import notify_account
    text = (text or "").strip()[:2000]
    if not text:
        raise ValueError("Write a message first.")
    thread = StaffHelpThread.objects.select_for_update().get(pk=thread.pk)
    staff_side = is_staff_or_admin(sender) and sender.pk != thread.requester_id
    if not staff_side and sender.pk != thread.requester_id:
        raise PermissionError("Only the person who asked and the staff team can write here.")
    message = StaffHelpMessage.objects.create(thread=thread, sender=sender, text=text, from_staff=staff_side)
    thread.status = StaffHelpThread.Status.ANSWERED if staff_side else StaffHelpThread.Status.OPEN
    thread.save(update_fields=["status", "updated_at"])
    link = reverse("staff-help-thread", args=[thread.pk])
    if staff_side:
        notify_account(thread.requester, f"Staff replied to your request: {thread.subject}", link=link, priority=True)
    else:
        for member in _staff_team().exclude(pk=sender.pk):
            notify_account(member, f"New message in the staff inbox: {thread.subject}", link=link, priority=True)
    return message


def set_staff_help_status(thread, actor, resolved):
    from .models import StaffHelpThread
    thread.status = StaffHelpThread.Status.RESOLVED if resolved else StaffHelpThread.Status.OPEN
    thread.save(update_fields=["status", "updated_at"])
    audit(actor, "resolved_staff_help" if resolved else "reopened_staff_help", thread, "")
    return thread
