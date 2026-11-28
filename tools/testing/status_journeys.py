"""v2.1.0: every post status can be reached by CLICKING, with the accounts that must cooperate.

Run from the project folder, with the server already running on 127.0.0.1:8000 (or set FINDIT_URL),
after `migrate` and `seed_demo`:
    python tools/testing/status_journeys.py

Each journey makes its own new post (titles end with a time stamp) and only uses buttons people can
see, in a real Chrome window (Playwright), signed in as the demo accounts:
  A. FOUND, handed over in person:   finder posts → claimant claims → finder approves → finder marks
     returned → claimant confirms                 (Open → Claim in Progress → Returned → Claimed)
  B. FOUND, via the guard house:     finder posts and ticks "I'll bring it" → claimant claims → finder
     approves → guard types the turn-in code and confirms → guard releases to the approved claimant
                                                   (Open → Claim in Progress → At Guard House → Claimed)
  C. LOST, owner verified in chat:   owner posts LOST → finder "I found this – message the owner" →
     finder sends 3 ownership questions (＋ menu) → owner answers → finder approves → finder marks
     returned → owner confirms                    (Open → Claim in Progress → Returned → Claimed)
  D. Guard house and back:           finder posts, brings it, guard confirms (At Guard House) → finder
     asks staff to take it back → guard approves  (At Guard House → Open)
  E. Closed:                          author closes the listing (Open → Closed)
Prints PASS/FAIL per step and saves screenshots to tools/testing/out/status_journeys/.
"""
import io
import os
import sys
import time

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "findit.settings")
os.environ["DJANGO_DEBUG"] = "1"
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
import django  # noqa: E402

django.setup()
from django.conf import settings  # noqa: E402

settings.ALLOWED_HOSTS = ["*"]
from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402
from PIL import Image  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from core.models import ItemPost  # noqa: E402

BASE = os.environ.get("FINDIT_URL", "http://127.0.0.1:8000")
OUT = os.path.join("tools", "testing", "out", "status_journeys")
FINDER, CLAIMANT, OWNER, GUARD = "2026-0001", "2026-0003", "2026-0002", "security.demo"
STAMP = time.strftime("%H%M%S")
RESULTS = []
os.makedirs(OUT, exist_ok=True)
PHOTO = os.path.join(OUT, "photo.jpg")
Image.new("RGB", (320, 240), (40, 110, 90)).save(PHOTO, "JPEG")


def cookie_for(username):
    client = Client()
    client.force_login(get_user_model().objects.get(username=username))
    return client.cookies[settings.SESSION_COOKIE_NAME].value


def check(label, ok, detail=""):
    RESULTS.append((label, ok))
    print(("PASS " if ok else "FAIL ") + label + (f"  ({detail})" if detail else ""))


def status_of(title):
    return ItemPost.objects.get(title=title).get_status_display()


class Person:
    def __init__(self, browser, username, width=1280):
        self.username = username
        self.ctx = browser.new_context(viewport={"width": width, "height": 900})
        self.ctx.add_cookies([{"name": settings.SESSION_COOKIE_NAME, "value": cookie_for(username), "url": BASE}])
        self.page = self.ctx.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))

    def go(self, path):
        self.page.goto(BASE + path)
        self.page.wait_for_load_state("networkidle")

    def click(self, text, scope=None):
        target = (scope or self.page).get_by_role("button", name=text).or_(
            (scope or self.page).get_by_role("link", name=text)).locator("visible=true").first
        target.click()
        self.page.wait_for_load_state("networkidle")

    def shot(self, name):
        self.page.screenshot(path=os.path.join(OUT, f"{name}.png"))


def post_item(person, post_type, title, guardhouse=False):
    person.go("/home/")
    person.click("Report found item" if post_type == "FOUND" else "Report lost item")   # from the sidebar
    page = person.page
    page.select_option("select[name=category]", index=1)
    page.fill("input[name=title]", title)
    page.set_input_files("input[name=photos]", PHOTO)
    if guardhouse:
        page.check("input[name=bring_to_guardhouse]")
    page.get_by_role("button", name="Publish post").click()
    page.wait_for_load_state("networkidle")
    return ItemPost.objects.get(title=title)


def claim_item(claimant, post):
    claimant.go(f"/home/?q={post.title}")
    claimant.page.get_by_text(post.title).first.click()          # open it from the listing
    claimant.page.wait_for_load_state("networkidle")
    claimant.click("Claim this item")
    form = claimant.page.locator("#claim-form form")
    for select in form.locator("select").all():
        select.select_option(index=1)
    for box in form.locator("textarea, input[type=text]").all():
        box.fill("Blue with a small scratch near the bottom")
    form.get_by_role("button", name="Submit private claim").click()
    claimant.page.wait_for_load_state("networkidle")


def approve_from_post(finder, post):
    finder.go(f"/p/{post.pk}/")
    finder.page.locator(".application-row").get_by_role("button", name="Approve").first.click()
    finder.page.wait_for_load_state("networkidle")


def journey_a(browser):
    title = f"Journey A wallet {STAMP}"
    finder, claimant = Person(browser, FINDER), Person(browser, CLAIMANT)
    post = post_item(finder, "FOUND", title)
    check("A1 finder posts FOUND → Open for Claim", status_of(title) == "Open for Claim")
    claim_item(claimant, post)
    check("A2 claimant claims → Claim in Progress", status_of(title) == "Claim in Progress")
    approve_from_post(finder, post)
    finder.go(f"/p/{post.pk}/")
    finder.click("Mark returned")
    check("A3 finder approves + marks returned → Returned", status_of(title) == "Returned")
    claimant.go(f"/p/{post.pk}/")
    claimant.click("Confirm I received it")
    claimant.shot("A_claimed")
    check("A4 claimant confirms → Claimed", status_of(title) == "Claimed")
    return finder.errors + claimant.errors


def journey_b(browser):
    title = f"Journey B calculator {STAMP}"
    finder, claimant, guard = Person(browser, FINDER), Person(browser, CLAIMANT), Person(browser, GUARD)
    post = post_item(finder, "FOUND", title, guardhouse=True)
    ticket = post.turn_in_tickets.get(finder__username=FINDER)
    check("B1 finder posts FOUND and ticks guard house (staff told)", ticket.requested_at is not None)
    claim_item(claimant, post)
    approve_from_post(finder, post)
    check("B2 claim submitted and approved → Claim in Progress", status_of(title) == "Claim in Progress")
    guard.go("/staff/")
    guard.click("Scan turn-in QR")   # staff dashboard button
    guard.page.fill("#manual-code", ticket.code)
    guard.click("Look up code")
    guard.click("Confirm turned in")
    guard.shot("B_at_guard_house")
    check("B3 guard types the turn-in code and confirms → At Guard House", status_of(title) == "At Guard House")
    guard.go(f"/p/{post.pk}/")
    guard.click("Release at guard house")
    check("B4 guard releases to the approved claimant → Claimed", status_of(title) == "Claimed")
    return finder.errors + claimant.errors + guard.errors


def journey_c(browser):
    title = f"Journey C earphones {STAMP}"
    owner, finder = Person(browser, OWNER), Person(browser, FINDER)
    post = post_item(owner, "LOST", title)
    check("C1 owner posts LOST → Open for Claim", status_of(title) == "Open for Claim")
    finder.go(f"/home/?type=LOST&q={post.title}")
    finder.page.get_by_text(post.title).first.click()
    finder.page.wait_for_load_state("networkidle")
    finder.click("I found this – message the owner")
    finder.page.wait_for_timeout(1500)
    frame = finder.page.frame(name="findit-chat")
    check("C2 'I found this' opens the chat window", frame is not None and "/conversations/" in frame.url)
    frame.locator(".chat-plus").click()
    frame.get_by_role("menuitem", name="Ownership questions").click()
    boxes = frame.locator(".chat-question-list input[type=checkbox]")
    for i in range(3):
        boxes.nth(i).check()
    frame.get_by_role("button", name="Send questions").click()
    finder.page.wait_for_timeout(1200)
    check("C3 finder sends 3 ownership questions → Claim in Progress", status_of(title) == "Claim in Progress")
    conversation = ItemPost.objects.get(title=title).conversations.first()
    owner.go(f"/conversations/{conversation.pk}/")
    for _ in range(5):   # answer one card at a time (the cards are redrawn after each answer)
        form = owner.page.locator(".question-answer-form").first
        if not form.count():
            break
        if form.locator("select").count():
            form.locator("select").select_option(index=1)
        else:
            form.locator("textarea").fill("Black case, my initials inside")
        form.get_by_role("button", name="Answer").click()
        owner.page.wait_for_load_state("networkidle")
        owner.page.wait_for_timeout(400)
    check("C4 owner answers all questions", conversation.questions.filter(answered_at__isnull=True).count() == 0)
    finder.go(f"/conversations/{conversation.pk}/")
    finder.click("Approve")
    finder.click("Mark returned to owner")
    check("C5 finder approves and marks returned → Returned", status_of(title) == "Returned")
    owner.go(f"/conversations/{conversation.pk}/")
    owner.click("Confirm I received it")
    check("C6 owner confirms → Claimed", status_of(title) == "Claimed")
    return owner.errors + finder.errors


def journey_d(browser):
    title = f"Journey D umbrella {STAMP}"
    finder, guard = Person(browser, FINDER), Person(browser, GUARD)
    post = post_item(finder, "FOUND", title)
    finder.go(f"/p/{post.pk}/")
    finder.click("I'm bringing it to the guard house")
    ticket = post.turn_in_tickets.get(finder__username=FINDER)
    guard.go(f"/staff/turn-in/{ticket.code}/")
    guard.click("Confirm turned in")
    check("D1 finder brings it, guard confirms → At Guard House", status_of(title) == "At Guard House")
    finder.go(f"/p/{post.pk}/")
    finder.page.locator("#guardhouse-panel summary").click()
    finder.page.select_option("select[name=requested_status]", value="OPEN")
    finder.page.fill("textarea[name=reason], input[name=reason]", "The owner messaged me; I will hand it over myself.")
    finder.click("Send to staff")
    guard.go(f"/p/{post.pk}/")
    guard.page.locator(".status-request-row").get_by_role("button", name="Approve").click()
    guard.page.wait_for_load_state("networkidle")
    check("D2 finder asks to take it back, guard approves → Open for Claim", status_of(title) == "Open for Claim")
    return finder.errors + guard.errors


def journey_e(browser):
    title = f"Journey E notebook {STAMP}"
    author = Person(browser, FINDER)
    post = post_item(author, "FOUND", title)
    author.go(f"/p/{post.pk}/")
    author.click("Close listing")
    check("E1 author closes the listing → Closed", status_of(title) == "Closed")
    return author.errors


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        errors = []
        for journey in (journey_a, journey_b, journey_c, journey_d, journey_e):
            try:
                errors += journey(browser)
            except Exception as exc:  # keep going so one broken step does not hide the others
                check(f"{journey.__name__} stopped", False, str(exc).splitlines()[0][:160])
        check("no script errors in any page", not errors, "; ".join(errors[:3]))
        browser.close()
    passed = sum(ok for _, ok in RESULTS)
    print(f"\n{passed} of {len(RESULTS)} checks passed")
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
