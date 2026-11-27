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
- Work for the next version happens on **`release/1.1.1`** (branched from `v1.1.0`).
- One bug or change = one commit (message starts with its ID, e.g. `BUG-003: …`), so any fix can be reverted alone.
- **Version plan:** v1.1.1 = V2-I school verification + bug fixes → v2.0.0 interface overhaul → v2.1.0 its bug fixes → v3.0.0 online hosting + PostgreSQL + all of V2-J (performance and uptime evidence). Don't start hosting/PostgreSQL/Redis/SMTP/V2-J work before v3.0.0 unless asked; keep the code PostgreSQL-compatible meanwhile. Details in `docs/ROADMAP.md`.
- When the owner approves 1.1.1: merge `release/1.1.1` into `main`, tag `v1.1.1`. Never rewrite or delete history.
- Log every fix in `docs/BUG_REPORTS.md` and add a "Changes in <version>" section to `HANDOFF.md`.

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
4. **Roles:** Student, Staff, Admin, plus **Developer** (v1.1.1, above Admin: the only one who makes/removes admins and opens `/django-admin/`; created only with `manage.py create_developer`, never via a web page, no email reset; superusers are not admins). **Security guards = plain Staff:** approve/decline claims, guard house, finder status requests, view claim answer forms. **Verified moderators (Staff verified by an admin) + Admins only:** read other people's private chats, pause chats, review reports.
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
python manage.py seed_demo          # fictional demo data (local only)
python manage.py test core          # 202 tests; keep them passing, add tests for each fix
python manage.py create_developer   # the owner's Developer account (password typed privately)
python manage.py makemigrations --check --dry-run   # must say "No changes detected" before committing
python manage.py backup_now [--list] / restore_backup NAME
```
Demo sign-ins: students by email, e.g. `alex.finder@example.com` (or verified ID `2026-0001`) / `DemoFindIt!2026` (students 0001–0004 verified, `casey.unverified@example.com` not verified), `security.demo` (guard), `moderator.demo` (verified moderator) / `DemoStaff!2026`, `findit-admin` / `DemoAdmin!2026`.

## Where things are
- `core/models.py`, `forms.py`, `services.py` (all state changes go through services), `views.py`, `urls.py`, `permissions.py`
- `core/chat_history.py` (byte-sized history pages, chat search), `core/chat_media.py` (chat photos/videos, worker), `core/images.py` (photo compression)
- `docs/CHANGES_v1.1.1.md`, `docs/TEST_REPORT_v1.1.1.md`, `tools/testing/` (bug-hunt and performance scripts)
- `core/verification.py` (v1.1.1 verification, Student IDs, ID reviews, limits, report & block), `core/auth.py` (sign-in rules), `core/mail.py` (Test inbox)
- `core/matching.py` (LOST↔FOUND matches), `core/backups.py`, `core/idempotency.py` (duplicate-submit protection), `core/security.py` (sign-in lockout)
- `templates/core/`, `static/css/app.css`, `static/js/app.js`, `chat.js`, `scan.js`
- `core/tests/` (sessions 1–4 tests), `docs/handoffs/session-N.md` (each session's original handoff), `docs/OPERATIONS.md`
- Figma: https://www.figma.com/design/HlBvwAA17U86RADmkm56Fk — Starter plan (3 pages max); new screens live in the "New Features (Nov 2026)" section on page "01 — Screens & Overview".
