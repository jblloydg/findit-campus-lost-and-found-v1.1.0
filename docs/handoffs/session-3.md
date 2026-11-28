# HANDOFF — Task 3: Search, filters and possible LOST/FOUND matches

## Feature

- **Search and filters** on `/home/`: keyword search plus filters for post type (Lost/Found), status, item category, and an item-date range (`From` / `To`). "Clear filters" resets them.
- **Item category** field on posts (Bags, Electronics, Clothing, IDs/Cards, …, Other). It is chosen on the create/edit form and used by search and matching. Existing posts default to **Other**.
- **Possible matches** (`core/matching.py`): for a LOST post, the app scores open, non-archived FOUND posts by same category (30 pts), title similarity (up to 40 pts) and description similarity (up to 30 pts), and keeps scores of 40 or higher, best first, up to 10. After a LOST post is created, the author sees a message saying how many possible matches were found.
- No location data is used.

## Starting commit

`0f2bbca` — "Remove imported findit-campus-lost-and-found code" (the repo was empty at this point). This upload adds the full app with the Task 3 changes on top.

## Files changed for Task 3

- `core/models.py` — `ItemPost.Category` choices and `category` field
- `core/migrations/0002_itempost_category.py` — **new migration**
- `core/matching.py` — **new**, `find_possible_matches()`
- `core/forms.py` — category added to the post form
- `core/views.py` — home search/filters, match count message after creating a LOST post, `show_matches` / `possible_matches` in post detail
- `templates/core/home.html` — category and date filters
- `templates/core/post_form.html` — category field with help text

Fix made during upload: in `core/views.py` (`post_detail`), `show_matches = (...)` was indented inside the staff-only `if` block. Every post page crashed with `UnboundLocalError` for students. It is now at the correct indentation.

## Migrations

- `0001_initial.py`
- `0002_itempost_category.py` — adds `ItemPost.category` (default `OTHER`, indexed)

Run `python manage.py migrate`. Do not run `makemigrations` again for these changes.

## Setup and run (Windows PowerShell, VS Code)

```powershell
git clone https://github.com/jblloydg/3.git
cd 3
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
.\start_findit.ps1
```

Open http://127.0.0.1:8000/. Next time, only run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
.\start_findit.ps1
```

If the script is blocked as "not digitally signed" (files from a downloaded zip), run `Get-ChildItem -Recurse | Unblock-File` once.

Already have a database from before this change and see `no such column: core_itempost.category`? Run `python manage.py migrate`.

Demo accounts (fictional, local only) are listed in README.md, e.g. `2026-0001` / (password: FindIT.cmd menu 2).

## Test steps

1. Sign in as `2026-0001`. On `/home/`, search by keyword, then filter by type, status, category and date range. Check "Clear filters".
2. Create a FOUND post (for example "Black wallet", category Bags or IDs/Cards).
3. Sign in as `2026-0002` and create a LOST post with a similar title, the same category and a similar description. After saving, a message should report possible matches.
4. Open any post as a student, as staff (`security.demo`) and as admin. Each page should load without errors.
5. `python manage.py check` and `python manage.py makemigrations --check --dry-run` should report no issues and no changes.

Checked before upload: on a fresh database, `migrate`, `seed_demo`, `check` and the migration check pass. Home, search with filters, new post, My posts, My claims and every post detail page return 200 for student and staff demo accounts.

## Open issues

- **Possible matches are not shown on the post page.** `post_detail` passes `show_matches` and `possible_matches` to the template, but `templates/core/post_detail.html` has no section that displays them, so the "See Possible Matches below" message points to nothing yet. Add a section that lists each match's title, category, score and a link to `/p/<id>/`.
- Matching scans every open FOUND post in Python. That's fine for a campus demo, but it may need pre-filtering (for example, by category or date) if there are many posts.
- There are no automated tests yet (`python manage.py test` runs 0 tests).
