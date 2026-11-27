import os, sys
# Run from the project folder: python tools/testing/browser_notice.py  (see tools/testing/README.md)
sys.path.insert(0, os.getcwd())
SERVER_CMD = [sys.executable, "manage.py", "runserver", "127.0.0.1:8765", "--noreload"]
CHROME = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
import os, subprocess, time
from playwright.sync_api import sync_playwright
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
BASE = "http://127.0.0.1:8765"; PY = sys.executable; ROOT = os.getcwd()
def start():
    p = subprocess.Popen(SERVER_CMD); time.sleep(5); return p
def django(code):
    return subprocess.run([PY, "manage.py", "shell", "-c", code], cwd=ROOT, capture_output=True, text=True, env={**os.environ, "DJANGO_DEBUG": "1"}).stdout.strip()
srv = start()
errors = []
with sync_playwright() as pw:
    b = pw.chromium.launch(**CHROME, args=["--no-proxy-server"])
    ctx = b.new_context(); page = ctx.new_page(); chat = ctx.new_page()
    for p in (page, chat): p.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "/login/")
    page.fill("input[name=username]", "sam.second@example.com"); page.fill("input[name=password]", "DemoFindIt!2026")
    page.click("form.stack-form button[type=submit]")
    page.goto(BASE + "/notifications/"); page.goto(BASE + "/home/"); page.wait_for_timeout(1500)
    print("start badge:", page.locator(".notice-count").count() and page.inner_text(".notice-count"))
    href = None
    page2 = chat; page2.goto(BASE + "/messages/")
    href = page2.locator("a[href^='/conversations/']").first.get_attribute("href"); page2.goto(BASE + href); page2.wait_for_timeout(1500)
    conv = href.strip("/").split("/")[1]
    # Live notification while connected: Alex (another browser) approves Sam's claim.
    alex_ctx = b.new_context(); alex = alex_ctx.new_page()
    alex.goto(BASE + "/login/"); alex.fill("input[name=username]", "alex.finder@example.com"); alex.fill("input[name=password]", "DemoFindIt!2026")
    alex.click("form.stack-form button[type=submit]")
    alex.goto(BASE + href); alex.click("form[action*='/approve/'] button"); alex.wait_for_timeout(1500)
    page.wait_for_timeout(1500)
    print("live badge:", page.locator(".notice-count").count() and page.inner_text(".notice-count"),
          "priority:", page.locator(".priority-count").count() and page.inner_text(".priority-count"),
          "| flash:", page.locator(".flash", has_text="approved").count())
    srv.terminate(); srv.wait(); page.wait_for_timeout(1500)
    # While the server is down: Alex writes in the chat, Jamie gets 2 notices.
    print(django(f"from core.models import ChatMessage, Conversation; from django.contrib.auth import get_user_model as g; c=Conversation.objects.get(pk='{conv}'); ChatMessage.objects.create(conversation=c, sender=g().objects.get(username='2026-0001'), text='Sent while you were offline'); print('made')"))
    django("from core.verification import notify_account; from django.contrib.auth import get_user_model as g; u=g().objects.get(username='2026-0003'); notify_account(u, 'Offline notice A', '/home/'); notify_account(u, 'Offline notice B', '/home/', priority=True)")
    for p in (page, page2):
        p.evaluate("""() => { window.__flashes = []; new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => { if (n.classList && n.classList.contains('flash')) window.__flashes.push(n.textContent); }))).observe(document.body, {childList: true, subtree: true}); }""")
    t0 = time.time(); srv = start()
    chat_t = notice_t = None
    for _ in range(120):
        page.wait_for_timeout(500)
        if chat_t is None and page2.locator(".chat-message p", has_text="Sent while you were offline").count(): chat_t = time.time() - t0
        if notice_t is None and len(page.evaluate("window.__flashes")) >= 2: notice_t = time.time() - t0
        if chat_t and notice_t: break
    print("server back -> chat caught up after", chat_t and round(chat_t), "s; notices after", notice_t and round(notice_t), "s | flashes:", page.evaluate("window.__flashes"))
    real = django("from core.models import InAppNotification as N; from django.contrib.auth import get_user_model as g; u=g().objects.get(username='2026-0003'); q=N.objects.filter(recipient=u, read_at__isnull=True); print(q.count(), q.filter(is_priority=True).count())")
    print("after reconnect badge:", page.inner_text(".notice-count"), "priority:", page.locator(".priority-count").count() and page.inner_text(".priority-count"), "| database says:", real)

    print("page2 hidden:", page2.evaluate("document.hidden"), "| page2 status:", repr(page2.inner_text("#chat-status")) if page2.locator("#chat-status").count() else "no status line", "| can-send:", page2.get_attribute("#chat-messages", "data-can-send"))
    print("db:", django(f"from core.models import ChatMessage as M; print(M.objects.filter(conversation_id='{conv}', text__startswith='Sent while').count())"))
    print("chat caught up:", page2.locator(".chat-message p", has_text="Sent while you were offline").count())
    page.reload(); page.wait_for_timeout(2000)
    print("after reload badge:", page.inner_text(".notice-count"), "| duplicate flashes:", page.locator(".flash", has_text="Offline notice").count())
    b.close()
print("JS errors:", errors or "none")
srv.terminate()
