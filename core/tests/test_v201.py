"""v2.0.1 tests (patch for v2.0.0)."""
from core.models import ChatQuestion, Conversation, InAppNotification, QuestionTemplate

from .base import FindItTestCase


class FinderAsksInFoundChatTests(FindItTestCase):
    """CHG-011: on a FOUND post, the author is the finder; in a chat without a claim
    ("Message poster") the author can send ownership questions and the other person answers."""

    def setUp(self):
        super().setUp()
        self.found = self.create_post(self.finder, "FOUND")
        self.owner_client = self.client_for(self.alice)
        self.finder_client = self.client_for(self.finder)
        self.owner_client.get(f"/p/{self.found.pk}/?resume=message")
        self.conv = Conversation.objects.get(post=self.found, initiator=self.alice)
        self.assertIsNone(self.conv.claim)
        self.templates = list(QuestionTemplate.objects.filter(is_default=True)[:3])

    def ask(self, client, templates):
        return client.post(f"/conversations/{self.conv.pk}/questions/", {"questions": [t.pk for t in templates]})

    def test_author_finder_sees_button_and_asks_other_person_answers(self):
        page = self.finder_client.get(f"/conversations/{self.conv.pk}/").content.decode()
        self.assertIn("＋ Questions (5 left)", page)
        self.assertIn("You found this item.", page)
        self.assertNotIn("＋ Questions", self.owner_client.get(f"/conversations/{self.conv.pk}/").content.decode())
        self.ask(self.finder_client, self.templates[:2])
        self.assertEqual(self.conv.questions.count(), 2)
        self.assertIn("＋ Questions (3 left)", self.finder_client.get(f"/conversations/{self.conv.pk}/").content.decode())
        self.assertTrue(InAppNotification.objects.filter(recipient=self.alice, is_priority=True).exists())
        for q in self.conv.questions.all():
            self.owner_client.post(f"/chat-questions/{q.pk}/answer/", {"answer": q.choices[0] if q.choices else "blue"})
        self.assertEqual(ChatQuestion.objects.filter(conversation=self.conv, answered_at__isnull=False).count(), 2)
        self.conv.refresh_from_db()
        self.assertIsNone(self.conv.claim)  # no claim is made; the owner still claims the normal way

    def test_other_person_cannot_ask_or_finder_answer(self):
        self.assertEqual(self.ask(self.owner_client, self.templates[:1]).status_code, 403)
        self.ask(self.finder_client, self.templates[:1])
        q = self.conv.questions.first()
        self.assertEqual(self.finder_client.post(f"/chat-questions/{q.pk}/answer/", {"answer": "x"}).status_code, 403)

    def test_at_most_five_questions(self):
        bank = list(QuestionTemplate.objects.filter(is_active=True)[:6])
        self.ask(self.finder_client, bank)
        self.assertEqual(self.conv.questions.count(), 5)
        self.assertNotIn("＋ Questions", self.finder_client.get(f"/conversations/{self.conv.pk}/").content.decode())
