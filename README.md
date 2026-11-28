# Find-IT v1.1.2

Campus lost-and-found web app for Davao Oriental State University.

The local demo uses fictional accounts and a local SQLite database. It does not verify real campus enrollment. Do not add real student information to the demo.

## What is included

- Share mode: a post becomes viewable without signing in only after someone signed in presses **Copy link**. Posting, claims, comments, messages and sharing always require sign-in.
- Lost and found posts with a required, admin-managed category and 1-20 photos (title and description optional). Posts above 10 photos need a randomized captcha; new posts per hour are limited (admin setting).
- Ownership questions picked from an admin-managed question bank (3-5 per found post; defaults fill the minimum) plus a required claimant description. Answers are visible only to the finder and authorized staff.
- Approve / decline claims with an approval order, optional decline reason, one re-application, and in-chat question cards (also used to verify owners on LOST posts).
- Guard house: private turn-in QR per found post, staff Scan page with an offline queue, intake records, walk-in items, and finder status requests.
- Live in-app chat using WebSockets (also as a show/hide panel on the post page), messages retained alongside their post.
- Duplicate-submit protection on every form, daily backups with command-line restore, and an automated test suite.
- Student, staff, and administrator workflows, status history, notifications, staff chat review, and administrator reports.
- Responsive pages styled to match the navy and teal Padlet wireframes.
- **New in 1.1.1:** optional email verification (✔ Verified badge, Test inbox for local testing), sign-in with email, Student ID rules with ID reviews, lower limits and a warning for unverified students, and Report & block. See **HANDOFF.md → Changes in 1.1.1**.
- **New in 1.1.2 (bug fixes and security):** the start window no longer reopens the browser every 20 seconds; the design shows on every Windows PC; notifications only open Find-IT's own pages; the post page category link works; demo passwords are made fresh on each PC and are never published. See **docs/CHANGES_v1.1.2.md**.

Version 1.1.0 combines four development sessions; see **HANDOFF.md** for what came from each, the decisions taken where they differed, setup steps and quick checks.

## Run locally on Windows

**Read `START-HERE.txt`.** In short:

1. Download the ZIP from GitHub and extract it to a simple folder such as `C:\FindIT`.
2. Double-click **`FindIT.cmd`**. The first time it installs everything by itself (it can even install Python for you).
3. Press **1** (or wait 20 seconds). Your browser opens http://127.0.0.1:8000/. Keep the black window open; close it to stop.

The menu also shows the demo sign-ins for your PC (2), resets the demo data (3), runs the automatic checks (4) and makes a backup (5). The 20-second automatic start happens only the first time the menu shows. Run `make_desktop_shortcut.cmd` once for a Desktop icon.

**Opened it twice?** The second window says Find-IT is already running and opens your browser once. Close that extra window (or press 0); keep the first one open.

## Get the latest version with Git Bash

One time only: download a copy that can update itself, and make a one-word shortcut.

~~~bash
cd ~
git clone https://github.com/jblloydg/findit-campus-lost-and-found-v1.1.0.git
echo "alias findit='cd ~/findit-campus-lost-and-found-v1.1.0 && git pull --ff-only && start FindIT.cmd'" >> ~/.bashrc
source ~/.bashrc
~~~

Every time after that, open Git Bash and type **`findit`**. It downloads the newest released version (`main`) and opens the Find-IT window. Your database, photos, backups and demo sign-ins are never touched by an update (Git ignores them).

- If `git pull` says it cannot fast-forward, a file in that folder was edited by hand: run `git stash`, then `findit` again.
- If `start` does not work in your Git Bash, use `cmd.exe //c start "" FindIT.cmd` in the alias instead.
- To try a version before it is released, switch branch once: `git checkout release/1.1.2` (back with `git checkout main`).

<details><summary>Manual steps for developers (PowerShell)</summary>

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate             # migrations are in the repo; do not run makemigrations
python manage.py seed_demo           # fictional demo data, local only
.\start_findit.ps1                   # website + timer runner; stop with Ctrl+C
~~~
</details>

## Fictional demo accounts

The demo data makes these fictional accounts **for local testing only** (never on an online site).
Their passwords are made at random on each PC the first time the demo data is created and are
never stored in this repository: **open FindIT.cmd → menu 2** to see the passwords for your PC
(they are also in `demo-logins.txt` in the Find-IT folder, which Git ignores).

| Role | Sign-in | Password |
| --- | --- | --- |
| Student / finder (verified) | alex.finder@example.com or 2026-0001 | menu 2 |
| Student / claimant (verified) | jamie.claimant@example.com or 2026-0002 | menu 2 |
| Student / second claimant (verified) | sam.second@example.com or 2026-0003 | menu 2 |
| Student / declined claimant (verified) | riley.third@example.com or 2026-0004 | menu 2 |
| Student, **not verified** (shows the limits and warning) | casey.unverified@example.com | menu 2 |
| Staff (security guard) | security.demo | menu 2 |
| Staff (verified moderator) | moderator.demo | menu 2 |
| Administrator | findit-admin | menu 2 |

Students sign in with their email; a student whose Student ID is ✔ Verified can also type the Student ID.

## Main routes

- **/** — landing and sign-in
- **/home/** — signed-in search and browse
- **/p/<post-id>/** — direct post link
- **/posts/new/** — create a lost or found post
- **/my-posts/** and **/my-claims/** — personal listing and claim history
- **/staff/** — staff review and moderation workspace
- **/staff/scan/** — guard-house QR scanner; **/staff/walk-in/** — record a walk-in item
- **/staff/categories/** and **/staff/questions/** — administrator-managed categories and question bank
- **/verify-email/** — verify your email (optional); **/test-inbox/** — local test emails (this PC only)
- **/profile/student-id/**, **/id-review/new/**, **/profile/blocked/** — Student ID, ID review request, blocked people
- **/staff/id-reviews/** — Student ID reviews (verified moderators and administrators)
- **/django-admin/** — Django model administration, **Developer only**

## Status and privacy behavior

- A new found post is **Open for Claim**. The first claim changes it to **Claim in Progress**.
- Claims are **Submitted**, then **Approved** or **Declined** by the finder or staff. Several claims can be approved; the finder records **Returned** to any approved claimant, who confirms receipt (**Claimed**). Claims with seven days of inactivity expire (three days for unverified students).
- The finder says they are bringing an item to the guard house; it becomes **At Guard House** only when staff confirm receipt (QR scan, typed code, or the post page). Claims and chats stay open for the administrator's guard-house grace days; while the item is there the finder sends status requests instead of changing the status.
- An author, staff member, or administrator can close or remove a listing. Removal hides it from active browse but preserves chat and claim history.
- Administrators can set an optional guard-house grace period and optional archive auto-delete period. Blank settings mean disabled. Permanent deletion removes the post, photo, claims, and chats together. Posts connected to a pending safety report are retained until the report is resolved.
- Authorized staff can read any chat for safety review, pause it, and send a report to an administrator. Administrators decide account restrictions. Staff reviews and moderation actions are recorded.
- The local demo channel layer is in-memory and intended for one development process. Set **REDIS_URL** and install **requirements-production.txt** when preparing a multi-process hosted deployment.

## Deployment preparation

The project can use PostgreSQL through **DATABASE_URL** and Redis through **REDIS_URL**; see **.env.example**. Before hosting, set a private **DJANGO_SECRET_KEY**, **DJANGO_DEBUG=0**, correct allowed hosts and CSRF origins, configure durable media storage, run database migrations, and provide an external scheduler for **python manage.py process_due**. Never deploy with demo accounts.

No hosting provider has been selected. v1.1.1 verifies email ownership only (emails are printed locally); real email sending and school-ID barcode checks are planned for v3.0.0. Confirm campus data-retention, account-verification, and moderation policies before using real student accounts.

## Design references

The Figma file remains the editable visual source. The repository includes the original diagrams and wireframe preview under **docs/reference/**.

- [Wireframe preview](docs/reference/wireframes.png)
- [System architecture](docs/reference/architecture.png)
- [Entity relationship diagram](docs/reference/erd.png)
- [Padlet 5 system-design document](docs/reference/system-design.docx)

All database migrations are kept in source control (core/migrations). Installs and hosted releases run **python manage.py migrate**; never regenerate migrations on a server.

## License

This project is released under The Unlicense. See [LICENSE](LICENSE) for the full text.
