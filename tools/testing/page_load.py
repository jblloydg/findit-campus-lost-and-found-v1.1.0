"""Page load in a real browser (v1.1.2): a slowed-down phone (4x CPU, 1.5 Mbit/s, 150 ms) and a desktop.

Signs in as a demo student, then opens key pages and prints, per page: time until the page is usable
(DOMContentLoaded), time until everything has loaded, how much was downloaded, and whether the design
(CSS) was applied. Run from the project folder: python tools/testing/page_load.py
Needs Playwright + Chrome (see README). Uses demo-logins.txt; for an older database you can set
DEMO_PASSWORD instead (never write a password in this file).
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.getcwd())
from playwright.sync_api import sync_playwright

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
SERVER_CMD = [sys.executable, "manage.py", "runserver", "127.0.0.1:8765", "--noreload"]
CHROME = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
BASE = "http://127.0.0.1:8765"
LOGIN = "alex.finder@example.com"


def password():
    if os.environ.get("DEMO_PASSWORD"):
        return os.environ["DEMO_PASSWORD"]
    from core.demo_logins import password_for
    return password_for(LOGIN)


def measure(page, received, url):
    received.clear()
    start = time.perf_counter()
    page.goto(BASE + url, wait_until="load")
    timing = page.evaluate("""() => { const t = performance.getEntriesByType('navigation')[0];
        return {dom: t.domContentLoadedEventEnd, load: t.loadEventEnd}; }""")
    styled = page.evaluate("getComputedStyle(document.body).fontFamily !== '' && "
                           "getComputedStyle(document.querySelector('.topbar, header, body')).display !== ''")
    has_design = page.evaluate("[...document.styleSheets].some(s => (s.href || '').includes('/static/css/findit.css') && s.cssRules.length > 0)")
    return {"url": url, "dom_ms": round(timing["dom"]), "load_ms": round(timing["load"]),
            "kb": round(sum(received) / 1024), "design": bool(has_design and styled),
            "wall_ms": round((time.perf_counter() - start) * 1000)}


def run(phone, pages):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**CHROME, args=["--no-proxy-server"])
        options = {"viewport": {"width": 390, "height": 800}, "is_mobile": True, "has_touch": True} if phone else \
                  {"viewport": {"width": 1366, "height": 768}}
        context = browser.new_context(**options)
        page = context.new_page()
        cdp = context.new_cdp_session(page)
        cdp.send("Network.enable")
        page.goto(BASE + "/login/")
        page.fill("input[name=username]", LOGIN)
        page.fill("input[name=password]", password())
        page.click("form.stack-form button[type=submit]")
        page.wait_for_load_state("load")
        if phone:
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
            cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150,
                     "downloadThroughput": 1.5 * 1024 * 1024 / 8, "uploadThroughput": 750 * 1024 / 8})
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        received = []
        cdp.on("Network.loadingFinished", lambda event: received.append(event.get("encodedDataLength", 0)))
        results = [measure(page, received, url) for url in pages]
        browser.close()
        return results


if __name__ == "__main__":
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "findit.settings")
    django.setup()
    from core.models import ItemPost
    post = ItemPost.objects.filter(author__username="2026-0001").first()
    pages = ["/home/", f"/p/{post.pk}/", "/my-posts/", "/messages/", "/notifications/", "/profile/"]
    server = subprocess.Popen(SERVER_CMD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)
    try:
        for label, phone in (("phone", True), ("desktop", False)):
            for row in run(phone, pages):
                print(f"{label:8} {row['url'][:24]:26} usable {row['dom_ms']:5} ms  loaded {row['load_ms']:5} ms  "
                      f"{row['kb']:5} KB  design={'yes' if row['design'] else 'NO'}")
    finally:
        server.terminate()
        server.wait()
