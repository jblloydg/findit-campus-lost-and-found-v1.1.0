# Find-IT v2.1.0 — Test report

Branch `release/2.1.0`, 2026-11-28. Chrome (Playwright), Python 3.13, Django 5.2. "Before" = v2.0.0
(`stable/v2.0.0`), measured on the same machine with its own fresh demo data. All test tools are in `tools/testing/`
(how to run them: `tools/testing/README.md`; raw results of this run: `tools/testing/out/`, not kept in Git).

## 1. Summary
| Check | Result |
| --- | --- |
| Automated tests (`python manage.py test core`) | **320 tests, all pass** (272 at the start of v2.1.0; 48 new, in `core/tests/test_v210.py`) |
| Missing migrations (`makemigrations --check`) | none (one new migration, `0015_v210_staff_help`) |
| **Every status by clicking** (`status_journeys.py`, new) | **18 of 18 steps pass**: Open, Claim in Progress, At Guard House, Returned, Claimed, Closed, and back to Open — each by the role who should do it |
| **Every page reachable by clicking** (`reachability.py`, new) | 8 roles; **80 of 87 addresses reached by clicking, 0 missing**; the other 7 are not pages (chat script data, uploads, media files, email/QR links) |
| Crawl of every page per role (`crawl.py`) | 1,172 pages (7 roles): **no server errors** |
| Hostile form input (`form_fuzz.py`) | 88 form routes: **0 problems** |
| Hostile addresses (`address_fuzz.py`) | **no problems** |
| Master Instruction (`responsive_check.py`) | **1,314 page views** at 360 / 390 / 430 / 768 / 1280 / 1920 px, every role: **no Find-IT problems** |
| Campus background (`campus_bg_check.py`) | 621 page views: **no Find-IT problems** |
| Chat queue across a server stop (`browser_queue.py`) | pass: 2 messages typed offline sent after restart, each saved **once** |
| Notifications across a restart (`browser_notice.py`) | pass: live badge, offline notices caught up in 6 s, no duplicates, no script errors |
| Leak check (no passwords / tester accounts in shared files) | pass (now also refuses `tester-accounts.txt`, `Accounts/`, `accounts.md`) |
| Speed vs v2.0.0 | server time the same; first visit +21 KB per page; phone (4× slower CPU) +0.03–0.05 s per page in normal browsing (details §6) |

The only findings of the two screen checks are on Django's yellow **debug** "page not found" screen for a made-up
address, which exists only in local debug mode (same as in v2.0.0).

## 2. Automated tests
`python manage.py test core` — 320 tests, OK (≈ 200 s). New tests by change (all in `core/tests/test_v210.py`):
BUG-019/020/CHG-011 (from the start of v2.1.0), DES-006 (5), BUG-021 (2), BUG-023 (3), CHG-013 (5),
CHG-014 (3, with made-up tester accounts only), DES-007 (7), BUG-024 (4), DES-008 (2), CHG-015 (1), CHG-016 (4),
CHG-017 (2), CHG-019 (5), BUG-022 (2), BUG-025 (3), CHG-020 (4), CHG-021 (1), DES-009 (2).
Changed tests: two v2.0.0/v1.1.2 tests now expect the new wording ("Ownership questions (N left)"; photo error
mentions AVIF) and the seed count (testers come only from the private file).

## 3. Click-through tests (new in v2.1.0)
### 3.1 Every status, by the right people (`tools/testing/status_journeys.py`)
Real Chrome, only visible buttons, signed in as the demo finder, claimant, owner and guard. Guide for people:
`docs/STATUS_GUIDE.md`.
| Journey | Steps (all PASS) |
| --- | --- |
| A. FOUND, handed over in person | posts → Open · claimant claims → Claim in Progress · finder approves + Mark returned → Returned · claimant confirms → Claimed |
| B. FOUND via the guard house | posts with "I'll bring it" ticked (staff told) · claim + approve → Claim in Progress · guard types the code at Scan turn-in QR → At Guard House · guard releases → Claimed |
| C. LOST, owner checked in chat | owner posts → Open · finder "I found this" opens the chat window · ＋ → 3 ownership questions → Claim in Progress · owner answers · finder approves + returns → Returned · owner confirms → Claimed |
| D. Guard house and back | finder brings it, guard confirms → At Guard House · finder asks to take it back, guard approves → Open |
| E. Closed | author closes → Closed |
Note: run it on fresh demo data. After several runs the demo finder reaches the posts-per-hour limit (a real rule)
and later journeys stop; this happened once during testing and is not a bug.

### 3.2 Every page reachable by clicking (`tools/testing/reachability.py`)
Starts only from the page each role lands on and follows only links and buttons on the pages. It first makes, through
the normal pages, the situations some buttons need (a system report with a screenshot, a chat safety report, a paused
chat, a declined owner check, an unanswered ownership question, a staff request, an item on its way to the guard house)
and undoes them afterwards.
| Role | Pages opened by clicking | Kinds of page/action reached |
| --- | --- | --- |
| Student (verified) | 82 | 37 |
| Student (other) | 70 | 35 |
| Student (not verified) | 62 | 29 |
| Student with an open ID review | 62 | 30 |
| Guard (staff) | 79 | 44 |
| Verified moderator | 122 | 49 |
| Admin | 171 | 67 |
| Signed out | 4 | 4 |
Result: 87 addresses — **80 reached by clicking, 7 not pages** (chat messages data, chat upload + upload status,
chat media files, the QR picture, email links for verification and password reset), **0 missing**.

### 3.3 Feature checks in Chrome (phone 390 px and PC 1280 px)
- Chat window (DES-007/008): opens over a post, Messages and Notifications; the address shows `/conversations/<id>/`;
  ＋ menu (Photo or video; Ownership questions only for the finder); questions open, message sends; × / Esc / Back close
  it and the page is where it was (scroll position kept); no script errors.
- Live vs reload (BUG-022): the same message shows "Name · Nov 28 · 4:40 p.m." both ways.
- Contact staff (CHG-019): a student asks from a guard-house post; **three different staff accounts** (guard,
  moderator, admin) see it with a red count; one replies; the student is notified, sees the reply, marks it resolved.
- Sign-in (BUG-024): login page, landing page, the pop-up on a post; phone + PC; `127.0.0.1` and `localhost`: all sign
  in and show "Welcome back"; Student ID on an unverified account gets the email hint; staff username any case.
- Tester accounts (CHG-014): in the owner's private copy, `seed_demo` makes both testers; both sign in by email and by
  Student ID; the two chats exist (checked; the public copy makes none).
- Search everything (CHG-020): finds posts, chats (only your own), pages by role; hostile text (`' OR 1=1 --`,
  `<script>`, 500 characters) is harmless.

## 4. Bug hunt over the whole program
- `crawl.py` — every page every role can open: 2026-0001 183 pages, 2026-0003 151, 2026-0005 (not verified) 101,
  guard 122, moderator 229, admin 364, signed out 22 → **1,172 pages, no server errors, no broken pages**.
- `form_fuzz.py` — 88 form routes with empty, huge, wrong-type, script and SQL-like input: **0 problems**.
- `address_fuzz.py` — made-up ids, other people's ids, path tricks: **no problems** (404/403 as expected).
- Private pages: a staff request opens only for the person who asked and the staff team (others 403, tested);
  chats in search results only for people in the chat (tested).
- Bugs found by the team or during testing, all fixed: BUG-021, BUG-022, BUG-023, BUG-024, BUG-025, the question rows
  squeezed in the scrolling list (in DES-007), notifications marked read before being shown (in DES-009).

## 5. Security and privacy
- **Leak check** (`test_v112.py::NoSensitiveDataInSharedFilesTests`): pass. Tester accounts are only in the owner's
  private copy; the shared code, docs and tests contain no tester names, emails, IDs or passwords (also tested).
- **Chat window framing:** `X-Frame-Options: SAMEORIGIN` (tested) — only Find-IT can frame its own pages.
- **AVIF photos** go through the same SEC-001 pipeline (re-encoded to JPEG, lowest bits scrambled, output checked;
  tested that the stored copy is a JPEG). HEIC is never opened.
- **Sign-in hint** is shown for every Student ID that fails, so it does not reveal whether an account exists.
- **Staff inbox:** at most 5 open requests per student; 2,000 characters per message; audit trail entries.
- `check --deploy`: same 7 debug-mode warnings as v2.0.0 (local use; they go away with the v3.0.0 hosting settings).

## 6. Performance (v2.0.0 → v2.1.0, same machine, fresh demo data each)
**Backend** (`page_timing.py`, server time and database queries):
| Page | v2.0.0 | v2.1.0 |
| --- | --- | --- |
| Chat page | 8 ms, 18 queries | 8 ms, 18 queries |
| Post page | 10 ms, 22 queries | 10 ms, **21** queries (old chat panel removed) |
| Notifications | 5 ms, 9 queries | 4 ms, **8** queries |
| Messages | 6 ms, 9 queries | 6 ms, 9 queries |
| Dashboard | 8 ms, 13 queries | 8 ms, 13 queries |
| My claims | 6 ms, 9 queries | 6 ms, 9 queries |
| Profile | 5 ms, 11 queries | 7 ms, 11 queries |
Staff pages count the open staff-inbox requests (one small extra query, staff only).

**Web / phone, first visit** (`page_load.py`: phone = 390 px, 4× slower CPU, slow 4G; PC = 1280 px; time until the page
is usable):
| Page | Phone v2.0.0 | Phone v2.1.0 | PC v2.0.0 | PC v2.1.0 | Size v2.0.0 → v2.1.0 |
| --- | --- | --- | --- | --- | --- |
| Dashboard | 1,228 ms | 1,233 ms | 86 ms | 97 ms | 321 → 344 KB |
| Post page | 1,275 ms | 1,284 ms | 72 ms | 131 ms | 318 → 340 KB |
| My posts | 1,099 ms | 1,261 ms | 55 ms | 74 ms | 315 → 336 KB |
| Messages | 1,138 ms | 1,256 ms | 47 ms | 70 ms | 305 → 326 KB |
| Notifications | 1,177 ms | 1,272 ms | 50 ms | 57 ms | 303 → 324 KB |
| Profile | 1,101 ms | 1,272 ms | 80 ms | 71 ms | 304 → 325 KB |

**Normal browsing** (files already downloaded; average of runs): phone v2.0.0 ≈ 230–300 ms, v2.1.0 ≈ 270–340 ms per page
(**+0.03–0.05 s**); PC 35–70 ms vs 55–100 ms (not noticeable).

Why: the stylesheet grew from 86 to 103 KB and `app.js` from 20 to 25 KB (chat window, ＋ menu, staff inbox, search,
status help, redesigned pages). Find-IT serves them uncompressed locally; compressed (as hosting will in v3.0.0) the
growth is about **+5 KB** in total. Nothing new is downloaded per page; the chat window loads the chat only when opened.

## 7. Bugs found and fixed in v2.1.0
BUG-019, BUG-020 (start of v2.1.0), BUG-021 Messages icon hidden on phones, BUG-022 name/time live vs reload,
BUG-023 nothing explained how a chat starts, BUG-024 sign-in confusion, BUG-025 AVIF refused / HEIC unclear; during
testing: question rows squeezed in scrolling lists (fixed in DES-007), unread notifications never shown as unread
(fixed in DES-009). Details and commits: `docs/BUG_REPORTS.md`.

## 8. What was **not** tested
- Real phones (Safari on iPhone, Chrome on Android): tested with Chrome's phone emulation only. In particular, iPhone
  photo picking (HEIC → JPEG conversion by iOS) and the chat window's bottom sheet on a real iPhone.
- Older browsers without `Sec-Fetch-Dest` (they still get the chat window through `?embed=1`).
- Video upload through the new ＋ menu end to end (same input and script as before; covered by the existing chat media
  tests and the unchanged upload code).
- Many staff at once replying to the same staff request (works, but there is no "someone is replying" sign).
- Hosting, PostgreSQL, heavy load: planned for v3.0.0.
