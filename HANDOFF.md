# Find-IT v1.1.0 — integration handoff

> **Continuing the work?** Read `CLAUDE.md` (rules and decisions), `docs/ROADMAP.md` (V2 status and what's next) and `docs/BUG_REPORTS.md` (how to report). Next version work happens on branch `release/1.1.1`; tag `v1.1.0` is the rollback point. A paste-ready prompt for a new Claude session is in `docs/TRANSFER_PROMPT.md`.

Version **1.1.0** combines the work of four separate development sessions on top of the original Find-IT starter. Each session's own handoff is kept unchanged in `docs/handoffs/session-1.md` … `session-4.md`.

All accounts, names and photos in the demo are fictional. The repository contains **no** database file, real student data, real passwords, secret keys, backups, uploads or report attachments.

---

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

| Role | Sign-in | Password |
| --- | --- | --- |
| Student (finder) | 2026-0001 | DemoFindIt!2026 |
| Student (claimant, approved #1) | 2026-0002 | DemoFindIt!2026 |
| Student (claimant, submitted) | 2026-0003 | DemoFindIt!2026 |
| Student (claimant, declined) | 2026-0004 | DemoFindIt!2026 |
| Staff — security guard | security.demo | DemoStaff!2026 |
| Staff — **verified moderator** | moderator.demo | DemoStaff!2026 |
| Administrator | findit-admin | DemoAdmin!2026 |

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
