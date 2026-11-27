# Find-IT roadmap

## Status of the paper's "Version 2" list in v1.1.0

The V2 list was written before v1.1.0. The four sessions already built most of it.

| Code | Item | Status in v1.1.0 | Built by | Notes |
| --- | --- | --- | --- | --- |
| V2-A | Match suggestions for LOST posts, ranked | ✅ Done | Session 3 | Scored by category, title, description; shown to the LOST author and staff; message after posting. |
| V2-B | More search filters (date, category) | ✅ Done | Sessions 3 + 4 | Date range + admin-managed categories (15 starter categories). |
| V2-C | Approximate time | ✅ Done | Session 2 | With date rules (time needs a date; nothing in the future). |
| V2-D | Approve/reject claims, decision shown to claimant | ✅ Done — **D1 + staff** | Session 4 | Finder or staff decide (D1 with staff able to decide). **D3 (automatic answer checking) rejected** by the owner. |
| V2-E | Profile editing (name, password) | ✅ Done | Session 1 | Plus contact number, profile photo, password reset by email. |
| V2-F | Staff/admin controls: verify moderators, change roles, item/system reports | ✅ Done | Session 1 | Moderator verification, admin account editing (role/status), chat + general reports. |
| V2-G | Guard-house intake form | ✅ Done (no condition notes) | Session 4 | Records received-by, time, method, handed-over-by. Condition notes left out by the owner's choice. |
| V2-H | Daily backups and restore | ✅ Done | Sessions 4 + 1 | Session 4 engine; session 1 admin page, scheduler scripts, OPERATIONS.md. |
| V2-I | School account verification | ✅ Done (local) in **v1.1.1** | v1.1.1 | Optional email code → ✔ Verified; Student ID locked on verification; ID reviews; unverified limits + warning; Report & block. Real email sending and ID-barcode checks → v3.0.0. |
| V2-J | Performance and uptime evidence (→ v3.0.0) | 🟡 Partly | Sessions 1 + 4 | Session 1 measured 15–181 ms medians locally on 3,000 posts (see `docs/handoffs/session-1.md` §D). `/health/` exists. Real proof needs hosting + an uptime monitor. |

**Remaining V2 work: all of V2-J in v3.0.0.** (V2-I done in v1.1.1.)

## Version plan (set by the owner)

| Version | Goal | Status |
| --- | --- | --- |
| **v1.1.0** | Sessions 1–4 integrated. Covers most V1 and V2 goals. | Released (`main`) |
| **v1.1.1** | V2-I school account verification, chat/media, speed + bug fixes + easier start. | Released on `main` (rollback: `stable/v1.1.0`) |
| **v1.1.2** | Bug fixes for v1.1.1 from testers (`docs/BUG_REPORTS.md`). Must keep running on local devices. Branch `release/1.1.2`. | Waiting for bug reports |
| **v2.0.0** | Interface overhaul. Lead: *(to be named)* | Planned |
| **v2.1.0** | Fix bugs found in 2.0.0 **+ adaptive layout**: every page adapts from PC to phone using relative sizes (percentages / fluid units) instead of fixed pixel sizes. | Planned |
| **v3.0.0** | Online hosting: put the app on the internet, move SQLite → PostgreSQL, all of V2-J (2.5-second and uptime evidence). | Planned |

### What v1.1.1 contains
- **V2-I school account verification**: optional email code (printed locally + Test inbox), sign-in with email, Student ID rules (shared until verified, 14-day grace, 3 IDs = disabled), ID reviews, unverified limits and warning, Report & block.
- **Developer role** (only it makes admins; `create_developer` command).
- **Easier start** (`FindIT.cmd` menu, `START-HERE.txt`).
- **Chat:** message and notification queues (never lost or doubled), Messenger-style history (byte-sized pages, scroll to load, search), photos and videos in chats (re-encoded, private, limited).
- **Speed:** smooth chat on slow phones, no overload with many users, photos compressed on upload.
- **Bug fixes** BUG-001…007 (`docs/BUG_REPORTS.md`). Full list: `docs/CHANGES_v1.1.1.md`; tests: `docs/TEST_REPORT_v1.1.1.md`.

### Moved to v3.0.0 (hosting)
- **Confirm the 2.5-second target and reliable uptime** (all of V2-J): needs measurement on the hosted app; the local app alone cannot show them.
- **Daily backups and restore in the online app:** the local command-line engine exists (`backup_now`, `restore_backup`, daily via the timer runner), but the hosted app needs its own scheduler, off-site backup storage and a tested restore procedure (no in-app restore yet).
- **Real email connection** for verification codes, welcome emails and password resets (SMTP / email service); the Test inbox turns off automatically.
- **Load test at campus scale** on the hosted system (about 1,600 people at once = 10% of ~16k DOrSU students) with PostgreSQL, Redis and several server processes. v1.1.1 is tuned for one PC.
- **How to verify an account properly:** read the **barcode on the back of the school ID** (find out what it contains; it can be copied, so combine it with other checks), and decide later security changes.
- **Two-step sign-in** (authenticator app such as Google/Microsoft Authenticator) for the Developer and administrators, set up once on the online site.
Also: PostgreSQL testing and switch, hosting provider, HTTPS, real email (SMTP) for password resets and verification, Redis for live chat across processes, uptime monitor (rest of V2-J), scheduled backups on the server.

### v2.0.0 / v2.1.0 — interface
- **v2.0.0:** interface overhaul (lead to be named).
- **v2.1.0:** bug fixes for 2.0.0 and an **adaptive layout**: pages scale from PC to phone with
  relative sizes (%, `rem`, `vw`, `clamp()`), not fixed `px`; chat bubbles, photos and videos
  size themselves to the screen; touch-friendly buttons. (v1.1.1 only made the phone fast, not
  re-designed.)

### Messages — ideas for later versions (not built yet)
- Photo viewer inside the chat (swipe, zoom) instead of opening a new tab.
- Several photos in one message (album), and a "retry" button on failed uploads.
- Resumable uploads for big videos on weak Wi-Fi (upload in pieces).
- Read receipts ("Seen") and "typing…" indicator.
- Delete / unsend a message for both people (with a moderator copy kept for reports).
- Voice messages (compressed like videos).
- Smaller files with WebP/AVIF photos and newer video formats when phones support them well.
- Storage rules: how long chat media is kept after a post is closed, and a per-student storage quota.
- Push notifications on phones (installable web app / PWA) and an offline cache of recent chats.
- Faster search for big databases (PostgreSQL full-text search) — with hosting.
- Video processing on a separate worker service (Celery/Redis) when hosted — with hosting.

### Not scheduled yet
The dormant campus-map location (DOrSU map in segments).

## Known open items (after 1.1.1)

- `FindIT.cmd` (new menu in 1.1.1) still needs a first run on a real Windows PC.
- Browser/UI behaviour, phone layouts, camera QR scanning and two-user live tests not yet done by people.
- PostgreSQL untested. Password-reset email needs SMTP settings when hosted.
- Paper updates needed: see `docs/handoffs/session-4.md` §9 and `HANDOFF.md` §8.
