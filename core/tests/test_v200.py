"""v2.0.0 integration tests (v1.1.2 + the front-end team's design)."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

BASE = Path(settings.BASE_DIR)

# Class names that had a style in v1.1.1's app.css and are still used by templates.
# findit.css replaced app.css in v2.0.0; every one of them must still be styled.
STYLED_IN_V111 = {
    "accounts-panel", "compact-form", "panel", "stack-form", "button", "button-primary", "button-outline",
    "staff-row", "staff-list", "result-heading", "accounts-table", "table-scroll", "inline-filter",
    "claim-strip", "status-approved", "status-declined", "decline-reason", "item-tags", "auth-page",
}


def css_classes():
    text = "".join(p.read_text(encoding="utf-8") for p in (BASE / "static" / "css").glob("*.css"))
    return set(re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]*)", text))


def template_classes():
    used = set()
    for path in (BASE / "templates").rglob("*.html"):
        for value in re.findall(r'class="([^"]*)"', path.read_text(encoding="utf-8")):
            used.update(name for name in value.split() if "{" not in name and "%" not in name)
    return used


class StylesKeptTests(SimpleTestCase):
    """BUG-011: the new stylesheet dropped two styles that pages still use."""

    def test_lost_styles_are_back(self):
        defined = css_classes()
        self.assertIn("accounts-panel", defined)
        self.assertIn("compact-form", defined)

    def test_every_v111_style_still_used_is_defined(self):
        missing = sorted((STYLED_IN_V111 & template_classes()) - css_classes())
        self.assertEqual(missing, [], "classes used by templates but no longer styled")


class VersionLabelTests(SimpleTestCase):
    """DES-005: "Find-IT v<VERSION>" near the bottom of every page, read from the VERSION file."""

    def test_version_comes_from_the_version_file(self):
        from core.version import FINDIT_VERSION, read_version
        self.assertEqual(FINDIT_VERSION, (BASE / "VERSION").read_text(encoding="utf-8").strip())
        self.assertEqual(read_version(), FINDIT_VERSION)
        self.assertRegex(FINDIT_VERSION, r"^\d+\.\d+\.\d+$")

    def test_version_is_never_typed_into_templates(self):
        typed = [str(p.relative_to(BASE)) for p in (BASE / "templates").rglob("*.html")
                 if re.search(r"Find-IT v\d", p.read_text(encoding="utf-8"))]
        self.assertEqual(typed, [])

    def test_500_page_shows_the_version(self):
        from django.test import RequestFactory
        from core.views import server_error
        from core.version import FINDIT_VERSION
        response = server_error(RequestFactory().get("/"))
        self.assertEqual(response.status_code, 500)
        self.assertIn(f"Find-IT v{FINDIT_VERSION}", response.content.decode())


from django.test import TestCase  # noqa: E402


class VersionLabelOnPagesTests(TestCase):
    def test_signed_out_pages_show_the_label(self):
        from core.version import FINDIT_VERSION
        for name in ("landing", "login", "signup", "password_reset"):
            html = self.client.get(reverse(name)).content.decode()
            self.assertIn(f'version-label--public">Find-IT v{FINDIT_VERSION}<', html, name)

    def test_signed_in_pages_show_it_in_sidebar_and_phone_footer(self):
        from django.contrib.auth.models import User
        from core.models import Profile
        from core.version import FINDIT_VERSION
        user = User.objects.create_user("2020-0001", email="juan.cruz@example.com", password="x-test-pw-1",
                                        first_name="Juan", last_name="Cruz")
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role, profile.student_id = Profile.Role.STUDENT, "2020-0001"
        profile.save()
        self.client.force_login(user)
        for name in ("home", "my-posts", "notifications", "my-profile"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)
            html = response.content.decode()
            self.assertIn(f'version-label--sidebar">Find-IT v{FINDIT_VERSION}<', html, name)
            self.assertIn(f'version-label--footer">Find-IT v{FINDIT_VERSION}<', html, name)
        html = self.client.get("/no-such-page/").content.decode()  # 404 uses the same frame
        self.assertIn(f"Find-IT v{FINDIT_VERSION}", html)


class LocalDataNeverTrackedTests(SimpleTestCase):
    """BUG-018: SQLite's WAL mode (PERF-002) makes db.sqlite3-wal / -shm next to the database.
    They hold the same data as the database (sessions, demo accounts), so Git must never track them."""

    LOCAL = re.compile(r"(^|/)(db\.sqlite3(-wal|-shm|-journal)?|.*\.sqlite3(-wal|-shm|-journal)?|demo-logins\.txt|\.env)$"
                       r"|^(media|private_media|backups|tools/testing/out)/")

    def git(self, *args):
        import subprocess
        try:
            return subprocess.run(["git", *args], cwd=BASE, capture_output=True, text=True, check=False)
        except OSError:
            self.skipTest("Git is not available in this folder.")

    def test_no_local_data_files_tracked(self):
        result = self.git("ls-files")
        if result.returncode:
            self.skipTest("Not a Git folder.")
        tracked = [name for name in result.stdout.split() if self.LOCAL.search(name)]
        self.assertEqual(tracked, [])

    def test_sqlite_helper_files_are_ignored(self):
        for name in ("db.sqlite3", "db.sqlite3-wal", "db.sqlite3-shm", "demo-logins.txt", "tools/testing/out/x.png"):
            result = self.git("check-ignore", "-q", "--no-index", name)
            if result.returncode == 128:
                self.skipTest("Not a Git folder.")
            self.assertEqual(result.returncode, 0, f"{name} is not in .gitignore")
