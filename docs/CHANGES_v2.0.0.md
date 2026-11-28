# Find-IT v2.0.0 — Patch notes (what changed and why)

**v2.0.0 = v1.1.2 + the front-end team's v2.0.0 interface**, checked against the owner's v2.0.0 list
and the v2.0.0 Master Instruction, with the bugs found on the way fixed.
Tests and measurements: `docs/TEST_REPORT_v2.0.0.md`. Every change has its own commit and a line in
`docs/BUG_REPORTS.md`. Background photo details: `docs/design/CAMPUS_BACKGROUND.md`.

## Summary
- **New look on every page:** dark-green sidebar (a slide-in menu on phones), the DOrSU monument
  photo behind every page, forest / emerald / sage / off-white colours, new fonts. One layout that
  adapts from phone to desktop.
- **Every backend feature now has a page:** the 9 items that had a backend but no screen (13 points).
- **Version label** "Find-IT v2.0.0" on every page, read from `VERSION`.
- **Master Instruction bugs fixed:** buttons and links too small to tap, text smaller than 12 px,
  fixed px on the error page (BUG-015, BUG-016, BUG-017).
- **Privacy fix:** the database's helper files could be committed by mistake (BUG-018).
- **Everything from v1.1.2 is kept:** SEC-001 (photo/video hardening), SEC-002 (notification links),
  CHG-008 (random demo passwords), BUG-008/009/010.
- No database migrations, no new packages. Tests: 266 (228 in v1.1.2).

## Where it came from (branches)
| Branch | What it is |
| --- | --- |
| `main` | Released v1.1.2 until the owner approves v2.0.0. |
| `stable/v1.1.2` | Frozen v1.1.2, the rollback point. |
| `release/2.0.0` | **This version.** Replaces the earlier v2 draft that was on this branch (normal merge, nothing deleted). |
| `design/v2-interface` | The front-end team's work. Their BASTA-KAY zip is exactly this branch (0 different files). Based on the final v1.1.1. |
| `archive/v2-alt-design` | The earlier, different v2 design that was on `release/2.0.0`. Kept unchanged so nothing is lost; not used. |

**Why the team's design and not the earlier draft:** the owner chose it (it is the front-end team's
official v2.0.0). Because their copy started from v1.1.1, v1.1.2 was merged into it (CHG-009).

## 1. Integration of v1.1.2 (CHG-009)
The merge had 4 conflicts. How each was settled, and why:

| File | Decision | Why |
| --- | --- | --- |
| `FindIT.cmd` | v1.1.2's version | The team's copy still printed the **old fixed demo passwords** (CHG-008 removed them) and lacked the BUG-009 menu fix. |
| `core/management/commands/seed_demo.py` | Both | The team added two example students (Drew: red-flagged; Morgan: Student ID conflict + open ID review). In their copy these got the old fixed password; now they get a **random password per PC** in `demo-logins.txt`, like every demo account. |
| `CLAUDE.md`, `tools/testing/README.md` | Both | Both sides added useful lines; the password text was left out. |

Also adjusted: the BUG-010 tests and `page_load.py` now look for `findit.css` (the new stylesheet
replaced `app.css`), and one sentence in the team's draft test report that described the Developer
account was rewritten (the leak-check test caught it). A line-by-line check confirmed every line
v1.1.2 added is still there.

## 2. The new interface (front-end team: DES-001 … DES-004)
| Part | What changed |
| --- | --- |
| Whole app | New stylesheet `static/css/findit.css` replaces `app.css` (same class names, so all pages and `app.js` / `chat.js` / `scan.js` keep working). Sizes in rem / % / `clamp()`. Fonts are files in `static/fonts/` (free licence), so it works without internet. |
| Background | The DOrSU monument photo behind every page (`static/css/campus-bg.css`): dark green on public pages, light off-white when signed in. |
| Signed-in frame | Dark-green **sidebar** (Overview, Report an item, My activity with counts, Staff, review links, Administrator, Test inbox). **Top bar:** search, New post, Messages, Notifications, profile menu. Below 1024 px (64em) the sidebar is a slide-in menu. |
| Redesigned pages | Landing, Log in, Sign up, the 4 password-reset pages, 500 page, Dashboard / Browse (with Lost items and Found items), Admin dashboard, Accounts, Edit account, new Audit trail and System status pages. |
| All other pages | New colours, fonts, cards, chips and frame from the shared stylesheet; their layout is the v1.1.1 layout (see "Not included"). |

**The 9 items that had a backend but no page (DES-004, 13 points)** are all built: verification details
on Edit account; red-flagged accounts panel and Verification filter on Accounts; Developer view on
Accounts; Withdraw an ID review (My profile); dormant location field (only with
`FINDIT_LOCATION_ENABLED=1`); admin dashboard numbers; Audit trail page (`/staff/admin/audit/`);
video length/size badge in chats; System status page (`/staff/admin/status/`).
A check of every address in the program found no backend page without a link or button to it.

## 3. Added during integration
### DES-005 — Version label (owner's rule CHG-007)
- Small light-gray **"Find-IT v2.0.0"**: at the bottom of the sidebar on PC; in the page footer on
  tablets and phones (where the sidebar is hidden); in the public footer when signed out; on the 500 page.
- The number is read once from the `VERSION` file (`core/version.py`), never typed into a page.
  `VERSION` is now `2.0.0`. **Change `VERSION` with every new version.**

### BUG-011 — Two styles lost in the new stylesheet
`.accounts-panel` (Accounts, Edit account, Backups, Moderators, My reports: panels touched the content
above) and `.compact-form` (small forms on the post page and chat). Added back; a test now checks
that styles the pages use stay defined.

## 4. Master Instruction fixes (bug fixes on the front-end output)
The three developers worked separately, so each page was measured in Chrome, for every role, at
360, 390, 430 (phones), 768 (tablet), 1280 and 1920 px (desktops) with the new tool
`tools/testing/responsive_check.py`. The stylesheets already used relative units; what the
measurements found were sizes that were *relative* but **too small**:

| ID | Problem | Fix |
| --- | --- | --- |
| BUG-015 | Tap targets under 44 px: small buttons 36 px, profile-menu links 40 px, Browse tabs 38 px, password "Show" 32 px, phone menu button squeezed to 31 px wide, checkbox rows 24–39 px, text-only actions ("Report this listing", "Decline…", "Withdraw") 17–21 px. | Every one uses the shared tap size `--tap: 2.75rem` (44 px). |
| BUG-016 | Text under 12 px: the smallest text size went down to 10.9 px on phones (help text, small labels, chips, badges, table headings, footer), plus 6 fixed sizes below 0.75rem. | Smallest size now 0.75rem (12 px), still with `clamp()`. |
| BUG-017 | The 500 page used fixed px for width, margins, padding and button. | %, rem and `clamp()`; button 2.75rem tall. |

Result: **179 kinds of problems before → 0** on Find-IT pages; 0 sideways scrolling at any width;
icons all between 12 and 48 px; text lines never wider than 75rem (content width is capped at 72rem).

## 5. Privacy fix
### BUG-018 — Database helper files not ignored
Since v1.1.1 (PERF-002) SQLite keeps `db.sqlite3-wal` and `db.sqlite3-shm` next to the database.
`.gitignore` only listed `db.sqlite3`, so `git add -A` could commit the local database (sessions,
demo accounts). It happened once during this integration and was removed before anything was pushed.
`.gitignore` now covers these files and test screenshots; a test fails if any of them is tracked.

## 6. Found and fixed by the front-end team (renumbered in the log)
| New ID | Team's ID | What |
| --- | --- | --- |
| BUG-012 | BUG-008 | A leftover `<<<<<<< HEAD` line printed on every Browse card. **Still present in the released v1.1.2**; gone in v2.0.0. |
| BUG-013 | BUG-009 | Sideways scrolling on 5 staff/admin pages at phone width. |
| BUG-014 | BUG-010 | A model edit that would have dropped a database index (caught before commit). |
The team's IDs clashed with v1.1.2's BUG-008/009/010, so they were renumbered in the log; their
commits are unchanged.

## 7. Speed (details in the test report)
- **Server:** same as v1.1.2 (every page 5–15 ms; 100 people chatting: all messages delivered, 0 errors).
- **Normal browsing on a slow phone:** same as v1.1.2 (about 0.24–0.36 s per page).
- **First visit on a slow phone:** slower — about 1.2 s until usable (v1.1.2: 0.8 s), because the
  monument photo (116 KB) and fonts (82 KB) are downloaded once. The browser keeps them afterwards.
  On the hosted version the stylesheet is also compressed (84 KB → about 16 KB).

## 8. Database migrations and packages
None.

## 9. Tests
266 automated tests (v1.1.2: 228; front-end team +26; integration +12 in `core/tests/test_v200.py`:
version label, lost styles, Master Instruction rules, no database files in Git).

## 10. Not included / still open
**Pages that got the new colours but kept their v1.1.1 layout** (accepted for v2.0.0; for the team to
redesign next). By developer, following the v2.0.0 list:
- **Developer 1 (design system & accounts):** error pages 403 / 404 / 503 / security error; My profile;
  Edit profile; Change password; Verify email; Change Student ID; Request an ID review; ID reviews
  list + detail; shared parts avatar, pagination, red unverified-warning bar.
- **Developer 2 (posts & guard house):** **Post page (XL)**; **Create / edit post (XL)** (also used by
  Walk-in item); My posts; My claims; Private claim form view; Report a problem + My reports; Staff
  workspace; Scan QR; Confirm turned in + public turn-in page; Categories + edit.
- **Developer 3 (messages & admin):** Messages; **Chat room (XL)**; chat panel on the post page;
  Report & block; Report a conversation; Notifications; Blocked people; Test inbox; Moderator
  verification; Chat safety reports + detail; General reports + detail; Question bank + edit;
  System settings; Backup status.

Also open:
- Phone first-visit download is larger (photo + fonts); a smaller phone-size photo is an idea for v2.1.0.
- Not tested on real iPhones (Safari) or Android phones, or on the owner's Windows PC.
- The v2.0.0 list asks for every page drawn twice in Figma (PC + phone); these are working pages that
  adapt, not Figma drawings.
