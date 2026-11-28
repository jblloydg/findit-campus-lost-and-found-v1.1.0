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

## Added after the owner's check of the v2.0.0 list (DES-004)
The owner's v2.0.0 list (103 points) had 9 items (13 points) with a backend but no page yet. All are built now:

| List item | Size | Where to see it |
| --- | --- | --- |
| 1. Account verification details | M 2 | Accounts → open an account (Edit account) → "Verification details": email verified date, Student ID and lock, Student IDs used (of 3), Student ID history table, ID conflict deadline, red flag, ID reviews. |
| 1. Red-flagged accounts list/filter | M 2 | Accounts: "Red-flagged accounts" panel (shown when any exist) + new "Verification" filter (Red-flagged / Verified students / Not verified students / Student ID conflict) + a Verification column in the table. |
| 1. Developer view of Accounts | S 1 | Signed in as the Developer: purple "Developer view" note on Accounts and Edit account; Role shows **Administrator** only for the Developer (backend rule unchanged). |
| 1. Withdraw an ID review | S 1 | My profile → My ID reviews → **Withdraw** (only the student who asked, only while waiting). New: `withdraw_id_review()` in `core/verification.py`, `POST /id-review/<id>/withdraw/`, recorded in the audit trail. |
| 2. Location input, filter and tag (dormant) | M 2 | Post form "Where (optional)" field, filter on Browse and tag on cards/post page. **Only when `FINDIT_LOCATION_ENABLED=1`** (decision 8); hidden and not collected otherwise. |
| 3. Admin dashboard numbers | S 1 | Admin dashboard → "Students & Student IDs": Verified students, Not verified yet, Red-flagged accounts, Open ID reviews (each opens the matching list). |
| 3. Full audit log page | M 2 | `/staff/admin/audit/` ("Audit trail" in the sidebar, Accounts and the admin dashboard): every recorded action, search, filter by action, 50 per page, read-only. Admins and the Developer only. |
| 3. Video length/size badge in chat | S 1 | Under each video in a chat: "▶ 0:42 · 3.1 MB" (page and live messages). |
| 3. System status page from /health/ | S 1 | `/staff/admin/status/` ("System status"): database (with answer time), migrations, daily backup age (warns after 26 h = timer runner not running), chat media queue (warns if stuck 15 min), open queues. Admins only. |

**Demo data:** two fictional students so these screens have something to show — `2026-0016` Drew (red-flagged, inactive, used 3 IDs) and `morgan.shared@example.com` (not verified, typed Riley's Student ID, 14-day conflict deadline, open ID review to withdraw). Run `FindIT.cmd` → 3 (Reset the demo data) to get them.

### Full v2.0.0 list status: 103 of 103 points
| Part | Points | Built |
| --- | --- | --- |
| 1. Design system, accounts and identity | 36 | 36 |
| 2. Posts, claims and guard house | 34 | 34 |
| 3. Messages, safety and administration | 33 | 33 |
Note: the list says every page is "drawn twice (PC + phone)". These are working pages that adapt to both (checked at 320–1920 px), not separate Figma drawings.

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
- The screenshots' "Lost and found activity" counts on the admin dashboard were not added (not in the
  owner's list); the audit trail now has its own page instead.
- Not tested on real iPhones / Android phones or Safari.
