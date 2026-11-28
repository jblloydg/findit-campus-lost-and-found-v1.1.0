"""v1.1.2 tests: BUG-008, SEC-002, CHG-008 (demo sign-ins per PC, no sensitive data in shared files). All people here are fictional."""
import os
import re
import subprocess
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from core import demo_logins
from core.models import Category, InAppNotification, ItemPost
from core.security import is_own_site_path
from core.verification import notify_account

from .base import FindItTestCase

User = get_user_model()


class PostDetailTagLineTests(FindItTestCase):
    """BUG-008: category link uses the id and shows the name; location stays dormant."""

    def test_category_link_uses_id_and_shows_name(self):
        post = self.create_post()
        html = self.client_for(self.alice).get(reverse("post-detail", args=[post.pk])).content.decode()
        self.assertIn(f'href="{reverse("home")}?category={self.category.pk}">{self.category.name}</a>', html)

    def test_category_link_filters_browse(self):
        post = self.create_post()
        other_category = Category.objects.exclude(pk=self.category.pk).first()
        other = self.create_post(category=other_category.pk)
        response = self.client_for(self.alice).get(f"{reverse('home')}?category={self.category.pk}")
        self.assertContains(response, reverse("post-detail", args=[post.pk]))
        self.assertNotContains(response, reverse("post-detail", args=[other.pk]))

    @override_settings(FINDIT_LOCATION_ENABLED=False)
    def test_dormant_location_hidden(self):
        post = self.create_post()
        ItemPost.objects.filter(pk=post.pk).update(location="Library 2nd floor")
        response = self.client_for(self.alice).get(reverse("post-detail", args=[post.pk]))
        self.assertNotContains(response, "Library 2nd floor")

    @override_settings(FINDIT_LOCATION_ENABLED=True)
    def test_location_shown_when_enabled(self):
        post = self.create_post()
        ItemPost.objects.filter(pk=post.pk).update(location="Library 2nd floor")
        response = self.client_for(self.alice).get(reverse("post-detail", args=[post.pk]))
        self.assertContains(response, "📍 Library 2nd floor")

    def test_post_without_category_has_no_empty_link(self):
        post = self.create_post()
        ItemPost.objects.filter(pk=post.pk).update(category=None)
        response = self.client_for(self.alice).get(reverse("post-detail", args=[post.pk]))
        self.assertNotContains(response, 'class="category-tag"')


class NotificationLinkTests(FindItTestCase):
    """SEC-002: tapping a notice never leaves Find-IT."""

    UNSAFE = [
        "https://evil.example.com/", "http://evil.example.com", "//evil.example.com/", "/\\evil.example.com",
        "/\\/evil.example.com", "\\\\evil.example.com", "javascript:alert(1)", "/\t/evil.example.com",
        "/%0a/evil.example.com\n", "evil.example.com", " /home/",
    ]

    def open_notice(self, link):
        notice = InAppNotification.objects.create(recipient=self.alice, text="Test notice", link=link)
        return self.client_for(self.alice).get(f"{reverse('notifications')}?open={notice.pk}")

    def test_own_page_link_opens(self):
        response = self.open_notice(reverse("my-profile"))
        self.assertRedirects(response, reverse("my-profile"), fetch_redirect_response=False)

    def test_other_website_links_never_redirect_away(self):
        for link in self.UNSAFE:
            with self.subTest(link=link):
                self.assertFalse(is_own_site_path(link))
                response = self.open_notice(link)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], reverse("notifications"))

    def test_unsafe_link_is_not_stored(self):
        notice = notify_account(self.alice, "Hello", link="//evil.example.com/")
        self.assertEqual(notice.link, "")
        notice = notify_account(self.alice, "Hello again", link=reverse("home"))
        self.assertEqual(notice.link, reverse("home"))


class DemoLoginsTests(FindItTestCase):
    """CHG-008: demo passwords are random per PC, saved only in demo-logins.txt (ignored by Git)."""

    def setUp(self):
        # No super().setUp(): seed_demo makes its own demo accounts.
        import tempfile
        self.folder = tempfile.mkdtemp(prefix="findit-demo-")
        self.file = os.path.join(self.folder, "demo-logins.txt")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.folder, ignore_errors=True)
        super().tearDown()

    def seed(self, *args):
        with override_settings(DEBUG=True, FINDIT_DEMO_LOGINS_FILE=self.file):
            call_command("seed_demo", *args, stdout=StringIO())
            return demo_logins.load()

    def test_random_passwords_saved_and_working(self):
        logins = self.seed()
        self.assertEqual(len(logins), 8)
        self.assertEqual(len(set(logins.values())), 8)  # every account gets its own
        for username, password in logins.items():
            self.assertRegex(password, r"^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$")
            self.assertTrue(User.objects.get(username=username).check_password(password), username)
        response = self.client.post(reverse("login"), {"username": "alex.finder@example.com", "password": logins["2026-0001"]})
        self.assertEqual(response.status_code, 302)

    def test_running_again_keeps_the_same_passwords(self):
        first = self.seed()
        self.assertEqual(self.seed(), first)

    def test_old_published_password_is_replaced(self):
        self.seed()
        user = User.objects.get(username="security.demo")
        old = "Demo" + "Staff!" + "2026"  # the old public password, built so it is not written in the code
        user.set_password(old)
        user.save()
        logins = self.seed("--logins-only")
        self.assertFalse(User.objects.get(username="security.demo").check_password(old))
        self.assertTrue(User.objects.get(username="security.demo").check_password(logins["security.demo"]))

    def test_logins_only_without_file_resets_passwords_and_keeps_data(self):
        self.seed()
        posts = ItemPost.objects.count()
        users = User.objects.count()
        os.remove(self.file)
        logins = self.seed("--logins-only")
        self.assertEqual(len(logins), 8)
        self.assertEqual(User.objects.count(), users)
        self.assertEqual(ItemPost.objects.count(), posts)
        self.assertTrue(User.objects.get(username="2026-0002").check_password(logins["2026-0002"]))


class NoSensitiveDataInSharedFilesTests(SimpleTestCase):
    """Owner's rule (v1.1.2): the shared repository never contains demo passwords or
    Developer-account instructions. This scans every file Git tracks."""

    PATTERNS = [
        (re.compile(r"Demo(FindIt|Staff|Admin)!\d{4}"), "an old published demo password"),
        (re.compile(r"create_developer"), "Developer account instructions"),
    ]
    # Code that must name the command itself (the program needs it).
    ALLOWED = {
        "create_developer": {
            "core/management/commands/create_developer.py", "core/tests/test_v111.py", "FindIT.cmd",
            "core/tests/test_v112.py", "core/forms.py", "core/models.py", "core/views.py", "core/permissions.py",
            "core/signals.py",
        },
    }

    def test_no_leaks(self):
        root = Path(settings.BASE_DIR)
        try:
            files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.split()
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("Git is not available in this folder.")
        self.assertNotIn("demo-logins.txt", files)
        problems = []
        for name in files:
            path = root / name
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".ico", ".mp4", ".pdf", ".woff", ".woff2"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for pattern, what in self.PATTERNS:
                if pattern.search(text) and name not in self.ALLOWED.get(pattern.pattern, set()):
                    problems.append(f"{name}: {what}")
        self.assertEqual(problems, [], "Sensitive data in shared files (move it to the owner's private copy)")
