"""DES-002: the DOrSU monument photo is the background of every page.
BUG-008: no leftover merge-conflict markers in templates."""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import Client, RequestFactory
from django.contrib.auth.models import AnonymousUser

from .base import FindItTestCase

HERO_PAGES = ["/", "/login/", "/signup/", "/password-reset/", "/password-reset/sent/", "/password-reset/complete/"]
BODY_CLASS = re.compile(r'<body class="campus-bg (campus-bg--hero|campus-bg--app)[" ]')


class CampusBackgroundTests(FindItTestCase):
    def body_variant(self, response):
        html = response.content.decode()
        match = BODY_CLASS.search(html)
        self.assertIsNotNone(match, "page has no campus-bg body class")
        self.assertIn("css/campus-bg.css", html)
        self.assertIn("css/findit.css", html)
        return match.group(1)

    def test_photo_and_stylesheets_exist(self):
        for path in ["img/campus/dorsu-monument.jpg", "img/campus/dorsu-monument.webp",
                     "css/campus-bg.css", "css/findit.css", "fonts/geist-latin-var.woff2",
                     "fonts/instrument-serif-latin-italic.woff2", "fonts/geist-mono-latin-400.woff2"]:
            self.assertIsNotNone(finders.find(path), path)

    def test_public_pages_use_the_green_hero_look(self):
        client = Client()
        for url in HERO_PAGES:
            with self.subTest(url=url):
                response = client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.body_variant(response), "campus-bg--hero")

    def test_signed_in_pages_use_the_light_app_look_for_every_role(self):
        pages = {
            self.finder: ["/home/", "/my-posts/", "/my-claims/", "/messages/", "/notifications/", "/profile/",
                          "/posts/new/", "/my-reports/", "/reports/new/"],
            self.staff: ["/staff/", "/staff/scan/"],
            self.admin: ["/staff/admin/", "/staff/accounts/", "/staff/settings/", "/staff/reports/",
                         "/staff/general-reports/", "/staff/categories/", "/staff/questions/", "/staff/moderators/"],
        }
        for user, urls in pages.items():
            client = self.client_for(user)
            for url in urls:
                with self.subTest(user=user.username, url=url):
                    response = client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(self.body_variant(response), "campus-bg--app")

    def test_item_page_signed_out_after_sharing_uses_app_look(self):
        post = self.create_post()
        self.client_for(self.finder).post(f"/posts/{post.pk}/share/")
        response = Client().get(f"/p/{post.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body_variant(response), "campus-bg--app")

    def test_error_pages_show_the_photo(self):
        request = RequestFactory().get("/missing/")
        request.user = AnonymousUser()
        for template in ["404.html", "403.html", "503.html", "core/csrf_failure.html"]:
            with self.subTest(template=template):
                self.assertRegex(render_to_string(template, {}, request=request), BODY_CLASS)
        # 500.html works without Django's template tags, so it links the photo directly.
        self.assertIn("/static/img/campus/dorsu-monument.jpg", Path(settings.BASE_DIR, "templates", "500.html").read_text())


class NoConflictMarkerTests(FindItTestCase):
    def test_templates_have_no_merge_conflict_markers(self):
        marker = re.compile(r"^(<{7}|>{7}|={7})( |$)", re.M)
        for path in Path(settings.BASE_DIR, "templates").rglob("*.html"):
            with self.subTest(path=path.name):
                self.assertIsNone(marker.search(path.read_text(encoding="utf-8")))

    def test_browse_cards_do_not_show_marker_text(self):
        self.create_post()
        response = self.client_for(self.finder).get("/home/")
        self.assertNotContains(response, "&lt;&lt;&lt;&lt;&lt;&lt;&lt;")
        self.assertNotContains(response, "<<<<<<<")
