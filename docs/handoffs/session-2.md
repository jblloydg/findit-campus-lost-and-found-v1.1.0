# HANDOFF – Feature 2: Create, Edit and Track LOST/FOUND Posts and Record Item Photos

## 1. Feature completed

**Feature 2 – Create, edit, and track LOST/FOUND posts and record item photos.**

- **New: approximate time.** LOST and FOUND posts now record an *approximate time lost/found*. It has a time picker on the create and edit forms. It is shown on the item detail page, the Browse cards and My Posts, and it can be changed or cleared when editing.
- **Improved: item photos (still optional, now encouraged).**
  - The form says: "Adding a photo is optional, but highly encouraged to help identify the item."
  - A preview of the chosen photo appears before you submit.
  - When editing, you see the current photo and can replace it or tick **Remove the current photo**.
  - The old file is deleted from `media/` when a photo is replaced or removed.
  - File type is checked by extension and by the real image format (JPG, PNG or WebP only; up to 5 MB).
- **Kept as-is: create / edit / status tracking.** Post types, verification questions, the status workflow, status history and permissions all work as before (see section 7).

## 2. Starter version used

| | |
|---|---|
| Starter repository | `https://github.com/jblloydg/findit-campus-lost-and-found` |
| Branch | `main` |
| **Starter commit** | **`ba12ca12b36c062bdc52e2d5265cc0a8a1d63b86`** ("Unpack Find-IT source into repository root") |

The starter's full Git history (all 4 commits, from `8290e4d` "Initial commit" onward) is kept unchanged in this repository's `main` branch. My work is added as new commits on top of it. Nothing was rewritten or deleted.

## 3. Files changed

| File | What changed and why |
|---|---|
| `core/models.py` | Added `ItemPost.approximate_time` (`TimeField`, optional). Added a small `has_approximate_when` helper for templates. |
| `core/forms.py` | `ItemPostForm`: added the `approximate_time` field with an `<input type="time">` picker and the requested label and help text. Added a `remove_photo` checkbox. Added checks: a time needs a date, the date can't be in the future, and today's time can't be later than now. A replaced or removed photo file is deleted after saving. |
| `core/validators.py` | `validate_photo` now also checks the file extension. It skips photos already saved, so editing an old post never crashes if its image file is missing from disk. |
| `core/views.py` | `post_detail` passes a new `can_edit` flag. The **Edit post** button now shows only to the author or an administrator, matching the existing rule in `edit_post`. Before, staff saw the button and got a 403 error. |
| `core/admin.py` | Approximate date and time added to the Django admin post list. |
| `templates/core/post_form.html` | Form split into sections: **Post type → Item information (title, description, date, time) → Item photo (preview, current photo, replace/remove) → private questions → actions.** |
| `templates/core/post_detail.html` | New "Current status / Approx. date / Approx. time" boxes. Posts without a date or time show "Not provided". |
| `templates/core/home.html`, `templates/core/my_posts.html` | Show the approximate time next to the date. |
| `static/js/app.js` | Image preview before submitting, early type and size warnings, and remove/replace behaviour. |
| `static/css/app.css` | Styles for the form sections, the date/time row (stacks on phones), the photo preview and the detail facts. Same navy/teal design. |
| `core/migrations/0001_initial.py` | **New file.** The starter's initial migration, generated from the *unchanged* starter models (separate commit). |
| `core/migrations/0002_itempost_approximate_time.py` | **New file.** Adds the `approximate_time` column. |
| `core/tests.py` | **New file.** 26 automated tests for this feature. |
| `README.md` | Setup step 5 no longer runs `makemigrations`, because the migrations are now committed. |

## 4. Database fields and migrations

- **Added field:** `core_itempost.approximate_time` — `TIME`, nullable (`null=True, blank=True`). It's optional in the same way `approximate_date` already was, so posts made before this change stay valid. They simply have no time.
- **Migrations:**
  - `0001_initial` — the starter schema. The starter told everyone to run `makemigrations` locally, so no migration was in Git; this file is exactly what that command produces for the starter models.
  - `0002_itempost_approximate_time` — a single, non-destructive `ALTER TABLE core_itempost ADD COLUMN approximate_time time NULL`. No data is deleted or changed. It works on SQLite now and PostgreSQL later.
- The database engine is unchanged (SQLite). `db.sqlite3`, `media/`, `.env` and other private files are **not** committed (they are in `.gitignore`).

## 5. Set up and run on Windows PowerShell

Requires Python 3.12 or later and Git.

```powershell
# 1. Get the code
git clone https://github.com/jblloydg/2.git findit
cd findit

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
#   If PowerShell blocks activation, run this once and try again:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 3. Install packages
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Create/update the database and load fictional demo accounts
python manage.py migrate
python manage.py seed_demo

# 5. (Optional) run the automated tests
python manage.py test core

# 6. Start the site (web server + timer runner)
.\start_findit.ps1
#   If blocked:  powershell -ExecutionPolicy Bypass -File .\start_findit.ps1
#   Or just the web server:  python manage.py runserver
```

Open **http://127.0.0.1:8000/**. Stop with **Ctrl+C**.

### Already have an older Find-IT database?

If you ran the starter before, your `core/migrations/0001_initial.py` was generated locally and is not tracked by Git, so it may conflict when you pull.

1. Delete your local `core\migrations\0001_initial.py` (only if Git reports it as untracked or blocks the pull).
2. Pull, then run `python manage.py migrate`.

Your database already records `core.0001_initial` as applied, so only `0002_itempost_approximate_time` runs. Your existing posts are kept. Do **not** delete `db.sqlite3`.

## 6. See the feature working (about 5 minutes)

Sign in as **2026-0001** / **DemoFindIt!2026** (fictional demo account).

1. **Create a LOST post with a time:** click **Create post**. Choose **Lost**, enter a title and description, pick yesterday's date and a time such as 3:40 PM, then click **Publish post**. You'll see "Your post is live." and the detail page shows **Approx. time lost: 3:40 PM**.
2. **Photo preview:** create another post, this time **Found**. Fill in the five private questions and choose a JPG/PNG photo. A preview appears under the file box before you publish. After publishing, the photo shows on the detail page.
3. **No photo:** create a post without choosing a photo. It saves normally and shows "No photo was added".
4. **Edit:** open your post → **Edit post**. The time is already filled in. Change the title, date and time, then replace the photo (or tick **Remove the current photo**). Click **Save changes** to see "Your post was updated." and the new values.
5. **Validation:** in a new post, enter a time but no date → "Add the approximate date as well…". A future date → "cannot be in the future". A `.gif` → "Upload a JPG, PNG, or WebP exterior photo."
6. **Old records:** the two seeded demo posts ("Blue insulated bottle", "Black folding umbrella") have no time. They open fine and show "Not provided".
7. **Status tracking:** the detail page shows **Current status**. Sign in as **2026-0002** / **DemoFindIt!2026** and claim "Blue insulated bottle" (status → Claim in Progress). As 2026-0001, open the post → **Mark returned** (→ Returned). As 2026-0002, **Confirm I received it** (→ Claimed). The status history panel lists each step.
8. **Permissions:** as 2026-0002, visit the edit link of a post owned by 2026-0001 (`/posts/<id>/edit/`). You get "Only the post author or an administrator may edit this post." Staff account **security.demo** / **DemoStaff!2026** no longer sees an Edit button on other people's posts, but still has the staff actions.
9. **Mobile:** in your browser, press F12 → device toolbar → choose a phone size. The date and time fields stack, and the photo preview fits the screen.

## 7. Test results

`python manage.py test core` → **26 tests, all passing** (Django 5.2.19, Python 3.13).

| Required test | Result |
|---|---|
| 1 – Create LOST post with date and time | Pass – saved, and shown on the detail page, Browse and My Posts |
| 2 – Create FOUND post with photo | Pass – file stored under `media/item-photos/`, shown on detail |
| 3 – Post without photo | Pass |
| 4 – Edit title, description, date, time; replace photo | Pass – old photo file removed; remove-photo and clear-time also tested |
| 5 – Track post status | Pass – Open → Claim in Progress → Returned → Claimed, plus Turned Over → Closed; history recorded |
| 6 – Permissions | Pass – other users get 403 on edit; turn-over, close, remove and the staff dashboard stay protected |
| 7 – Existing records without time | Pass – also checked by migrating a real starter-era database copy: both posts kept, time empty |
| 8 – Mobile responsiveness | Checked by hand in Chrome at 390 px and 1280 px widths (create, edit, detail, home) |

Extra tests cover invalid time, time without date, future date, non-image files, GIF uploads, oversize files, the time pre-filled on edit, and editing a post whose photo file is missing.

## 8. Unfinished items and setup notes

- **Approximate time is optional.** That matches how the starter treats approximate date. The form encourages it but doesn't force it, and a time can't be saved without a date. If the team wants the date and time to be required for new posts, it's a one-line change in `ItemPostForm`.
- **Time zone:** times are stored exactly as entered (local campus time). The future-date check uses the project's `TIME_ZONE = "Asia/Manila"`.
- **Status labels were not renamed.** The starter shows "At Guard House" and "Returned", while the requirements document says "Turned Over / At Guard House" and "Returned to a Selected Claimant". I left the labels alone to preserve the existing workflow; renaming them is a display-only change in `ItemPost.Status`.
- **Staff vs. edit:** the starter only lets the author or an administrator edit a post (staff cannot). I kept that rule and just hid the button that led staff to an error page.
- **Mobile layout of the detail page:** on phones, the starter puts the action panel above the photo. That is existing behaviour I didn't change.
- **Migration note for teammates:** see "Already have an older Find-IT database?" above.
- No new packages were added. Nothing private is committed: no `db.sqlite3`, no `media/`, no `.env`, no real student data. The only passwords mentioned are the starter's public fictional demo credentials.
