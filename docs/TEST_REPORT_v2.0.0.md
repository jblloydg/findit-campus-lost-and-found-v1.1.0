# Find-IT v2.0.0 — Test report

Tested on Linux (Python 3.13, Django 5.2, Google Chrome headless via Playwright), local SQLite with
`seed_demo` data. Not yet tested on the team's Windows machines or a real phone — please do.

## 1. Automated tests
`python manage.py test core` → **202 tests, all pass** (before and after the change).
`python manage.py makemigrations --check --dry-run` → No changes detected (no migrations in v2.0.0).
One test limit was raised on purpose: home page database queries 11 → 13 (two constant dashboard counts).

## 2. Bug hunt
| Check | Tool | Result |
| --- | --- | --- |
| Every reachable page as each demo role (3 students incl. unverified, guard, moderator, admin, signed out) | `tools/testing/crawl.py` | 521 page loads, **0 problems** |
| Broken / hostile addresses (`?page=abc`, SQL text, impossible dates…) | `tools/testing/address_fuzz.py` | **0 problems** |
| Empty and hostile form data on every route, every role | `tools/testing/form_fuzz.py` | 81 routes, **0 problems** |
| Real browser, desktop 1366 px: landing, log in, dashboard, post page, create post, chat, my claims, messages, notifications, my posts, profile, staff workspace, admin dashboard, accounts, moderators, report detail | Playwright screenshots | No JavaScript errors. Found and fixed BUG-v2-03 and BUG-v2-04 (see bug log). |
| Real browser, phone 390 px: landing, log in, dashboard, post page, my claims, accounts | Playwright screenshots | Layout matches the phone pictures; nothing cut off. |
| Phone menu: ☰ opens the sidebar, Escape / tapping outside closes it | Playwright | Works |
| Deactivate pop-up: opens, Cancel keeps the page, Deactivate submits ("… was deactivated") | Playwright | Works |
| Code review | — | Found BUG-v2-01 (merge text in CSS), BUG-v2-02 (merge marker in Browse), `.gitignore` gap |

Security checks: no new routes, no new form fields; every POST form still has `{% csrf_token %}`; the
confirm pop-up only delays a normal form submit; the dashboard numbers count only the signed-in
person's own posts/claims; admin numbers are on the admin-only page. Fonts are local files (no
third-party font server sees visitors).

## 3. Performance (before = `main` v1.1.1, after = `release/2.0.0`)
Server (`tools/testing/page_timing.py`, same database):
| Page | Time before → after | HTML size before → after | Queries before → after |
| --- | --- | --- | --- |
| /home/ | 6 → 9 ms | 7 → 19 KB | 11 → 13 |
| post page | 10 → 12 ms | 9 → 18 KB | 22 → 22 |
| chat | 8 → 9 ms | 5 → 14 KB | 18 → 18 |
| /messages/ | 6 → 8 ms | 4 → 13 KB | 9 → 9 |
| /my-claims/ | 5 → 9 ms | 5 → 13 KB | 9 → 9 |

Phone (390 px, CPU slowed 4×, slow network, median of 3, page fully loaded):
| Page | Before → after |
| --- | --- |
| Dashboard | 244 → 256 ms |
| Post page | 237 → 295 ms |
| Messages | 206 → 274 ms |

Why bigger: the sidebar icons are drawn inside each page (about 8 KB of HTML, compresses well) and
three font files load once (≈ 116 KB, then cached). Still well under one second on a slow phone.
Possible v2.1.0 improvement: one shared icon file instead of icons inside each page.

## 4. Not tested
- Windows, a real phone, Safari/iPhone, Firefox.
- Chat load test and media upload tests (chat code was not changed, only its look).
- Screen readers (labels and focus order were kept; the menu and pop-up move focus correctly in Chrome).
