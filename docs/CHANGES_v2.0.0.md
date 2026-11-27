# Find-IT v2.0.0 — What changed (report)

Short report of the v2.0.0 interface overhaul compared with v1.1.1 (`main`). Plain text so it can be
read in any Claude session. Tests and measurements: `docs/TEST_REPORT_v2.0.0.md`; bug log:
`docs/BUG_REPORTS.md`; how to build pages with the new look: `docs/design/V2_DESIGN_SYSTEM.md`.

## Branches (rollback)
- `release/2.0.0` — all v2.0.0 work (this branch). Started from `design/v2-campus-background`
  (DES-001, the DOrSU monument photo kit), which itself starts from `main` (v1.1.1).
- `main` — still v1.1.1. Merge `release/2.0.0` into `main` only after the owner approves.
- Not included: the v1.1.2 bug-fix work on `release/1.1.2` (docs only so far). Merge it separately.
Every change is its own commit (`git log --oneline`), so any single one can be reverted.

## What the owner asked for
"Apply the designs (the 7 pictures) to the repo, especially the pages in the v2 doc."
Choices made (the question card got no preference, so the recommended options were used):
1. The pictures' look **plus** the DES-001 monument photo behind the pages (owner's v2 identity decision).
2. The new look on **every** page (one shared stylesheet), with the pictured pages redone in detail.
3. Pushed to a new branch `release/2.0.0`, not `main`.

## New interface
| ID | Change |
| --- | --- |
| DES-002 | **Design system** (`static/css/v2.css`): forest / emerald / sage / off-white palette, Instrument Sans + Instrument Serif italics + JetBrains Mono labels (stored in the project, works offline), pill buttons, fields, cards, status pills with colours per status, stat tiles, modals, flash messages, empty states. Sizes use rem / % / clamp (owner's rule). |
| DES-002 | **App shell for signed-in pages:** dark green sidebar grouped Overview / Report an item / My activity / Staff / Administrator (links shown by role), person + "Hand-offs happen on school premises only" at the bottom; top bar with search, New post, Messages and Notifications badges, profile menu. On phones/tablets the sidebar becomes a slide-in menu (☰). |
| DES-002 | **Public pages:** dark header (Overview / How it works / Privacy, Log in, Create account) and dark footer. **Landing page** rebuilt from the picture: hero with sign-in card, "02 — How it works" (3 steps + status chips), "03 — Privacy by design" (4 cards), "A safer hand-off" banner. **Log in** page with the green "Campus lost & found, returned safely." header (phone picture). |
| DES-002 | **Dashboard** (`/home/`): "Hello, Alex." banner with the monument photo, Report lost / found buttons, 4 tiles (Active posts, Open claims, Messages need you, Unread updates), All / Lost / Found tabs, new filter panel, new post cards (type pill, status pill, category chip, author + date). Sidebar "Lost items" / "Found items" open the same page filtered. |
| DES-002 | **Report lost item / Report found item** links pre-select the post type on the Create post form (`?type=LOST` / `?type=FOUND`). |
| DES-002 | **Admin dashboard** rebuilt from the picture: shortcuts (Accounts, Moderator verification, Student ID reviews, Question bank), User accounts (now also shows ✔ verified students and red-flagged accounts — backend existed, no frontend before), **Lost and found activity** (lost active, found active, at guard house, claimed or closed, claims awaiting, claims completed), Moderator verification, Chat safety reports, **Item reports vs System reports** split, open item & system report queue, **Recent audit trail** (last 6 staff actions). |
| DES-002 | **Staff workspace** from the picture: Scan turn-in QR / Walk-in item at the top, 5 tiles (Active posts, On the way, At the guard house, Status requests, Moderator status or open reports), shortcuts (Claims, Found items, Lost items), "Moderator authorization required" banner. The long admin button row moved to the sidebar. |
| DES-002 | **Post page:** new photo frame, facts strip (status / date / time), "More in <category>" chip, lavender "At the guard house" box, comments card, side panels. |
| DES-002 | **Styled "Are you sure?" pop-up** (picture 6) for Deactivate account. Any button can use it with `data-confirm="…"`. Without JavaScript the button still works. |
| DES-003 | Chat, create-post form, accounts, moderators, report pages: restyled with the same parts (no layout or field changes). |

## Not changed on purpose
- No backend names changed: every form field name, `id` and `data-…` attribute used by JavaScript, `{% csrf_token %}` and `method="post"` are kept (v2 doc rule).
- No database migrations. No new Python packages. Fonts are files in `static/vendor/fonts/` (OFL licence files next to them).
- Location stays dormant (decision 8) — it is now hidden on the post page too (see BUG-v2-03).

## Small backend changes (display only)
| File | Change |
| --- | --- |
| `core/views.py` `home` | two counts for the dashboard tiles (my active posts, my open claims) |
| `core/views.py` `create_post` | `?type=LOST/FOUND` pre-selects the post type |
| `core/views.py` `admin_dashboard` | lost/found activity counts, item vs system report counts, last 6 audit entries |
| `core/context_processors.py` | `location_enabled` available on every page |
| `core/tests/test_session1.py` | home query limit 11 → 13 (the 2 new constant tile counts; still flat with more posts) |

## Bugs fixed
| ID | Bug |
| --- | --- |
| BUG-v2-01 | `app.css` contained leftover merge text (`@@ -186,6 …`), which broke the CSS rule after it. |
| BUG-v2-02 | The Browse page showed a leftover `<<<<<<< HEAD` merge marker as text above each post card's details. |
| BUG-v2-03 | The post page showed an empty round "category" link (it used `get_category_display` on a ForeignKey, and linked by name instead of id) and showed the location although location is dormant. |
| BUG-v2-04 | "Jump to latest" showed on every chat (and other `hidden` elements could show) because a CSS rule overrode the `hidden` attribute. |
| — | Local database side files `db.sqlite3-shm` / `-wal` were not in `.gitignore` (risk of committing them). |

## Differences from the pictures (and why)
- The pictures' sign-in box says "Student ID or staff username" with example `2024-0122`. v1.1.1 rules: students sign in with **email** (or a verified Student ID), and the example ID must be **2020-0001**. The page follows the rules.
- The pictures show a "Claims" sidebar link and a "Full audit trail" link. There is no staff claim list page or full audit log page in the backend yet (the v2 doc lists the audit page as future work), so these were not added; the staff workspace "Claims" shortcut jumps to Open items, where each item's claims are reviewed.
- The monument photo shows behind the pages (DES-001, owner decision) — the pictures used plain green.

## Not included / next
- Signup, password reset, profile, ID review and settings pages use the new parts but were not redesigned beyond that (no pictures for them yet).
- New v2-doc pages that need small backend actions (Withdraw ID review, full audit log, red-flagged list page, /health status page) — not started.
- v2.1.0: fix anything found while testing this version.
