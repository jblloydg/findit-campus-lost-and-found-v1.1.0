"""Open the big chat on a slow 'phone' (4x CPU slowdown), then the other person sends
a burst2 of 200 messages. Measure frames per second and long freezes (>50 ms)."""
import os, sys
# Run from the project folder: python tools/testing/phone_fps.py  (see tools/testing/README.md)
sys.path.insert(0, os.getcwd())
from core.demo_logins import password_for  # CHG-008: demo passwords come from demo-logins.txt
SERVER_CMD = [sys.executable, "manage.py", "runserver", "127.0.0.1:8765", "--noreload"]
CHROME = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}

import os, subprocess, time, json, asyncio, sys
from playwright.sync_api import sync_playwright
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
BASE = "http://127.0.0.1:8765"; PY = sys.executable; ROOT = os.getcwd()
srv = subprocess.Popen(SERVER_CMD); time.sleep(5)
def login(ctx, email, pw):
    p = ctx.new_page(); p.goto(BASE + "/login/"); p.fill("input[name=username]", email); p.fill("input[name=password]", pw)
    p.click("form.stack-form button[type=submit]"); return p
MEASURE = """async (ms) => {
  const longTasks = []; new PerformanceObserver(l => l.getEntries().forEach(e => longTasks.push(e.duration))).observe({entryTypes: ['longtask']});
  let frames = 0, worst = 0, last = performance.now(); const end = last + ms;
  await new Promise(res => { function f(t) { frames++; worst = Math.max(worst, t - last); last = t; if (t < end) requestAnimationFrame(f); else res(); } requestAnimationFrame(f); });
  return {fps: Math.round(frames / (ms / 1000)), worstFrameMs: Math.round(worst), longTasks: longTasks.length, longestTaskMs: Math.round(Math.max(0, ...longTasks))};
}"""
with sync_playwright() as pw:
    b = pw.chromium.launch(**CHROME, args=["--no-proxy-server"])
    sam_ctx = b.new_context(viewport={"width": 390, "height": 800})
    sam = login(sam_ctx, "sam.second@example.com", password_for("sam.second@example.com"))
    conv = sys.argv[1]
    cdp = sam_ctx.new_cdp_session(sam); cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    t = time.time(); sam.goto(f"{BASE}/conversations/{conv}/"); sam.wait_for_selector("#chat-form"); load = time.time() - t
    sam.wait_for_timeout(1500)
    print(f"page load (slow phone): {load:.1f} s | messages on page: {sam.locator('.chat-message').count()}")
    print("idle:", sam.evaluate(MEASURE, 3000))
    alex = login(b.new_context(), "alex.finder@example.com", password_for("alex.finder@example.com"))
    alex.goto(f"{BASE}/conversations/{conv}/"); alex.wait_for_timeout(1500)
    alex.evaluate("""() => { const p = document.getElementById('chat-messages'); const ws = new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws/conversations/'+p.dataset.conversation+'/');
      ws.onopen = () => { let i = 0; const t = setInterval(() => { ws.send(JSON.stringify({message: 'burst2 '+i, client_id: 'burst-'+i+'-'+Date.now()})); if (++i >= 200) clearInterval(t); }, 20); }; }""")
    print("during 200-message burst:", sam.evaluate(MEASURE, 5000))
    sam.wait_for_timeout(2000)
    print("received on screen:", sam.locator(".chat-message p", has_text="burst2").count())
    b.close()
srv.terminate()
