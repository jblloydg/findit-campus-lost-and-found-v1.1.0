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
    """The real tester accounts live only in the owner's private copy; these tests use made-up ones."""
    ROWS = ("# example only\n"
            "1999-0001 | finder.example@example.com | Example | Finder | FOUND | example-only-1\n"
            "1999-0002 | owner.example@example.com | Example | Owner | LOST | example-only-2\n")

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="findit-testers-")
        self.logins = os.path.join(self.folder, "demo-logins.txt")
        self.accounts = os.path.join(self.folder, "tester-accounts.txt")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def seed(self, rows=None):
        if rows is not None:
            with open(self.accounts, "w", encoding="utf-8") as f:
                f.write(rows)
        with override_settings(DEBUG=True, FINDIT_DEMO_LOGINS_FILE=self.logins, FINDIT_TESTER_ACCOUNTS_FILE=self.accounts):
            call_command("seed_demo", stdout=StringIO())
            return demo_logins.load()

    def test_testers_post_found_and_lost_and_chat_on_both(self):
        logins = self.seed(self.ROWS)
        users = get_user_model().objects
        a, b = users.get(username="1999-0001"), users.get(username="1999-0002")
        self.assertTrue(a.check_password("example-only-1") and b.check_password("example-only-2"))
        self.assertEqual(logins["1999-0001"], "example-only-1")
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
        self.assertEqual(self.client.post("/login/", {"username": "owner.example@example.com", "password": "example-only-2"}).status_code, 302)
        self.assertEqual(self.client.post("/login/", {"username": "1999-0001", "password": "example-only-1"}).status_code, 302)

    def test_no_file_no_testers(self):
        self.seed()
        self.assertFalse(get_user_model().objects.filter(username__startswith="1999-").exists())

    def test_tester_data_not_in_shared_code(self):
        code = Path(settings.BASE_DIR, "core", "management", "commands", "seed_demo.py").read_text(encoding="utf-8")
        self.assertNotIn("_tester_accounts(login_rows)" , code.replace("self._tester_accounts(login_rows)", ""))
        self.assertNotRegex(code, r"TESTER|tester\.[a-z]+@")   # no tester account written in the code
        ignore = Path(settings.BASE_DIR, ".gitignore").read_text(encoding="utf-8").splitlines()
        for name in ("tester-accounts.txt", "Accounts/", "accounts.md"):
            self.assertIn(name, ignore)


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


# ---- DES-008: the chat window opens over whatever page you are on ----
class ChatWindowEverywhereTests(FindItTestCase):
    def test_window_on_ordinary_pages_but_not_on_the_full_chat_page(self):
        client = self.client_for(self.finder)
        for url in ("/home/", "/messages/", "/notifications/", "/my-posts/"):
            self.assertIn('id="chat-overlay"', client.get(url).content.decode(), url)
        lost = self.create_post(self.alice, "LOST")
        client.get(f"/p/{lost.pk}/?resume=message")
        conv = Conversation.objects.get(post=lost, initiator=self.finder)
        self.assertNotIn('id="chat-overlay"', client.get(f"/conversations/{conv.pk}/").content.decode())
        self.assertIn(f'href="/conversations/{conv.pk}/"', client.get("/messages/").content.decode())

    def test_signed_out_pages_have_no_window(self):
        self.assertNotIn('id="chat-overlay"', self.client.get("/login/").content.decode())


# ---- CHG-015: explain that Find-IT sets the status (only a guard sets "At Guard House") ----
class StatusHelpTests(FindItTestCase):
    def test_post_page_and_form_explain_status(self):
        post = self.create_post(self.finder, "FOUND")
        page = self.client_for(self.alice).get(f"/p/{post.pk}/").content.decode()
        self.assertIn("How does the status change?", page)
        self.assertIn("only a guard (staff) can set this", page)
        self.assertIn("You don't set the status", self.client_for(self.alice).get("/posts/new/").content.decode())


# ---- CHG-016: the guard-house step can be found (while posting, and with the main buttons) ----
from django.core.files.uploadedfile import SimpleUploadedFile
from core.models import Category, TurnInTicket


def _jpeg():
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (10, 120, 90)).save(buffer, "JPEG")
    return SimpleUploadedFile("item.jpg", buffer.getvalue(), content_type="image/jpeg")


class GuardhouseWhilePostingTests(FindItTestCase):
    def post_found(self, **extra):
        data = {"post_type": "FOUND", "category": Category.objects.first().pk, "photos": _jpeg(), **extra}
        return self.client_for(self.finder).post("/posts/new/", data, follow=True)

    def test_choice_on_form_for_found_only_markup(self):
        page = self.client_for(self.finder).get("/posts/new/?type=FOUND").content.decode()
        self.assertIn('name="bring_to_guardhouse"', page)
        self.assertIn("data-found-only", page)

    def test_ticking_it_tells_staff(self):
        response = self.post_found(bring_to_guardhouse="1")
        post = ItemPost.objects.filter(author=self.finder).latest("created_at")
        ticket = TurnInTicket.objects.get(post=post, finder=self.finder)
        self.assertIsNotNone(ticket.requested_at)
        self.assertContains(response, ticket.code)

    def test_not_ticked_nothing_requested(self):
        self.post_found()
        post = ItemPost.objects.filter(author=self.finder).latest("created_at")
        self.assertIsNone(TurnInTicket.objects.get(post=post, finder=self.finder).requested_at)

    def test_button_with_main_actions_for_the_finder(self):
        post = self.create_post(self.finder, "FOUND")
        page = self.client_for(self.finder).get(f"/p/{post.pk}/").content.decode()
        top = page[page.index('class="primary-actions top-actions"'):page.index('class="item-facts"')]
        self.assertIn("I'm bringing it to the guard house", top)


# ---- CHG-017: a post at the guard house can still be messaged (its author can help the owner) ----
class ChatAtGuardHouseTests(FindItTestCase):
    def test_owner_can_message_the_author_of_a_guard_house_post(self):
        post = self.create_post(self.finder, "FOUND")
        ItemPost.objects.filter(pk=post.pk).update(status=ItemPost.Status.TURNED_OVER)
        owner = self.client_for(self.alice)
        page = owner.get(f"/p/{post.pk}/").content.decode()
        self.assertIn("Message poster", page)
        response = owner.get(f"/p/{post.pk}/?resume=message")
        conv = Conversation.objects.get(post=post, initiator=self.alice)
        self.assertRedirects(response, f"/conversations/{conv.pk}/", fetch_redirect_response=False)

    def test_claimed_or_closed_posts_still_take_no_new_chats(self):
        for status in (ItemPost.Status.CLAIMED, ItemPost.Status.CLOSED):
            post = self.create_post(self.finder, "FOUND")
            ItemPost.objects.filter(pk=post.pk).update(status=status)
            self.client_for(self.alice).get(f"/p/{post.pk}/?resume=message")
            self.assertFalse(Conversation.objects.filter(post=post).exists(), status)


# ---- CHG-019: Contact staff — one shared staff inbox ----
from core.models import StaffHelpThread


class StaffInboxTests(FindItTestCase):
    def ask(self, client=None, **extra):
        client = client or self.client_for(self.alice)
        return client.post("/help/new/", {"subject": "", "text": "The finder does not reply.", **extra})

    def test_student_request_reaches_every_staff_member(self):
        post = self.create_post(self.finder, "FOUND")
        self.ask(post=str(post.pk))
        thread = StaffHelpThread.objects.get(requester=self.alice)
        self.assertEqual(thread.post, post)
        self.assertEqual(thread.subject, f"About: {post.display_title}")
        link = f"/help/{thread.pk}/"
        for member in (self.staff, self.admin):
            self.assertTrue(InAppNotification.objects.filter(recipient=member, link=link).exists())
            self.assertIn(thread.subject, self.client_for(member).get("/help/").content.decode())

    def test_any_staff_replies_and_student_is_told(self):
        self.ask()
        thread = StaffHelpThread.objects.get(requester=self.alice)
        self.client_for(self.staff).post(f"/help/{thread.pk}/", {"text": "We can help at the guard house."})
        thread.refresh_from_db()
        self.assertEqual(thread.status, StaffHelpThread.Status.ANSWERED)
        self.assertTrue(thread.messages.filter(from_staff=True, sender=self.staff).exists())
        self.assertTrue(InAppNotification.objects.filter(recipient=self.alice, link=f"/help/{thread.pk}/").exists())
        self.client_for(self.admin).post(f"/help/{thread.pk}/", {"text": "Also seen by the admin."})
        self.assertEqual(thread.messages.filter(from_staff=True).count(), 2)

    def test_private_to_requester_and_staff(self):
        self.ask()
        thread = StaffHelpThread.objects.get(requester=self.alice)
        self.assertEqual(self.client_for(self.bob).get(f"/help/{thread.pk}/").status_code, 403)
        self.assertEqual(self.client_for(self.bob).post(f"/help/{thread.pk}/", {"text": "x"}).status_code, 403)
        self.assertNotIn(thread.subject, self.client_for(self.bob).get("/help/").content.decode())

    def test_resolve_and_limit(self):
        for _ in range(5):
            self.ask()
        self.ask()
        self.assertEqual(StaffHelpThread.objects.filter(requester=self.alice).count(), 5)
        thread = StaffHelpThread.objects.filter(requester=self.alice).first()
        self.client_for(self.alice).post(f"/help/{thread.pk}/", {"action": "resolve"})
        thread.refresh_from_db()
        self.assertEqual(thread.status, StaffHelpThread.Status.RESOLVED)

    def test_reachable_by_clicking(self):
        post = self.create_post(self.finder, "FOUND")
        student = self.client_for(self.alice)
        self.assertIn('href="/help/"', student.get("/home/").content.decode())                  # sidebar
        self.assertIn(f'href="/help/new/?post={post.pk}"', student.get(f"/p/{post.pk}/").content.decode())  # post page
        self.assertIn('href="/help/"', self.client_for(self.staff).get("/staff/").content.decode())  # staff sidebar + workspace


# ---- BUG-022: a chat message shows the same name and time live and after a reload ----
class SameNameAndTimeTests(SimpleTestCase):
    def test_live_sender_is_first_name_like_the_page(self):
        consumers = Path(settings.BASE_DIR, "core", "consumers.py").read_text(encoding="utf-8")
        media = Path(settings.BASE_DIR, "core", "chat_media.py").read_text(encoding="utf-8")
        self.assertIn("self.sender_name = (user.first_name or user.username)", consumers)
        self.assertNotIn("uploader.get_full_name()", media)

    def test_script_time_format_matches_the_page(self):
        js = Path(settings.BASE_DIR, "static", "js", "chat.js").read_text(encoding="utf-8")
        page = Path(settings.BASE_DIR, "templates", "core", "chat_room.html").read_text(encoding="utf-8")
        self.assertIn('date:"M j · g:i a"', page)
        self.assertIn('" · " + hour + ":"', js)
        self.assertIn('"a.m." : "p.m."', js)


# ---- BUG-025: AVIF photos are accepted (and re-encoded to JPEG like every photo); HEIC gets a clear message ----
from PIL import features as _pil_features
from unittest import skipUnless


def _avif():
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (80, 60), (200, 40, 40)).save(buffer, "AVIF")
    return SimpleUploadedFile("phone.avif", buffer.getvalue(), content_type="image/avif")


@skipUnless(_pil_features.check("avif"), "this PC's Pillow cannot read AVIF")
class AvifPhotoTests(FindItTestCase):
    def test_post_with_avif_photo_is_stored_as_jpeg(self):
        response = self.client_for(self.finder).post("/posts/new/", {
            "post_type": "FOUND", "category": Category.objects.first().pk, "photos": _avif()})
        self.assertEqual(response.status_code, 302)
        post = ItemPost.objects.filter(author=self.finder).latest("created_at")
        stored = post.photos.first().image
        stored.open("rb")
        self.assertTrue(stored.read(3) == b"\xff\xd8\xff")   # JPEG
        stored.close()

    def test_heic_gets_a_clear_message(self):
        fake = SimpleUploadedFile("IMG_0001.HEIC", b"\x00\x00\x00\x18ftypheic", content_type="image/heic")
        response = self.client_for(self.finder).post("/posts/new/", {
            "post_type": "FOUND", "category": Category.objects.first().pk, "photos": fake})
        self.assertContains(response, "HEIC photos (iPhone)")

    def test_chat_accepts_avif_as_a_photo_and_reencodes_it(self):
        import io
        from core.chat_media import kind_of
        from core.images import compress
        from core.models import ChatAttachment
        self.assertEqual(kind_of("phone.avif"), ChatAttachment.Kind.PHOTO)
        data = compress(io.BytesIO(_avif().read()), max_side=1600, max_bytes=300 * 1024)
        self.assertTrue(data.startswith(b"\xff\xd8\xff"))
