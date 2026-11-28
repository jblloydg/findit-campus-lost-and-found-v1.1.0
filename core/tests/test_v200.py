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


class MasterInstructionCssTests(SimpleTestCase):
    """BUG-015 / BUG-016: the stylesheet keeps the v2.0.0 Master Instruction rules.
    The full on-screen check is tools/testing/responsive_check.py (every page, 360-1920 px)."""

    def css(self):
        return "".join(p.read_text(encoding="utf-8") for p in (BASE / "static" / "css").glob("*.css"))

    def test_no_text_below_12px(self):
        css = self.css()
        small_rem = [m.group(0) for m in re.finditer(r"font-size:\s*(0?\.\d+)rem", css) if float(m.group(1)) < 0.75]
        self.assertEqual(small_rem, [])
        steps = dict(re.findall(r"(--step-[-0-9]+):\s*clamp\(([0-9.]+)rem", css))
        self.assertTrue(steps, "type scale not found")
        self.assertTrue(all(float(v) >= 0.75 for v in steps.values()), steps)

    def test_tap_size_is_2_75rem_and_used_by_small_controls(self):
        css = self.css()
        self.assertIn("--tap: 2.75rem", css)
        for rule in (".button-small {", ".link-button, .text-action {", ".password-toggle {", ".segmented a {"):
            body = css.split(rule, 1)[1].split("}", 1)[0]
            self.assertIn("var(--tap)", body, rule)

    def test_px_only_for_borders_shadows_and_outlines(self):
        bad = []
        css = re.sub(r"/\*.*?\*/", "", self.css(), flags=re.S)  # comments
        css = re.sub(r"(height:\s*1px|margin:\s*0 -1px -1px 0)", "", css)  # 1px divider lines, border overlap
        for line in css.splitlines():
            if re.search(r"\d+px", line) and not line.strip().startswith(("/*", "*")):
                rest = re.sub(r"(border[^;]*;|[a-z-]*shadow[^;]*;|outline[^;]*;|translateY\(-1px\)|blur\(1px\))", "", line)
                if re.search(r"\d+px", rest) and ".sr-only" not in line and "--shadow" not in line:
                    bad.append(line.strip()[:90])
        self.assertEqual(bad, [])


class HiddenAttributeTests(SimpleTestCase):
    """BUG-019: the found-item question picker showed on LOST posts because
    .question-editor { display: grid } overrode the hidden attribute."""

    def test_hidden_always_wins(self):
        css = (BASE / "static" / "css" / "findit.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"(?m)^\[hidden\]\s*\{\s*display:\s*none\s*!important;\s*\}")

    def test_question_picker_is_hidden_for_lost_by_script(self):
        js = (BASE / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('questionBlock.hidden = typeSelect.value !== "FOUND"', js)


class ReportLinkHighlightTests(SimpleTestCase):
    """BUG-020: the sidebar highlighted "Report found item" on a Lost post form."""

    def test_sidebar_follows_the_chosen_type(self):
        sidebar = (BASE / "templates" / "core" / "includes" / "sidebar.html").read_text(encoding="utf-8")
        self.assertIn('data-report-kind="LOST"', sidebar)
        self.assertIn('data-report-kind="FOUND"', sidebar)
        self.assertNotIn("kind != 'LOST'", sidebar)  # no type chosen must not mean "found"
        js = (BASE / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('link.getAttribute("data-report-kind") === typeSelect.value', js)
