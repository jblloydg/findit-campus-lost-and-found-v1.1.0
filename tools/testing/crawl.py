"""Open every reachable page as each demo role and report crashes (5xx) and odd statuses."""
import os, sys
# Run from the project folder: python tools/testing/crawl.py  (see tools/testing/README.md)
sys.path.insert(0, os.getcwd())
SERVER_CMD = [sys.executable, "manage.py", "runserver", "127.0.0.1:8765", "--noreload"]
CHROME = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}

import os, re, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "findit.settings")
os.environ["DJANGO_DEBUG"] = "1"
import django
django.setup()
from django.conf import settings
settings.ALLOWED_HOSTS = ["*"]
from django.test import Client
from django.contrib.auth import get_user_model
U = get_user_model()
ROLES = ["2026-0001", "2026-0003", "2026-0005", "security.demo", "moderator.demo", "findit-admin", "dev.test", None]  # dev.test: a local Developer account made only for testing
SKIP = ("/logout/", "/static/", "/media/", "/captcha/", "/django-admin/logout", "/django-admin/jsi18n")
problems = []
for name in ROLES:
    c = Client(raise_request_exception=False)
    if name:
        user = U.objects.filter(username=name).first()
        if user is None:
            print(f"{name}: skipped (no such account on this PC)")
            continue
        c.force_login(user)
    seen, queue = set(), ["/", "/home/", "/staff/", "/staff/admin/", "/profile/", "/verify-email/", "/test-inbox/",
                          "/staff/id-reviews/", "/profile/blocked/", "/id-review/new/", "/profile/student-id/",
                          "/notifications/", "/messages/", "/my-claims/", "/my-posts/", "/signup/", "/login/",
                          "/password-reset/", "/staff/settings/", "/staff/accounts/", "/django-admin/", "/health/"]
    while queue and len(seen) < 400:
        url = queue.pop(0)
        if url in seen or url.startswith(SKIP):
            continue
        seen.add(url)
        r = c.get(url)
        if r.status_code >= 500 or r.status_code not in (200, 301, 302, 403, 404, 405):
            problems.append((name, url, r.status_code))
        if r.status_code == 200 and "text/html" in r.get("Content-Type", ""):
            for href in re.findall(r'href="(/[^"#]*)', r.content.decode("utf-8", "replace")):
                href = href.replace("&amp;", "&")
                if href not in seen and not href.startswith(SKIP) and "download" not in href:
                    queue.append(href)
    print(f"{name or 'signed-out'}: {len(seen)} pages")
print("PROBLEMS:", problems or "none")
