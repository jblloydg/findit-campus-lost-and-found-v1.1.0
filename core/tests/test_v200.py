"""v2.0.0 integration tests (v1.1.2 + the front-end team's design)."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

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
