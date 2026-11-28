"""v2.1.0 tests."""
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

# ---- DES-006: Report an item wide layout (create / edit post, walk-in) ----
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR, "static", "css", "findit.css").read_text(encoding="utf-8")

# Every field the post form sent before the redesign; the layout change must keep them all.
FIELD_NAMES = ["post_type", "category", "photos", "title", "description", "approximate_date", "approximate_time", "questions"]


class PostFormLayoutCssTests(SimpleTestCase):
    def test_two_columns_on_pc_one_on_phones(self):
        self.assertIn("grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);", CSS)
        self.assertIn(".post-form-grid { grid-template-columns: minmax(0, 1fr); }", CSS)


class PostFormLayoutPageTests(FindItTestCase):
    def assert_fields_kept(self, response):
        for name in FIELD_NAMES:
            self.assertContains(response, f'name="{name}"')
        for element_id in ["verification-questions", "question-list", "question-search", "question-picked",
                           "photo-preview-grid", "photo-count", "human-check"]:
            self.assertContains(response, f'id="{element_id}"')

    def test_create_page_has_the_wide_layout_and_every_field(self):
        response = self.client_for(self.finder).get("/posts/new/?type=FOUND")
        for part in ["post-form-grid", "post-form-details", "post-form-photos", "post-form-side", "post-form-submit"]:
            self.assertContains(response, part)
        self.assertContains(response, "About the item")
        self.assertContains(response, "Meet-up reminder")
        self.assert_fields_kept(response)

    def test_edit_page(self):
        post = self.create_post()
        response = self.client_for(self.finder).get(f"/posts/{post.pk}/edit/")
        self.assertContains(response, "post-form-grid")
        self.assertContains(response, "Save changes")
        self.assertContains(response, 'name="remove_photos"')

    def test_walk_in_page(self):
        response = self.client_for(self.staff).get("/staff/walk-in/")
        self.assertContains(response, "post-form-grid")
        self.assertContains(response, 'name="handed_over_by_name"')
        self.assertContains(response, "Post and record at guard house")

    def test_posting_still_works(self):
        from .base import photo
        from core.models import ItemPost
        response = self.client_for(self.finder).post("/posts/new/", {
            "post_type": "LOST", "category": self.category.pk, "title": "Blue umbrella", "photos": photo(),
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ItemPost.objects.filter(title="Blue umbrella", post_type="LOST").exists())


# ---- BUG-021: Messages icon in the top bar on every screen size ----
class MessagesIconAllSizesTests(FindItTestCase):
    def test_icon_never_hidden_by_css(self):
        self.assertNotRegex(CSS, r"\.icon-messages\s*\{[^}]*display:\s*none")

    def test_icon_and_count_in_top_bar(self):
        page = self.client_for(self.alice).get("/home/").content.decode()
        self.assertIn('class="icon-button icon-messages"', page)


# ---- BUG-023: "we posted and still no chat" — explain how a chat starts ----
class HowChatStartsTests(FindItTestCase):
    def test_messages_empty_state_explains_second_account(self):
        page = self.client_for(self.alice).get("/messages/").content.decode()
        self.assertIn("No chats yet", page)
        self.assertIn("another person", page)
        self.assertIn("You can't message your own post", page)

    def test_author_sees_no_chats_yet_then_the_chat(self):
        lost = self.create_post(self.alice, "LOST")
        author = self.client_for(self.alice)
        page = author.get(f"/p/{lost.pk}/").content.decode()
        self.assertIn("Chats about this post", page)
        self.assertIn("No one has messaged you about this post yet", page)
        self.client_for(self.finder).get(f"/p/{lost.pk}/?resume=message")
        conv = Conversation.objects.get(post=lost, initiator=self.finder)
        page = author.get(f"/p/{lost.pk}/").content.decode()
        self.assertNotIn("No one has messaged you about this post yet", page)
        self.assertIn(f"/conversations/{conv.pk}/", page)
        self.assertIn("May have found your item", page)

    def test_other_people_do_not_see_the_author_list(self):
        lost = self.create_post(self.alice, "LOST")
        self.assertNotIn("Chats about this post", self.client_for(self.finder).get(f"/p/{lost.pk}/").content.decode())
