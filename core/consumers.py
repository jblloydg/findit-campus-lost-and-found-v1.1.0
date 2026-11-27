import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db import IntegrityError
from django.utils import timezone

from .models import ChatMessage, ClaimApplication, Conversation
from .permissions import can_review_private_chats


def _staff_user(user):
    """Only administrators and verified moderators may open other people's chats."""
    if not user.is_authenticated:
        return False
    return can_review_private_chats(user)


class ConversationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.group_name = f"conversation_{self.conversation_id.hex}"
        user = self.scope["user"]
        allowed = await self._can_view(user.pk if user.is_authenticated else None)
        if not allowed:
            await self.close(code=4403)
            return
        self.can_send = await self._can_send(user.pk)
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
        limit = await self._limit_message(message, client_id)
        if limit:
            await self.send(text_data=json.dumps({"type": "error", "message": limit, "client_id": client_id}))
            return
        stored = await self._save_message(self.scope["user"].pk, message, client_id)
        if not stored:
            await self.send(text_data=json.dumps({"type": "error", "message": "This conversation is no longer open."}))
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

    @database_sync_to_async
    def _limit_message(self, text, client_id=""):
        """v1.1.1: unverified students have a per-message length and a messages-per-window limit.
        A resend of a message that is already saved (same client_id) is never counted again."""
        from django.contrib.auth import get_user_model
        from .verification import chat_limit_message
        if client_id and ChatMessage.objects.filter(conversation_id=self.conversation_id, client_id=client_id).exists():
            return None
        user = get_user_model().objects.select_related("profile").filter(pk=self.scope["user"].pk).first()
        if user is None:
            return "Please sign in again."
        return chat_limit_message(user, text)

    @database_sync_to_async
    def _save_message(self, user_id, text, client_id=""):
        conversation = Conversation.objects.select_related("post", "claim").filter(pk=self.conversation_id).first()
        if not self.scope["user"].is_active or not conversation or conversation.is_closed or conversation.is_paused:
            return None
        if user_id not in {conversation.initiator_id, conversation.recipient_id}:
            return None
        if client_id:
            # A resend after a dropped connection carries the same id: save once.
            try:
                message, created = ChatMessage.objects.get_or_create(
                    conversation=conversation, client_id=client_id,
                    defaults={"sender_id": user_id, "text": text},
                )
            except IntegrityError:
                # Two copies arrived at the same moment: the other one was saved; use it.
                message, created = ChatMessage.objects.get(conversation=conversation, client_id=client_id), False
            if not created:
                if message.sender_id != user_id:
                    return None  # an id belongs to the person who sent it
                return self._serialize(message, user_id)
        else:
            message = ChatMessage.objects.create(conversation=conversation, sender_id=user_id, text=text)
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["updated_at"])
        if conversation.claim_id:
            ClaimApplication.objects.filter(pk=conversation.claim_id).update(last_activity_at=timezone.now())
        return self._serialize(message, user_id)

    @staticmethod
    def _serialize(message, user_id):
        return {
            "id": message.pk,
            "sender": message.sender.get_full_name() or message.sender.username,
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

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_created(self, event):
        await self.send(text_data=json.dumps({
            "type": "notification",
            "id": event["id"],
            "text": event["text"],
        }))
