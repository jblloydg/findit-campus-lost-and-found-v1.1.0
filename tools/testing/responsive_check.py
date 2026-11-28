"""v2.0.0 Master Instruction check: one layout that works on phone, tablet and desktop.

Run from the project folder, with the server already running on 127.0.0.1:8000 (or set FINDIT_URL),
after `migrate` and `seed_demo`:
    python tools/testing/responsive_check.py
    WIDTHS=360,390,430,768,1280,1920 python tools/testing/responsive_check.py   (the default)

For every demo role it finds every page (same way as campus_bg_check.py) and, at each width, checks:
  - no sideways scrolling,
  - tap targets (buttons, fields, menu links, icon buttons, chips, pagination) at least 2.75rem
    (44 px) high and wide; plain links inside a sentence are allowed to be smaller (WCAG 2.5.8),
  - no visible text smaller than 12 px,
  - icons between 12 and 48 px (not too small on phones, not too big on desktops),
  - text lines no wider than about 75rem on a wide screen (content keeps a max width).
Problems are grouped by element so the same issue on many pages is listed once.
"""
import collections
import os
import sys

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "tools", "testing"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "findit.settings")
os.environ["DJANGO_DEBUG"] = "1"
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"  # Playwright runs an event loop; local test script only

from campus_bg_check import BASE, CHROME, HEIGHTS, ROLES, U, discover  # noqa: E402  (also sets up Django)
from django.conf import settings  # noqa: E402
from django.test import Client  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

WIDTHS = [int(w) for w in os.environ.get("WIDTHS", "360,390,430,768,1280,1920").split(",")]

AUDIT_JS = """() => {
  const out = [];
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && r.right > 0 && r.left < innerWidth
      && !e.closest('[aria-hidden="true"], .sr-only, [hidden]'); };
  const name = e => e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className.trim() ? '.' + e.className.trim().split(/\\s+/).slice(0, 2).join('.') : '')
      + (e.type && e.tagName === 'INPUT' ? '[' + e.type + ']' : '');
  const where = e => { const p = e.parentElement; return p ? name(p) : ''; };
  // 1. sideways scrolling
  const over = document.documentElement.scrollWidth - innerWidth;
  if (over > 1) out.push({kind: 'sideways-scroll', el: 'page', px: over});
  // 2. tap targets
  const taps = document.querySelectorAll('button, select, textarea, summary, [role=button], input:not([type=hidden]), a.button, a.nav-link, a.icon-button, a.chip, a.filter-chip, a.text-action, .pagination a, .segmented a, .tabs a, a.quick-link, a.profile-menu-item, .profile-dropdown a, a.sidebar-user');
  for (const e of taps) {
    if (!vis(e) || e.closest('.sidebar') && innerWidth <= 1024 && !document.body.classList.contains('drawer-open')) continue;
    let r = e.getBoundingClientRect();
    if (e.matches('input[type=checkbox], input[type=radio]')) { const l = e.closest('label'); if (l) r = l.getBoundingClientRect(); }
    if (e.matches('input[type=file]') && getComputedStyle(e).opacity === '0') continue;
    if (r.height < 43.5 || r.width < 43.5) out.push({kind: 'small-tap', el: name(e), in: where(e), px: Math.round(r.width) + 'x' + Math.round(r.height)});
  }
  // 3. tiny text
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const t = walker.currentNode, e = t.parentElement;
    if (!e || seen.has(e) || !t.textContent.trim() || !vis(e) || e.closest('script, style, svg')) continue;
    seen.add(e);
    const fs = parseFloat(getComputedStyle(e).fontSize);
    if (fs < 12) out.push({kind: 'small-text', el: name(e), in: where(e), px: fs.toFixed(1)});
  }
  // 4. icons
  for (const s of document.querySelectorAll('svg')) {
    if (!vis(s) || s.closest('.qr-box, .brand-illustration, .empty-illustration')) continue;
    const r = s.getBoundingClientRect(), size = Math.max(r.width, r.height);
    if (size < 11.5 || size > 48.5) out.push({kind: size < 12 ? 'icon-too-small' : 'icon-too-big', el: name(s), in: where(s), px: Math.round(size)});
  }
  // 5. line length on wide screens
  if (innerWidth >= 1280) for (const p of document.querySelectorAll('p, li, dd, .muted')) {
    if (!vis(p) || p.textContent.trim().length < 80) continue;
    const w = p.getBoundingClientRect().width, rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
    if (w > 75 * rem) out.push({kind: 'too-wide-text', el: name(p), in: where(p), px: Math.round(w)});
  }
  return out;
}"""


def main():
    groups = collections.defaultdict(lambda: {"pages": set(), "widths": set(), "sizes": set()})
    checked = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**({"executable_path": CHROME} if CHROME else {}), args=["--no-proxy-server"])
        for role in ROLES:
            client = Client(raise_request_exception=False)
            if role:
                client.force_login(U.objects.get(username=role))
            pages = discover(client)
            cookies = []
            if role:
                cookies = [{"name": settings.SESSION_COOKIE_NAME,
                            "value": client.cookies[settings.SESSION_COOKIE_NAME].value, "url": BASE}]
            label = role or "signed-out"
            print(f"{label}: {len(pages)} page patterns", flush=True)
            for w in WIDTHS:
                ctx = browser.new_context(viewport={"width": w, "height": HEIGHTS.get(w, 900)}, device_scale_factor=1)
                if cookies:
                    ctx.add_cookies(cookies)
                page = ctx.new_page()
                for pat, url in sorted(pages.items()):
                    page.goto(BASE + url, wait_until="networkidle")
                    checked += 1
                    for item in page.evaluate(AUDIT_JS):
                        key = (item["kind"], item["el"], item.get("in", ""))
                        groups[key]["pages"].add(pat)
                        groups[key]["widths"].add(w)
                        groups[key]["sizes"].add(str(item["px"]))
                ctx.close()
        browser.close()
    print(f"\n{checked} page views checked at widths {WIDTHS}")
    if not groups:
        print("PROBLEMS: none")
        return
    print(f"PROBLEMS: {len(groups)} kinds\n")
    for (kind, el, parent), g in sorted(groups.items()):
        pages = sorted(g["pages"])
        print(f"{kind:15} {el}  (in {parent})  widths {sorted(g['widths'])}  sizes {sorted(g['sizes'])[:4]}")
        print(f"{'':15} {len(pages)} page(s): {', '.join(pages[:6])}{' …' if len(pages) > 6 else ''}")


if __name__ == "__main__":
    main()
