"""100 students in 50 chats at once (+100 notification connections, +20 people loading pages),
each sending a message every 2 seconds for 30 seconds, while the timer runner also runs.
Measures how long a message takes to come back, errors, and 'database is locked'."""
import os, sys
# Run from the project folder: python tools/testing/load_test.py  (see tools/testing/README.md)
sys.path.insert(0, os.getcwd())
SERVER_CMD = [sys.executable, "manage.py", "runserver", "127.0.0.1:8765", "--noreload"]
CHROME = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}

import asyncio, json, os, sys, time, statistics, subprocess, random
sys.path.insert(0, os.getcwd()); os.environ["DJANGO_SETTINGS_MODULE"] = "findit.settings"; os.environ["DJANGO_DEBUG"] = "1"
import django; django.setup()
from django.contrib.auth import get_user_model, SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from core.models import Conversation, ItemPost, Category
import websockets, aiohttp
U = get_user_model()
author = U.objects.get(username="2026-0001")
post = ItemPost.objects.filter(post_type="LOST").first()
pairs = []
for i in range(int(os.environ.get("PAIRS", "50"))):
    a, _ = U.objects.get_or_create(username=f"load-a{i}", defaults={"email": f"la{i}@example.com"})
    b, _ = U.objects.get_or_create(username=f"load-b{i}", defaults={"email": f"lb{i}@example.com"})
    for u in (a, b):
        u.profile.email_verified_at = timezone.now(); u.profile.save()  # verified: no chat limits
    conv, _ = Conversation.objects.get_or_create(post=post, initiator=a, recipient=b, claim=None)
    pairs.append((a, b, conv))
def cookie(user):
    s = SessionStore(); s[SESSION_KEY] = str(user.pk); s[BACKEND_SESSION_KEY] = "core.auth.FindItBackend"
    s[HASH_SESSION_KEY] = user.get_session_auth_hash(); s.create(); return f"sessionid={s.session_key}"
jobs = [(cookie(a), conv) for a, b, conv in pairs] + [(cookie(b), conv) for a, b, conv in pairs]
URL = "ws://127.0.0.1:8765"
latencies, errors, sent = [], [], [0]
async def chatter(ck, conv, seconds):
    try:
        async with websockets.connect(f"{URL}/ws/conversations/{conv.pk}/", additional_headers={"Cookie": ck, "Origin": "http://127.0.0.1:8765"}) as ws:
            await ws.recv()
            waiting = {}
            async def reader():
                async for raw in ws:
                    d = json.loads(raw)
                    if d.get("type") == "message" and d.get("client_id") in waiting:
                        latencies.append((time.perf_counter() - waiting.pop(d["client_id"])) * 1000)
                    elif d.get("type") == "error": errors.append(d.get("message"))
            task = asyncio.create_task(reader())
            end = time.time() + seconds
            await asyncio.sleep(random.random() * 2)
            while time.time() < end:
                cid = f"{random.random()}"
                waiting[cid] = time.perf_counter(); sent[0] += 1
                await ws.send(json.dumps({"message": "load test message", "client_id": cid}))
                await asyncio.sleep(2)
            await asyncio.sleep(3); task.cancel()
    except Exception as e:
        errors.append(repr(e)[:120])
async def notices(ck, seconds):
    try:
        async with websockets.connect(f"{URL}/ws/notifications/", additional_headers={"Cookie": ck, "Origin": "http://127.0.0.1:8765"}) as ws:
            await ws.recv(); end = time.time() + seconds
            while time.time() < end:
                await ws.send(json.dumps({"type": "sync"})); await ws.recv(); await asyncio.sleep(5)
    except Exception as e:
        errors.append("notice " + repr(e)[:100])
page_times = []
async def browser(ck, seconds):
    async with aiohttp.ClientSession(headers={"Cookie": ck}) as s:
        end = time.time() + seconds
        while time.time() < end:
            for path in ("/home/", "/messages/", "/notifications/"):
                t = time.perf_counter()
                async with s.get("http://127.0.0.1:8765" + path) as r:
                    await r.read()
                    if r.status != 200: errors.append(f"page {path} {r.status}")
                page_times.append((time.perf_counter() - t) * 1000)
            await asyncio.sleep(1)
async def main():
    await asyncio.gather(*[chatter(ck, c, 30) for ck, c in jobs], *[notices(ck, 30) for ck, _ in jobs],
                         *[browser(ck, 30) for ck, _ in jobs[:int(os.environ.get("LOADERS", "20"))]])
timer = subprocess.Popen([sys.executable, "manage.py", "process_due", "--loop"], env={**os.environ, "DJANGO_DEBUG": "1"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
t0 = time.time(); asyncio.run(main()); timer.terminate()
q = sorted(latencies)
pct = lambda p: round(q[min(len(q) - 1, int(len(q) * p))]) if q else None
print(f"{len(jobs)} chat + {len(jobs)} notice connections + 20 page loaders for {time.time()-t0:.0f} s")
print(f"messages sent {sent[0]}, echoed back {len(q)}, rate ~{sent[0]/30:.0f}/s")
print(f"message round trip ms: median {pct(.5)}, 95% {pct(.95)}, worst {round(q[-1]) if q else None}")
pq = sorted(page_times); print(f"page loads {len(pq)}: median {round(pq[len(pq)//2])} ms, 95% {round(pq[int(len(pq)*.95)])} ms, worst {round(pq[-1])} ms")
print("errors:", len(errors), errors[:5])
