# Find-IT v1.1.0

Campus lost-and-found web app for Davao Oriental State University. This project follows the Padlet 5 design and the editable [Find-IT Figma file](https://www.figma.com/design/HlBvwAA17U86RADmkm56Fk/Find-IT-Padlet-5-System-Design).

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

Version 1.1.0 combines four development sessions; see **HANDOFF.md** for what came from each, the decisions taken where they differed, setup steps and quick checks.

## Run locally on Windows

1. Install Python 3.12 or later.
2. Open this folder in VS Code, then open a PowerShell terminal in the project folder.
3. Create and activate a virtual environment:

   ~~~powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ~~~

4. Install the project packages:

   ~~~powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ~~~

5. Create the local database tables and fictional demo accounts (the migrations are already in the repository; do not run makemigrations):

   ~~~powershell
   python manage.py migrate
   python manage.py seed_demo
   ~~~

6. Start the website and its local timer runner:

   ~~~powershell
   .\start_findit.ps1
   ~~~

7. Open http://127.0.0.1:8000/.

If PowerShell blocks the starter script, run it for this terminal only:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\start_findit.ps1
~~~

Stop the website with Ctrl+C; the local timer process stops with it.

## Fictional demo accounts

| Role | Sign-in name | Password |
| --- | --- | --- |
| Student / finder | 2026-0001 | DemoFindIt!2026 |
| Student / claimant | 2026-0002 | DemoFindIt!2026 |
| Student / second claimant | 2026-0003 | DemoFindIt!2026 |
| Student / declined claimant | 2026-0004 | DemoFindIt!2026 |
| Staff (security guard) | security.demo | DemoStaff!2026 |
| Staff (verified moderator) | moderator.demo | DemoStaff!2026 |
| Administrator | findit-admin | DemoAdmin!2026 |

These accounts are created only when you run **seed_demo**. Their passwords are public demo credentials. Never run the demo seeder on a real or hosted site.

To create a separate administrator account, run **python manage.py createsuperuser**; superusers receive the app administrator role. Administrators can create staff accounts from **Staff → Staff accounts**.

## Main routes

- **/** — landing and sign-in
- **/home/** — signed-in search and browse
- **/p/<post-id>/** — direct post link
- **/posts/new/** — create a lost or found post
- **/my-posts/** and **/my-claims/** — personal listing and claim history
- **/staff/** — staff review and moderation workspace
- **/staff/scan/** — guard-house QR scanner; **/staff/walk-in/** — record a walk-in item
- **/staff/categories/** and **/staff/questions/** — administrator-managed categories and question bank
- **/django-admin/** — Django model administration for administrators

## Status and privacy behavior

- A new found post is **Open for Claim**. The first claim changes it to **Claim in Progress**.
- Claims are **Submitted**, then **Approved** or **Declined** by the finder or staff. Several claims can be approved; the finder records **Returned** to any approved claimant, who confirms receipt (**Claimed**). Claims with seven days of inactivity expire.
- The finder says they are bringing an item to the guard house; it becomes **At Guard House** only when staff confirm receipt (QR scan, typed code, or the post page). Claims and chats stay open for the administrator's guard-house grace days; while the item is there the finder sends status requests instead of changing the status.
- An author, staff member, or administrator can close or remove a listing. Removal hides it from active browse but preserves chat and claim history.
- Administrators can set an optional guard-house grace period and optional archive auto-delete period. Blank settings mean disabled. Permanent deletion removes the post, photo, claims, and chats together. Posts connected to a pending safety report are retained until the report is resolved.
- Authorized staff can read any chat for safety review, pause it, and send a report to an administrator. Administrators decide account restrictions. Staff reviews and moderation actions are recorded.
- The local demo channel layer is in-memory and intended for one development process. Set **REDIS_URL** and install **requirements-production.txt** when preparing a multi-process hosted deployment.

## Deployment preparation

The project can use PostgreSQL through **DATABASE_URL** and Redis through **REDIS_URL**; see **.env.example**. Before hosting, set a private **DJANGO_SECRET_KEY**, **DJANGO_DEBUG=0**, correct allowed hosts and CSRF origins, configure durable media storage, run database migrations, and provide an external scheduler for **python manage.py process_due**. Never deploy with demo accounts.

No hosting provider or student-verification method has been selected. Confirm campus data-retention, account-verification, and moderation policies before using real student accounts.

## Design references

The Figma file remains the editable visual source. The repository includes the original diagrams and wireframe preview under **docs/reference/**.

- [Wireframe preview](docs/reference/wireframes.png)
- [System architecture](docs/reference/architecture.png)
- [Entity relationship diagram](docs/reference/erd.png)
- [Padlet 5 system-design document](docs/reference/system-design.docx)

All database migrations are kept in source control (core/migrations). Installs and hosted releases run **python manage.py migrate**; never regenerate migrations on a server.

## License

This project is released under The Unlicense. See [LICENSE](LICENSE) for the full text.
