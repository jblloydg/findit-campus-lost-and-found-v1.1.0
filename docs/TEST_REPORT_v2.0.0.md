# Find-IT v2.0.0 — Test report (bug hunt, Master Instruction check and performance)

Branch `release/2.0.0` (= v1.1.2 + the front-end team's v2.0.0 interface + integration fixes).
Tested on Linux with Chrome (Playwright), Python 3.13, Django 5.2, fresh demo data from `seed_demo`
plus a 3,000-message chat. **v1.1.2 (`main`) was measured again on the same machine with the same
data**, so the before/after numbers compare like with like. Model: `docs/TEST_REPORT_v1.1.2.md`.
(The front-end team's own draft report for their branch is replaced by this one.)

## 1. Summary
- **266 automated tests pass** (v1.1.2: 228). `makemigrations --check`: no changes.
- **Bug hunt:** 710 pages as 8 roles, 84 form routes, hostile addresses: **0 crashes, 0 problems**.
- **Master Instruction (every page, every role, 6 widths 360–1920 px):** before the fixes 179 kinds of
  problems (tap targets under 44 px, text under 12 px); after BUG-015/016/017: **0 problems on 1,182 page views** (the only findings are on Django's developer error page for a made-up address, shown only in local test mode).
- **v1.1.2 kept:** every line v1.1.2 added is still in the code; its SEC-001, SEC-002, CHG-008 and
  BUG-010 tests pass; the leak check passes.
- **Speed:** server and normal browsing as fast as v1.1.2; the first visit on a slow phone is slower
  (photo + fonts, 0.8 s → 1.2 s until usable).
- **Bugs found and fixed:** BUG-011, BUG-015, BUG-016, BUG-017, BUG-018 (section 6).

## 2. Automated tests
`python manage.py test core` → **266 tests, OK** (about 3 minutes).

| Group | Tests | What |
| --- | --- | --- |
| v1.1.2 and earlier | 228 | unchanged, plus 3 lines adjusted: BUG-010 tests check `findit.css` (the new stylesheet); demo-login tests count 10 accounts (8 + the team's Drew and Morgan) and check Morgan's random password |
| Front-end team | 26 | `test_v2_interface.py`, `test_v2_remaining.py`, `test_campus_background.py` (sidebar per role, dashboard counts, the 9 new pages, withdraw rules, location hidden by default, video badge, background) |
| Integration (`test_v200.py`) | 12 | version label from `VERSION` on signed-in, signed-out, 404 and 500 pages, never typed into a template; lost styles back; no text under 0.75rem; tap size 2.75rem used by small controls; px only for borders/shadows; no database / demo-login / screenshot files tracked by Git and all of them ignored |

## 3. Bug hunt (whole program)
| Check | Result |
| --- | --- |
| Every reachable page as each role (`crawl.py`): student finder, second claimant, unverified student, security guard, verified moderator, administrator, Developer (local test account), signed-out | **710 pages, 0 crashes** (73 / 57 / 48 / 60 / 81 / 182 / 187 / 22) |
| Every form action with empty and hostile data as 5 roles (`form_fuzz.py`) | **84 routes, 0 problems** |
| Hostile page addresses (`?page=abc`, SQL text, impossible dates…) (`address_fuzz.py`) | **0 problems** |
| Every page at 320, 390, 768, 1280, 1920 px (`campus_bg_check.py`, 6 roles) | photo background on every Find-IT page, **0 px sideways scrolling**. Only the test address `/this-page-does-not-exist/` showed Django's developer error page, which appears only in local test mode (DEBUG on), never to users |
| Real browser: chat messages typed while the connection was down (`browser_queue.py`) | shown as waiting, sent by themselves after reconnecting, each saved **once**, still once after reload |
| Real browser: live notices, missed notices and chat catch-up across a server restart (`browser_notice.py`) | badges match the database, chat caught up, **0 duplicates**, **no JavaScript errors** |
| Version label (screenshots) | PC: bottom of the sidebar; phone: page footer; signed out: public footer |
| Every backend address has a page link or button | yes (the 3 without links are the chat's data feed and two password-reset pages reached by redirect, as intended) |

## 4. Master Instruction check (new tool `tools/testing/responsive_check.py`)
Every page for every role (student, unverified student, guard, moderator, administrator,
signed-out) at **360, 390, 430** (phones), **768** (tablet), **1280, 1920** (desktops).

| Rule | Before fixes (1,206 page views) | After fixes (1,182 page views) |
| --- | --- | --- |
| No sideways scrolling | 0 problems on Find-IT pages | 0 |
| Tap targets ≥ 2.75rem (44 px) | 31 kinds of controls too small (36–40 px buttons and menu links, 32 px password Show, 31 px-wide phone menu button, 17–21 px text actions, 24–39 px checkbox rows) | **0** |
| Text ≥ 12 px | 144 kinds of text at 10.9–11.8 px (help text, labels, chips, badges, table headings, footer) | **0** |
| Icons 12–48 px | 0 problems | 0 |
| Text lines ≤ 75rem on wide screens | 0 problems on Find-IT pages (content width is capped at 72rem) | 0 |
| No fixed px for size or placement (code) | only the 500 page's inline style | fixed (BUG-017); a test checks the stylesheets |

Plain links inside a sentence are allowed to be smaller than 44 px (WCAG 2.5.8); the tool skips them.

## 5. Security and privacy checks
| Check | Result |
| --- | --- |
| v1.1.2 features after the merge | line-by-line check: every line v1.1.2 added is present (the only changes are the 7 test/tool lines that now point to `findit.css` / count 10 demo accounts) |
| SEC-001 photo/video hardening, SEC-002 notification links | their v1.1.2 tests pass unchanged |
| **Leak check** (`NoSensitiveDataInSharedFilesTests`) | caught Developer-account wording in the team's old draft report → rewritten. The team's `FindIT.cmd` and `seed_demo.py` still had the **old fixed demo passwords** → replaced by v1.1.2's random ones. No password anywhere now |
| **BUG-018** | the local database's `-wal`/`-shm` files were not ignored and got committed once during the integration (local only, removed before any push); `.gitignore` fixed, new test |
| `check --deploy` with online settings | only the same 2 optional HSTS notes as v1.1.2 (decide when hosting, v3.0.0) |
| Code check (pyflakes) of changed files | no new problems (6 unused imports are the same as in v1.1.2) |

## 6. Bugs found and fixed in v2.0.0
| ID | Found by | Bug | Fix |
| --- | --- | --- | --- |
| BUG-011 | class check (styles used by pages vs stylesheet) | `.accounts-panel` and `.compact-form` lost in the new stylesheet | added back in rem |
| BUG-015 | `responsive_check.py` | tap targets under 44 px on many pages | `var(--tap)` = 2.75rem |
| BUG-016 | `responsive_check.py` | text under 12 px on many pages | minimum 0.75rem |
| BUG-017 | code audit | 500 page used fixed px | %, rem, `clamp()` |
| BUG-018 | happened during integration | database helper files not ignored by Git | `.gitignore` + test |
| BUG-012 (team) | team | leftover `<<<<<<<` line on every Browse card | fixed by the team; **still in released v1.1.2** |

## 7. Performance (v1.1.2 → v2.0.0, same machine, same data)

### 7.1 Backend (server time per page, `page_timing.py`, 3,000-message chat)
| Page | v1.1.2 | v2.0.0 | Size v1.1.2 → v2.0.0 / queries |
| --- | --- | --- | --- |
| Chat (3,000 messages) | 17 ms | 16 ms | 18 → 26 KB / 19 |
| Post page | 15 ms | 16 ms | 14 → 22 KB / 22 |
| Messages | 14 ms | 15 ms | 4 → 12 KB / 9 |
| Browse / Dashboard | 7 ms | 9 ms | 8 → 19 KB / 11 → 13 (2 dashboard counts) |
| Notifications, My claims, Profile | 5–8 ms | 6–7 ms | +8 KB each (sidebar) / same |

### 7.2 Phone and desktop in a real browser (`page_load.py`)
Phone = 4× slower processor, 1.5 Mbit/s, 150 ms delay. "Usable" = page ready to use.

**First visit** (nothing kept by the browser):
| Page | Phone v1.1.2 | Phone v2.0.0 | Desktop v1.1.2 | Desktop v2.0.0 |
| --- | --- | --- | --- | --- |
| Browse | 778 ms (84 KB) | 1,128 ms (321 KB) | 67 ms | 108 ms |
| Post page | 846 ms | 1,224 ms | 148 ms | 76 ms |
| My posts | 814 ms | 1,202 ms | 104 ms | 81 ms |
| Messages | 776 ms | 1,118 ms | 148 ms | 73 ms |
| Notifications | 766 ms | 1,111 ms | 54 ms | 80 ms |
| Profile | 790 ms | 1,136 ms | 49 ms | 76 ms |
Fully loaded on the phone: about 0.8 s → 2.1 s. The extra ~220 KB: monument photo 116 KB (owner's
requirement), 4 font files 82 KB, bigger stylesheet. On the hosted version WhiteNoise compresses the
stylesheet (84 KB → about 16 KB); the photo and fonts are already compressed.

**Normal browsing** (`CACHE=1`: photo, fonts and stylesheet kept from earlier pages):
| Page | Phone v1.1.2 | Phone v2.0.0 | Desktop v1.1.2 | Desktop v2.0.0 |
| --- | --- | --- | --- | --- |
| Browse | 280 ms | 299 ms | 82 ms | 86 ms |
| Post page | 280 ms | 321 ms | 82 ms | 66 ms |
| My posts | 243 ms | 270 ms | 39 ms | 56 ms |
| Messages | 250 ms | 273 ms | 72 ms | 66 ms |
| Notifications | 248 ms | 228 ms | 54 ms | 73 ms |
| Profile | 272 ms | 240 ms | 49 ms | 50 ms |
Differences of ±60 ms are normal run-to-run variation.

### 7.3 Chat on a slow phone (`phone_fps.py`, 3,000-message chat)
| Measure | v1.1.2 | v2.0.0 |
| --- | --- | --- |
| Opening the chat | 0.3 s | 0.5 s |
| Smoothness while 200 messages arrive | 60 fps, worst frame 33 ms | 60 fps, worst frame 17 ms |
| Idle | 61 fps | 61 fps |

### 7.4 Many people at once (`load_test.py`)
| Scenario | v1.1.2 | v2.0.0 |
| --- | --- | --- |
| Realistic: 20 people chatting + 20 notice connections + 20 page loaders | 299/299 delivered, median 22 ms per message, pages median 38 ms, 0 errors | 300/300 delivered, median 21 ms, pages median 45 ms, 0 errors |
| Heavy: 100 people chatting (~50 messages/s) + 100 notice connections + 20 page loaders | 1,499/1,499 delivered, median 103 ms, 0 errors | 1,499/1,499 delivered, median 101 ms, 0 errors |
Sections 7.3 and 7.4 were measured before BUG-015/016 (stylesheet sizes only; no effect on the server or chat code).

## 8. What was **not** tested
- Real iPhones (Safari) and real Android phones; Windows high-contrast mode; screen readers.
- On the owner's Windows PC with `FindIT.cmd` — please run menu 1, open a few pages on the PC and on
  a phone (same Wi-Fi), and check the version label at the bottom.
- Photo/video sending in a real browser (`media_browser.py`, needs the sample media files); the media
  code did not change since v1.1.2 and its unit tests pass.
- Find-IT's own 404 page with test mode off (the local test server shows Django's developer page instead).
