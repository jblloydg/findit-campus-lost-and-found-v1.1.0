# Find-IT v2.0.0 — DOrSU monument background (DES-001)

**For:** the three v2.0.0 front-end developers.
**What it is:** one shared background, using the owner's photo of the DOrSU campus monument, for every Find-IT page.
**Status:** on branch `design/v2-campus-background`. DES-001 added the kit; **DES-002 switched it on for every existing page** (see the last section). The page layouts were not changed.

## Files in the kit

| File | What it is |
| --- | --- |
| `static/img/campus/dorsu-monument.webp` | The owner's photo (WebP, for modern browsers). Not edited. |
| `static/img/campus/dorsu-monument.jpg` | The same photo as JPG, for older browsers. |
| `static/css/campus-bg.css` | All of the background code: the photo layer, the green and off-white washes, and the card styles. |
| `static/design/campus-background-demo.html` | A demo page. Open it in a browser and use the buttons at the bottom to switch between Landing, Sign-up, Student and Admin. |

**Photo rules (from the owner):** use this exact photo. Don't swap in another campus picture, generate a new one or edit the monument. Colour washes go *on top* of the photo, not into the file.

**Swapping in a bigger photo:** the current photo is 554 × 554 px, and the owner is sending a bigger one. When it arrives, replace both files in `static/img/campus/` and keep the same names. Then set `--campus-blur` to `0rem` in all the media queries in `campus-bg.css`. (The small blur only hides how soft the small photo looks on wide screens.)

## How to use it: two classes on `<body>`

| Class | Look | Use on |
| --- | --- | --- |
| `campus-bg campus-bg--hero` | Deep forest-green wash; the monument shows clearly on the right | Public pages: people who are not signed in |
| `campus-bg campus-bg--app` | Off-white wash; the monument shows faintly near the top and fades out behind content | Every signed-in page |

In `templates/core/base.html`, add the stylesheet and the body class once, so every page gets the background without any per-page work:

```django
<link rel="stylesheet" href="{% static 'css/campus-bg.css' %}">
...
<body class="campus-bg {% block bg_variant %}{% if user.is_authenticated %}campus-bg--app{% else %}campus-bg--hero{% endif %}{% endblock %}" ...>
```

A page that needs the other look can override the block, e.g. `{% block bg_variant %}campus-bg--hero{% endblock %}`.

**Important:** the page wrapper and `<main>` must not paint their own full-page background colour. If they do, the photo is hidden. Put colour on cards, not on the page.

## Which pages get which look

| # | Page | Template(s) | Look |
| --- | --- | --- | --- |
| 1 | Public landing page | `landing.html` | hero |
| 2 | Login | `login.html` | hero |
| 3 | Registration | `signup.html`, `verify_email.html` | hero |
| – | Password reset (4 pages) | `password_reset_*.html` | hero |
| – | QR turn-in page (public view) | `turn_in_public.html` | hero when signed out, app when signed in |
| – | Error pages | `403/404/500/503.html` | hero |
| 4 | Student dashboard | `home.html` (use `.campus-banner` for the "Hello, …" block) | app |
| 5–6 | Lost items, Found items | `home.html` list views | app |
| 7 | Item details | `post_detail.html`, `post_form.html` | app |
| 8 | My posts | `my_posts.html` | app |
| 9 | My claims | `my_claims.html`, `claim_review.html` | app |
| 10 | Messages and chat | `messages.html`, `chat_room.html` | app (chat bubbles sit on a solid `.campus-card`) |
| 11 | Notifications | `notifications.html` | app |
| 12 | Staff workspace | `staff_dashboard.html` | app |
| 13 | Guard house management | `staff_scan.html`, `turn_in_confirm.html` | app |
| 14 | Moderator pages | `moderator_verifications.html`, `id_reviews.html`, `chat_report_*.html` | app |
| 15 | Administrator dashboard | `admin_dashboard.html`, `staff_accounts.html` | app |
| 16 | System settings | `admin_settings.html`, `admin_categories.html`, `admin_questions.html`, `backup_status.html` | app |
| 17 | Reports and audit trail | `admin_reports.html`, `general_report*.html`, `my_reports.html` | app |
| 18 | Everything else | profile, account, blocked people, etc. | app (falls out of `base.html` automatically) |

## Surfaces: what goes on top of the photo

| Class | Use for | Never use for |
| --- | --- | --- |
| `.campus-card` | **Solid** off-white. Forms, tables, chat, item details, anything people read for long or type into. | — |
| `.campus-glass` | Slightly see-through off-white. Stat tiles, short page headers, empty-state boxes. | Forms, tables, long text |
| `.campus-topbar` | The sticky top bar (turns dark-glass automatically on hero pages) | — |
| `.campus-sidebar` | The dark green sidebar; the monument glows through it very slightly | — |
| `.campus-banner` | The dashboard greeting block: the one place inside the app where the monument is shown clearly | More than one per page |
| `.campus-scrim` | Modal backdrop (e.g. "Deactivate this account?") | — |

Inputs, selects, textareas and tables are forced to a solid white background inside `.campus-bg`, even if someone puts them in glass by mistake.

## Responsive behaviour (already built in)

- The photo is a fixed layer behind the page, using `background-size: cover`. It is never stretched; on any screen shape it is cropped, not squashed.
- The anchor point moves with screen size, so the graduates' raised arms and caps stay in view: phones `50% 38%`, tablets `50% 34%`, desktops `50% 30%`, short landscape phones `50% 28%`.
- On phones the hero wash is even from top to bottom, because text runs full width there. On desktop it is darkest on the left, where the text sits, and lighter on the right, where the monument shows.
- It works on iPhones too: a fixed layer is used instead of `background-attachment: fixed`, which iOS ignores.
- Accessibility: blur-free solid cards if the browser can't blur; solid surfaces when the device asks for "reduce transparency"; a thicker wash for "increase contrast"; no photo in Windows high-contrast mode or when printing.

## Palette tokens (from the v2 screenshots)

`--fi-forest #0b2a23` · `--fi-forest-2 #14392f` · `--fi-emerald #1f5245` · `--fi-emerald-2 #2d6a59` · `--fi-sage #9fc2b0` · `--fi-sage-pale #e2eee7` · `--fi-canvas #eef3ee` · `--fi-paper #fbfaf6` · `--fi-ink #10261f` · `--fi-muted #3a4d44`

## Test results (demo page, Chrome)

- **Widths tested:** 320, 360, 390, 430, 768, 1280, 1440 and 1920 px, on all four demo views (landing, sign-up, student, admin), plus the phone menu and the modal. No sideways scrolling at any width. Every button, link and field is at least 44 × 44 px.
- **Text contrast, worst case** (text over the brightest part of the photo):
  - White text on the hero wash: 9.2 : 1 on desktop, 7.5 : 1 on phones.
  - Dark text on the app wash: 8.9 : 1.
  - Grey "muted" text on the app wash: 5.6 : 1, after it was darkened from `#4f6359`, which only reached 3.6 : 1.
  - WCAG asks for 4.5 : 1, so all of these pass.
- **Bug found and fixed in the demo:** at 320–360 px, the table and grid pushed the page wider than the screen. The fix: give grid children `min-width: 0`, and let tables scroll inside their own box (`.table-wrap`, table `min-width: 32rem`). Use the same pattern in real pages.
- **Not tested:** real Safari on iPhone, and the real Django pages (they don't exist yet in v2.0.0).

## DES-002: switched on for every existing page

**What changed (additions only; no page layout, spacing or structure was changed):**

| File | Change |
| --- | --- |
| `templates/core/base.html` | Loads `campus-bg.css` and `campus-bg-pages.css` after `app.css`, preloads the photo, and adds `class="campus-bg {% block bg_variant %}campus-bg--app{% endblock %}"` to `<body>`. Every page that extends `base.html` (all of them except `500.html`) now has the photo. |
| `landing.html`, `login.html`, `signup.html`, `password_reset_form/done/confirm/complete.html` | One line each: `{% block bg_variant %}campus-bg--hero{% endblock %}` (dark green look). |
| `templates/500.html` | Stand-alone on purpose (it must work when Django is failing), so the photo and light wash are added in its own `<style>` with a plain `/static/` path. |
| `static/css/campus-bg-pages.css` (new) | The bridge between the kit and the current pages. Darkens three text colours slightly so they stay readable over the photo, and turns the landing-page text that sits straight on the photo light on the green look. |
| `core/tests/test_campus_background.py` (new) | 7 tests: the photo and stylesheets exist; public pages use the hero look, all signed-in pages and roles use the app look; error pages show the photo; no leftover merge-conflict markers (BUG-008). |
| `tools/testing/campus_bg_check.py` (new) | Opens every reachable page for every demo role in Chrome, checks the photo really loaded and there is no sideways scrolling, and saves screenshots. |

**Which look each page has now:** the hero (dark green) look is on the landing, log in, sign-up and the four password-reset pages. **Every other page** (all student, staff, moderator and admin pages, the item page opened from a shared link, error pages) has the app (light) look. The table above, "Which pages get which look", still describes the v2.0.0 plan. The QR turn-in page and error pages use the app look for now, because their content sits on light cards made for a light page.

**Colour changes for readability** (only on pages with the photo, same hue, a little darker). Contrast is the worst case over the real photo and wash:

| Colour | Before | After | Contrast before → after |
| --- | --- | --- | --- |
| Grey "muted" text (`--muted`) | `#64778a` | `#475a6b` | 3.2 : 1 → 4.9 : 1 |
| Grey lead text on the landing page | `#536a7d` | `#455b6d` | 3.9 : 1 → 4.8 : 1 |
| Teal labels and links (`--teal-dark`) | `#00736f` | `#00625e` | 3.9 : 1 → 5.0 : 1 |
| Landing headline (hero look) | navy | `#f4f7f2` | 10.5 : 1 desktop, 7.3 : 1 phone |
| "Found something?" and small labels (hero look) | teal | `#b8d6c6` | 7.3 : 1 desktop, 5.1 : 1 phone |

WCAG asks for 4.5 : 1. Navy headings were already 8.8 : 1 and are unchanged.

**DES-002 test results (Chrome):**

- 6 widths (320, 360, 430, 768, 1280 and 1920 px) × 6 roles (two students, guard, moderator, admin, signed out) × every reachable page (7 to 42 page types per role): **1,158 page views**. Every page has the photo layer, and the photo loaded every time.
- Error pages (403, 404, 503, form expired, 500) checked with debug off, at 360 and 1280 px: photo shown, no sideways scrolling. One bug was found and fixed: the first version of the 500 page was 37 px too wide at 360 px.
- `python manage.py test core`: **209 tests, all pass** (202 existing + 7 new). `makemigrations --check`: no changes.
- **Speed** (login page, simulated slow phone network: 1.6 Mbit/s, 150 ms delay, median of 5):

  | | Before (main) | After |
  | --- | --- | --- |
  | First visit | 79 KB, 0.78 s | 210 KB, 1.42 s |
  | Next page (photo already saved by the browser) | 0.20 s | 0.20 s |

  The extra 131 KB is the photo (116 KB WebP) plus the two stylesheets (14 KB). It downloads once and is then reused on every page. A smaller WebP would only save about 25 KB at a visible loss of detail (the photo is mostly leaves), so the photo was left as it is.
- **Found, not caused by this change, not fixed** (BUG-009): at phone width the pages `/staff/accounts/`, `/staff/reports/`, `/staff/general-reports/`, `/staff/moderators/` and `/staff/admin/backups/` scroll sideways by 17–487 px (wide tables and the top menu). The numbers are the same with the photo switched off. This belongs to the v2.1.0 adaptive-layout work.
- **Not tested:** real Safari on iPhone, real Android phones, Windows high-contrast mode.
