# Find-IT v1.1.2 — Test report (bug hunt, security checks and performance)

Plain-text report for test documentation. Written so it can be read in any Claude session or
pasted into the paper. All accounts, names and files used were fictional/generated.

- **Version tested:** v1.1.2, branch `release/1.1.2` (see `docs/CHANGES_v1.1.2.md` for what changed and why)
- **Compared with:** v1.1.1 (`main` / `stable/v1.1.1`), measured on the same machine with the same data
- **Date:** 28 November 2026
- **Tested by:** Claude (AI assistant), on request of the project owner. No human testers yet.
- **Test machine:** Linux test computer (not the team's Windows PC), Python 3.13, Django 5.2.19, the local
  development server (daphne 4.2), SQLite, Google Chrome (headless), ffmpeg 6.1.
- **Phone simulation:** Chrome with a 390 × 800 screen, processor slowed down 4×, network 1.5 Mbit/s with
  150 ms delay.
- **Test data:** fresh database + `seed_demo` (random per-PC demo passwords) + a 3,000-message chat.
- **Tools:** `tools/testing/` (see its README). New in v1.1.2: `page_load.py`; `crawl.py` also covers a
  Developer account.

---

## 1. Summary

| Area | Result |
| --- | --- |
| Automated tests | **228 tests, all pass** (202 from v1.1.1 + 26 new); `makemigrations --check`: no changes |
| Bug hunt (whole program) | **665 pages** × 8 roles incl. Developer and signed-out, **81 routes** with hostile data, hostile page addresses → **0 crashes** |
| Security checks | hostile photos/videos (11 tests), notification redirect tricks, CSRF, online-settings check, leak scan → **all pass** |
| Bugs found in this round | **0 new bugs**. One counting mistake in the docs (test total) was corrected. |
| Speed vs v1.1.1 | pages, chat and load: **same or faster**; photo processing +0.09 s, video processing +1.1 s (background) |
| Design (BUG-010) | design applied on every tested page, phone and desktop |

---

## 2. Automated tests

`python manage.py test core` → **Ran 228 tests … OK**.

| Group | Tests | What they check |
| --- | --- | --- |
| Sessions 1–4 (v1.1.0) | 142 | posts, claims, guard house, share mode, backups, accounts, reports, security |
| v1.1.1 | 60 | verification, Student IDs, limits, report & block, Developer role, chat queue, history, photos, chat media |
| **v1.1.2** (`core/tests/test_v112.py`) | **26** | see below |

v1.1.2 tests:

| Item | Tests | What they prove |
| --- | --- | --- |
| BUG-008 | 5 | category link uses the id and the name, filters Browse, no empty link, location hidden unless turned on |
| BUG-010 | 2 | with a "broken registry" (`.css` = plain text) the design file is still sent as `text/css`; pages link the stylesheet |
| SEC-002 | 3 | own pages open; 11 tricks (full addresses, `//`, `/\`, `javascript:`, tabs, newlines…) never leave the site; unsafe links are not even stored |
| CHG-008 | 5 | random passwords per PC, saved and working, kept on re-run, old published password replaced, older databases handled; **leak scan** of every shared file |
| SEC-001 photos | 6 | hidden message in pixel lowest bits destroyed; change invisible (≤ 3/255); appended ZIP, EXIF, comment and colour profile removed; BMP/TIFF/GIF never opened; disguised file gets a friendly message; post photo and preview clean |
| SEC-001 videos | 5 | subtitle + attachment + metadata removed (only picture + sound kept); appended ZIP removed; HLS playlist, remote playlist and concat file refused; hidden bits in frames destroyed; poster clean |

**Proof the security tests are meaningful:** run against the v1.1.1 code, the photo tests for colour
profile/comments and disguised formats **fail** (v1.1.1 kept those and opened any picture type), while
the pixel-bit and appended-ZIP tests already passed (v1.1.1's re-encoding destroyed those too). v1.1.2
passes all of them.

---

## 3. Bug hunt (whole program)

| Check | Result |
| --- | --- |
| Every reachable page as each role (`crawl.py`): student finder, second claimant, unverified student, security guard, verified moderator, administrator, Developer, signed-out | **665 pages, 0 crashes** (69 / 53 / 44 / 56 / 76 / 170 / 175 / 22) |
| Every form action with empty and hostile data (SQL text, 5,000-character text, wrong ids, `../../etc/passwd`, external links) as 5 roles (`form_fuzz.py`) | **81 routes, 0 crashes** |
| Hostile page addresses (`?page=abc`, SQL text, `?open=abc`, impossible dates…) (`address_fuzz.py`) | **0 crashes** |
| Real browser: chat messages typed while the server was down (`browser_queue.py`) | shown as waiting, sent by themselves after restart, each saved **once** |
| Real browser: live notices, missed notices and chat catch-up across a server restart (`browser_notice.py`) | live notice at once; after restart chat and notices caught up in **6 s**; no duplicates after reload |

---

## 4. Security checks

| Check | Result |
| --- | --- |
| **SEC-001 photos** (unit tests above) | hidden pixel message → matches only at chance level (50 %) afterwards; ZIP, EXIF, comment, colour profile gone; disguised BMP/TIFF/GIF refused with "JPG, PNG, or WebP" |
| **SEC-001 videos** (unit tests above) | only H.264 picture + AAC sound remain; subtitle, attachment, title/comment metadata gone; appended ZIP gone; playlist/concat files refused before ffmpeg opens them |
| SEC-001 visual check | invisible noise alone changes colours by at most 3 of 255 steps (average 1.4); the stored copy differs from the original by 2.5 on average, mostly from normal JPEG compression (see `sec001-before-after` image sent to the owner) |
| **SEC-002** on the running app: 7 redirect tricks | `https://…`, `//…`, `/\…`, `/\/…`, `javascript:`, tab tricks → Notifications page. Percent-encoded forms (`/%5C…`, `/%2F%2F…`) open a page **on Find-IT itself** (browser URL rules checked), so they cannot leave the site |
| Forms without the security (CSRF) token | refused (403) |
| `check --deploy` with online settings | only 2 optional HSTS notes (subdomains, preload) — to decide when hosting (v3.0.0) |
| Demo data on an online setting | refused (`seed_demo only runs on a local PC`) |
| **BUG-010** on the running app | `/static/css/app.css` → `text/css`; `app.js`, `chat.js` → `text/javascript` |
| **CHG-008 leak scan** of GitHub `release/1.1.2` | no demo passwords anywhere; Developer command only in the program itself (`FindIT.cmd` menu 6, code); no `demo-logins.txt`, database, `.env`, backups or private notes in the repository |
| Code check (pyflakes) of changed files | no errors (2 harmless unused imports that were already in v1.1.1) |

---

## 5. Performance (v1.1.1 → v1.1.2, same machine, same data)

### 5.1 Backend (server time per page, `page_timing.py`, 3,000-message chat)
| Page | v1.1.1 | v1.1.2 | Size / queries |
| --- | --- | --- | --- |
| Chat (3,000 messages) | 23 ms | 25 ms | 18 KB / 19 |
| Post page | 20 ms | 22 ms | 14 KB / 22 |
| Messages | 20 ms | 17 ms | 4 KB / 9 |
| Browse | 7 ms | 8 ms | 8 KB / 11 |
| Notifications, My claims, Profile | 5–6 ms | 5–7 ms | same |

### 5.2 Phone and desktop in a real browser (`page_load.py`, time until usable)
| Page | Phone v1.1.1 | Phone v1.1.2 | Desktop v1.1.1 | Desktop v1.1.2 | Design shown |
| --- | --- | --- | --- | --- | --- |
| Browse | 761 ms (84 KB) | 790 ms (106 KB) | 112 ms | 89 ms | yes |
| Post page | 819 ms | 863 ms | 122 ms | 104 ms | yes |
| My posts | 799 ms | 752 ms | 61 ms | 58 ms | yes |
| Messages | 778 ms | 787 ms | 111 ms | 85 ms | yes |
| Notifications | 755 ms | 795 ms | 59 ms | 54 ms | yes |
| Profile | 760 ms | 818 ms | 54 ms | 55 ms | yes |

Differences of ±60 ms are normal run-to-run variation. **Browse downloads 22 KB more** in v1.1.2: the
SEC-001 noise makes simple drawn pictures (like the generated demo pictures) compress a little less. On a
realistic 12-megapixel photo the stored files grow only about **5 %** (186 → 196 KB; preview 27 → 28 KB),
and the size limits (300 KB / 40 KB) still apply.

### 5.3 Chat on a slow phone (`phone_fps.py`, 3,000-message chat)
| Measure | v1.1.1 report | v1.1.2 |
| --- | --- | --- |
| Opening the chat | 0.5 s | **0.4 s** |
| Smoothness while 200 messages arrive | 54 fps, worst frame 50 ms | **58 fps**, worst frame 50 ms |
| Idle | — | 61 fps |

### 5.4 Many people at once (`load_test.py`)
| Scenario | v1.1.1 report | v1.1.2 |
| --- | --- | --- |
| Realistic: 20 people chatting + 20 notice connections + 20 page loaders | 8 ms per message, 18 ms per page | **6 ms** per message (95 %: 24 ms), **20 ms** per page; 299/299 delivered, 0 errors |
| Heavy: 100 people chatting (~50 messages/s) + 100 notice connections + 20 page loaders | median 0.18 s, all delivered | **median 0.04 s** (95 %: 0.88 s), 1,499/1,499 delivered, 0 errors |

### 5.5 Media processing (SEC-001 cost)
| Upload | v1.1.1 | v1.1.2 | Note |
| --- | --- | --- | --- |
| 12-megapixel phone photo → stored copy | 452 ms | 539 ms | noise + checks |
| 15-second 1080p chat video → stored copy | 3.0 s | 4.1 s | background worker; the chat stays quick |

---

## 6. Bugs found and fixed in v1.1.2

| ID | Found by | Summary | Status |
| --- | --- | --- | --- |
| BUG-009 | testers via owner | FindIT.cmd reopened the login page every 20 s | fixed — needs a check on a real Windows PC |
| BUG-010 | testers via owner | design missing on some Windows PCs | fixed — confirm on the PCs that had it |
| BUG-008 | code review | post page category link empty, dormant location shown | fixed |
| SEC-002 | owner + Claude | notification link `/\other.site` could open another website | fixed |
| SEC-001 | owner | hidden data in photos/videos (colour profile/comments kept, any picture type opened, extra video streams, playlists) | fixed |
| CHG-008 | owner | demo passwords and private instructions in the shared repository | fixed |

No new bugs were found in this round's bug hunt.

---

## 7. What was **not** tested

- **The team's Windows PC:** `FindIT.cmd` (BUG-009) cannot run on the Linux test machine; BUG-010 was
  tested by simulating the broken registry, not on an affected PC. Video processing is likely slower on a laptop.
- **Real phones** (only simulated), camera QR scanning, real campus Wi-Fi, real people.
- Photos/videos from real phones (tests used generated pictures and clips).
- Report attachments (screenshots/PDFs in "Report a problem") are not covered by SEC-001 — owner to decide.
- 1,600 people at once on the online system (needs hosting — v3.0.0).
