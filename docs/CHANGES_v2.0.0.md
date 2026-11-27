# Find-IT v2.0.0 (draft) — What changed (report)

Draft report for the v2.0.0 interface overhaul, built on branch **`design/v2-interface`**
(from `design/v2-campus-background`, which is from `main` = v1.1.1). Not merged into `main`;
waiting for the owner's approval. Tests and measurements: `docs/TEST_REPORT_v2.0.0.md`;
bug log: `docs/BUG_REPORTS.md`; background details: `docs/design/CAMPUS_BACKGROUND.md`.

## Branches (rollback)
- `main` — v1.1.1, unchanged.
- `design/v2-campus-background` — DES-001 (background kit), BUG-008, DES-002 (background on the v1.1.1 pages).
- `design/v2-interface` — this work (DES-003) on top of that.
Every change is its own commit, so each can be reverted alone.

## What the owner asked for
"Make every page look like the v2 screenshots (green sidebar design), with the DOrSU monument
photo as the background of every page." The owner chose: **all pages**, **follow the screenshots**,
**new branch in this repo**. Decided exception: the screenshots' example ID `2024-0122` is the
owner's real account (CLAUDE.md decision 10), so `2020-0001` is used instead.

## New look (DES-003)
| Part | What changed |
| --- | --- |
| Whole app | New stylesheet `static/css/findit.css` **replaces** `app.css` (removed). Same class names, so all 70 templates and `app.js` / `chat.js` / `scan.js` keep working. Forest / emerald / sage / off-white palette, Geist + Instrument Serif (italic accents) + Geist Mono (small uppercase labels). All sizes in rem / % / clamp() (master instruction); fixed px only for 1px borders and shadows. |
| Fonts | Self-hosted in `static/fonts/` (SIL Open Font License, free), so the app also works with no internet on campus. |
| Background | The DOrSU monument photo (`campus-bg.css`, DES-001) behind every page: dark green on public pages, light off-white on signed-in pages, and clearly visible in the dashboard and log-in banners. |
| Signed-in layout | New dark-green **sidebar** (`templates/core/includes/sidebar.html`): Overview (Dashboard, Lost items, Found items), Report an item, My activity (with red/green counts), Staff (guards), review links (verified moderators + admins), Administrator (admins), Test inbox (local only). Name and role at the bottom with "Hand-offs happen on school premises only." **Top bar:** search, New post, Messages and Notifications with counts, profile menu. |
| Phones and tablets | Below 1024 px the sidebar becomes a slide-in **drawer** (menu button; closes with ×, Escape or a tap outside; keyboard focus moves into it). Top bar shrinks to menu, search, round + button, bell, profile picture. |
| Landing page | Rebuilt like the screenshot: hero ("Lost something? *Found something?*") with log-in card, "02 — How it works" (3 steps + status chips), "03 — Privacy by design" (4 cards), "A safer hand-off" band, dark footer. |
| Log in, sign-up, password reset | One card with the green "Campus lost & found, *returned safely.*" banner. |
| Dashboard | "Hello, *name*." banner with Report lost / Report found buttons, 4 tiles (Active posts, Open claims, Messages need you, Unread updates), All posts / Lost / Found tabs, filters, listing cards (type + status chips, category chip, author + date). |
| Lost items / Found items | Same page filtered, with their own heading and "Report lost/found item" button. |
| Admin dashboard | Section names (Accounts, Moderators, Safety, Listings & platform) instead of A–D, shortcut cards, dark "Total users" tile, stat cells with coloured edges. |
| Every other page | Restyled through the shared stylesheet (cards, chips, tables, forms, chat bubbles, modals, QR scanner, reports). |

## Small code changes (behaviour unchanged)
| File | Change |
| --- | --- |
| `core/views.py` `home` | Two counts for the dashboard tiles (your active posts, your open claims). |
| `core/views.py` `create_post` | `?type=LOST` / `?type=FOUND` pre-selects the post type (sidebar "Report lost/found item"). |
| `core/context_processors.py` | `current_can_review` so the sidebar shows review links only to verified moderators and admins (same rule as before). |
| `static/js/app.js` | Live counts update every copy (sidebar and top bar); drawer open/close. |
| `templates/500.html` | Green colours (it stays stand-alone on purpose). |

## Bugs fixed
| ID | Bug |
| --- | --- |
| BUG-008 | Leftover `<<<<<<< HEAD` line printed on every Browse card (on `design/v2-campus-background`; also needed on `main` / `release/1.1.2`). |
| BUG-009 | Sideways scrolling on 5 staff/admin pages at phone width (17–487 px). Gone with the new layout: 0 px on every page at 320–1920 px. |
| — | (found during this work) Staff workspace heading 129 px too wide for admins at 1280 px; report filter bars cramped; empty gap under headings on phones; one grey text colour at 4.4 : 1. All fixed before commit. |

## Speed (see the test report)
First visit is heavier because of the photo and fonts (79 KB → about 300 KB on the local server;
the stylesheet is 16 KB instead of 82 KB in production, where it is compressed). Every page after
that is as fast as before (about 0.2–0.35 s on a slow phone network), because the photo, fonts
and stylesheet are kept by the browser.

## Migrations, packages
- No database migrations. No new Python packages. Fonts are files, not packages.

## Not included / still to do
- Not merged into `main`; v2.0.0 version number not set; the small light-grey version label in
  the footer (CHG-007 instruction on `release/1.1.2`) is not added yet.
- The three front-end developers' own v2.0.0 wireframe work: this branch is the base to build on.
- New admin data shown in the screenshots but not in v1.1.1 (e.g. "Lost and found activity" counts,
  "Recent audit trail" list on the admin dashboard) was **not** invented; only existing data is shown.
- Not tested on real iPhones / Android phones or Safari.
