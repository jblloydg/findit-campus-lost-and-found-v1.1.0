"""DES-002 check: every page shows the DOrSU monument background, at every screen size.

Run from the project folder, with the server already running on 127.0.0.1:8000
(or set FINDIT_URL), after `migrate` and `seed_demo`:

    python tools/testing/campus_bg_check.py            # all pages, 3 widths
    WIDTHS=360,390,768,1280,1920 python tools/testing/campus_bg_check.py

For each demo role it:
  1. finds every reachable page (same crawl idea as crawl.py, one page per URL pattern),
  2. opens it in Chrome at each width and checks
       - <body> has the campus-bg class and the photo layer really loaded,
       - nothing makes the page wider than the screen (no sideways scrolling),
  3. saves a screenshot to tools/testing/out/campus_bg/<role>/<width>/<page>.png
Set CHROME_PATH if Chrome is not found automatically.
"""
import os, re, sys, json
sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "findit.settings")
os.environ["DJANGO_DEBUG"] = "1"
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"  # Playwright runs an event loop; this is a local test script
import django
django.setup()
from django.conf import settings
settings.ALLOWED_HOSTS = ["*"]
from django.test import Client
from django.contrib.auth import get_user_model
from playwright.sync_api import sync_playwright

BASE = os.environ.get("FINDIT_URL", "http://127.0.0.1:8000")
WIDTHS = [int(w) for w in os.environ.get("WIDTHS", "360,768,1280").split(",")]
HEIGHTS = {320: 640, 360: 780, 390: 844, 430: 932, 768: 1024, 1280: 800, 1440: 900, 1920: 1080}
CHROME = os.environ.get("CHROME_PATH") or next((p for p in ("/usr/bin/google-chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe") if os.path.exists(p)), None)
OUT = os.path.join("tools", "testing", "out", "campus_bg")
ROLES = ["2026-0001", "2026-0005", "security.demo", "moderator.demo", "findit-admin", None]
SKIP = ("/logout/", "/static/", "/media/", "/captcha/", "/django-admin/", "/health/", "/chat-media/")
START = ["/", "/home/", "/staff/", "/staff/admin/", "/profile/", "/verify-email/", "/test-inbox/",
         "/staff/id-reviews/", "/profile/blocked/", "/id-review/new/", "/profile/student-id/",
         "/notifications/", "/messages/", "/my-claims/", "/my-posts/", "/my-reports/", "/reports/new/",
         "/signup/", "/login/", "/password-reset/", "/password-reset/sent/", "/password-reset/complete/",
         "/staff/settings/", "/staff/accounts/", "/staff/moderators/", "/staff/general-reports/",
         "/staff/reports/", "/staff/categories/", "/staff/questions/", "/staff/admin/backups/",
         "/staff/scan/", "/posts/new/", "/profile/edit/", "/profile/password/", "/this-page-does-not-exist/"]
U = get_user_model()


def pattern(url):
    url = url.split("?")[0]
    url = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<uuid>", url)
    url = re.sub(r"/\d+/", "/<n>/", url)
    url = re.sub(r"/[A-Z0-9]{6,}/", "/<code>/", url)
    return url


def discover(client):
    seen, found, queue = set(), {}, list(START)
    while queue and len(seen) < 500:
        url = queue.pop(0)
        if url in seen or url.startswith(SKIP):
            continue
        seen.add(url)
        r = client.get(url)
        if "text/html" not in r.get("Content-Type", "") or r.status_code not in (200, 403, 404):
            continue
        found.setdefault(pattern(url), url)
        for href in re.findall(r'href="(/[^"#]*)', r.content.decode("utf-8", "replace")):
            href = href.replace("&amp;", "&")
            if "?" in href or "download" in href or "/qr.svg" in href or "/attachment/" in href:
                continue
            if href not in seen and not href.startswith(SKIP):
                queue.append(href)
    return found


CHECK_JS = """() => {
  const b = document.body, before = getComputedStyle(b, '::before');
  const wide = [...document.querySelectorAll('body *')].filter(e => {
    const r = e.getBoundingClientRect(); return r.width && r.right > innerWidth + 1 && getComputedStyle(e).position !== 'fixed';
  }).slice(0, 3).map(e => e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : ''));
  return {
    cls: b.className,
    photo: before.backgroundImage.includes('dorsu-monument'),
    overflow: document.documentElement.scrollWidth - innerWidth,
    wide,
  };
}"""


def slug(p):
    return re.sub(r"[^a-z0-9]+", "-", p.lower()).strip("-") or "root"


def main():
    results, problems = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**({"executable_path": CHROME} if CHROME else {}))
        for role in ROLES:
            client = Client(raise_request_exception=False)
            if role:
                client.force_login(U.objects.get(username=role))
            pages = discover(client)
            cookies = []
            if role:
                cookies = [{"name": settings.SESSION_COOKIE_NAME, "value": client.cookies[settings.SESSION_COOKIE_NAME].value, "url": BASE}]
            label = role or "signed-out"
            print(f"{label}: {len(pages)} page patterns")
            for w in WIDTHS:
                ctx = browser.new_context(viewport={"width": w, "height": HEIGHTS.get(w, 900)}, device_scale_factor=1)
                if cookies:
                    ctx.add_cookies(cookies)
                page = ctx.new_page()
                folder = os.path.join(OUT, slug(label), str(w))
                os.makedirs(folder, exist_ok=True)
                for pat, url in sorted(pages.items()):
                    page.goto(BASE + url, wait_until="networkidle")
                    info = page.evaluate(CHECK_JS)
                    shot = os.path.join(folder, slug(pat) + ".png")
                    page.screenshot(path=shot, full_page=True)
                    row = {"role": label, "width": w, "page": pat, **info}
                    results.append(row)
                    bad = []
                    if "campus-bg" not in info["cls"]:
                        bad.append("no campus-bg class")
                    elif not info["photo"]:
                        bad.append("photo layer missing")
                    if info["overflow"] > 1:
                        bad.append(f"{info['overflow']}px sideways scroll ({', '.join(info['wide'])})")
                    if bad:
                        problems.append((label, w, pat, "; ".join(bad)))
                ctx.close()
        browser.close()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "results.json"), "w") as fh:
        json.dump(results, fh, indent=1)
    print(f"checked {len(results)} page views")
    print("PROBLEMS:")
    for p in problems:
        print("  ", *p)
    if not problems:
        print("   none")


if __name__ == "__main__":
    main()
