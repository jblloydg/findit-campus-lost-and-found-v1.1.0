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
        self.assertIn('Ownership questions <span class="questions-left">(5 left)</span>', page)
        self.assertIn("You found this item.", page)
        self.assertNotIn("data-open-questions", self.owner_client.get(f"/conversations/{self.conv.pk}/").content.decode())
        self.ask(self.finder_client, self.templates[:2])
        self.assertEqual(self.conv.questions.count(), 2)
        self.assertIn('<span class="questions-left">(3 left)</span>', self.finder_client.get(f"/conversations/{self.conv.pk}/").content.decode())
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
        self.assertNotIn("data-open-questions", self.finder_client.get(f"/conversations/{self.conv.pk}/").content.decode())

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


# ---- CHG-013: clear finder action on LOST posts, near the top on phones ----
class FinderActionButtonTests(FindItTestCase):
    def test_lost_post_says_i_found_this(self):
        lost = self.create_post(self.alice, "LOST")
        page = self.client_for(self.finder).get(f"/p/{lost.pk}/").content.decode()
        self.assertIn("I found this – message the owner", page)
        self.assertNotIn("Message poster", page)
        # once under the title (phones) and once in the side box (PC); CSS shows one of them
        self.assertEqual(page.count("I found this – message the owner</a>"), 2)
        self.assertIn('class="primary-actions top-actions"', page)

    def test_found_post_keeps_message_poster(self):
        found = self.create_post(self.finder, "FOUND")
        page = self.client_for(self.alice).get(f"/p/{found.pk}/").content.decode()
        self.assertIn("Message poster", page)
        self.assertNotIn("I found this – message the owner", page)

    def test_author_has_no_finder_button(self):
        lost = self.create_post(self.alice, "LOST")
        self.assertNotIn("I found this – message the owner</a>", self.client_for(self.alice).get(f"/p/{lost.pk}/").content.decode())

    def test_button_still_opens_the_chat(self):
        lost = self.create_post(self.alice, "LOST")
        response = self.client_for(self.finder).get(f"/p/{lost.pk}/?resume=message")
        conv = Conversation.objects.get(post=lost, initiator=self.finder)
        self.assertRedirects(response, f"/conversations/{conv.pk}/", fetch_redirect_response=False)

    def test_css_shows_top_copy_only_on_small_screens(self):
        self.assertIn(".top-actions { display: none; }", CSS)
        self.assertRegex(CSS, r"@media \(max-width: 56em\) \{\s*\.top-actions \{ display: grid")


# ---- CHG-014: two tester accounts that already chat with each other ----
import os
import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from core import demo_logins
from core.models import ItemPost


class TesterAccountsTests(TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="findit-testers-")
        self.logins = os.path.join(self.folder, "demo-logins.txt")
        self.fixed = os.path.join(self.folder, "tester-passwords.txt")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def seed(self):
        with override_settings(DEBUG=True, FINDIT_DEMO_LOGINS_FILE=self.logins, FINDIT_TESTER_PASSWORDS_FILE=self.fixed):
            call_command("seed_demo", stdout=StringIO())
            return demo_logins.load()

    def test_testers_post_found_and_lost_and_chat_on_both(self):
        self.seed()
        users = get_user_model().objects
        a, b = users.get(username="2026-0101"), users.get(username="2026-0102")
        found = ItemPost.objects.get(author=a, post_type="FOUND")
        lost = ItemPost.objects.get(author=b, post_type="LOST")
        on_found = Conversation.objects.get(post=found, initiator=b, recipient=a, claim__isnull=True)
        on_lost = Conversation.objects.get(post=lost, initiator=a, recipient=b, claim__isnull=True)
        self.assertEqual(on_found.messages.count(), 2)
        self.assertEqual(on_lost.messages.count(), 2)
        self.assertTrue(a.profile.is_verified and b.profile.is_verified)
        self.seed()  # running again adds nothing twice
        self.assertEqual(on_found.messages.count(), 2)
        self.assertEqual(Conversation.objects.filter(post__in=[found, lost]).count(), 2)

    def test_fixed_passwords_from_private_file(self):
        with open(self.fixed, "w", encoding="utf-8") as f:
            f.write("# private\ntester.a.found@example.com | Example-Only-111\n2026-0102 | Example-Only-222\n")
        logins = self.seed()
        users = get_user_model().objects
        self.assertTrue(users.get(username="2026-0101").check_password("Example-Only-111"))
        self.assertTrue(users.get(username="2026-0102").check_password("Example-Only-222"))
        self.assertEqual(logins["2026-0101"], "Example-Only-111")
        self.assertNotEqual(logins["2026-0001"], "Example-Only-111")  # other demo accounts stay random
        self.assertEqual(self.client.post("/login/", {"username": "tester.b.lost@example.com", "password": "Example-Only-222"}).status_code, 302)

    def test_without_the_file_passwords_are_random(self):
        logins = self.seed()
        self.assertRegex(logins["2026-0101"], r"^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$")

    def test_password_file_is_ignored_by_git(self):
        ignore = Path(settings.BASE_DIR, ".gitignore").read_text(encoding="utf-8")
        self.assertIn("tester-passwords.txt", ignore.splitlines())


# ---- DES-007: Messenger-style chat bar and the chat window over the post page ----
class ChatBarTests(FindItTestCase):
    def setUp(self):
        super().setUp()
        self.lost = self.create_post(self.alice, "LOST")
        self.finder_client = self.client_for(self.finder)
        self.finder_client.get(f"/p/{self.lost.pk}/?resume=message")
        self.conv = Conversation.objects.get(post=self.lost, initiator=self.finder)

    def page(self, client, **headers):
        return client.get(f"/conversations/{self.conv.pk}/", **headers).content.decode()

    def test_bar_is_plus_message_send_and_keeps_script_names(self):
        page = self.page(self.finder_client)
        bar = page[page.index('<div class="chat-bar">'):page.index('<p class="chat-status"')]
        self.assertIn('class="chat-plus', bar)
        self.assertIn('aria-haspopup="menu" aria-expanded="false" aria-controls="chat-plus-menu"', bar)
        for name in ('id="chat-form"', 'id="chat-file"', 'id="chat-input"', "data-upload-url=", "data-status-url=",
                     "data-photo-mb=", "data-video-mb=", "data-video-seconds="):
            self.assertIn(name, bar)
        self.assertNotIn("chat-attach", bar)          # the 📎 button moved into the ＋ menu
        self.assertIn("Photo or video", bar)
        self.assertIn('id="chat-status"', page)
        for name in ('id="question-ask"', 'class="question-filter"', "chat-question-list", 'method="post"'):
            self.assertIn(name, page)

    def test_only_the_finder_has_ownership_questions_in_the_menu(self):
        self.assertIn("data-open-questions", self.page(self.finder_client))
        owner_page = self.page(self.client_for(self.alice))
        self.assertIn("Photo or video", owner_page)
        self.assertNotIn("data-open-questions", owner_page)

    def test_chat_window_mode_has_no_sidebar(self):
        full = self.page(self.finder_client)
        framed = self.page(self.finder_client, HTTP_SEC_FETCH_DEST="iframe")
        self.assertIn('class="app-shell"', full)
        self.assertNotIn('class="app-shell"', framed)
        self.assertIn('data-embed="true"', framed)
        self.assertIn('id="chat-form"', framed)
        self.assertIn('data-embed="true"', self.finder_client.get(f"/conversations/{self.conv.pk}/?embed=1").content.decode())

    def test_frame_only_from_this_site(self):
        response = self.finder_client.get(f"/conversations/{self.conv.pk}/")
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")

    def test_post_page_has_chat_window_and_launcher(self):
        page = self.finder_client.get(f"/p/{self.lost.pk}/").content.decode()
        self.assertIn('id="chat-overlay"', page)
        self.assertIn(f'data-chat-url="/conversations/{self.conv.pk}/"', page)
        self.assertNotIn('id="chat-panel"', page)   # the old small panel is gone

    def test_found_post_message_poster_chat_gets_launcher(self):
        found = self.create_post(self.finder, "FOUND")
        alice = self.client_for(self.alice)
        alice.get(f"/p/{found.pk}/?resume=message")
        conv = Conversation.objects.get(post=found, initiator=self.alice)
        self.assertIn(f'data-chat-url="/conversations/{conv.pk}/"', alice.get(f"/p/{found.pk}/").content.decode())

    def test_question_list_rows_never_squeezed(self):
        self.assertIn(".question-list { grid-auto-rows: max-content; }", CSS)


# ---- BUG-024: sign-in problems the team ran into ----
from .base import PASSWORD


class SignInHelpTests(FindItTestCase):
    def test_staff_username_any_case(self):
        response = self.client.post("/login/", {"username": "Guard.Test", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)

    def test_student_cannot_use_internal_username_in_any_case(self):
        response = self.client.post("/login/", {"username": "2026-0001".upper(), "password": PASSWORD})
        self.assertEqual(response.status_code, 302)  # verified Student ID still works
        self.make_user("2026-0099", verified=False)
        self.client.logout()
        response = self.client.post("/login/", {"username": "2026-0099", "password": PASSWORD}, follow=True)
        self.assertContains(response, "A Student ID only works after your email is verified")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.post("/login/", {"username": "2026-0099".lower(), "password": PASSWORD}).status_code, 200)

    def test_wrong_student_id_shows_the_same_hint(self):
        # The hint is shown for any Student ID, so it does not reveal whether an account exists.
        response = self.client.post("/login/", {"username": "2026-9999", "password": "nope-nope"}, follow=True)
        self.assertContains(response, "A Student ID only works after your email is verified")

    def test_top_log_in_on_a_post_comes_back_to_the_post(self):
        post = self.create_post(self.finder, "FOUND")
        post.is_shared = True
        post.save(update_fields=["is_shared"])
        page = self.client.get(f"/p/{post.pk}/").content.decode()
        self.assertIn(f"/login/?next=/p/{post.pk}/", page)
