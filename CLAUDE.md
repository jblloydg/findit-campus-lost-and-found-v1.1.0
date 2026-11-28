# Find-IT — project brief for Claude (Claude Code reads this automatically)

Campus lost-and-found web app for Davao Oriental State University (DOrSU). Student capstone project.
Read this first, then `HANDOFF.md` (what v1.1.0 contains) and `docs/ROADMAP.md` (what's next).

## Stack (fixed — do not change without the owner's approval)
- **Python + Django 5.2** (backend and server-rendered templates), Django Channels for live chat.
- **SQLite** locally; must stay **PostgreSQL-compatible** (`DATABASE_URL`) for hosting later.
- Windows is the team's machine. Run with `FindIT.cmd` (double-click) or the PowerShell steps in `HANDOFF.md` §6.
- Use **Python 3.13 or 3.14** (Django 5.2 supports up to 3.14; tested on 3.13).

## Repositories
| Repo | Role |
| --- | --- |
| `jblloydg/findit-campus-lost-and-found` | Original starter. **Read-only, never change.** |
| `jblloydg/1`, `/2`, `/3`, `/4` | The four sessions that built v1.1.0. **Read-only references, never change.** Ignore `ITPE30_INTEG-`. |
| `jblloydg/findit-campus-lost-and-found-v1.1.0` | **This repo — the only one to work in.** |

## Branches and versions
- `main` = the stable released version. Branch **`stable/v1.1.0`** is the frozen v1.1.0 rollback point (this session could not push tags; add tag `v1.1.0` from GitHub Releases if wanted).
- Work for the next version happens on **`release/1.1.2`** (in both the public repo and the owner's private copy, see below) (branched from the finished v1.1.1 on `main`). v1.1.2 = bug fixes for v1.1.1 found by testers; it must keep running on local devices (one Windows PC, no hosting). Frozen copies: `stable/v1.1.0`, `stable/v1.1.1`.
- One bug or change = one commit (message starts with its ID, e.g. `BUG-003: …`), so any fix can be reverted alone.
- **Version plan:** v1.1.1 = V2-I school verification + bug fixes → v2.0.0 interface overhaul → v2.1.0 its bug fixes → v3.0.0 online hosting + PostgreSQL + all of V2-J (performance and uptime evidence). Don't start hosting/PostgreSQL/Redis/SMTP/V2-J work before v3.0.0 unless asked; keep the code PostgreSQL-compatible meanwhile. Details in `docs/ROADMAP.md`.
- When the owner approves a version: merge its `release/…` branch into `main` and add a frozen `stable/v<version>` branch (tags can be added on GitHub). Never rewrite or delete history.
- Log every fix in `docs/BUG_REPORTS.md` and add a "Changes in <version>" section to `HANDOFF.md`.

## Version label (owner's instruction — implement in v2.0.0, not before)
- From **v2.0.0** (after all v2.0.0 wireframes are integrated), every page shows the app version near the bottom: small, light-gray text such as "Find-IT v2.0.0". Its exact place is decided in the v2.0.0 wireframes.
- The number must come from the **`VERSION`** file (read once by the app), never typed into pages.
- For **every** version update from then on, change `VERSION` in the same work, so the label always matches the version people are running.

## v1.1.2 instructions from the owner (do these in the v1.1.2 session)
1. **BUG-009 — FindIT.cmd reopens the login page every ~20 seconds.** Cause: when Find-IT is already running, the "already running" branch opens the browser and returns to the menu, whose 20-second auto-start then fires again → endless loop (seen when the shortcut is opened twice). Fix: auto-start only the first time the menu shows; in the "already running" case open the browser once and wait at the menu with no timer (or close). Must still work on a plain Windows PC.
2. **BUG-008 — post page category/location line** (`templates/core/post_detail.html`, the `item-tags` line): the category link is empty (`get_category_display` does not exist for the category model) and filters by name instead of id, and the dormant location is shown when a post has one. Fix: link to `?category=<id>` with the category name; show location only when `FINDIT_LOCATION_ENABLED=1`.
3. **SEC-001 — media steganography / hidden payloads: everything becomes plain pixels.** Goal: anything hidden inside a photo or video (steganography, appended files, malicious metadata or streams) must end up as meaningless colors/noise in the stored copy, never as data a keylogger or other malware could read or run. Already true in v1.1.1: every photo/video is decoded and re-encoded (photo → JPEG, video → H.264/AAC MP4), originals deleted, files served with `nosniff` and a sandbox CSP. Strengthen in v1.1.2:
   - **Videos:** keep only one video stream and at most one audio stream; drop everything else (`-map 0:v:0 -map 0:a:0? -sn -dn -map_chapters -1 -map_metadata -1`, no attachments/fonts/subtitles/data streams); never stream-copy, always re-encode.
   - **Block tricky inputs:** only local files may be read (`-protocol_whitelist file,pipe`); refuse inputs whose detected container is not in an allow-list (mp4/mov, webm/matroska, 3gp) — e.g. HLS/playlist or "concat" files that try to read other files or the network.
   - **Destroy hidden bits in pixels:** besides lossy re-encoding and resizing, apply a tiny change that scrambles the lowest bits (e.g. slight re-scaling, mild noise or colour re-quantisation) to photos, video frames and video posters, so least-significant-bit steganography cannot survive; check visually that people cannot see the change.
   - **Check the output:** after encoding, probe the result and accept it only if it is exactly what we expect (JPEG photo; MP4 with H.264 video + optional AAC audio, no other streams, no metadata); otherwise refuse the file.
   - **Run safely:** ffmpeg as a separate program with a time limit, in a temporary folder, without a shell, low priority; same rules for post photos, profile photos and status-request photos.
   - **Tests:** a photo and a video with hidden data in pixel lowest bits, an appended ZIP, extra data/subtitle/attachment streams, metadata, and an HLS/concat "video" — the stored copy must contain none of it (compare bytes and extract the lowest bits). Log as SEC-001 and include it in the v1.1.2 test report.
   - Plain explanation for the paper: hidden data in a picture cannot run by itself; the danger is a program that later reads it. Re-encoding turns that hidden data into ordinary color noise, so there is nothing left to read.

## Private data stays out of the shared repository (owner's rule since v1.1.2 — EVERY version)
This repository and its release branches are shared publicly. **Never** put any of these in a file, commit message, handoff, report or test here:
- passwords of any kind (demo, test or real), sign-in lists with passwords, keys, `.env` values;
- instructions for creating or managing the owner's Developer account;
- real people's names, Student IDs, emails or other personal data;
- any other sensitive instruction the owner marks as private.
They belong only in the owner's **private copy** (a private repository or the owner's PC). If a task needs one, ask the owner instead of writing it here.

**Two copies of every release (owner's rule since v1.1.2):** this **public** repository has the full program without the private parts; the owner's **private** repository has the same branches (`main`, `release/<version>`, `stable/v<version>`) plus the private notes. Changes flow **public → private only**: do the work here, then merge each public branch into the private branch of the same name. **Never push or merge a private branch into this repository.** When a version is approved, update and freeze both copies (merge into `main`, add `stable/v<version>` in both).

Demo passwords are made per PC (`core/demo_logins.py`). `core/tests/test_v112.py::NoSensitiveDataInSharedFilesTests` scans every tracked file and must pass; extend its patterns when something new must stay private. Check for leaks in every version's bug hunt.

## Reports required for EVERY version (owner's rule since v1.1.1)
Before a version is pushed for approval, it must include, in plain text (readable in any Claude session):
1. **`docs/CHANGES_v<version>.md`** — what changed: features, speed changes, bugs fixed, migrations, new packages, what is not included. Model: `docs/CHANGES_v1.1.1.md`.
2. **`docs/TEST_REPORT_v<version>.md`** — automated test results, **bug hunt** over the whole program (pages per role, hostile form/address input, security checks, real-browser checks), **performance** on phone + web + backend with before/after numbers, bugs found and fixed, what was not tested. Model: `docs/TEST_REPORT_v1.1.1.md`. Reuse and extend `tools/testing/`.
3. Every bug and change logged in **`docs/BUG_REPORTS.md`** with its commit.
Run the bug hunt again after any big change (e.g. chat, media) and once more on the whole program before pushing.

## Decisions already made by the owner (keep them)
1. **Session 4's design has priority** whenever sessions named or behaved differently.
2. **Claim states:** Submitted → Approved → Returned → Completed, plus Declined, Closed, Expired. Several claims can be approved; public counts, private rank; the finder picks who gets the item. Decline reason optional, shown to the claimant. Re-apply once. 7-day inactivity expiry (incl. Approved). **No automatic answer checking — people judge answers.**
3. **Ownership questions** are picked from an admin question bank: 3–5 per found post (defaults fill to 3) + a required claimant description (no minimum length).
4. **Roles:** Student, Staff, Admin, plus **Developer** (v1.1.1, above Admin: the only one who makes/removes admins and opens `/django-admin/`; never created or edited via a web page; superusers are not admins). How the owner creates and manages it is in the owner's private notes only. **Security guards = plain Staff:** approve/decline claims, guard house, finder status requests, view claim answer forms. **Verified moderators (Staff verified by an admin) + Admins only:** read other people's private chats, pause chats, review reports.
5. **Share mode:** posts are visible signed-out only after someone signed in presses Copy link; then permanently.
6. **Posts:** category required (admin-managed), 1–20 photos required, title/description optional, captcha above 10 photos (django-simple-captcha, randomized, **no audio**), posts-per-hour limit (admin setting).
7. **Guard house:** only staff change the status (QR scan / code / manual). The QR link opens for anyone, but only staff see Confirm. Claims and chats stay open there; the finder sends status requests (reason required, photo optional). No storage location, no condition notes (main campus only).
8. **Location is DORMANT** (future DOrSU campus map in segments). Keep the field; don't show, collect or filter it unless `FINDIT_LOCATION_ENABLED=1`. Don't remove it, don't build the map unless asked.
9. **Backups:** session 4 engine (`backup_now`, `restore_backup`), daily via the timer runner, 14 days kept.
10. **Example values in the interface, docs, Figma and tests:** Student ID **`2020-0001`**, name **Cruz, Juan D. (Dela)**. **Never use the old example ID from the starter project** — it is the owner's real personal account. Never use any real ID or name as an example.
11. **Chat (v1.1.1):** messages and notifications have queues and one-time ids (never lost or doubled). History pages are sized by bytes (~8 KB, max 50 messages), load on scroll; search per chat. **Photos/videos in chats** are re-encoded (JPEG / 720p MP4), private, original not kept. Verified: photo 5 MB, video 20 MB/60 s, unlimited count but heavy floods quietly slowed down. Unverified: photo 2 MB, video 8 MB/20 s, 3 per chat. Post photos are compressed on upload too (1600 px/~300 KB + 480 px preview). Posts stay photos-only.
12. **Verification (V2-I, v1.1.1):** optional email code → ✔ Verified. Students sign in with email (or a verified Student ID). Student IDs may be shared until one account verifies (then locked; others get 14 days; 3 different IDs = disabled); ID reviews by verified moderators/admins. Unverified limits: 3 open claims, 3-day claim expiry, 1 post/day, 10 chat msgs/10 min, 100 chars, red warning for others. Report & block = one button, reason optional ("Block" category). Real email, ID barcode and 2-step sign-in → v3.0.0.
13. Privacy: no real student data, passwords, secrets, `db.sqlite3`, `media/`, `private_media/`, `backups/` or `.env` in Git. Demo accounts are fictional and local-only.

## Working rules (how the owner wants Claude to work)
- **Ask before building** when anything is unclear — the owner prefers many questions over a wrong implementation. Use question cards/options when available.
- When a request conflicts with a decision above, a role/status name, or the paper, **say so and ask** before changing it.
- Plan first for anything bigger than a small fix; get approval.
- **Never** change the read-only repos. Never force-push. Don't push to `main` without approval.
- Keep explanations plain; the owner is a student, not a professional developer.

## Commands
```powershell
python manage.py migrate            # never run makemigrations on a server; commit new migrations
python manage.py seed_demo          # fictional demo data (local only); random passwords -> demo-logins.txt
python manage.py test core          # 228 tests (v1.1.2); keep them passing, add tests for each fix
python manage.py makemigrations --check --dry-run   # must say "No changes detected" before committing
python manage.py backup_now [--list] / restore_backup NAME
```
Demo sign-ins: made at random on each PC by `seed_demo`, saved in `demo-logins.txt` (ignored by Git), shown by FindIT.cmd menu 2. Students sign in by email (e.g. `alex.finder@example.com`); staff `security.demo` (guard), `moderator.demo` (verified moderator); admin `findit-admin`. Test scripts read passwords with `core.demo_logins.password_for()`. v2.0.0 examples: `casey.unverified@example.com` not verified, `morgan.shared@example.com` not verified with a Student ID conflict and an open ID review, Drew (`2026-0016`) red-flagged and disabled.

## Where things are
- `core/models.py`, `forms.py`, `services.py` (all state changes go through services), `views.py`, `urls.py`, `permissions.py`
- `core/chat_history.py` (byte-sized history pages, chat search), `core/chat_media.py` (chat photos/videos, worker), `core/images.py` (photo compression)
- `docs/CHANGES_v1.1.1.md`, `docs/TEST_REPORT_v1.1.1.md`, `tools/testing/` (bug-hunt and performance scripts)
- `core/verification.py` (v1.1.1 verification, Student IDs, ID reviews, limits, report & block), `core/auth.py` (sign-in rules), `core/mail.py` (Test inbox)
- `core/matching.py` (LOST↔FOUND matches), `core/backups.py`, `core/idempotency.py` (duplicate-submit protection), `core/security.py` (sign-in lockout)
- `templates/core/` (shell: `base.html`, `includes/sidebar.html`, `includes/icon.html`), `static/css/findit.css` (v2.0.0 look, replaced `app.css`), `static/css/campus-bg.css` (monument background), `static/js/app.js`, `chat.js`, `scan.js`
- `core/tests/` (sessions 1–4 tests), `docs/handoffs/session-N.md` (each session's original handoff), `docs/OPERATIONS.md`
- Figma: https://www.figma.com/design/HlBvwAA17U86RADmkm56Fk — Starter plan (3 pages max); new screens live in the "New Features (Nov 2026)" section on page "01 — Screens & Overview".
