import os, sys
# Run from the project folder: python tools/testing/page_timing.py  (see tools/testing/README.md)
sys.path.insert(0, os.getcwd())
SERVER_CMD = [sys.executable, "manage.py", "runserver", "127.0.0.1:8765", "--noreload"]
CHROME = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
import os, sys, time
sys.path.insert(0, os.getcwd()); os.environ["DJANGO_SETTINGS_MODULE"] = "findit.settings"; os.environ["DJANGO_DEBUG"] = "1"
import django; django.setup()
from django.conf import settings; settings.ALLOWED_HOSTS = ["*"]
from django.test import Client
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.contrib.auth import get_user_model
from core.models import Conversation
sam = get_user_model().objects.get(username="2026-0003")
c = Conversation.objects.filter(initiator=sam).first()
cl = Client(); cl.force_login(sam)
for url in [f"/conversations/{c.pk}/", f"/p/{c.post_id}/", "/notifications/", "/messages/", "/home/", "/my-claims/", "/profile/"]:
    best = None
    for _ in range(3):
        with CaptureQueriesContext(connection) as q:
            t = time.perf_counter(); r = cl.get(url); dt = (time.perf_counter() - t) * 1000
        best = dt if best is None else min(best, dt)
    print(f"{url[:40]:42} {r.status_code} {best:7.0f} ms  {len(r.content)/1024:7.0f} KB  {len(q.captured_queries):4d} queries")
