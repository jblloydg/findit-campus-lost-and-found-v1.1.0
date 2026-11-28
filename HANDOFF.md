# Find-IT handoff — v2.0.0 (and earlier versions below)

> **Continuing the work?** Read `CLAUDE.md` (rules and decisions), `docs/ROADMAP.md` (V2 status and what's next) and `docs/BUG_REPORTS.md` (how to report). Version 2.0.0 is on branch `release/2.0.0`; `main` stays on the released v1.1.2 until the owner approves 2.0.0. Frozen rollback points: `stable/v1.1.0`, `stable/v1.1.1`, `stable/v1.1.2`. A paste-ready prompt for a new Claude session is in `docs/TRANSFER_PROMPT.md`.

Version **1.1.0** combines the work of four separate development sessions on top of the original Find-IT starter. Each session's own handoff is kept unchanged in `docs/handoffs/session-1.md` … `session-4.md`.

All accounts, names and photos in the demo are fictional. The repository contains **no** database file, real student data, real passwords, secret keys, backups, uploads or report attachments.

---

## Changes in 2.0.0

The interface overhaul (branch `release/2.0.0`): **v1.1.2 + the front-end team's v2.0.0 interface**.
Full patch notes with the reason behind each change: **`docs/CHANGES_v2.0.0.md`**; tests and speed:
**`docs/TEST_REPORT_v2.0.0.md`**. In short:
- **New look** (DES-001…004, front-end team): dark-green sidebar (slide-in menu on phones), DOrSU monument
  photo behind every page, new colours and fonts (`static/css/findit.css` replaces `app.css`,
  `static/css/campus-bg.css`), the 9 backend features that had no page (Audit trail, System status, …).
- **CHG-009** v1.1.2 merged in; the team's new demo examples (Drew, Morgan) get random passwords too.
- **DES-005** version label "Find-IT v2.0.0" from `VERSION` (`core/version.py`).
- **BUG-011** two lost styles; **BUG-015** tap targets ≥ 2.75rem; **BUG-016** text ≥ 12 px;
  **BUG-017** 500 page without fixed px; **BUG-018** SQLite `-wal`/`-shm` files ignored by Git.
- Renumbered team entries: BUG-012 (leftover `<<<<<<<` line on Browse, still in v1.1.2), BUG-013, BUG-014.
- New tool `tools/testing/responsive_check.py` (Master Instruction check). No migrations, no new packages. Tests: 266.
- Still to redesign (layout kept from v1.1.1): see `docs/CHANGES_v2.0.0.md` §10.

## Changes in 1.1.2

Bug fixes and security updates for v1.1.1 (branch `release/1.1.2`). Full patch notes with the reason
behind each change: **`docs/CHANGES_v1.1.2.md`**. In short:
- **BUG-009** FindIT.cmd: 20-second auto-start only once; "already running" opens the browser once.
- **BUG-010** Design missing on some Windows PCs: standard file types for Find-IT's own files (`core/apps.py`).
- **BUG-008** Post page category link fixed; dormant location hidden.
- **SEC-001** Photos and videos: only real JPEG/PNG/WebP and MP4/MOV/3GP/MKV/WebM accepted; lowest colour bits
  randomised; metadata, colour profiles, extra streams and appended files removed; playlists refused;
  output checked (`core/images.py`, `core/chat_media.py`, `core/validators.py`).
- **SEC-002** Notifications only open Find-IT's own pages (`core/security.is_own_site_path`).
- **CHG-008** No private data in the shared repository; random demo passwords per PC (`core/demo_logins.py`,
  FindIT.cmd menu 2); leak-check test.
- No migrations, no new packages. Tests: 228.

## Changes in 1.1.1

**Goal:** the last V2 item, **V2-I school account verification**, plus bug fixes and an easier way to run the app. Everything runs on one PC without hosting: emails are printed in the Find-IT window and copied to a **Test inbox** page instead of being sent.

### Starting point and branches

| | |
| --- | --- |
| Started from | `release/1.1.1` at `4f0d819` (= v1.1.0 `bd1bf55` + roadmap edits) |
| Rollback point | branch `stable/v1.1.0` → `bd1bf55` (GitHub refused tag pushes from this session, so a branch is used; tag `v1.1.0` can be added later from GitHub's Releases page) |
| `main` | unchanged (v1.1.0) until the owner approves; then merge `release/1.1.1` and tag `v1.1.1` |

Commits (each can be reverted on its own): `V2-I …` (feature), `BUG-001`, `V2-I: … form submissions too`, `CHG-002`, `BUG-002`, `BUG-003`, the docs commit, a merge of the owner's README edit from `main`, `CHG-003` (chat queue), `BUG-005`, `BUG-004`, `CHG-004 / BUG-006` (notification queue), the docs commit, the release merge into `main`, then `PERF-001` and `PERF-002`.

### A. Email verification (optional) — V2-I

- After signing up and signing in, a student can verify their email: **Verify my email** (profile menu, the yellow strip at the top, or the "Verify your email" notice) → a 6-digit code is emailed → type it → **✔ Verified** on their profile, posts, claims and chats.
- Codes work for **15 minutes**, at most **5 codes a day** and one per minute, and a code stops working after **5 wrong tries**. Only a hash of the code is stored.
- Changing the email in Edit profile removes the badge until the new email is verified.
- Staff, administrators and the Developer count as verified (an administrator created them).
- **Welcome messages:** every new account gets 3 notifications, each also sent as an email: *Welcome to Find-IT*, *Verify your email* (tapping it opens the Verify page; the email contains a code), *Start posting and browsing* (opens Browse). Tapping any notification now opens its page.
- **Test inbox** (`/test-inbox/`, link in the top menu): each person sees only their own test emails. It exists only on a local PC (DEBUG on, no mail server); it can never appear on an online site.

### B. Signing in

- **Students sign in with their email.** A student whose Student ID is verified (locked to them) can also type the Student ID. The password must always match.
- Staff, administrators and the Developer sign in with their username.
- New student accounts get an internal username (`student-…`) that is never used to sign in.

### C. Student ID rules

- While nobody has verified a Student ID, **several accounts may use it**.
- When one account verifies its email, the ID is **locked** to that account. The other accounts get a notice and **14 days** (System settings) to change their ID or appeal. After that, their ID is cleared and they must set a new one before using the site.
- Sign-up with a locked ID is refused, unless the person ticks *"This is my Student ID…"*: the account is created **without** an ID and they go straight to the ID review form.
- An account that has used **3 different Student IDs** (sign-up counts) is **red-flagged and disabled**. The Change Student ID page warns before the third.
- **ID reviews** (`/id-review/new/`): impostor, lost access, or appeal. A required short explanation and a captcha. **Anti-flood:** 1 open review per account, at most 3 every 30 days, at most 5 per network address per day, and the moderator queue (`/staff/id-reviews/`) shows one row per Student ID. **Verified moderators and administrators** decide: keep the ID with the verified account, or move it to the person who asked (the old holder must then set a new ID). While an appeal is open, the 14-day deadline is paused.
- Existing accounts from v1.1.0 (whose IDs were already unique) are marked verified with a locked ID by the migration, so nobody is locked out.

### D. Limits for unverified students (admin can change them in System settings)

| | Unverified student | Verified student |
| --- | --- | --- |
| Open claims at once | 3 | no limit |
| Claim expires after no activity | 3 days | 7 days |
| New posts | 1 per day | 10 per hour (existing setting) |
| Chat | 10 messages per 10 minutes, 100 characters each | 2,000 characters |
| Others see | a red warning at the bottom: "Warning: this user is not yet verified. Please be careful…" (they can still continue) | ✔ Verified |

### E. Report & block (one button)

- **⛔ Report & block** on the post page (the poster), the private claim form (the claimant) and in chats (the other person).
- The reason is optional. With no reason, the report is filed under the new chat-report category **"Block (no reason given)"** for verified moderators; otherwise under the chosen category. Moderators can read the chat it came from.
- Effect: their chats become read-only, open claims between them are **Closed**, and neither can claim, comment on or message about the other's posts. **My profile → Blocked people** lists them, with **Unblock** (closed chats and claims stay closed). Staff accounts cannot be blocked.

### F. Developer account and admin protection

- New role **Developer**, above Administrator. Only the Developer can **make or remove administrators**, change an administrator's role or status, and open **`/django-admin/`**. Admins can still create and manage staff and students.
- The Developer account is created and managed only on the owner's own computer (never through a web page, never reset by email). The steps are in the owner's private notes, not in this repository.
- The Developer account is hidden from administrators' account lists and cannot be edited through any web page.
- `createsuperuser` no longer makes administrators. Being a Django superuser gives no Find-IT role by itself.
- `seed_demo` refuses to run when DEBUG is off, so demo accounts can never reach an online site. (From v1.1.2 their passwords are random per PC, see `demo-logins.txt`.) The demo `findit-admin` is no longer a Django superuser.
- **For hosting later (v3.0.0):** the owner sets up the Developer account on the server (steps in the private notes). Two-step sign-in (authenticator app) is planned for v3.0.0.

### G. SQL injection

All database access uses Django's ORM, which sends what people type as **separate values (parameterized queries)**, never as part of the SQL text. The only hand-written SQL is the fixed `SELECT 1` health check, which takes no input. New tests try classic attacks (`' OR '1'='1`, `'; DROP TABLE …`) on sign-in, sign-up and search and confirm they do nothing.

### H. Easier to run

`FindIT.cmd` is a numbered menu (1 Start — also automatic after 20 seconds, 2 demo sign-ins, 3 reset demo data with a backup first, 4 automatic checks, 5 backup, 6 Developer account). It offers to install Python 3.13 when missing and explains common problems. `START-HERE.txt` has the steps in plain words.

### H2. Chat queue and duplicate protection (CHG-003)

- Every chat message carries a **one-time id**. The server saves each id **once**, so a double press, a resend after a dropped connection, or two copies arriving together all end up as **one** message. A re-sent message is never counted twice against the unverified-student limits, and nobody can reuse another person's message id.
- Messages written while the connection is down go into a **queue** in that browser (it survives a page reload). They show as *"Waiting to send…"* and are sent **automatically, in order**, when the chat reconnects by itself (it keeps retrying, and retries at once when the PC comes back online). Messages from the other person that arrived meanwhile are fetched and shown.
- If a waiting message is refused (limit, chat closed), the reason shows under the chat box and the text is put back.
- Forms (claims, comments, question answers, approvals…) already had one-time keys (`core/idempotency.py`); the guard-house Scan page already had its offline queue.
- Tested in a real browser: chat open → server stopped → messages typed (one pressed twice) → server started → both messages sent once, nothing duplicated after reload.
- **Notifications (CHG-004):** the saved notices on the server are the queue. Each time the page (re)connects, the server sends the true unread counts and the page fetches any notices it missed. Each notice id is shown and counted once, also after a reload. The red Messages count updates live. Both connections reconnect by themselves within about 10 seconds (immediately when the tab is shown again or the PC is back online). Open pages also re-check once a minute, so notices made by the timer runner appear without reloading (BUG-006).
- Browser test across a server restart: a live approval notice appeared once; two notices and one chat message created while the server was down appeared about 6 seconds after it came back; the badges matched the database; nothing was shown twice after reload.

### H3. Speed and smoothness (PERF-001, PERF-002) — measured, not guessed

| Test | Before | After |
| --- | --- | --- |
| Chat page with 3,000 messages (server) | 828 KB, 373 ms | 27 KB, 17 ms |
| Opening that chat on a 4× slowed-down phone | 2.3 s | 0.5 s |
| Phone smoothness while 200 messages arrive | 9 fps, freezes up to 250 ms | 54 fps, worst frame 50 ms |
| Phone smoothness during a 500-message flood | — | 50 fps; at most 300 messages kept on screen |
| Heavy load: 100 people chatting (50 msgs/s) + 100 notice connections + 20 page loaders + timer | median 20.7 s per message, 919 of 1,500 not delivered, "database is locked" errors | median 0.18 s (95% under 1.1 s), all 1,500 delivered, no lock errors |
| Realistic load: 20 people chatting + 5 loading pages | — | median 8 ms per message, 18 ms per page |

What changed: the chat opens with the newest 100 messages ("Show older messages" loads 100 more); incoming messages are drawn in one batch per screen frame; after a reconnect only the missed messages are fetched; chat saves take one database trip in their own worker thread; SQLite runs in WAL mode with IMMEDIATE transactions. These numbers come from this test machine with the local development server; v3.0.0 hosting will repeat the measurements on the real server (V2-J).

### H4. Chat history, search, photos and videos (CHG-005, PERF-003, CHG-006)

- **History like Messenger:** pages sized by bytes (~8 KB, max 50 messages); scrolling up loads older messages by themselves after a short pause; "Jump to latest". **Search** box in every chat.
- **Photos everywhere are compressed on upload** (original never stored or sent): post photos 1600 px/~300 KB + 480 px preview; profile pictures 256 px. GPS data removed.
- **📎 Photos and videos in chats:** re-encoded (JPEG / 720p MP4), fake or unsafe files refused, private (only the two people + reviewers). Upload queue on the device with progress, "Processing…", auto-retry after a lost connection or reload. Limits: verified photo 5 MB, video 20 MB/60 s, any number (heavy floods quietly slowed down); unverified photo 2 MB, video 8 MB/20 s, 3 per chat.
- New package: `imageio-ffmpeg` (installed automatically). Migrations `0013`, `0014`.
- Full numbers: `docs/TEST_REPORT_v1.1.1.md`. Short list of all changes: `docs/CHANGES_v1.1.1.md`.

### I. Bugs found and fixed (details in `docs/BUG_REPORTS.md`)

- **BUG-001** chat never showed the server's error messages, and the typed text was lost when a message was refused.
- **BUG-002** a damaged `claim_id`/student value crashed *Mark returned* and the guard-house pickup (500 error).
- **BUG-003** an impossible date (e.g. 2026-99-99) in the report filters crashed the report lists.
- **BUG-004** live notices and chat updates were pushed before the database save was final.
- **BUG-005** the chat connection crashed on valid JSON that is not an object (e.g. `[1]`).
- **BUG-006** notices made by the timer runner never reached pages that were already open.
- **BUG-007** chat media files stayed on disk after a chat/post was permanently deleted.

How they were found (two rounds; the second after the chat/notification queue, run on the whole program): every page opened as every demo role plus a Developer account (about 1,150 pages including /django-admin/, 0 crashes after the fixes), forms without the security (CSRF) token refused, `check --deploy` with online settings, every form action sent empty and hostile data as every role (77 routes), a live run of the real server (sign-up → Test inbox code → limited chat over WebSocket → verify → sign in with Student ID), the timer runner, and a backup/restore round trip.

### Database changes — migration `0012_v111_school_verification`

- **Profile:** `student_id` is no longer unique by itself; new `student_id_locked`, `email_verified_at`, `id_conflict_deadline`, `flagged_at`, `flag_reason`; database rule *a locked Student ID is unique*; role **developer** added.
- New tables: **StudentIdRecord** (every ID an account used), **EmailVerificationCode** (hashed codes), **TestEmail** (local test inbox), **IdReviewCase**, **UserBlock**.
- **InAppNotification:** `post` optional, new `link`. **AbuseReport:** new reason **BLOCK**. **SystemSettings:** the seven limits above.
- Data step: existing students become verified with a locked ID.

Run `python manage.py migrate` (FindIT.cmd does it for you). Never run `makemigrations` on a server.

### Files

New: `core/verification.py`, `core/auth.py`, `core/mail.py`, `core/templatetags/findit_tags.py`, an owner-only management command, `core/migrations/0012_v111_school_verification.py`, `core/tests/test_v111.py`, templates `verify_email.html`, `student_id_change.html`, `id_review_form.html`, `id_reviews.html`, `id_review_detail.html`, `report_block.html`, `blocked_people.html`, `test_inbox.html`, `includes/unverified_warning.html`, `START-HERE.txt`.
Changed: `core/models.py`, `forms.py`, `views.py`, `urls.py`, `permissions.py`, `services.py`, `signals.py`, `consumers.py`, `middleware.py`, `context_processors.py`, `management/commands/seed_demo.py`, `findit/settings.py`, `findit/urls.py`, `static/js/chat.js`, `static/css/app.css`, several templates, `FindIT.cmd`, `README.md`, tests `base.py` and `test_session1.py` (updated for sign-in by email and the Developer rule).

### See it working (after menu 3 "Reset the demo data", then menu 1)

1. **Sign up** a new student with Student ID `2020-0001`, name Cruz, Juan D. (Dela). Open **Updates**: 3 notices. Open **Test inbox**: 3 emails, one with a code.
2. As that new student, open a post by Alex: no warning. Sign in as `alex.finder@example.com` in a private window and open the new student's claim or chat: the **red warning** shows at the bottom, and the new student shows **Not verified**.
3. As the new student, try a chat message over 100 characters, or 11 messages quickly: the reason shows under the chat box.
4. Tap **Verify my email**, type the code from the Test inbox: ✔ Verified. Sign out and sign in with `2020-0001`.
5. Sign up again with `2020-0001` and a different email: refused. Tick *"This is my Student ID…"* → ID review form → send. Sign in as `moderator.demo` → **Staff → Student ID reviews** → decide.
6. Sign in as `casey.unverified@example.com` (unverified demo student): see the yellow strip and the limits.
7. **Report & block:** as Alex, open a claim form or chat → ⛔ Report & block → the chat becomes read-only; `moderator.demo` sees it in **Chat reports** under "Block (no reason given)".
8. **Developer:** run menu 6 → create your account. Sign in with it → Staff → Accounts → edit a staff account → role Administrator. `findit-admin` cannot do that, and `/django-admin/` sends `findit-admin` to its sign-in page.

### Still open

- Real email sending, the school-ID barcode check and two-step sign-in wait for online hosting (v3.0.0, see the roadmap). Until then, email verification shows only that the person can read that mailbox (on a local PC: the Test inbox).
- No human testers yet: phone layouts, camera scanning and two-person live chat still need people to try them (`docs/BUG_REPORTS.md`).
- `FindIT.cmd` was written for Windows but could only be reviewed, not run, in this environment. Please try menu options 1–6 once and report anything odd.

---

# v1.1.0 integration (unchanged below)

## 1. Starting point and sources

| | Repository | Commit used |
| --- | --- | --- |
| **Initial work (basis)** | `jblloydg/findit-campus-lost-and-found` | `615e9cfe835c647208bb8a3088a52955763f9ee6` "Add Find-IT source archive" |
| Session 1 | `jblloydg/1` | `3c4f0c9d22dc7d5c53d1848cf7952da6c12fe5c3` |
| Session 2 | `jblloydg/2` | `adcf286dff659e800419cc1c12b2797a0c735c2d` |
| Session 3 | `jblloydg/3` | `4433a7811dba3803cf08cf9a8d13bec3326e83a9` |
| Session 4 (priority) | `jblloydg/4` | `fd9c77305761ec2c18c7645b09554e8ce62458e7` |

Repos 1–4 and the initial repo were **only read, never changed**. They remain the reference for what each session built.

**How the history is laid out (`git log --graph`):**
1. The initial work's three commits (`8290e4d` → `18654cd` → `615e9cf`).
2. Session 4's commits (unpack, first migration, then one commit per feature), because session 4 has priority.
3. For each of sessions 2, 3 and 1: an `Import session N code …` commit (that session's final code on top of the initial work) merged by an `Integrate session N …` commit, which records every conflict decision in its message.
4. This handoff and the version bump.

---

## 2. What v1.1.0 contains, by session

| Session | Features in v1.1.0 |
| --- | --- |
| **1** | Account management and profiles (contact number, profile photo, change password) · admin dashboard and account editing · **moderator verification** · chat safety reports and general reports (reference numbers, review queue, history, private attachments) · password reset by email · sign-in lockout · friendly error pages · `/health/` · logging · performance indexes and pagination · claimant can view own answers · OPERATIONS.md and backup scheduler scripts |
| **2** | Approximate **time** lost/found (with date rules) · stricter photo file check · only author/admin see "Edit post" · photo preview before upload (rebuilt for multiple photos) |
| **3** | Item-date range filter and "Clear filters" · **possible LOST↔FOUND matches** (author and staff only) · match count message after posting a LOST item |
| **4** | Required category (admin-managed) and 1–20 photos with captcha · ownership question bank · approve/decline with approval order, re-apply once, in-chat question cards, LOST owner verification · share mode · chat panel · guard house (QR turn-in, scan + offline queue, intake, walk-ins, status requests) · duplicate protection · daily backups and restore |

---

## 3. Where sessions disagreed and how it was decided

Rule given for this integration: **session 4 wins when the same thing is named or works differently**; everything else from other sessions is added.

| Topic | Sessions | Decision |
| --- | --- | --- |
| Item category | 1 and 3 each had a fixed list; 4 has an admin-managed list | **Session 4's** list. Session 3's matching and filters use it. |
| Photos | 1 and 2: one optional photo; 4: 1–20 required | **Session 4's** photos. Session 2's preview idea kept. |
| Backups | 1 and 4 each built one | **Session 4's** engine (`backup_now`, `restore_backup`). Session 1's admin Backups page, scheduler scripts and OPERATIONS.md now use it. Session 4 backups now also include session 1's private report attachments. |
| Who can read chats / review reports | 4: all Staff; 1: verified moderators + admins | **Your decision:** verified moderators + admins read others' chats, pause chats and review reports. All Staff (security guards) keep session 4 powers: approve/decline claims, review finder status requests, guard house, view claim answer forms. |
| Chat-report statuses | Starter: Pending/Resolved/Action taken; 1: Submitted/Under Review/Resolved/Dismissed | **Session 1's** (4 never changed reports). Existing reports are converted by migration 0009. |
| Location | 1 added a location field and filter; the paper says avoid exact location | **Dormant.** The column exists for the future campus-map (DOrSU map in segments) but nothing shows, collects or filters it unless `FINDIT_LOCATION_ENABLED=1`. |
| Claim states, questions, share mode | Only session 4 changed these | Session 4 as built. |

Bugs found in other sessions while integrating, and fixed:
- Session 3 calculated possible matches but its post page never displayed them; the "Possible matches" section was added.
- Session 4's merged staff page counted claims once per post (found by session 1's query-count test); now one query.

---

## 4. Files changed (compared with the initial work)

113 files. The main groups:
- **Models, forms, services, views, URLs** (`core/`): all four sessions' features combined.
- **New modules**: `core/matching.py` (3), `core/security.py`, `core/middleware.py` (1), `core/backups.py`, `core/idempotency.py`, `core/captcha_challenges.py` (4).
- **Commands**: `backup_now`, `restore_backup` (4); `seed_demo` merged (demo emails from 1, scenarios from 4, a verified moderator).
- **Templates**: session 1's profile, account, report, moderator, password-reset and error pages; session 3's match section; session 4's question bank, scan, turn-in and claim pages; merged browse, post, chat, staff pages.
- **Static**: merged `app.css`, `app.js`, `chat.js`; `scan.js` and `vendor/jsQR.js` (4).
- **Docs and scripts**: `docs/OPERATIONS.md`, `scripts/` (1); `docs/handoffs/` (all sessions); `HANDOFF.md`, `VERSION`.
- **Tests** (`core/tests/`): sessions 4's suite, session 1's suite (`test_session1.py`), and new `test_session2.py` / `test_session3.py`.

Run `git diff 615e9cf HEAD --stat` for the full list.

---

## 5. Database migrations

Run `python manage.py migrate`; **do not** run `makemigrations`.

| Migration | From | Adds / changes |
| --- | --- | --- |
| 0001 | initial | Starter models |
| 0002–0006 | session 4 | Categories + photos; question bank + claim description; approvals, LOST verification, chat questions, idempotency, priority notices; share mode; guard house + post limit setting |
| 0007 | session 2 | `ItemPost.approximate_time` |
| 0008 | session 1 | `Profile.contact_number`, `Profile.photo` |
| 0009 | session 1 | Report reference numbers, statuses, reviewers, history; `GeneralReport`; `ModeratorVerification` (+ history). Converts existing reports. |
| 0010 | session 1 | Performance indexes |
| 0011 | session 1 | `ItemPost.location` (dormant) |

`makemigrations --check` reports no changes.

---

## 6. Set up and run on Windows

### Easiest: double-click

1. Install **Python 3.12+** from python.org and tick **"Add python.exe to PATH"**.
2. Get the code (Git: `git clone https://github.com/jblloydg/findit-campus-lost-and-found-v1.1.0.git Find-IT`, or GitHub → Code → Download ZIP and extract it).
3. Double-click **`FindIT.cmd`** in the folder. The first run installs everything and creates the demo accounts (a few minutes); later runs start in seconds. The browser opens http://127.0.0.1:8000/ by itself. Close the black window to stop.
4. Optional: double-click **`make_desktop_shortcut.cmd`** once to put a **Find-IT** shortcut on your Desktop.

If Windows shows "Windows protected your PC" for a downloaded file, choose **More info → Run anyway**.

### Manual (PowerShell)

```powershell
git clone https://github.com/jblloydg/findit-campus-lost-and-found-v1.1.0.git Find-IT
cd Find-IT
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py test core            # optional: 142 tests
.\start_findit.ps1
```

Open **http://127.0.0.1:8000/**. To start over: stop the site, delete `db.sqlite3`, `media` and `private_media`, run `migrate` and `seed_demo` again.

### Demo accounts (fictional, local only)

`seed_demo` makes the demo accounts with random passwords for this PC and saves them in `demo-logins.txt` (ignored by Git). FindIT.cmd menu 2 shows them.

Password-reset emails print in the terminal locally (session 1).

---

## 7. Quick checks for the integration

- **Guard vs moderator:** sign in as `security.demo` → Staff → you can scan turn-ins, approve/decline claims, open a claim's answers, but **Chat reports / private chats are blocked**. Sign in as `moderator.demo` → reports and chat review work.
- **Session 3 matches:** as `2026-0002`, create a LOST post in "Water bottles & tumblers" titled "Blue bottle" → a message says matches were found → "Possible matches" on your post.
- **Session 2 time:** create a post with an approximate date and time → shown on the post page and browse card.
- **Session 1 accounts:** profile menu → Edit profile / Change password / Report a problem; `findit-admin` → Admin dashboard, Accounts, Moderators, Backups.
- **Session 4 features:** see `docs/handoffs/session-4.md` section 6.
- **Health:** http://127.0.0.1:8000/health/ → `{"status": "ok"}`.

---

## 8. Unfinished items and notes

- **Location is dormant.** Turning it on (`FINDIT_LOCATION_ENABLED=1`) only re-enables session 1's text field/filter; the planned campus-map segments are not built.
- Session 2's 26 original tests target its single-photo form and were not copied; its approximate-time rules are covered by `test_session2.py`. Session 3 had no tests; `test_session3.py` was written.
- Everything in each session's own "unfinished" list still applies (see `docs/handoffs/`), e.g. camera scanning needs localhost/HTTPS, PostgreSQL untested, password-reset email needs SMTP settings when hosted.
- The final paper changes listed in `docs/handoffs/session-4.md` section 9 still apply, plus: moderator verification (session 1) and the guard/moderator split.
