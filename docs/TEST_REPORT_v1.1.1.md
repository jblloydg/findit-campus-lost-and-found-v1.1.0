# Find-IT v1.1.1 — Test report (bug hunts and performance)

Plain-text report for test documentation. Written so it can be read in any Claude session or
pasted into the paper. All accounts, names and files used were fictional/generated.

- **Version tested:** v1.1.1, branch `release/1.1.1` (see `docs/CHANGES_v1.1.1.md` for what changed)
- **Date:** 27 November 2026
- **Tested by:** Claude (AI assistant), on request of the project owner. No human testers yet.
- **Test machine:** Linux test computer (not the team's Windows PC), Python 3.13, Django 5.2,
  the local development server (daphne), SQLite in WAL mode, Google Chrome (headless).
- **Phone simulation:** Chrome with a 390 × 800 screen and the processor slowed down 4×;
  for media also a slow network (1.5 Mbit/s down, 150 ms delay).
- **Tools:** `tools/testing/` (see its README to run them again).

---

## 1. Summary

| Area | Result |
| --- | --- |
| Automated tests | **202 tests, all pass** (`python manage.py test core`) |
| Bug hunts | 3 rounds over the whole program; **7 bugs found, all fixed** (BUG-001 … BUG-007) |
| Crashes left | **0** in the last round (558 pages × 7 roles, 81 routes with hostile data) |
| Performance problems found | **3** (PERF-001 chat lag, PERF-002 overload, PERF-003 heavy photos) — all fixed and re-measured |
| Chat on a slow phone | 54–60 fps (smooth) with bursts of messages and with media |
| Opening a chat full of media on a slow phone | text after 1.2 s; only 130 KB of media downloaded at first |

---

## 2. Automated tests

`python manage.py test core` → **Ran 202 tests … OK**.

| Group | Tests | What they check |
| --- | --- | --- |
| Sessions 1–4 (v1.1.0) | 142 | posts, claims, guard house, share mode, backups, accounts, reports, security |
| V2-I verification | 33 | email code, sign-in by email / verified ID, Student ID rules, ID reviews, unverified limits, report & block, Developer role, test inbox, SQL-injection attempts |
| Bug fixes | 2 | BUG-002, BUG-003 |
| Chat queue / notifications | 7 | one-time ids, resends saved once, limits not double-counted, junk input, catch-up, after-save push, worker thread |
| Photos / history / search | 9 | compression, GPS removed, previews, byte-sized pages, full history readable with no gaps, search, privacy, rate limits |
| Chat media | 9 | hidden payload removed, private files, fake files refused, unverified limits, video length, quiet slow-down, video byte ranges, duplicates, file clean-up |

---

## 3. Bug hunts

### Round 1 — after V2-I (whole program)
- Every page opened as every demo role: **487 pages**.
- Every form action sent empty and hostile data (SQL text, 5,000-character text, wrong ids,
  external `next` links) as 5 roles: **77 routes**.
- Live server run: sign-up → Test inbox code → chat limits over WebSocket → verify → sign in with Student ID.
- Timer runner and a backup/restore round trip with the new tables.

| ID | Found | Fixed |
| --- | --- | --- |
| BUG-001 | Chat never showed the server's error messages; typed text was lost when a message was refused. | Status line under the chat; text put back. |
| BUG-002 | A damaged `claim_id`/student value crashed "Mark returned" and guard-house pickup (500). | 404 / clear message. |
| BUG-003 | An impossible date (2026-99-99) in report filters crashed the report lists (500). | Invalid dates ignored. |

### Round 2 — after the chat and notification queue (whole program)
- Real browser: server stopped and restarted while chatting and while notices arrived.
- Pages as every role **plus a Developer account** (about 1,150 pages incl. `/django-admin/`).
- Forms without the security (CSRF) token → all refused (403).
- `check --deploy` with online settings; Test inbox off and demo data refused when DEBUG is off.

| ID | Found | Fixed |
| --- | --- | --- |
| BUG-004 | Live notices/chat updates were pushed before the database save was final. | Push waits for the save. |
| BUG-005 | Chat WebSocket crashed on valid JSON that is not an object (e.g. `[1]`). | Answers "Invalid message". |
| BUG-006 | Notices made by the timer runner never reached pages that were already open. | Pages re-check about once a minute. |

### Round 3 — after Messenger-style history, search, photo compression and chat media (whole program)
- **558 pages** × 7 roles, **81 routes** with hostile data (incl. media ids and `../../etc/passwd`) → **0 crashes**.
- Hostile page addresses (`?page=abc`, SQL text, `?open=abc`, impossible dates…) → **0 crashes**.
- Video range requests (`bytes=abc`, `bytes=999999999-`, `bytes=-0`, `bytes=5-2`, multi-range) → correct 200/206/416 answers.
- Fake files: a program renamed to `.jpg`, a script renamed to `.mp4`, an `.exe` → all refused; nothing stored.
- A real JPEG with a hidden ZIP payload appended → the stored copy is a clean re-encoded JPEG, payload gone.
- Code check (pyflakes) of all new files: no undefined names or real errors (only unused imports in older test files).

| ID | Found | Fixed |
| --- | --- | --- |
| BUG-007 | Chat photo/video files would stay on disk when a chat or post was permanently deleted. | Files deleted with the chat/post (found during development, fixed before release). |

Not a bug (checked): in one scroll test older messages did not load — the test only scrolled
7,500 of 29,583 pixels; scrolling to the top loads them correctly (50 → 100 messages).

---

## 4. Performance

### 4.1 Chat text (PERF-001)
3,000-message chat, slowed-down phone:

| Measure | Before | After |
| --- | --- | --- |
| Chat page from the server | 828 KB, 373 ms | 21–27 KB, 17 ms |
| Opening the chat on the phone | 2.3 s | 0.5 s |
| Smoothness while 200 messages arrive | 9 fps, freezes up to 250 ms | 54 fps, worst frame 50 ms |
| Smoothness during a 500-message flood | — | 50 fps, at most 300–400 messages kept on screen |

Pages are now sized by **bytes** (about 8 KB of text, at most 50 messages per page). Older
messages load by themselves when scrolling up (after a 250 ms pause, rate-limited to
120 pages per minute per person). Search waits until typing pauses (450 ms), max 20 per minute.

### 4.2 Many people at once (PERF-002)
| Scenario | Before | After |
| --- | --- | --- |
| Heavy: 100 people chatting (50 messages/s) + 100 notice connections + 20 page loaders + timer runner | median 20.7 s per message, 919 of 1,500 not delivered, "database is locked" | median 0.18 s (95% under 1.1 s), all 1,500 delivered, no lock errors |
| Realistic: 20 people chatting + 5 page loaders | — | median 8 ms per message, 18 ms per page |

### 4.3 Photos (PERF-003)
| Upload | Stored | Notes |
| --- | --- | --- |
| Post photo, 3.5 MB phone photo with GPS | ≤ 300 KB (max 1600 px) + preview ≤ 40 KB (max 480 px) | GPS and other hidden data removed; original not kept |
| Chat photo, 3.9 MB (4000 × 3000) | **271 KB** (1600 × 1200) | visible in the chat **1.7 s** after picking it on the slow phone |
| 7 MB photo (verified limit 5 MB) | refused before uploading | message: "photos can be up to 5 MB" |

### 4.4 Videos in chats (CHG-006)
| Upload | Stored | Time |
| --- | --- | --- |
| 19.3 MB, 59 s, 1920 × 1080 video | **5.1 MB, 1280 × 720, 59 s** | upload 2.0 s (local network), playable **25.2 s** after picking (re-encoding ≈ 23 s on the test machine) |

While that video was being re-encoded, the Browse page still loaded in **163 ms** — videos are
processed by a background worker and never slow down the website. On the team's Windows
laptop re-encoding will likely take longer; the person sees "Processing…" meanwhile.

### 4.5 Opening a chat full of media (phone + slow network)
Chat with 60 photos/videos between text messages; phone = 4× slower CPU, 1.5 Mbit/s network:

| Measure | Result |
| --- | --- |
| Text visible | **1.2 s** |
| Page size | 21 KB (50 messages, 25 media placeholders) |
| Media downloaded on opening | **130 KB, 11 files** — only what is on screen (photos as 40 KB previews; videos load only when played) |
| Scrolling up through media | **60 fps**, worst frame 17 ms |

### 4.6 Offline / reconnect behaviour
| Test | Result |
| --- | --- |
| Messages typed while the server was down (one pressed twice) | shown as "Waiting to send…", sent by themselves when it came back, each saved **once**, nothing doubled after reload |
| Photo picked while the server was down | "Waiting for the connection…", uploaded by itself afterwards, sent once |
| Notices and a chat message created while the server was down | appeared about **6 s** after it came back; badges matched the database; no duplicates |

---

## 5. Limits set in v1.1.1 (for the paper)

| | Verified student / staff | Unverified student |
| --- | --- | --- |
| Chat text | 2,000 characters per message | 100 characters, 10 messages per 10 minutes |
| Chat photos | up to 5 MB each → stored ≤ 300 KB | up to 2 MB each → stored ≤ 200 KB |
| Chat videos | up to 20 MB and 60 s → stored 720p ~1 Mbit/s | up to 8 MB and 20 s → stored 480p |
| Number of chat photos/videos | no limit (a heavy flood in one chat is quietly slowed down) | 3 per chat |
| History page | ~8 KB of text, max 50 messages | same |
| Search | 20 per minute | same |

---

## 6. What was **not** tested yet

- The team's Windows PC (FindIT.cmd menu, video re-encoding speed there).
- Real phones (only simulated), camera QR scanning, real campus Wi-Fi.
- Real people (no human testers yet) — see `docs/BUG_REPORTS.md` for how to report.
- 1,600 people at once on the **online** system (needs hosting, PostgreSQL, Redis and several
  server processes — planned for v3.0.0 together with the 2.5-second and uptime evidence).
