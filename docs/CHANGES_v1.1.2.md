# Find-IT v1.1.2 — What changed (report) — DRAFT, work in progress

Short report of everything fixed in v1.1.2 compared with v1.1.1. Plain text so it can be
read in any Claude session. Bug log: `docs/BUG_REPORTS.md`; tests and measurements:
`docs/TEST_REPORT_v1.1.2.md` (written before v1.1.2 goes to `main`).

v1.1.2 = bug fixes for v1.1.1 reported by testers and the owner. It still runs on one
Windows PC with `FindIT.cmd` (no hosting).

## Branches (rollback)
- `stable/v1.1.1` — frozen v1.1.1 (go back here if v1.1.2 causes trouble).
- `release/1.1.2` — all v1.1.2 work, newest.
- `main` — the released version; updated only with the owner's approval.
Every fix is its own commit (`git log --oneline`), so any single one can be reverted.

## Bugs fixed
| ID | Bug | Fix |
| --- | --- | --- |
| BUG-009 | `FindIT.cmd` opened the login page again about every 20 seconds when nobody pressed a key (seen when Find-IT was opened twice). | The 20-second auto-start now runs only the first time the menu shows. If Find-IT is already running, the extra window opens the browser once and waits; close it or press 0. |
| BUG-010 | Some PCs showed Find-IT with no design (plain text page). Cause: a Windows registry setting changed by another program made the design file look like plain text, so the browser refused it. | Find-IT now always sends its design and script files with the standard types. PCs that were fine are not affected. |
| BUG-008 | Post page: the category tag was empty and its link filtered by name; a dormant location could be shown. | The tag shows the category name and opens Browse filtered by that category. Location shows only when `FINDIT_LOCATION_ENABLED=1`. |

## Security
| ID | Change |
| --- | --- |
| CHG-008 | **No private data in the shared repository.** Demo passwords are no longer in the code or docs: each PC gets random ones the first time the demo data is made, saved in `demo-logins.txt` (ignored by Git) and shown by FindIT.cmd menu 2. Older databases get new ones the first time menu 2 is opened. Developer-account instructions are only in the owner's private notes. A test scans every shared file for leaks, and CLAUDE.md makes this a rule for every version. |
| SEC-002 | Notifications only ever open a page of Find-IT itself. Full web addresses, `//other.site`, backslash tricks such as `/\other.site` and `javascript:` links are refused, both when a notice is created and when it is tapped. |
| SEC-001 (planned, waiting for the owner's approval) | Photos and videos: anything hidden inside (steganography, appended files, extra streams, metadata, playlist tricks) ends up as plain color noise, never as readable data. |

## Changed for testers
- Demo passwords are different on every PC: FindIT.cmd → menu 2 shows yours. The old published passwords stop working once menu 2 or the demo data is run on v1.1.2.
- Developer test scripts in `tools/testing/` read the passwords from `demo-logins.txt`.

## Database migrations
None so far.

## New packages
None so far.

## Tests
`python manage.py test core`: 224 tests (202 from v1.1.1 + 22 new in `core/tests/test_v112.py`).

## Not included / still open
- `FindIT.cmd` still has to be run once on a real Windows PC (it cannot be run in Claude's Linux workspace).
- Real-phone and real-people tests are still open from v1.1.1.
