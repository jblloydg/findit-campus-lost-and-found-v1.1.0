# Find-IT Handoff — Security, claim privacy, backups, performance, and reliability

> Newest work is first. Earlier handoffs are kept below, newest first.
> Operator procedures (backup, restore, scheduling, deployment, monitoring) are in **`Find-IT/docs/OPERATIONS.md`**.

## Assessment before coding

| Requirement | Found | Done |
| --- | --- | --- |
| Password hashing and validators | Implemented: Django PBKDF2 and 4 validators | Verified by tests |
| Password change | Implemented | Verified; other sessions are signed out |
| **Password reset** | **Missing** | Added Django's token-based email reset |
| Passwords in error reports | **Partial**: the custom login, signup, and password views didn't mark fields as sensitive | Added `sensitive_post_parameters` |
| Brute-force protection | **Missing** | Added sign-in throttling |
| Role protection | Implemented, with tests | Added a test suite covering the 6 required scenarios, and friendly 403 pages |
| Claim answers | **Partial**: **the claimant got 403 on their own answers**, and pages had no `no-store` | Fixed both; nothing else in the claim flow changed |
| Backups and restore | **Missing** | Added commands, retention, an admin status page, and scheduler scripts |
| Performance | Never measured; home page capped at 100 with no pagination; several N+1 query patterns | Fixed, indexed, and measured |
| Reliability | **Partial**: DEBUG and secret-key guard existed | Added logging, error pages, `/health/`, transactional requests, and a production settings review |

---

## A. Password and role security

**What changed**

- **Password reset** (`/password-reset/`):
  - Django's token flow, with a link on the login page.
  - The link expires in **1 hour** and works **once**.
  - The page looks the same whether or not the email exists.
  - Inactive accounts get no email.
  - Emails print to the console locally. They are sent by SMTP when `DJANGO_EMAIL_HOST` is set.
- **Sign-in throttling** (`core/security.py`):
  - After **5** failed attempts for the same username from the same IP address, that pair is blocked for **15 minutes** (HTTP 429).
  - The message doesn't reveal whether the account exists.
  - A successful sign-in resets the counter.
  - Both limits can be changed in the environment.
- `sensitive_post_parameters` is now on login, sign-up, change password, and staff-account creation, so passwords are hidden from Django error reports.
- Plain 403 responses now show inside the Find-IT layout with the same message. Expired forms (CSRF) get their own page.

**Test results** (all run, all passing)

| Test | Result |
| --- | --- |
| Passwords are stored as `pbkdf2_sha256$…`, never as plain text, for sign-up, staff, and admin accounts | ✅ |
| Submitted passwords never appear in login, sign-up, or change-password responses | ✅ |
| Password fields are marked sensitive for error reports | ✅ |
| **1.** Student opens Admin URLs (dashboard, accounts, moderators, settings, backups, edit account, Django admin) → 403, or redirect for Django admin | ✅ |
| **2.** Student uses Staff functions (staff workspace, comment moderation, guard-house turnover, close listing, pause chat) → 403, nothing changed | ✅ |
| **3.** Staff, even a verified moderator, uses Admin functions (pages, deactivate, edit, verify moderators, create staff) → 403, nothing changed | ✅ |
| **4.** User modifies another user's account or password (edit-account URL, a tampered `user_id` on the profile and password forms) → refused; only the signed-in user changes | ✅ |
| **5.** User changes their own role (student, staff, and moderator through the profile and account forms; admin self-edit) → role unchanged | ✅ |
| **6.** Signed-out visitor opens 18 protected pages and 2 POST actions → redirected to log in, nothing changed | ✅ |
| Lockout after repeated failures; other IP addresses not affected; success resets the counter | ✅ |
| Password reset: email sent, link sets a new password, link is single-use, unknown email gives the same page, inactive account gets no email, a token cannot be reused for another user | ✅ |

## B. Claim privacy

**Before:** the finder, Staff, and Admin could see answers, but **the claimant could not see their own answers**.

**Now** answers are visible to exactly:

- the **claimant**, read-only, through **My claims → My answers**
- the **finder**, who needs them to verify ownership
- **Staff/Admin**, who handle claims and guard-house pickups; every such view is recorded in the audit log

Claim pages and other private pages send `Cache-Control: no-store`, so shared computers don't cache them. The claim workflow itself is unchanged.

| Test | Result |
| --- | --- |
| 1. Student sees their own answers | ✅ |
| 2. Another student gets 403; answers don't appear on the listing, Browse, My claims, or notifications | ✅ |
| 3. Direct URLs: signed-out → login; random claim ID → 404; closing someone else's claim → 403; a claim ID from a different post → 404 | ✅ |
| 4. Finder sees answers (not audited); Staff sees answers and the view is audited | ✅ |
| 5. Admin sees answers and the view is audited | ✅ |
| Answers never appear in notifications, chat messages, or audit-log text | ✅ |

## C. Backup and restore

`backup_db`, `restore_db`, and `list_backups` commands, plus **Admin → Backups**, a read-only status page. They support SQLite (local) and PostgreSQL (hosting). Full procedure: `docs/OPERATIONS.md`.

**Results.** Each was run for real, in automated tests and by hand.

| Check | SQLite | PostgreSQL 16 |
| --- | --- | --- |
| Backup generated (date-stamped, e.g. `findit-daily-20261127-163318.sqlite3` or `.dump`) | ✅ | ✅ |
| Backup validated: integrity check or `pg_restore --list`, required tables present, SHA-256 checksum | ✅ | ✅ |
| Two backups in the same second → second gets `-2`; nothing overwritten | ✅ (test) | — |
| Restore of a valid backup (posts deleted → restored → count back to the original) | ✅ | ✅ |
| Pre-restore safety copy made automatically | ✅ | ✅ |
| Refused safely, database untouched: random bytes, checksum mismatch, a non-Find-IT database, wrong engine, missing file, truncated dump | ✅ | ✅ (wrong engine, truncated dump) |
| Restore needs a typed `RESTORE`; refuses when not run in a terminal without `--yes` | ✅ | ✅ |
| Failed backup: error exit code, logged, no `.partial` file left | ✅ | — |
| Database password never written to the backup log | — | ✅ |

**Retention** (tested): the defaults are 14 days, always keeping the newest 7. Both are configurable.

- With five backups aged 20–40 days plus a new one and *keep 3 / 14 days*, the three oldest were deleted and the newest three kept.
- A single 100-day-old backup is **never** deleted.
- A damaged backup is **never** deleted automatically.

**Access** (tested):

- Students, Staff, and moderators get 403 on **Admin → Backups**; signed-out visitors are sent to log in.
- No URL serves backup files: `/backups/…`, `/media/…`, and `/static/…` all return 404.
- The backup folder is outside `static/` and `media/` and is ignored by Git.

**Scheduling:**

- `scripts/register_backup_task.ps1` registers a Windows Task Scheduler task that runs every day at 2:00 AM, and also runs at the next start-up if the PC was off.
- `scripts/backup_daily.sh` is the Linux cron equivalent. I ran it and it worked.
- ⚠️ **The daily schedule has not been registered or tested on your Windows PC. It is not active yet.** Section 3 of `docs/OPERATIONS.md` has the three commands to register it and check its first run.

## D. Performance

**Changes made:**

- Home page pagination, 24 per page (before, a fixed cap of 100).
- N+1 queries removed:
  - **My posts** and **staff workspace:** claim counts are now annotated.
  - **My claims:** the conversation is now joined.
  - **Messages:** loads only the newest message per conversation, where before it loaded **every** message and then ran an extra query per row.
  - **Staff workspace reports:** the reporter is now joined.
- 4 new database indexes (migration `0005`): browse order, type and status, unread notifications, and chat message order.

**Query counts per page** (Django test client, large dataset):

| Page | Before | After |
| --- | --- | --- |
| Browse | 5 | 6 (+1 for the page count) |
| My posts | 23 | 5 |
| My claims | 23 | 5 |
| Messages | 36 | 6 |
| Staff workspace | 30 | 9 |

**Measured response times**

Test environment:

- Linux x86_64, 2 vCPU, 7.8 GB RAM
- Python 3.13.18, Django 5.2.19, SQLite 3.53.1
- **Production settings** (`DEBUG=0`, WhiteNoise), Daphne ASGI server over **HTTPS** (self-signed), client on the same machine
- Fictional dataset: **404 users, 3,002 listings, 900 claims (4,500 answers), 600 conversations / 7,200 messages, 6,000 notifications, 300 reports**

Method: 20 sequential requests per operation (10 for login), measuring server time to the full response. The script checked that every session was really signed in and that every claim was really created.

| Operation | Median | 95th % | Max | Meets ≤ 2.5 s? |
| --- | --- | --- | --- | --- |
| Login (POST, includes password hashing) | 181 ms | 227 ms | 227 ms | ✅ |
| Browse all items | 17 ms | 22 ms | 26 ms | ✅ |
| Lost item listing | 16 ms | 21 ms | 21 ms | ✅ |
| Found item listing | 18 ms | 21 ms | 36 ms | ✅ |
| Search + category + location + status filters | 15 ms | 18 ms | 18 ms | ✅ |
| Browse, page 50 (pagination) | 20 ms | 23 ms | 27 ms | ✅ |
| Item details | 15 ms | 18 ms | 19 ms | ✅ |
| Claim submission (POST, 5 answers) | 18 ms | 22 ms | 23 ms | ✅ |
| Claim review (finder) | 11 ms | 14 ms | 15 ms | ✅ |
| My claims | 22 ms | 36 ms | 89 ms | ✅ |
| Messages inbox | 18 ms | 37 ms | 39 ms | ✅ |
| Chat room | 11 ms | 14 ms | 19 ms | ✅ |
| Notifications | 11 ms | 15 ms | 17 ms | ✅ |
| Staff workspace (dashboard) | 54 ms | 62 ms | 68 ms | ✅ |
| Admin dashboard | 18 ms | 25 ms | 31 ms | ✅ |
| Chat safety reports | 15 ms | 19 ms | 22 ms | ✅ |
| Static CSS (WhiteNoise) | 3 ms | 5 ms | 6 ms | ✅ |
| Browse with **10 users at the same time** (100 requests) | 173 ms | 215 ms | 264 ms | ✅ |

> **Honesty note:** the first timing run was **discarded**. Over plain HTTP, the production setting `Secure` cookies (correctly) prevented sign-in, so those numbers only measured redirects. All the numbers above come from the HTTPS rerun, where every request was checked as signed in.
>
> **These are local measurements.** They exclude internet latency and use a different machine than production. Real hosted times depend on the server size, the network distance to the university, and PostgreSQL. Run the same checks again after hosting. Browser rendering time is not included.

## E. Reliability

- **Production configuration review:**
  - `DEBUG` defaults to on only for local use; production sets `DJANGO_DEBUG=0`.
  - The site **refuses to start** in production with the default secret key (tested).
  - All secrets come from environment variables; `.env.example` is updated, and no credentials are in the code.
  - Added HSTS (configurable), an optional trusted-proxy HTTPS header, `X-Frame-Options: DENY`, and HTTP-only session cookies.
  - `check --deploy` with production variables leaves only W005 and W021, which depend on the school domain. See OPERATIONS §4.
- **Error handling:**
  - Friendly pages for 403, 404, 500, 503, and expired forms. They show no tracebacks or technical text (tested).
  - **Every request runs in one database transaction** (`ATOMIC_REQUESTS`). If a database step fails partway, nothing from that request is kept (tested: a report row saved and then a failing history step leaves no report). The user sees a clear "not saved, try again" page.
  - SQLite waits up to 20 s for locks; PostgreSQL connections are health-checked.
- **Logging:** console plus `logs/findit.log`, rotating at 5 MB with 5 old files kept. Errors are logged with tracebacks (tested); request bodies and passwords are never logged.
- **`/health/`** is for uptime monitors. Tested against PostgreSQL:
  - database up → `200 ok`
  - **database stopped** → `503 error`, and pages showed the friendly 503
  - database restarted → back to `200` without restarting Find-IT
- **Monitoring recommendation** (OPERATIONS §6): an external HTTP monitor on `/health/` every 1–5 minutes with alerts, plus the hosting provider's resource and database alerts, the log file, and the backup page.

## F. Files

**Created**

- `core/backup.py`, `core/security.py`, `core/middleware.py`
- `core/management/commands/backup_db.py`, `restore_db.py`, `list_backups.py`
- `core/migrations/0005_performance_indexes.py`
- `scripts/backup_daily.ps1`, `scripts/register_backup_task.ps1`, `scripts/backup_daily.sh`
- `docs/OPERATIONS.md`
- Templates:
  - `templates/403.html`, `404.html`, `500.html`, `503.html`
  - `core/backup_status.html`, `core/csrf_failure.html`
  - `core/password_reset_form.html`, `_done.html`, `_confirm.html`, `_complete.html`
  - `core/email/password_reset_email.txt`, `password_reset_subject.txt`

**Modified**

| File | Change |
| --- | --- |
| `core/views.py` | Login throttling and sensitive parameters; `never_cache` on private pages; claimant access to own answers; home pagination; N+1 fixes; backup status page; health check; CSRF failure view |
| `core/forms.py` | `FindItSetPasswordForm` |
| `core/urls.py` | Password reset, `/health/`, `/staff/admin/backups/` |
| `core/models.py` | Indexes only |
| `core/tests.py` | 39 new tests, **133 in total** |
| `findit/settings.py` | Email from the environment, reset timeout, throttling limits, cache (Redis when set), backup settings, logging, error middleware, `ATOMIC_REQUESTS`, SQLite timeout, PostgreSQL health checks, HSTS and proxy settings, `X-Frame-Options`, CSRF failure view |
| `.env.example`, `.gitignore` | Updated |
| Templates | `claim_review`, `my_claims`, `home`, `login`, `messages`, `my_posts`, `staff_dashboard`, `admin_dashboard` |
| `static/css/app.css` | Additions at the end |

**Database:** only migration **`0005_performance_indexes`** (4 indexes). No tables or columns changed, and existing records are untouched.

**Commands**

```powershell
cd Find-IT
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py test core                      # 133 tests
python manage.py backup_db                      # make a backup now
python manage.py list_backups
python manage.py restore_db FILE --check-only   # validate a backup
powershell -ExecutionPolicy Bypass -File .\scripts\register_backup_task.ps1   # daily schedule
.\start_findit.ps1
```

**See it working:**

1. On the login page, click **Forgot your password?** and enter `alex.finder@example.com`. The reset email (with its link) prints in the terminal running Find-IT.
2. Type a wrong password 5 times. The 6th attempt is blocked for 15 minutes.
3. As `2026-0002`, submit a claim, then open **My claims → My answers**.
4. As `findit-admin`, open **Admin → Backups** after running `backup_db`.
5. Open `http://127.0.0.1:8000/health/`.

## G. Still needs real-world setup

| Item | Needs |
| --- | --- |
| Daily backups actually running | **Register the scheduled task** on the PC or server that runs Find-IT, then confirm `LastTaskResult 0` and a new file in **Admin → Backups** |
| Off-machine backup copies | Set `FINDIT_BACKUP_DIR` to another disk or a synced, access-controlled location |
| Media and attachment backup | `media/` and `private_media/` are files; include them in the server's file backup |
| Password-reset emails to real inboxes | SMTP account or host (`DJANGO_EMAIL_*` variables) |
| HTTPS, domain, HSTS policy | Hosting setup; decide on W005 and W021 with the school's IT office |
| Shared sign-in throttling across several processes | `REDIS_URL` (the local cache is per process) |
| Production performance numbers | Re-measure on the real host with PostgreSQL |
| Uptime percentage | An external monitor on `/health/` for a real period (e.g. 30 days). **No uptime figure is claimed** |
| Windows-specific checks | The PowerShell scripts were written for Windows but **not run on Windows** here; all other testing was on Linux |
| Password-reset email rate limit | Not implemented. Consider one if abuse appears after launch |

---

## Earlier handoff — Admin accounts, moderator verification, and reports (commit 40d085f)

### 1. Features completed

#### Assessment before coding

| Requirement | Before | What was done |
| --- | --- | --- |
| Accounts and roles | Partial: 3 roles, student signup, admin creates staff | Added **Edit account** (name, email, contact, role, active/inactive) for any account, deactivate/activate for any account, account search and filters, and pagination |
| Moderator verification | Missing | New `ModeratorVerification` model plus a history table |
| Chat safety reports | Partial: `AbuseReport`, staff-only, statuses Pending/Action taken/Resolved | **Extended `AbuseReport` in place**, so no duplicate model was created. Existing reports are migrated without losing data |
| General reports | Missing | New `GeneralReport` model with private attachments |
| Status tracking | Partial | Shared statuses, `ReportStatusEvent` history, and a **My reports** page |
| Admin dashboard | Partial: no counts | New **Admin dashboard** with sections A–D, all counted live from the database |

#### 1. User accounts and roles

- There are still only **Student, Staff, and Admin**. No Teacher role was added; teachers use Staff.
- **Accounts page** (`/staff/accounts/`, administrators only)
  - Create staff accounts.
  - Search by name, Student ID, username, or email, and filter by role and by active/inactive. Results are paginated.
  - Each row has **Edit** and **Activate/Deactivate**.
- **Edit account** (`/staff/accounts/<id>/edit/`) lets an administrator change name, email, contact number, **role**, and **status**. Every save is written to the staff audit log. Safety rules:
  - An administrator cannot change their **own** role or status.
  - Django superusers can only be changed in Django administration.
  - At least **one active administrator** must remain.
  - An account can become **Student** only if it has a Student ID.
  - Changing a Staff account to another role **automatically revokes** its moderator authorization.
- Students still cannot pick a role at sign-up, and staff and students get *403 Forbidden* on every admin page and action. All checks happen in the Django views.

#### 2. Staff moderator verification

- **Moderator verification page** (`/staff/moderators/`, administrators only)
  - Lists every Staff account with its current status: **Not requested, Pending, Verified, Rejected, or Revoked**.
  - Status cards at the top double as filters.
  - Actions:
    - **Select for verification** moves Not requested, Rejected, or Revoked to Pending.
    - **Approve** or **Reject** a Pending request.
    - **Revoke** a Verified moderator.
  - Each decision can carry optional remarks.
- Each verification stores the staff account, status, who requested it and when, the administrator who decided and when, and the remarks.
- **Verification history** lists every change, with pagination.
- Only **Verified, active Staff** get moderator permissions. Pending, Rejected, Revoked, and never-requested staff get none.
- The page states that this is an authorization inside Find-IT only. It **does not** claim to verify university employment.

**Permission change you should know about.** Before, *any* Staff account could read anyone's private chat and pause chats. To meet "do not expose private conversations to unauthorized users", these actions are now limited to **administrators and verified moderators**:

- reading other people's chats, including the live WebSocket view
- pausing chats
- reviewing reports

Other Staff work is unchanged: guard-house custody, post actions, comment moderation, and the staff workspace.

#### 3. Chat safety reports

- In any conversation, a participant can click **⚑ Report this conversation**. Authorized reviewers can also file a report.
- The report records:
  - a unique reference, such as `CSR-20261127-4F9A2C`
  - the reporter and the reported user
  - the conversation and, optionally, the specific message
  - the category and description
  - when it was submitted, the assigned reviewer, and the status
- Categories: Harassment or bullying, Threats or intimidation, Scam or suspicious behavior, Inappropriate messages, Spam, Other.
- **Review queue** (`/staff/reports/`, administrators and verified moderators): filter by category, status, and date range, and search by reference, name, or description. Results are paginated.
- **Report detail** shows the reported message highlighted with the messages around it, a link to the full conversation, and the full review history. A reviewer can:
  - mark the report **Under Review**, which assigns it to them
  - **Resolve** or **Dismiss** it
  - add **internal remarks** at any time
- Reviewer, review time, and resolution time are saved.
- **Nothing is automatic.** A report never suspends anyone, and a participant's report doesn't pause the chat. Only an **administrator** can record *suspend* or *restore* account, and only while resolving a report. Moderators cannot suspend accounts, which matches the original rule that staff can't ban.

#### 4. General item and system reports (separate from chat reports)

- Users submit one from **⚑ Report this listing** on a post, or from **Report a problem** in the profile dropdown (`/reports/new/`).
- Each report has its own reference, such as `GRP-…`, plus the reporter, category, optional related listing, description, an optional screenshot or PDF, when it was submitted, and its status.
- Categories: Suspicious or fraudulent listing, Incorrect item information, Duplicate listing, Inappropriate content or image, Suspected scam, Technical or system issue, Other.
- **Attachments are protected.**
  - Only JPG, PNG, WebP, or PDF files up to 5 MB are accepted. The file's real contents are checked, not just its name.
  - Files are saved under a random name in **`private_media/`**, outside the public `media/` folder.
  - Files are served only through a checked view, and only to the reporter, administrators, and verified moderators. Responses use `nosniff`, `no-store`, and a sandboxing Content-Security-Policy.
- **Review queue** (`/staff/general-reports/`) has the same search, filters, and pagination. **Report detail** shows the related listing (author, status, category, location, and a link), the attachment, the review form, and the history.
- Reported listings are **never hidden or deleted automatically**. The reviewer uses the listing's existing actions if needed.

#### 5. Report status and tracking

- Both report types use **Submitted, Under Review, Resolved, and Dismissed**.
- Every change is stored in `ReportStatusEvent`, with the old and new status, who made it, when, and the internal note.
- **My reports** (`/my-reports/`, in the profile dropdown) shows a user's own reports with reference, category, status, and dates. It **never** shows internal remarks or other people's reports.
- Automatic deletion of archived posts now also keeps a post while a general report about it is still open.

#### 6. Admin dashboard (`/staff/admin/`, the **Admin** link in the navigation)

- **A. User accounts:** total, students, staff, admins, active, inactive, plus a link to manage accounts.
- **B. Moderator verification:** pending, verified, rejected, revoked, a waiting list, and recent history.
- **C. Chat safety reports:** total, submitted, under review, resolved, dismissed, and open reports.
- **D. General reports:** the same counts, and open reports.
- Every number is counted from the database on each visit, and each card opens the matching filtered list.
- The existing **Staff workspace** still works. For verified moderators and administrators it now shows open-report counts. Other staff see a notice explaining that moderator authorization is needed.

### 2. Starting version

- Repository `jblloydg/1`, branch `main`, starting commit **`af32f31`** ("Add account management and user profile to Find-IT").

### 3. Files created or modified

All paths are inside `Find-IT/`. Root files (`README.md`, `LICENSE`, `Find-IT-local-app.zip`) are unchanged.

Modified:

| File | Change |
| --- | --- |
| `core/models.py` | Shared `ReportStatus`; extended `AbuseReport`; new `GeneralReport`, `ReportStatusEvent`, `ModeratorVerification`, `ModeratorVerificationEvent`; `StaffAuditLog.action_label` |
| `core/permissions.py` | `is_verified_moderator`, `can_review_reports`, `can_review_private_chats` |
| `core/services.py` | `review_report_status`, `record_report_submission`, `change_moderator_verification`, `revoke_moderator_if_not_staff`; archive purge also respects open general reports |
| `core/forms.py` | Chat `ReportForm` reworked; new `GeneralReportForm`, `ReportReviewForm`, `AdminAccountForm`, `ModeratorDecisionForm`; old `AdminReviewForm` removed (replaced) |
| `core/views.py` | Accounts search, filters, and pagination; `edit_account`; `staff_account_status` now covers any account; `admin_dashboard`; moderator views; chat and general report views; protected attachment view; `my_reports`; chat review and pause limited to reviewers |
| `core/urls.py` | New routes, listed below |
| `core/consumers.py` | Live chat viewing by non-participants limited to administrators and verified moderators |
| `core/validators.py` | `validate_report_attachment` |
| `core/admin.py` | Read-only Django admin views for the new models; reference column for chat reports |
| `core/tests.py` | 39 new tests (94 in total) |
| `findit/settings.py` | `PRIVATE_MEDIA_ROOT` |
| `.gitignore` | Ignores `private_media/` |
| `static/css/app.css` | New styles added at the end |
| `templates/core/base.html` | Admin link opens the dashboard; dropdown gets My reports, Report a problem, and Admin dashboard |
| `templates/core/staff_accounts.html`, `admin_reports.html`, `staff_dashboard.html`, `chat_room.html` | Updated pages |
| `templates/core/post_detail.html` | One added "Report this listing" link |
| `templates/core/profile.html`, `includes/avatar.html` | Safer name display, no behaviour change |

Created:

- `core/migrations/0004_reports_and_moderator_verification.py`
- Templates: `admin_dashboard.html`, `account_edit.html`, `moderator_verifications.html`, `chat_report_form.html`, `chat_report_detail.html`, `general_report_form.html`, `general_reports.html`, `general_report_detail.html`, `my_reports.html`
- Includes: `includes/pagination.html`, `report_filters.html`, `report_status.html`, `report_history.html`, `review_form.html`, `report_count_cards.html`

New URLs:

- `/staff/admin/`
- `/staff/accounts/<id>/edit/`
- `/staff/moderators/` and `/staff/moderators/<id>/decide/`
- `/staff/reports/<uuid>/`, the chat report detail, which replaces the old `…/review/` address
- `/staff/general-reports/` and `/staff/general-reports/<uuid>/`
- `/reports/new/` and `/reports/general/<uuid>/attachment/`
- `/my-reports/`

### 4. Database models and migrations

Migration **`0004_reports_and_moderator_verification`**:

- **`AbuseReport`** (chat safety reports), extended and not replaced:
  - New fields: `reference` (unique), `reported_message`, `assigned_reviewer`, and `reviewed_at`.
  - New statuses and categories.
  - `admin_note` is now labelled *internal remarks*.
  - The data step converts existing rows: Pending → Submitted, Action taken → Resolved, Resolved → Resolved, and the category "False claim or suspected fraud" → *Scam or suspicious behavior*. It also gives every old report a reference number.
  - Tested forwards and backwards on a copy with old-style reports. Nothing was lost.
- **`GeneralReport`**: reference, reporter, category, post (optional; kept as empty if the post is deleted), description, attachment (private storage), status, internal remarks, assigned reviewer, reviewed by and at, resolved at, and created at.
- **`ReportStatusEvent`**: history for either report type. A database constraint makes sure each row belongs to exactly one report.
- **`ModeratorVerification`**: one row per Staff account, holding status, requested by and at, reviewed by, decided at, and remarks.
- **`ModeratorVerificationEvent`**: verification history.

Everything uses standard Django fields and works on SQLite now and PostgreSQL later. Run `python manage.py migrate`.

### 5. Set up and run on Windows PowerShell

```powershell
# 1. Get the newest code
cd findit-repo            # your existing clone
git pull
cd Find-IT
#    (New computer: git clone https://github.com/jblloydg/1.git findit-repo; cd findit-repo\Find-IT)

# 2. Virtual environment (skip creating it if .venv already exists)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Packages
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Database update and demo accounts
python manage.py migrate
python manage.py seed_demo

# 5. Run
.\start_findit.ps1
```

If PowerShell blocks the script: `powershell -ExecutionPolicy Bypass -File .\start_findit.ps1`. Then open **http://127.0.0.1:8000/**.

Run the tests with `python manage.py test core`.

### 6. See the features working

These are the fictional demo logins: student `2026-0001` and `2026-0002` (passwords: FindIT.cmd menu 2), staff `security.demo` (password: FindIT.cmd menu 2), and admin `findit-admin` (password: FindIT.cmd menu 2).

1. **Moderator not yet verified.** Sign in as `security.demo`. The Staff workspace says moderator authorization is required. Opening **/staff/reports/** gives *Forbidden*.
2. **Verify a moderator.** In another browser or a private window, sign in as `findit-admin` and click **Admin** in the navigation.
   - Under **B. Moderator verification**, click **Review verifications**.
   - Click **Select for verification** on *Campus Staff*, then **Approve**, adding a remark.
   - The status and history update, and the dashboard count changes.
   - Refresh the staff window: report links and conversation review now appear.
3. **Chat report.**
   - As `2026-0002`, open the blue bottle listing and message the finder. As `2026-0001`, reply.
   - As `2026-0001`, open the conversation, click **⚑ Report this conversation**, choose a category and the message, describe it, and submit. You get a `CSR-…` reference.
   - **My reports** shows the report as *Submitted*.
4. **Review it.** As the moderator or the admin, open **Chat reports**.
   - Filter by status or category, then click **Review**.
   - Mark it **Under Review**, then **Resolve** it with remarks.
   - The history lists each step. The student's **My reports** shows *Resolved*, but not your remarks.
   - As the admin you can also choose *Suspend the reported account* while resolving.
5. **General report.** As `2026-0002`, open a listing and click **⚑ Report this listing**. Choose *Duplicate item listing*, describe it, attach a PNG screenshot, and submit. The listing stays visible. Then as the moderator open **General reports**, review it, and open the attachment.
6. **Accounts.** As the admin, open **Admin → Manage accounts**.
   - Search for `2026`, filter by role or inactive, and click **Edit** on a staff account.
   - Change the role to Admin, or set it to Inactive.
   - Your own account shows role and status as locked.
7. **Revoke.** On **Moderator verification**, click **Revoke** for Campus Staff. That account loses access to reports and chats right away.

### 7. Remaining limitations

- **Moderator scope.** "Moderator-only functions" are taken to mean reviewing chat and general reports, reading or pausing other people's chats, and opening report attachments. If more functions should be moderator-only, they can be added to `can_review_reports`.
- **No email or in-app notification** is sent when a report status changes or a moderator is approved. Users check **My reports**. The existing notification model is tied to a listing, so it was not reused for this.
- **Unique email** is still enforced by the forms, not the database (see the earlier handoff).
- **Django superusers** have to be edited in Django administration, not on the Find-IT accounts page.
- **Admin reopen.** A Resolved or Dismissed report can be set back to *Under Review* by a reviewer. There is no separate approval step for reopening.
- **Hosting.** `private_media/` must be on durable private storage when hosted, and must **not** be served publicly by the web server.
- **Testing:** done with Python 3.13 and Django 5.2.19 on Linux.
  - `manage.py check` and `makemigrations --check` are clean, and **94 of 94** tests pass.
  - The migration was run forwards and backwards on old-style data.
  - The dashboard, accounts, moderator, report list, report detail, report forms, My reports, and chat pages were checked in a real browser on desktop and phone.
  - It was not run on Windows itself.
- **Nothing private is committed:** no `db.sqlite3`, `media/`, `private_media/`, `.env`, secret keys, or real student data.

---

## Earlier handoff — Account management and user profile (commit af32f31)

### 1. Feature completed

#### Module 1 — Registration, login, and role assignment

- **Student registration** (`/signup/`) asks for first name, last name, Student ID, email address, password, and confirm password.
  - Every field is required and checked.
  - The Student ID must use the existing `YYYY-NNNN` format. This checks the **format only**. It does **not** verify real enrollment, and the page says so.
  - Duplicate Student IDs and duplicate email addresses are refused. The email check ignores letter case.
  - Passwords go through Django's password-strength validators, and both password boxes must match.
  - The **Student** role is assigned in code. Any role, `is_staff`, or `is_superuser` value added to the form is ignored.
  - Clear error messages appear beside each field, and a success message appears after sign-up.
- **Login** (`/login/`)
  - Students sign in with their Student ID. Staff and administrators sign in with their assigned username.
  - Each password box has a **Show/Hide** button, including the sign-in pop-up.
  - A wrong password and a suspended account both show the same safe error, so the page doesn't reveal which accounts exist.
  - Sign-in uses Django's session login, which rotates the session key. A `?next=` page is honoured only if it is on the same site.
  - After sign-in, students go to **Browse** and staff and administrators go to the **Staff workspace**, unless a safe `next` page was requested.
- **Roles.** There are still exactly three roles: Student, Staff, and Administrator. No Teacher role was added.
  - Students register themselves.
  - Staff accounts are created **only** by an administrator.
  - No page lets anyone change a role.
- **Admin account management** (`/staff/accounts/`, administrators only)
  - Create staff accounts with first and last name, username, optional email, and a temporary password with confirmation. The new account always gets the Staff role.
  - See the current staff list.
  - **Activate or Suspend** a staff account. Suspending ends that person's open sessions immediately.
  - See an **All accounts and roles** table, which can be filtered by role.
  - Every creation, suspension, and activation is written to the existing staff audit log.
  - The activate/suspend action works only on Staff accounts. Students, administrators, and the admin's own account are refused.
- **Backend permission checks** are on every new page and action.
  - Signed-out users are sent to log in.
  - Students get *403 Forbidden* on staff and admin pages, and staff get it on admin pages.
  - Activate/suspend accepts POST only.
  - All forms are protected with CSRF.

#### Module 2 — View and edit user profile

- **My profile** (`/profile/`) shows the profile picture (or an initial), full name, Student ID or username, email, contact number, role, registration date, and account status.
- **Edit profile** (`/profile/edit/`)
  - Users can update first name, last name, email, contact number, and profile picture, and can remove the current picture.
  - **Save changes** and **Cancel** buttons are included.
  - Validation:
    - First name and email are required.
    - Duplicate emails are refused.
    - Contact number allows digits, spaces, dashes, and a leading `+`, with 7–15 digits.
    - Pictures must be real JPG, PNG, or WebP images up to **2 MB**. Pillow checks the file contents, not just the name.
  - When a picture is replaced or removed, the old file is deleted.
  - Changes appear immediately on the profile page and in the header.
  - Student ID, username, role, and status appear in a locked box and **cannot** be edited. The edit page has no user ID in its address, so each user can only ever edit their own profile.
- **Change password** (`/profile/password/`) uses Django's own `PasswordChangeForm`.
  - It asks for the current password, the new password, and the new password again.
  - The new password goes through the strength validators.
  - This browser stays signed in, and other devices are signed out.
- **Navigation**
  - A **My profile** link was added to the main navigation.
  - A **profile dropdown** sits at the upper right: avatar and name, then My profile, Edit profile, Change password, Staff accounts (administrators only), and Log out.
  - All new pages reuse the existing Find-IT colours, cards, buttons, and fonts, and work on phone screens.

### 2. Starting version

- Repository: `jblloydg/1`, branch `main`
- Starting commit: **`c54da44`**, "Add item category and location filters to Find-IT". That commit was itself built on the original **`9f0b2ad`**.

### 3. Files changed

All paths are inside `Find-IT/`. Root files (`README.md`, `LICENSE`, `Find-IT-local-app.zip`) are still unchanged.

Changed:

| File | Change |
| --- | --- |
| `core/models.py` | `Profile.contact_number` and `Profile.photo` |
| `core/validators.py` | `validate_profile_photo`: JPG, PNG, or WebP, up to 2 MB |
| `core/forms.py` | Login form messages and toggles; `SignupForm` with email and duplicate checks; `StaffAccountForm` with email and password confirmation; new `ProfileForm`; new `FindItPasswordChangeForm` |
| `core/views.py` | Role-based login redirect and messages; signup messages; `my_profile`, `edit_profile`, `change_password`; `staff_accounts` list and role filter; new `staff_account_status` |
| `core/urls.py` | `/profile/`, `/profile/edit/`, `/profile/password/`, `/staff/accounts/<id>/status/` |
| `core/context_processors.py` | Adds `current_role_label` for the dropdown |
| `core/admin.py` | Django admin user list shows email and Find-IT role, plus a role filter; the profile inline shows contact number and picture |
| `core/management/commands/seed_demo.py` | Demo accounts get first and last names and fictional `@example.com` emails |
| `core/tests.py` | 48 new tests (56 in total) |
| `templates/core/base.html` | My profile link, profile dropdown, password toggle in the sign-in pop-up |
| `templates/core/login.html`, `signup.html`, `staff_accounts.html` | Updated forms and pages |
| `static/css/app.css` | New styles added at the end; also a small fix so the category and location tags from the earlier feature are not stretched |
| `static/js/app.js` | Show/Hide password buttons and dropdown closing, added at the end |

Added:

| File | Purpose |
| --- | --- |
| `core/migrations/0003_profile_contact_photo.py` | Adds the two new Profile fields |
| `templates/core/profile.html` | My profile |
| `templates/core/profile_edit.html` | Edit profile |
| `templates/core/change_password.html` | Change password |
| `templates/core/includes/avatar.html` | Small reusable picture-or-initial block |

Not touched: listings, claims, comments, messaging and chat, notifications, reports, timers, and their templates.

### 4. Database fields and migrations

Migration **`0003_profile_contact_photo`**, table `core_profile`:

| Field | Type | Rules |
| --- | --- | --- |
| `contact_number` | `CharField(max_length=20)` | Optional; blank by default |
| `photo` | `ImageField(upload_to="profile-photos/%Y/%m/")` | Optional; nullable; JPG, PNG, or WebP up to 2 MB |

- Both fields are optional, so **existing user records are kept as they are**.
- Email, first name, last name, registration date (`date_joined`), and status (`is_active`) already exist on Django's built-in user table, so no new columns were needed for them.
- The migration uses only standard Django fields and works on SQLite now and on PostgreSQL later.

### 5. Set up and run on Windows PowerShell

You need Python 3.12 or later and Git.

```powershell
# 1. Get the newest code
git clone https://github.com/jblloydg/1.git findit-repo
cd findit-repo\Find-IT
#    (If you already have the clone: cd into findit-repo, run "git pull", then cd Find-IT)

# 2. Create and activate a virtual environment (skip if .venv already exists)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install packages
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Update the database and create the fictional demo accounts
python manage.py migrate
python manage.py seed_demo

# 5. Start the website and the local timer runner
.\start_findit.ps1
```

If PowerShell blocks a script, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_findit.ps1
```

Open **http://127.0.0.1:8000/** and stop the site with **Ctrl+C**. Uploaded profile pictures are saved in the local `media\` folder, which Git ignores.

To run the automated tests:

```powershell
python manage.py test core
```

### 6. See the feature working

These are the public fictional demo logins from the original README.

| Role | Sign-in name | Password |
| --- | --- | --- |
| Student | 2026-0001 | see FindIT.cmd menu 2 |
| Staff | security.demo | see FindIT.cmd menu 2 |
| Administrator | findit-admin | see FindIT.cmd menu 2 |

1. **Register.** Open **/signup/**. Try the Student ID `20260003` and see the format error. Try `2026-0001` and see the duplicate-ID error. Try the email `alex.finder@example.com` and see the duplicate-email error. Then sign up with `2026-0003`, a new email, and a strong password. You are signed in as a **Student**.
2. **Show/Hide.** On **/login/**, type a password and click **Show**, then **Hide**.
3. **Student login.** Log out, then sign in as `2026-0001`. You land on **Browse**.
4. **Profile dropdown.** Click your name at the upper right. Choose **My profile** to see every account detail.
5. **Edit profile.** Click **Edit profile**. Change your last name, add a contact number such as `0917 123 4567`, and upload a JPG or PNG. Click **Save changes**. The new details and picture appear right away, including in the header. Note that Student ID, role, and status are locked.
6. **Bad inputs.** Edit again with the email `jamie.claimant@example.com`, which is already used. You see an error, and nothing is saved.
7. **Change password.** Open **Change password**. Enter a wrong current password and see the error. Then change it properly and see the success message.
8. **Staff login.** Log out and sign in as `security.demo`. You land on the **Staff workspace**. Visit **/staff/accounts/** and you get *Forbidden*.
9. **Admin.** Sign in as `findit-admin`, then open **Staff → Staff accounts**, or the dropdown's **Staff accounts** link.
   - Create a staff account.
   - Click **Suspend** on *Campus Staff*, then try signing in as `security.demo` in a private window. It is refused.
   - Click **Activate** to restore it.
   - Use the **All roles** filter on the accounts table.

### 7. Unfinished items and setup notes

- **The email rule is enforced by the forms, not the database.** Signup, profile edit, and staff creation all refuse duplicate emails. Django's built-in user table doesn't make email unique, though, and changing that would need a custom user model and a risky migration. Accounts created another way, such as **Django admin** or `createsuperuser`, could still share an email.
- **Existing demo accounts keep their old names.** If you already had a local database, `seed_demo` won't change existing accounts. Alex's name stays as first name "Alex Finder" with no last name, and there is no email. Fix it on **Edit profile**, or delete your local `db.sqlite3` and run the setup steps again.
- **Student accounts are not suspended from the account page.** As before, an administrator restricts a student through a safety report (**Staff → Reports**). The account page suspends and activates Staff accounts only, as the instructions asked.
- **No password reset by email.** No email sending has been configured yet. A student who forgets a password needs an administrator to reset it in Django admin.
- **Student ID is a format check only.** It does not prove enrollment, and no verification is claimed.
- **Profile pictures are stored locally** in `media/`. For online hosting, configure durable media storage as the original README says.
- **Testing:** done with Python 3.13 and Django 5.2.19 on Linux. `manage.py check` found no issues, and **56 of 56** tests passed. The login, sign-up, profile, edit, and staff-accounts pages were also checked in a real browser, on desktop and phone sizes. It was not run on a Windows machine.
- **Nothing private is included.** No `db.sqlite3`, no `media/`, no `.env`, no secret keys, and no real student data. The only passwords are the public fictional demo ones, and the tests use throwaway test passwords.

---

## Earlier handoff — Item category and location filter (commit c54da44)

#### 1. Feature completed

Every lost or found post now has:

- **Category** (required, from a fixed list): ID or card, Phone or electronics, Bag or wallet, Keys, Books or school supplies, Clothing or accessories, Bottle or container, Umbrella, Other.
- **Campus location** (optional, short free text): a broad area where the item was lost or found, such as "Library 2nd floor" or "Canteen".

Where the feature shows up:

- **Create post / Edit post** has a Category dropdown and a Campus location box.
- **Browse page (/home/)** has two new filters: **All categories** and **Any location**. They combine with the existing keyword, type and status filters. The keyword search now also matches the location. A **Clear all filters** link appears whenever a filter is active.
- **Post cards and the post detail page** show a category tag and a 📍 location tag. On the detail page, the category tag links to the browse page filtered to that category.
- **Django admin (/django-admin/)** lists category and location, filters by category, and searches by location.
- **Demo data (seed_demo)** gives the demo bottle the category *Bottle or container* at *Library 2nd floor*, and the demo umbrella the category *Umbrella* at the *Canteen*.

Posts that existed before this change automatically get the category **Other** and a blank location, so no data is lost.

#### 2. Starting version

- Repository: `jblloydg/1`, branch `main`
- Starting commit: **`9f0b2ad`**, "Initial commit: FindIT campus lost and found system"
- Source: the app inside `Find-IT-local-app.zip` from that commit

#### 3. Files changed

The original files at the repository root (`README.md`, `LICENSE`, `Find-IT-local-app.zip`) are **unchanged**. The full working project, with the new feature, is now unpacked in the new **`Find-IT/`** folder. Everything in that folder is the same as the zip except the files below.

Changed:

| File | Change |
| --- | --- |
| `Find-IT/core/models.py` | Added the `ItemPost.Category` choices and the `category` and `location` fields |
| `Find-IT/core/forms.py` | Added `category` and `location` to the post form |
| `Find-IT/core/views.py` | Added the category and location filters to the `home` view; keyword search also matches location |
| `Find-IT/core/admin.py` | Category and location in the admin list, filter and search |
| `Find-IT/core/management/commands/seed_demo.py` | Demo posts get a category and location |
| `Find-IT/templates/core/home.html` | New filter controls, Clear-filters link, tags on cards |
| `Find-IT/templates/core/post_form.html` | Category and location inputs |
| `Find-IT/templates/core/post_detail.html` | Category and location tags |
| `Find-IT/static/css/app.css` | Styles for the tags and filter row, added at the end of the file |

Added:

| File | Purpose |
| --- | --- |
| `Find-IT/core/migrations/__init__.py` | Migrations package |
| `Find-IT/core/migrations/0001_initial.py` | Baseline migration of the original Find-IT models, unchanged from commit 9f0b2ad |
| `Find-IT/core/migrations/0002_item_category_location.py` | Adds the two new fields |
| `Find-IT/core/tests.py` | 8 automated tests for this feature |
| `HANDOFF.md` | This file |

#### 4. Database fields and migrations

Table `core_itempost`:

| Field | Type | Rules |
| --- | --- | --- |
| `category` | `CharField(max_length=16)`, indexed | Required; one of the choices above; default `OTHER` |
| `location` | `CharField(max_length=120)` | Optional; blank by default |

- `0001_initial.py` was not in the zip. The original README asked you to generate it with `makemigrations`. It is now included and committed, as the README recommended, so you no longer need to run `makemigrations`. If you do run it, it should say "No changes detected".
- `0002_item_category_location.py` adds only the two columns above. It uses only standard Django fields, so it works on SQLite now and on PostgreSQL later without changes.

#### 5. Set up and run on Windows PowerShell

You need Python 3.12 or later and Git.

```powershell
# 1. Get the code (or run "git pull" inside an existing clone)
git clone https://github.com/jblloydg/1.git findit-repo
cd findit-repo\Find-IT

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install packages
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Create the local database and the fictional demo accounts
python manage.py migrate
python manage.py seed_demo

# 5. Start the website and the local timer runner
.\start_findit.ps1
```

If PowerShell blocks a script, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_findit.ps1
```

Open **http://127.0.0.1:8000/** and stop the site with **Ctrl+C**.

To run the automated tests (optional):

```powershell
python manage.py test core
```

#### 6. See the feature working

1. Sign in with the fictional demo account **2026-0001** (password: FindIT.cmd menu 2).
2. On **Browse items**, each card now has a teal category tag and a 📍 location tag. The bottle shows *Bottle or container* and *Library 2nd floor*. The umbrella shows *Umbrella* and *Canteen*.
3. In the **All categories** dropdown, choose **Umbrella** and click **Search**. Only the umbrella remains.
4. Click **Clear all filters**. Type `library` in the **Any location** box and click **Search**. Only the bottle remains.
5. Type `canteen` in the main search box with no other filters and click **Search**. The umbrella appears, because the keyword search now also checks location.
6. Click **＋ Create post**. Choose **Lost**, then category **Phone or electronics**, and enter a title, a description and the location `Gym`. Publish it. The detail page shows both tags.
7. On that detail page, click the category tag. You are taken back to the browse page filtered to *Phone or electronics*.

#### 7. Unfinished items and setup notes

- **The category list is fixed in code** (`ItemPost.Category` in `core/models.py`). Administrators cannot add categories from the website yet. Adding one means editing that list and creating a new migration.
- **Location is free text**, not a list of Davao Oriental State University buildings. People may spell the same place differently, for example "Lib" and "Library". A fixed list of campus areas could be added later once the building names are confirmed.
- **The project now exists in two places.** `Find-IT-local-app.zip` still holds the original version, because existing files were not to be changed. The `Find-IT/` folder is the current, working version. Use the folder.
- **If you already ran the old version locally:** you can keep your existing `db.sqlite3` by copying it into the new `Find-IT/` folder and running `python manage.py migrate`. That applies only `0002` and keeps your data. Do not copy your old self-generated `core/migrations` folder over the committed one.
- **Testing:** this was tested with Python 3.13 and Django 5.2.19 on Linux (8 automated tests plus page checks). It was not run on a Windows machine. The PowerShell steps are the same ones as the original README, minus `makemigrations`.
- **Nothing private is included.** No `db.sqlite3`, no uploaded media, no `.env`, no secret keys, and no real student data. The only passwords mentioned are the public fictional demo passwords from the original README. `Find-IT/.gitignore` keeps `db.sqlite3`, `.env` and `media/` out of Git.
