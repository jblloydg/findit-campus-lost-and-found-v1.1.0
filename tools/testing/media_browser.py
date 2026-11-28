import os, sys
# Run from the project folder: python tools/testing/media_browser.py  (see tools/testing/README.md)
sys.path.insert(0, os.getcwd())
from core.demo_logins import password_for  # CHG-008: demo passwords come from demo-logins.txt
SERVER_CMD = [sys.executable, "manage.py", "runserver", "127.0.0.1:8765", "--noreload"]
CHROME = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
import os, subprocess, time, json, sqlite3
from playwright.sync_api import sync_playwright
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
BASE = "http://127.0.0.1:8765"; ROOT = os.getcwd(); M = os.path.join(os.getcwd(), "tools", "testing", "media") + os.sep
def start():
    p = subprocess.Popen(SERVER_CMD); time.sleep(5); return p
srv = start(); report = {}
errors = []
with sync_playwright() as pw:
    b = pw.chromium.launch(**CHROME, args=["--no-proxy-server"])
    ctx = b.new_context(viewport={"width": 390, "height": 800}); p = ctx.new_page()
    p.on("pageerror", lambda e: errors.append(str(e)))
    p.goto(BASE + "/login/"); p.fill("input[name=username]", "sam.second@example.com"); p.fill("input[name=password]", password_for("sam.second@example.com")); p.click("form.stack-form button[type=submit]")
    p.goto(BASE + "/messages/"); href = p.locator("a[href^='/conversations/']").first.get_attribute("href"); p.goto(BASE + href); p.wait_for_timeout(1000)
    cdp = ctx.new_cdp_session(p); cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    # 1) too-big photo is refused before uploading
    p.set_input_files("#chat-file", M + "phone_photo.jpg"); p.wait_for_timeout(300)
    report["7 MB photo"] = p.inner_text("#chat-status")
    # 2) 4 MB photo: upload -> ready
    t = time.time(); p.set_input_files("#chat-file", M + "phone_photo_4mb.jpg")
    p.wait_for_selector(".chat-message[data-message-id] .chat-media img", timeout=60000)
    report["4 MB photo: picked -> visible in chat (s)"] = round(time.time() - t, 1)
    # 3) 20 MB / 59 s 1080p video: upload -> processing -> ready
    t = time.time(); p.set_input_files("#chat-file", M + "phone_video_59s.mp4")
    p.wait_for_selector(".is-pending time:has-text('processing')", timeout=120000)
    report["20 MB video: upload finished (s)"] = round(time.time() - t, 1)
    # page stays responsive while the server encodes the video
    t2 = time.time(); r = p.request.get(BASE + "/home/"); report["Browse page load while video encodes (ms)"] = round((time.time() - t2) * 1000)
    p.wait_for_selector(".chat-message[data-message-id] video.chat-media", timeout=300000)
    report["20 MB video: picked -> playable in chat (s)"] = round(time.time() - t, 1)
    # 4) offline: stop server, pick photo, restart -> sent by itself, once
    srv.terminate(); srv.wait(); p.wait_for_timeout(1500)
    p.set_input_files("#chat-file", M + "phone_photo_4mb.jpg"); p.wait_for_timeout(1500)
    report["offline photo bubble"] = p.locator(".is-pending time").last.inner_text()
    p.reload(wait_until="commit") if False else None
    srv = start()
    p.wait_for_function("document.querySelectorAll('.chat-message[data-message-id] .chat-media img').length >= 2", timeout=90000)
    report["offline photo sent after server came back"] = True
    p.wait_for_timeout(1500)
    report["pending bubbles left"] = p.locator(".is-pending").count()
    b.close()
db = sqlite3.connect(ROOT + "/db.sqlite3")
rows = db.execute("select kind,status,uploaded_bytes,stored_bytes,width,height,duration_seconds,error from core_chatattachment").fetchall()
report["stored"] = [dict(zip(["kind","status","uploaded_KB","stored_KB","w","h","sec","error"], [r[0], r[1], r[2]//1024, r[3]//1024, r[4], r[5], r[6], r[7]])) for r in rows]
report["JS errors"] = errors or "none"
print(json.dumps(report, indent=1))
srv.terminate()
