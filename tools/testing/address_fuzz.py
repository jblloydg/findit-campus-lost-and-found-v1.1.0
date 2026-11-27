import os, sys
# Run from the project folder: python tools/testing/address_fuzz.py  (see tools/testing/README.md)
sys.path.insert(0, os.getcwd())
SERVER_CMD = [sys.executable, "manage.py", "runserver", "127.0.0.1:8765", "--noreload"]
CHROME = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
import os, sys, re
sys.path.insert(0, os.getcwd())
os.environ["DJANGO_SETTINGS_MODULE"] = "findit.settings"; os.environ["DJANGO_DEBUG"] = "1"
import django; django.setup()
from django.conf import settings; settings.ALLOWED_HOSTS = ["*"]
from django.test import Client
from django.contrib.auth import get_user_model
from core.models import ItemPost, Conversation
U = get_user_model()
post = str(ItemPost.objects.first().pk); conv = str(Conversation.objects.first().pk)
urls = ["/home/", f"/p/{post}/", "/staff/accounts/", "/staff/reports/", "/staff/general-reports/", "/staff/id-reviews/",
        "/reports/new/", "/notifications/", "/my-claims/", "/my-posts/", "/staff/", "/staff/questions/", "/messages/",
        f"/conversations/{conv}/", "/staff/moderators/", "/login/", "/signup/", "/id-review/new/", "/staff/admin/"]
for u in U.objects.filter(username__startswith="student-"): pass
extra = [f"/people/{u.pk}/report-block/" for u in U.objects.all()]
params = ["?page=abc", "?page=-1", "?page=99999", "?post=bad", "?post=00000000-0000-0000-0000-000000000000", "?status=<script>",
          "?q=%27%20OR%201%3D1--", "?open=abc", "?open=99999", "?conversation=bad", "?category=abc", "?type=X&date_from=2026-99-99&date_to=abc",
          "?role=developer", "?resume=message", "?resume=claim", "?next=//evil.example.com"]
bad = []
for name in ["2026-0001", "2026-0005", "security.demo", "moderator.demo", "findit-admin", None]:
    c = Client(raise_request_exception=False)
    if name: c.force_login(U.objects.get(username=name))
    for url in urls + extra:
        for p in params:
            r = c.get(url + p)
            if r.status_code >= 500: bad.append((name, url + p, r.status_code))
print("PROBLEMS:", bad[:30] or "none")
