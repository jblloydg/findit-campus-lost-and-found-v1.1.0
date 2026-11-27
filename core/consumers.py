import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db import IntegrityError, models
from django.utils import timezone

from .models import ChatMessage, ClaimApplication, Conversation
from .permissions import can_review_private_chats


def _staff_user(user):
    """Only administrators and verified moderators may open other people's chats."""
    if not user.is_authenticated:
        return False
    return can_review_private_chats(user)


class ConversationConsumer(AsyncWebsocketConsumer):
    # PERF-002: chat database work runs in its own worker threads (not behind page loads).
    # Tests that keep all their data in one unsaved transaction switch this to True.
    DB_THREAD_SENSITIVE = False

    async def connect(self):
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.group_name = f"conversation_{self.conversation_id.hex}"
        user = self.scope["user"]
        allowed = await self._can_view(user.pk if user.is_authenticated else None)
        if not allowed:
            await self.close(code=4403)
            return
        self.can_send = await self._can_send(user.pk)
        await database_sync_to_async(self._load_sender, thread_sensitive=self.DB_THREAD_SENSITIVE)()
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            "type": "connection",
            "can_send": self.can_send,
            "notice": "Messages are private to participants and authorized staff.",
        }))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not self.can_send or not text_data:
            await self.send(text_data=json.dumps({"type": "error", "message": "This conversation is read-only."}))
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"type": "error", "message": "Invalid message."}))
            return
        if not isinstance(payload, dict):
            # BUG-005: valid JSON that is not an object (e.g. [1] or "hi") used to crash the connection.
            await self.send(text_data=json.dumps({"type": "error", "message": "Invalid message."}))
            return
        message = str(payload.get("message", "")).strip()
        client_id = str(payload.get("client_id", ""))[:64]
        if not message:
            return
        if len(message) > 2000:
            await self.send(text_data=json.dumps({"type": "error", "message": "Messages must be 2,000 characters or fewer."}))
            return
        # PERF-002: one trip to the database per message, in its own worker thread so
        # chat never waits behind page loads.
        stored, problem = await database_sync_to_async(self._handle_message, thread_sensitive=self.DB_THREAD_SENSITIVE)(message, client_id)
        if problem:
            await self.send(text_data=json.dumps({"type": "error", "message": problem, "client_id": client_id}))
            return
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.message",
                "id": stored["id"],
                "sender": stored["sender"],
                "sender_id": stored["sender_id"],
                "text": stored["text"],
                "sent_at": stored["sent_at"],
                "client_id": stored["client_id"],
            },
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "message",
            "id": event["id"],
            "sender": event["sender"],
            "sender_id": event["sender_id"],
            "text": event["text"],
            "sent_at": event["sent_at"],
            "client_id": event.get("client_id", ""),
        }))

    async def chat_event(self, event):
        """Question-card and claim updates pushed by the server."""
        await self.send(text_data=json.dumps({"type": "event", **event.get("payload", {})}))

    @database_sync_to_async
    def _can_view(self, user_id):
        if user_id is None:
            return False
        if not self.scope["user"].is_active:
            return False
        conversation = Conversation.objects.select_related("initiator", "recipient").filter(pk=self.conversation_id).first()
        if not conversation:
            return False
        user = self.scope["user"]
        return conversation.includes(user) or _staff_user(user)

    @database_sync_to_async
    def _can_send(self, user_id):
        conversation = Conversation.objects.filter(pk=self.conversation_id).first()
        if not self.scope["user"].is_active or not conversation or user_id not in {conversation.initiator_id, conversation.recipient_id}:
            return False
        return not conversation.is_closed and not conversation.is_paused

    SENDER_REFRESH_SECONDS = 60

    def _load_sender(self):
        """Facts about the sender, kept for a minute instead of re-read for every message."""
        from django.contrib.auth import get_user_model
        from .models import SystemSettings
        from .permissions import is_unverified_student
        user = get_user_model().objects.select_related("profile").filter(pk=self.scope["user"].pk).first()
        conversation = Conversation.objects.filter(pk=self.conversation_id).only("claim_id").first()
        self.sender_active = bool(user and user.is_active)
        self.sender_name = (user.get_full_name() or user.username) if user else ""
        self.sender_unverified = bool(user and is_unverified_student(user))
        self.limits = SystemSettings.current() if self.sender_unverified else None
        self.claim_id = conversation.claim_id if conversation else None
        self.sender_loaded_at = timezone.now()

    def _handle_message(self, text, client_id=""):
        """Save one chat message. Returns (message, None) or (None, reason)."""
        from datetime import timedelta
        from django.db import close_old_connections, transaction
        close_old_connections()
        try:
            if (timezone.now() - self.sender_loaded_at).total_seconds() > self.SENDER_REFRESH_SECONDS:
                self._load_sender()
            if not self.sender_active:
                return None, "This conversation is no longer open."
            user_id = self.scope["user"].pk
            with transaction.atomic():
                if client_id:
                    # A resend after a dropped connection carries the same id: save once,
                    # and never count it again against the limits.
                    existing = ChatMessage.objects.filter(conversation_id=self.conversation_id, client_id=client_id).first()
                    if existing:
                        if existing.sender_id != user_id:
                            return None, "This conversation is no longer open."  # ids belong to their sender
                        return self._serialize(existing, user_id), None
                if self.sender_unverified:
                    row = self.limits
                    if len(text) > (row.unverified_chat_max_chars or 100):
                        return None, (f"Unverified accounts can send up to {row.unverified_chat_max_chars} characters "
                                      "per message. Verify your email to send longer messages.")
                    window = row.unverified_chat_window_minutes or 10
                    limit = row.unverified_chat_messages or 10
                    since = timezone.now() - timedelta(minutes=window)
                    if ChatMessage.objects.filter(sender_id=user_id, sent_at__gte=since).count() >= limit:
                        return None, (f"Unverified accounts can send {limit} messages every {window} minutes. "
                                      "Please wait, or verify your email.")
                now = timezone.now()
                still_open = Conversation.objects.filter(
                    pk=self.conversation_id, is_closed=False, is_paused=False,
                ).filter(models.Q(initiator_id=user_id) | models.Q(recipient_id=user_id)).update(updated_at=now)
                if not still_open:
                    return None, "This conversation is no longer open."
                try:
                    with transaction.atomic():
                        message = ChatMessage.objects.create(
                            conversation_id=self.conversation_id, sender_id=user_id, text=text, client_id=client_id,
                        )
                except IntegrityError:
                    # Two copies arrived at the same moment: the other one was saved; use it.
                    message = ChatMessage.objects.get(conversation_id=self.conversation_id, client_id=client_id)
                    if message.sender_id != user_id:
                        return None, "This conversation is no longer open."
                if self.claim_id:
                    ClaimApplication.objects.filter(pk=self.claim_id).update(last_activity_at=now)
            return self._serialize(message, user_id), None
        finally:
            close_old_connections()

    def _serialize(self, message, user_id):
        return {
            "id": message.pk,
            "sender": self.sender_name,
            "sender_id": user_id,
            "text": message.text,
            "sent_at": message.sent_at.isoformat(),
            "client_id": message.client_id,
        }


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4403)
            return
        self.group_name = f"notifications_{user.pk}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        # The saved notifications are the queue: on every (re)connect the browser gets the
        # true unread counts, so nothing is missed while the connection was down.
        await self.send(text_data=json.dumps({"type": "sync", **(await self._counts())}))

    async def receive(self, text_data=None, bytes_data=None):
        """{"type": "since", "after_id": N}: the newest unread notices the browser has not shown yet."""
        try:
            payload = json.loads(text_data or "")
        except json.JSONDecodeError:
            return
        if isinstance(payload, dict) and payload.get("type") == "sync":
            # BUG-006: notices made by the timer runner (another program) cannot be pushed
            # live, so open pages ask about once a minute.
            await self.send(text_data=json.dumps({"type": "sync", **(await self._counts())}))
            return
        if not isinstance(payload, dict) or payload.get("type") != "since":
            return
        try:
            after_id = int(payload.get("after_id") or 0)
        except (TypeError, ValueError):
            return
        for row in await self._missed(after_id):
            await self.send(text_data=json.dumps({"type": "notification", **row}))

    @database_sync_to_async
    def _counts(self):
        from .models import InAppNotification
        unread = InAppNotification.objects.filter(recipient_id=self.scope["user"].pk, read_at__isnull=True)
        latest = InAppNotification.objects.filter(recipient_id=self.scope["user"].pk).order_by("-pk").first()
        return {
            "unread": unread.count(), "priority": unread.filter(is_priority=True).count(),
            "latest_id": latest.pk if latest else 0,
        }

    @database_sync_to_async
    def _missed(self, after_id):
        from .models import InAppNotification
        rows = InAppNotification.objects.filter(
            recipient_id=self.scope["user"].pk, read_at__isnull=True, pk__gt=after_id,
        ).order_by("-pk")[:5]
        return [{"id": n.pk, "text": n.text, "priority": n.is_priority, "catch_up": True} for n in reversed(list(rows))]

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_created(self, event):
        await self.send(text_data=json.dumps({
            "type": "notification",
            "id": event["id"],
            "text": event["text"],
            "priority": bool(event.get("priority")),
        }))
