"""v2.1.0: is every page and action reachable by CLICKING, not only by typing its address?

Run from the project folder after `migrate` and `seed_demo` (no server needed). Best on fresh demo data:
the situations below are made from the demo posts and accounts.
    python tools/testing/reachability.py

For each role it starts ONLY from the page that role lands on after signing in (students /home/,
staff /staff/, signed out /) and follows what a person can click: links (<a href>), GET forms
(search, filters) and the targets of POST forms (buttons that do something). Every address it
reaches is matched to its URL pattern. At the end it lists, for every URL pattern in core/urls.py,
which roles reached it, and the patterns nobody can reach by clicking.

Some addresses are not pages for people (data for the scripts, file downloads, the WebSocket),
or are only opened from an email or a QR code; those are listed in NOT_CLICKED with the reason.
"""
import collections
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "findit.settings")
os.environ["DJANGO_DEBUG"] = "1"
import django  # noqa: E402

django.setup()
from django.conf import settings  # noqa: E402

settings.ALLOWED_HOSTS = ["*"]
from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import Resolver404, resolve  # noqa: E402

from core import urls as core_urls  # noqa: E402

ROLES = {
    "student (verified)": ("2026-0001", "/home/"),
    "student (other)": ("2026-0002", "/home/"),
    "student (not verified)": ("2026-0005", "/home/"),
    "student (ID review open)": ("2026-0017", "/home/"),
    "guard (staff)": ("security.demo", "/staff/"),
    "verified moderator": ("moderator.demo", "/staff/"),
    "admin": ("findit-admin", "/staff/"),
    "signed out": (None, "/"),
}
# Addresses that are not pages people click to, and why (checked by hand; see the v2.1.0 test report).
NOT_CLICKED = {
    "conversation-messages": "data for the chat script (older messages, search)",
    "chat-messages-json": "data for the chat script (older messages, search)",
    "chat-upload": "the chat script uploads photos/videos here",
    "password_reset_done": "shown after submitting Forgot password (checked by submitting the form)",
    "password_reset_confirm": "opened from the password-reset email",
    "password_reset_complete": "shown after setting a new password from the email link",
    "chat-upload-status": "the chat script asks for upload progress here",
    "chat-media": "photo/video files inside a chat (shown in the chat, not a page)",
    "ticket-qr": "the QR picture (shown on the post; 'Download QR' link)",
    "verify-email-link": "opened from the verification email",
    "password-reset-confirm": "opened from the password-reset email",
    "turn-in-public": "opened by scanning the turn-in QR with any phone camera",
    "notification-open": "each notification's link (opens what it is about)",
    "health": "server health check for monitoring",
    "share-post": "the Copy link button (posted by the script)",
    "csrf-failure": "error page",
}
SKIP_PREFIX = ("/static/", "/media/", "/captcha/", "/django-admin/", "/ws/")
MAX_PAGES = 2500


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.get_forms, self.post_actions = [], [], []
        self._form = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "form":
            method = (a.get("method") or "get").lower()
            action = a.get("action") or ""
            (self.post_actions if method == "post" else self.get_forms).append(action)
        elif tag in ("button", "a") and a.get("data-chat-url"):
            self.links.append(a["data-chat-url"])


def own_path(base, href):
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    url = urljoin(base, href)
    parts = urlsplit(url)
    if parts.netloc and parts.netloc not in ("testserver", "127.0.0.1:8000", "localhost:8000"):
        return None
    path = parts.path + (("?" + parts.query) if parts.query else "")
    if path.startswith(SKIP_PREFIX):
        return None
    return path


def name_of(path):
    try:
        match = resolve(urlsplit(path).path)
    except Resolver404:
        return None
    return match.url_name


def crawl(username, start):
    client = Client(raise_request_exception=False)
    if username:
        client.force_login(get_user_model().objects.get(username=username))
    seen_pages, reached_names, queue = set(), collections.defaultdict(set), [start]
    pattern_budget = collections.Counter()   # at most a few pages per pattern (e.g. not every post)
    while queue and len(seen_pages) < MAX_PAGES:
        path = queue.pop(0)
        if path in seen_pages:
            continue
        name = name_of(path)
        if name == "logout":
            continue   # never sign out in the middle of the crawl (its button is counted below)
        if name and pattern_budget[name] >= (400 if name in ("post-detail", "chat-room") else 4):
            continue
        seen_pages.add(path)
        if name:
            pattern_budget[name] += 1
        response = client.get(path, follow=False)
        if name:
            reached_names[name].add(response.status_code)
        if response.status_code in (301, 302) and response.get("Location"):
            target = own_path(path, response["Location"])
            if target:
                queue.append(target)
            continue
        if response.status_code != 200 or "text/html" not in response.get("Content-Type", ""):
            continue
        parser = Links()
        parser.feed(response.content.decode("utf-8", "replace"))
        for href in parser.links + [f or path for f in parser.get_forms]:
            target = own_path(path, href)
            if target and target not in seen_pages:
                queue.append(target)
        for action in parser.post_actions:   # a button that does something: count its target as reached
            target = own_path(path, action or path)
            target_name = target and name_of(target)
            if target_name:
                reached_names[target_name].add("button")
    return reached_names, len(seen_pages)


def make_situations():
    """Create, through the normal pages, the situations some buttons need (undone afterwards):
    a system report with a screenshot, a chat safety report, a paused chat, a declined owner check."""
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    from core.models import ClaimApplication, Conversation
    users = get_user_model().objects
    def client(username):
        c = Client(raise_request_exception=False)
        c.force_login(users.get(username=username))
        return c
    picture = BytesIO()
    Image.new("RGB", (40, 40), (90, 90, 90)).save(picture, "PNG")
    client("2026-0001").post("/reports/new/", {"category": "TECHNICAL", "description": "Reachability check: page shows an error.",
                                               "attachment": SimpleUploadedFile("screen.png", picture.getvalue(), "image/png")})
    lost_check = ClaimApplication.objects.filter(finder__isnull=False, status="SUBMITTED", post__post_type="LOST").first()
    if lost_check:
        client(lost_check.finder.username).post(f"/claims/{lost_check.pk}/decline/", {"reason": "Reachability check"})
    chats = list(Conversation.objects.filter(is_closed=False, is_paused=False, post__is_archived=False)
                 .select_related("initiator").order_by("-updated_at")[:2])
    if chats:
        client(chats[0].initiator.username).post(f"/conversations/{chats[0].pk}/report/", {
            "reason": "SPAM", "details": "Reachability check.", "target_user": chats[0].recipient_id})
    if len(chats) > 1:
        client("moderator.demo").post(f"/conversations/{chats[1].pk}/pause/", {"reason": "Reachability check"})
    # a student asks the staff team for help (Contact staff → the shared Staff inbox)
    client("2026-0002").post("/help/new/", {"subject": "Reachability check", "text": "The finder does not reply."})
    # a finder says they are bringing a found item to the guard house (the guard's Confirm page)
    from core.models import ItemPost
    found = ItemPost.objects.filter(post_type="FOUND", status__in=["OPEN", "CLAIM_IN_PROGRESS"], is_archived=False,
                                    author__username="2026-0001").first()
    if found:
        client("2026-0001").post(f"/posts/{found.pk}/turn-over/")
    crawled = [username for username, _ in ROLES.values() if username]
    open_chat = (Conversation.objects.filter(is_closed=False, is_paused=False, claim__isnull=True, post__is_archived=False,
                                            initiator__username__in=crawled, recipient__username__in=crawled)
                 .exclude(pk__in=[c.pk for c in chats]).first())
    if open_chat is None:   # a finder messages an open LOST post of another tested student
        from core.models import ItemPost
        lost = ItemPost.objects.filter(post_type="LOST", status="OPEN", is_archived=False, author__username="2026-0002").first()
        if lost:
            client("2026-0001").get(f"/p/{lost.pk}/?resume=message")
            open_chat = Conversation.objects.filter(post=lost, initiator__username="2026-0001").first()
    if open_chat:   # a question waiting for an answer (the owner's Answer button)
        from core.models import QuestionTemplate
        from core.services import ask_chat_questions, chat_roles
        asker, _ = chat_roles(open_chat)
        if asker:
            ask_chat_questions(open_chat, asker, list(QuestionTemplate.objects.filter(is_active=True)[:1]))


class _Undo(Exception):
    pass


def main():
    from django.db import transaction
    try:
        with transaction.atomic():
            make_situations()
            run()
            raise _Undo
    except _Undo:
        pass


def run():
    all_names = sorted({p.name for p in core_urls.urlpatterns if getattr(p, "name", None)})
    by_role = {}
    for role, (username, start) in ROLES.items():
        if username and not get_user_model().objects.filter(username=username).exists():
            print(f"{role}: no such demo account on this PC, skipped")
            continue
        names, pages = crawl(username, start)
        by_role[role] = names
        print(f"{role:24} {pages:4} pages opened by clicking, {len(names):3} kinds of page/action reached")
    print()
    missing = []
    for name in all_names:
        roles = [role for role, names in by_role.items() if name in names]
        if roles:
            print(f"  ok   {name:32} {', '.join(roles)}")
        elif name in NOT_CLICKED:
            print(f"  --   {name:32} not a page to click: {NOT_CLICKED[name]}")
        else:
            missing.append(name)
            print(f"  MISSING {name:29} nobody reaches it by clicking")
    print(f"\n{len(all_names)} URL patterns; {len(missing)} not reachable by clicking: {', '.join(missing) or 'none'}")
    print("(The situations made for this check were undone; the demo data is unchanged.)")


if __name__ == "__main__":
    main()
