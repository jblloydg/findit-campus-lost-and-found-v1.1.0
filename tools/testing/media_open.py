import os, sys
# Run from the project folder: python tools/testing/media_open.py  (see tools/testing/README.md)
sys.path.insert(0, os.getcwd())
from core.demo_logins import password_for  # CHG-008: demo passwords come from demo-logins.txt
SERVER_CMD = [sys.executable, "manage.py", "runserver", "127.0.0.1:8765", "--noreload"]
CHROME = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
import os, subprocess, time, json, sys
from playwright.sync_api import sync_playwright
os.environ["NO_PROXY"] = "127.0.0.1,localhost"; BASE = "http://127.0.0.1:8765"; conv = (sys.argv[1] if len(sys.argv) > 1 else open("/tmp/conv").read().strip())
MEASURE = open(os.path.join(os.path.dirname(__file__), "phone_fps.py")).read().split('MEASURE = """')[1].split('"""')[0]
srv = subprocess.Popen(SERVER_CMD); time.sleep(5)
with sync_playwright() as pw:
    b = pw.chromium.launch(**CHROME, args=["--no-proxy-server"])
    ctx = b.new_context(viewport={"width": 390, "height": 800}); p = ctx.new_page()
    p.goto(BASE + "/login/"); p.fill("input[name=username]", "sam.second@example.com"); p.fill("input[name=password]", password_for("sam.second@example.com")); p.click("form.stack-form button[type=submit]")
    cdp = ctx.new_cdp_session(p); cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    cdp.send("Network.enable"); cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150, "downloadThroughput": 1_500_000 / 8 * 1, "uploadThroughput": 750_000 / 8})
    sizes = {"page": 0, "media": 0, "media_files": 0}
    def on_resp(r):
        try:
            n = int(r.headers.get("content-length") or 0)
        except ValueError:
            n = 0
        if "/chat-media/" in r.url: sizes["media"] += n; sizes["media_files"] += 1
        elif "/conversations/" in r.url: sizes["page"] += n
    p.on("response", on_resp)
    t = time.time(); p.goto(f"{BASE}/conversations/{conv}/", wait_until="domcontentloaded"); text_ready = time.time() - t
    p.wait_for_timeout(4000)
    out = {"slow 3G-like phone (1.5 Mbit/s, 4x slower CPU)": True,
           "text visible after (s)": round(text_ready, 1),
           "messages on page": p.locator("[data-message-id]").count(),
           "media in page": p.locator(".chat-media").count(),
           "page KB": sizes["page"] // 1024,
           "media KB downloaded on open (only what is on screen)": sizes["media"] // 1024,
           "media files downloaded on open": sizes["media_files"]}
    p.evaluate("document.getElementById('chat-messages').scrollTop = 0")
    out["scroll up through media, smoothness"] = p.evaluate("""async (ms) => { const box = document.getElementById('chat-messages'); const go = setInterval(() => { box.scrollTop -= 0; box.scrollBy(0, -40); }, 16); """ + MEASURE.strip()[len("async (ms) => {"):].rsplit("}", 1)[0] + """; }""" , 4000) if False else None
    box = "document.getElementById('chat-messages')"
    p.evaluate(f"{box}.scrollTop = {box}.scrollHeight")
    p.wait_for_timeout(1000)
    res = p.evaluate("""async () => {
      const box = document.getElementById('chat-messages'); let frames = 0, worst = 0, last = performance.now(); const end = last + 5000;
      await new Promise(res => { function f(t) { frames++; worst = Math.max(worst, t - last); last = t; box.scrollBy(0, -25); if (t < end) requestAnimationFrame(f); else res(); } requestAnimationFrame(f); });
      return {fps: Math.round(frames / 5), worstFrameMs: Math.round(worst)}; }""")
    out["scrolling up through media for 5 s"] = res
    p.wait_for_timeout(3000)
    out["media KB after scrolling"] = sizes["media"] // 1024
    out["messages on page after scrolling (older loaded by itself)"] = p.locator("[data-message-id]").count()
    print(json.dumps(out, indent=1))
    b.close()
srv.terminate()
