# Find-IT handoff — Milestone 4 feature set

This file explains what this version adds to the Find-IT starter, how to run it on Windows, how to see each feature working, and what is still open.

All accounts, names and photos in the demo are fictional. The repository contains **no** database file, real student data, real passwords, secret keys, backups, or uploaded photos.

---

## 1. Starting point

| | |
| --- | --- |
| Starter repository | `jblloydg/findit-campus-lost-and-found` (read-only, never changed) |
| Starter commit | **`615e9cfe835c647208bb8a3088a52955763f9ee6`** — "Add Find-IT source archive" (2026-11-11 23:05, UTC+8) |
| Starter history kept | `8290e4d` Initial commit → `18654cd` Update README.md → `615e9cf` Add Find-IT source archive. These three commits are the start of this repository's `main`; nothing was deleted or rewritten. |
| Next two commits | `Unpack Find-IT source from the starter archive` (zip extracted, file contents unchanged, zip removed) and `Add initial core migration generated from starter models` (the starter's own `0001_initial`, unchanged). |

Every feature after that is its own commit, so `git log` shows each change separately.

---

## 2. Features completed

| # | Feature | Paper item it covers |
| --- | --- | --- |
| A | Posts: required category, 1–20 photos, optional title/description, captcha above 10 photos, posts-per-hour limit | Posting rules |
| B | Ownership questions from an admin question bank (3–5 per found post) + required claimant description | 4. Submit a claim with private ownership questions |
| C | Approve / decline claims, approval order, re-apply once, in-chat question cards, LOST-post owner verification, priority badge, duplicate-submit protection | 4. Approve or reject a claim |
| D | Share mode (Copy link), closed-listing pop-up, Messenger-style chat panel | Shared posts, messaging |
| E | Guard house: private turn-in QR, staff Scan page with offline queue, intake record, walk-ins, finder status requests | 4. Receive and record items turned over to the guard house |
| F | Daily backups and command-line restore | Daily backups and restore |
| G | Demo data and 22 automated tests | Verification |
| H | 2.5-second target and uptime — documentation only (section 8) | Performance / uptime |

### Already in the starter (confirmed by testing, unchanged in purpose)

Shared post viewable without signing in (now only after **Copy link**, see D) · sign-in pop-up that returns to the same post/action · staff can create FOUND posts · public comments · private claim answers for the finder and authorized staff · status flow Open for Claim → Claim in Progress → At Guard House ("Turned Over" in the paper) → Returned → Claimed → Closed · on-campus meet-up reminders (not verified) · broad descriptions and no exact location field · `YYYY-NNNN` student ID format check (enrollment is not verified; the year is not range-checked, so `0000-0000` passes).

---

### A. Posts: categories, photos, optional text

- **Category is required** on LOST and FOUND posts. 15 starter categories are created by the migration. Administrators add, rename, reorder and turn off categories at **Staff → Categories** (`/staff/categories/`). Categories are turned off, never deleted, so old posts keep their label.
- **Photos are required: 1 to 20 per post** (JPG, PNG or WebP, 5 MB each; no video). Old single photos from the starter are copied into the new photo table by the migration.
- **Title and description are optional.** Lists show "Lost keys", "Found umbrellas", etc. when there is no title.
- **More than 10 photos → captcha** (django-simple-captcha, runs on your own server). Each captcha randomly uses distorted letters *or* a small math sum. No audio captcha (by request).
- **New posts per account per hour**: default 10, changeable by administrators at **Staff → System settings**.
- Browse search also matches category names, and there is a category filter. The post page shows a swipeable photo gallery.

### B. Ownership questions (question bank)

- Finders **pick** questions instead of typing them. There is a **search box**, and questions for the chosen category are listed first.
- Up to **5** picked questions. If the finder picks fewer than **3** (or none), **default questions** fill the gap:
  1. What is the item's main color? *(choice list)*
  2. What brand or make is it? *(free text)*
  3. Describe a distinctive mark, sticker, scratch or sign of wear on it. *(free text)*
- The migration seeds **41 questions**: 3 defaults, 10 general, 28 tied to categories. Answers are either a **choice list** (color, size, material…, usually with "Not sure") or **free text**.
- The claimant must also write a **description in their own words** (required, no minimum length, max 1,500 characters). So a claim has up to 6 parts.
- **Administrators only** manage the bank at **Staff → Question bank** (`/staff/questions/`): add, edit, set answer type and options, tie to categories, mark default, turn off. At least 3 active default questions must remain.
- Each post stores a **copy** of its questions, so editing the bank never changes what earlier claimants answered. Questions still lock once the first claim arrives.

### C. Approve / decline, approval order, re-apply, chat questions, LOST verification

- **Claim states:** Submitted → **Approved** → Returned → Completed, plus **Declined**, Closed and Expired. *(This follows the app, not the design document's list — see section 9.)*
- **Who decides:** the finder or staff (staff decisions are written to the staff audit log). This also works while the item is at the guard house.
- **Several claims can be approved.** Everyone viewing the post sees "*N claiming · M approved*". Each claimant sees only their own place ("#2 approved"). The finder and staff see the full ordered list and **choose any approved claimant** for "Returned". Other open claims close when one is returned.
- **Decline:** the reason is optional; the claimant sees it. The claim chat becomes **read-only** (history stays). A declined claimant can **re-apply once** from **My Claims → Declined**; a declined re-application cannot apply again.
- **7-day inactivity** now also expires Approved claims (shown as **Expired**; they drop out of the approval order).
- **In-chat question cards:** the finder taps **＋ Questions** in a chat, searches the bank, and sends picks as cards. The other side answers in the card; answered cards turn **green with a white check**. People read and judge answers — **nothing is checked automatically**. Works in FOUND claim chats and LOST chats (max 5 per round).
- **LOST posts (owner verification):** someone who found the item messages the owner and sends question cards. The first card opens a verification record. The finder can **approve only after at least 3 cards are sent and all are answered**, then records Returned, and the owner confirms Claimed. Other finders' chats then close read-only. A declined owner can ask to be verified again **once**.
- **Priority notifications** (approval, decline, answered questions, return recorded, status-request result) show as a **red count on Messages** until that chat is opened.
- **Duplicate protection:** every form carries a one-time key (a repeat with the same key is ignored with a notice); submit buttons disable after one click; chat messages carry an id so a resend is saved once; identical notifications within 60 seconds are merged; services also refuse repeated state changes.

### D. Share mode, closed pop-up, chat panel

- A post is visible **only to signed-in users** until someone signed in presses **Copy link**. From then on anyone with the link can view it without signing in, **permanently** (until the post is permanently deleted). Signed-out visitors of an unshared link are sent to sign in and then back to the post.
- The post shows **"Shared by author"** and **"Shared by N people"**.
- **Closed / claimed posts stay viewable** with a red banner and a pop-up saying the item is no longer active; photos and details remain.
- **Chat panel:** claimants (FOUND) and finders (LOST) get a 💬 Chat button on the post page that opens/hides a Messenger-style panel at any time (it remembers open/closed). It is read-only once the claim is declined, expired or closed.
- Every action (claim, comment, message, share) still requires sign-in on the server.

### E. Guard house

- **Private turn-in QR:** every FOUND post automatically gets an 8-character code and QR (shown only to the finder and staff; it is drawn inside the page, so it still shows if the page is already open when the internet drops; the button is greyed out if the QR could not be loaded). A finder on a LOST post gets one when they tap **Bring it to the guard house** in the chat. The QR can be downloaded as an image.
- **Finder:** taps **I'm bringing it to the guard house** → staff are notified; the status does **not** change yet.
- **Staff confirm receipt** (only staff change the status) by:
  1. **Scan page** (`/staff/scan/`, button on the staff workspace) — camera reads the QR → one-tap **Confirm turned in** screen;
  2. typing the code on the Scan page;
  3. **Confirm received at guard house** on the post page.
  Unknown codes show **"Not in the database"**.
- **The QR is a plain link anyone can open.** Non-staff (even signed out) see only a basic info page: the code, the item type/category, a link to the post (normal sign-in/share rules apply) and "bring it to the main-campus guard house". No finder name or photos. Signed-in staff/admin additionally get the Confirm prompt; the server re-checks the role on every confirm.
- **Offline queue:** if the Scan page loses internet, scans are saved in that browser and listed under **Queued scans**. When back online, staff open and confirm each one by hand; the server checks each code again. Nothing is confirmed automatically.
- **Intake record:** who received it, when, how (QR / code / manual / walk-in) and who handed it over (the finder's account or a typed name). No storage location (main campus only, by request). No condition notes (by request).
- **Claims and chats stay open** at the guard house. The finder and staff can still approve/decline; **staff release** the item to an approved claimant. Chats stay open for the admin's **guard-house grace days**; when that ends the listing closes and chats become read-only. Blank = open until claimed or closed.
- **Finder status requests:** while the item is at the guard house the finder cannot close/remove it. They send a request (close the listing, or take the item back) with a **required reason** and **optional photo**; staff approve or reject it with an optional note.
- **Walk-in items:** staff record an item handed in directly (`/staff/walk-in/`); it is posted as FOUND and already At Guard House.
- **Staff workspace** lists items on the way, items held, and pending status requests.

### F. Backups and restore

- `python manage.py backup_now` makes a backup now; `python manage.py backup_now --list` lists them.
- While `start_findit.ps1` is running, the timer runner makes **one backup a day** automatically.
- Each backup is a folder in `backups\` (ignored by Git — it contains private data) with `data.json` (all rows, Django's portable format, works on SQLite and PostgreSQL), `media.zip` (photos) and `manifest.json`.
- Backups older than **14 days** are deleted (the newest is always kept). Folder and days can be changed with `FINDIT_BACKUP_DIR` / `FINDIT_BACKUP_KEEP_DAYS`.
- **Restore (command line only, stop the website first):** `python manage.py restore_backup NAME` → type `RESTORE` to confirm. It first saves a safety backup of the current state, then replaces the database and photos.
- **Staff → Reports** (administrators) shows whether the last backup succeeded and the latest backups.

---

## 3. Files changed

**New**
- `core/backups.py`, `core/captcha_challenges.py`, `core/idempotency.py`
- `core/management/commands/backup_now.py`, `core/management/commands/restore_backup.py`
- `core/migrations/0001_initial.py` … `0006_guard_house.py` (see section 4)
- `core/tests/` (`base.py`, `test_posts_and_questions.py`, `test_claims.py`, `test_share_guardhouse_backups.py`)
- `static/js/scan.js`, `static/vendor/jsQR.js` (QR reader, Apache-2.0), `static/vendor/README.md`
- `templates/core/`: `_claim_row.html`, `admin_categories.html`, `admin_category_edit.html`, `admin_questions.html`, `admin_question_edit.html`, `staff_scan.html`, `turn_in_confirm.html`, `turn_in_public.html`
- `HANDOFF.md`

**Changed**
- `core/`: `admin.py`, `consumers.py`, `context_processors.py`, `forms.py`, `models.py`, `services.py`, `signals.py`, `urls.py`, `views.py`, `management/commands/process_due.py`, `management/commands/seed_demo.py`
- `findit/settings.py`, `findit/urls.py`, `requirements.txt`, `.gitignore`, `.env.example`, `README.md`
- `static/css/app.css`, `static/js/app.js`, `static/js/chat.js`
- `templates/core/`: `admin_reports.html`, `admin_settings.html`, `base.html`, `chat_room.html`, `claim_review.html`, `home.html`, `messages.html`, `my_claims.html`, `my_posts.html`, `notifications.html`, `post_detail.html`, `post_form.html`, `staff_dashboard.html`

**Removed**: `Find-IT-local-app.zip` (its contents are now normal files).

**New packages** in `requirements.txt`: `segno` (QR codes, offline) and `django-simple-captcha` (captcha). Both install with `pip install -r requirements.txt`.

---

## 4. Database changes and migrations

All migrations are included in `core/migrations/`. Run `python manage.py migrate`; **do not** run `makemigrations`.

| Migration | Adds / changes |
| --- | --- |
| `0001_initial` | The starter's models, unchanged. |
| `0002_categories_and_multiple_photos` | New **Category** (name, is_active, sort_order). New **PostPhoto** (post, image, order). ItemPost: **category** (FK), **title** and **description** now optional, old **photo** field removed after copying it into PostPhoto. Seeds 15 categories. |
| `0003_question_bank_and_claim_description` | New **QuestionTemplate** (text, answer_type, choices, categories, is_general, is_default, is_active, sort_order). VerificationQuestion: **template**, **answer_type**, **choices** (copy of the bank question). ClaimApplication: **description**. Seeds 41 questions. |
| `0004_approvals_lost_reports_chat_questions` | ClaimApplication: statuses **APPROVED**, **DECLINED**; **finder** (LOST verifications), **approved_at/by**, **declined_at/by**, **decline_reason**, **reapply_of**. New **ChatQuestion** (question cards). ChatMessage: **client_id** (resend-safe). InAppNotification: **is_priority**. New **IdempotencyKey**. |
| `0005_share_mode` | ItemPost: **is_shared**, **shared_at**. New **PostShare** (post, user). |
| `0006_guard_house` | SystemSettings: **posts_per_hour**. New **TurnInTicket** (code, post, finder, claim, requested_at, received_at), **GuardhouseIntake** (received_by/at, handed_over_by user or name, method), **StatusChangeRequest** (requested_status, reason, optional photo, decision, reviewer, note). Creates a ticket for every existing FOUND post. |

The captcha package adds its own small table (`captcha_captchastore`) through its migration.

---

## 5. Set up and run on Windows PowerShell

You need **Python 3.12 or later** and **Git**.

```powershell
# 1. Get the code
git clone https://github.com/jblloydg/4.git Find-IT
cd Find-IT

# 2. Create and turn on a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
#    If PowerShell blocks this, run once:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 3. Install packages
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Create the database and fictional demo data (no makemigrations)
python manage.py migrate
python manage.py seed_demo

# 5. Optional: check everything
python manage.py test core
python manage.py makemigrations --check --dry-run   # should say "No changes detected"

# 6. Start the website (also starts the timer runner: expiry, grace days, daily backup)
.\start_findit.ps1
#    or: powershell -ExecutionPolicy Bypass -File .\start_findit.ps1
```

Open **http://127.0.0.1:8000/**. Stop with **Ctrl+C**.

**Starting over:** stop the site, delete `db.sqlite3` and the `media` folder, then run step 4 again.

**Already have an older local copy?** If you previously ran the starter and generated your own `0001_initial`, delete your old `db.sqlite3` (and your own generated migration file if it differs) before `migrate`, because this repository now ships its own migrations.

**Phones on campus Wi-Fi (optional):** find the laptop's address with `ipconfig` (e.g. `192.168.1.20`), then before starting:

```powershell
$env:DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost,192.168.1.20"
$env:FINDIT_SITE_URL = "http://192.168.1.20:8000"
python manage.py runserver 0.0.0.0:8000
```

`FINDIT_SITE_URL` makes the QR codes point to an address phones can reach.

### Demo accounts (fictional, local only)

| Role | Sign-in | Password |
| --- | --- | --- |
| Finder (student) | 2026-0001 | DemoFindIt!2026 |
| Claimant, approved #1 (student) | 2026-0002 | DemoFindIt!2026 |
| Claimant, submitted (student) | 2026-0003 | DemoFindIt!2026 |
| Claimant, declined (student) | 2026-0004 | DemoFindIt!2026 |
| Guard-house staff | security.demo | DemoStaff!2026 |
| Administrator | findit-admin | DemoAdmin!2026 |

---

## 6. See each feature working

Use a normal window for one account and a private/incognito window for another.

**A. Posts** — sign in as `2026-0002` → **Create a post** → leave title empty, choose a category, add 1 photo → publish; the card shows "Lost …". Try 11+ photos → the captcha appears; 21 photos → error. Browse → category filter.

**B. Questions** — as `2026-0001`, create a FOUND post, type "keys" in the question search, pick 1 question → publish → the post has 3 questions (2 defaults added). As `findit-admin` → **Staff → Question bank** → add a list question; try to un-default a default → blocked.

**C. Approve / decline** — as `2026-0001`, open **Blue insulated bottle**: 3 claims, #1 approved, one declined with a reason. Approve `2026-0003` → it becomes #2. As `2026-0003` the post says "#2 approved"; signed-out views show only counts. As `2026-0004` → **My Claims → Declined** → reason shown → **Re-apply (1 left)**. As `2026-0001` → **Mark returned** on an approved claim → as that claimant **Confirm I received it**.

**C. LOST verification** — as `2026-0001` → **Messages** → the **Black folding umbrella** chat: 3 green answered cards → **Approve** is enabled. Send more with **＋ Questions**. As `2026-0002`, answer cards; see the red count on **Messages**.

**D. Share** — as any student, open a post that isn't shared, copy its address, open it in a signed-out window → sign-in page. Back in the signed-in window press **Copy link** → the signed-out window now shows the post with "Shared by N people". Close a post → it still opens with the closed pop-up. As a claimant, use the 💬 **Chat** button on the post page.

**E. Guard house** — as `2026-0001`, open a FOUND post you own (e.g. create one) → **Show turn-in QR** → **I'm bringing it to the guard house**. As `security.demo` → **Staff → Scan turn-in QR** → **Start camera** and show the QR (laptop webcam), or type the code → **Confirm turned in**. The post is now At Guard House; claims and chats stay open. As `2026-0001` → **Request a status change** (reason required). As staff, approve/reject it on the post or staff workspace; **Release at guard house** on an approved claim. **Walk-in item** on the staff workspace. Open `/staff/turn-in/ANYCODE/` → "Not in the database". Open a real code's link signed out → info page only.
*Offline queue:* on the Scan page, open the browser DevTools → Network → **Offline**, type a code → it is queued; switch back online → **Open & confirm**.

**F. Backups** — `python manage.py backup_now`, then `python manage.py backup_now --list`. Stop the site, delete a post via the app first if you like, then `python manage.py restore_backup <name>` → type `RESTORE` → the data is back. **Staff → Reports** shows the last backup.

---

## 7. Unfinished items and setup notes

- **Camera scanning** on the Scan page only works on `localhost` or an **HTTPS** site (browser rule), best in Chrome/Edge. On a phone over campus Wi-Fi (`http://192.168…`) use the phone's normal camera app (the QR is a plain link that opens the confirm screen) or type the code. Real HTTPS comes with hosting.
- **No audio captcha** (left out by request; it would need the Flite program).
- **PostgreSQL** is supported through `DATABASE_URL` and the backups use a portable format, but this version was tested on **SQLite** only.
- **Live updates** of question cards and chat use the in-memory channel layer (one process). For hosting, use Redis (`REDIS_URL`, `requirements-production.txt`).
- The **daily backup** and timers only run while `start_findit.ps1` (or `python manage.py process_due --loop`) is running. A hosted site needs a scheduler for `process_due`.
- **Backups are not encrypted** and contain private claim answers and chats. Keep the `backups` folder private.
- **Student enrollment** is still not verified (format check only).
- **Similarity search** for questions is planned for later (not included, by request).
- **Figma:** the Starter plan allows only 3 pages, so the new screens are in a section named **"New Features (Nov 2026)"** below the existing screens on **"01 — Screens & Overview"** (N1 Create post, N2 Post detail, N3 Chat question cards, N4 Scan + offline queue, N5 Turn-in link staff/public + status request, N6 Question bank, plus local button/chip/header components). Existing frames were not changed.

---

## 8. 2.5-second target and uptime (documentation only)

These cannot be proven by a local demo; they need the hosted system.

- **2.5-second page target:** after hosting, measure the main pages (browse/search, post page, claim form, chat) with a tool such as Lighthouse or WebPageTest from a campus network and a mobile connection, with realistic data (hundreds of posts, 20-photo posts). Record the median and slowest (95th percentile) load times. Likely improvements if slow: resize/compress photos on upload, serve static and media files through the host or a CDN, add database indexes on status/category/created_at, and use Redis.
- **Reliable uptime:** agree on a target with the team and adviser (for example 99% during school hours), add an uptime monitor that checks the site every few minutes and alerts the team, and keep the daily backups plus a tested restore. Report measured uptime over at least a month.

---

## 9. Changes the final paper needs (the app was built this way on purpose)

1. **Claim states** — the paper lists Submitted, Under Review, Accepted, Declined, Withdrawn, Completed. The app uses **Submitted, Approved, Declined, Returned, Completed, Closed, Expired** (no separate "Under Review"; "Withdrawn" is the claimant closing their own claim, shown as Closed).
2. **Approve / reject** — done by the **finder or staff**, never automatically by the system (the Milestone 4 diagram suggests the system decides; Milestone 3 says moderators). Several claims can be approved, with a visible approval order.
3. **Ownership questions** — not "exactly five finder-typed questions": **3–5 questions picked from an admin-managed bank** (defaults fill to 3) **plus a required claimant description**.
4. **LOST posts** — finders verify the owner through in-chat question cards (at least 3 answered) before approving.
5. **Share mode** — posts are public only after someone signed in presses Copy link; then permanently.
6. **Posts** — category and at least one photo are required; title/description optional; up to 20 photos with a captcha above 10.
7. **Guard house** — status changes only when staff confirm receipt (QR, code or manual); claims stay open there; the finder uses status requests; walk-ins; the paper's "Turned Over" is shown as "At Guard House".
8. **Backups** — daily automatic backups (14 days kept) with command-line restore.
