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
| BUG-008 | Post page: the category tag was empty and its link filtered by name; a dormant location could be shown. | The tag shows the category name and opens Browse filtered by that category. Location shows only when `FINDIT_LOCATION_ENABLED=1`. |

## Security (planned, waiting for the owner's approval of the plan)
| ID | Change |
| --- | --- |
| SEC-001 | Photos and videos: anything hidden inside (steganography, appended files, extra streams, metadata, playlist tricks) ends up as plain color noise, never as readable data. |

## Database migrations
None so far.

## New packages
None so far.

## Tests
`python manage.py test core`: 207 tests (202 from v1.1.1 + 5 new in `core/tests/test_v112.py`).

## Not included / still open
- `FindIT.cmd` still has to be run once on a real Windows PC (it cannot be run in Claude's Linux workspace).
- Real-phone and real-people tests are still open from v1.1.1.
