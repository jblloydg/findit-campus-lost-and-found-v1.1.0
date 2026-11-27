import os, sys
# Run from the project folder: python tools/testing/browser_queue.py  (see tools/testing/README.md)
sys.path.insert(0, os.getcwd())
SERVER_CMD = [sys.executable, "manage.py", "runserver", "127.0.0.1:8765", "--noreload"]
CHROME = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
import os, subprocess, time, sqlite3
from playwright.sync_api import sync_playwright
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
BASE = "http://127.0.0.1:8765"
def start():
    p = subprocess.Popen(SERVER_CMD); time.sleep(5); return p
srv = start()
with sync_playwright() as pw:
    b = pw.chromium.launch(**CHROME, args=["--no-proxy-server"])
    page = b.new_page()
    page.goto(BASE + "/login/")
    page.fill("input[name=username]", "jamie.claimant@example.com"); page.fill("input[name=password]", "DemoFindIt!2026")
    page.click("form.stack-form button[type=submit]")
    page.goto(BASE + "/messages/")
    href = page.locator("a[href^='/conversations/']").first.get_attribute("href")
    page.goto(BASE + href); page.wait_for_timeout(1500)
    conv = href.strip("/").split("/")[1]
    print("connected status:", repr(page.inner_text("#chat-status")))
    # 1) Server goes down.
    srv.terminate(); srv.wait(); page.wait_for_timeout(1500)
    print("after drop:", page.inner_text("#chat-status"))
    page.fill("#chat-input", "Queued while offline 1"); page.click("#chat-form button")
    page.fill("#chat-input", "Queued while offline 1"); page.click("#chat-form button")  # double press, same text
    print("pending bubbles:", page.locator(".is-pending").count())
    # 2) Reload while the server is still down? Can't load a page then, so queue one more and keep the page.
    page.fill("#chat-input", "Queued while offline 2"); page.click("#chat-form button")
    print("pending bubbles:", page.locator(".is-pending").count(), "| status:", page.inner_text("#chat-status"))
    # 3) Server comes back; the chat reconnects by itself and sends the queue.
    srv = start(); page.wait_for_timeout(12000)
    print("after reconnect pending:", page.locator(".is-pending").count(), "| status:", repr(page.inner_text("#chat-status")))
    texts = page.locator("#chat-messages .chat-message p").all_inner_texts()
    print("on screen:", [t for t in texts if t.startswith("Queued")])
    # 4) Reload: the queue is empty and nothing is sent twice.
    page.reload(); page.wait_for_timeout(2500)
    texts = page.locator("#chat-messages .chat-message p").all_inner_texts()
    print("after reload:", [t for t in texts if t.startswith("Queued")], "pending:", page.locator(".is-pending").count())
    b.close()
db = sqlite3.connect(os.path.join(os.getcwd(), "db.sqlite3"))
print("saved in database:", db.execute("select text, count(*) from core_chatmessage where text like 'Queued%' group by text").fetchall())
srv.terminate()
