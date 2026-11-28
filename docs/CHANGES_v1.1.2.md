# Find-IT v1.1.2 — What changed (report) — DRAFT (the test report comes before approval)

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
| SEC-001 | **Hidden data in photos and videos becomes plain pixels.** Photos (posts, profiles, status requests, chats, video posters): only real JPEG, PNG and WebP pictures are opened (a BMP, TIFF or GIF renamed to .png gets a clear "JPG, PNG, or WebP" message); the two lowest bits of every colour value are replaced by random noise (at most 3 of 255 colour steps, invisible); no EXIF, comments or colour profile are kept (wide-colour phone photos are converted to normal sRGB first, so they look the same); every result is checked to be one clean JPEG with nothing after its end. Chat videos: recognised by their first bytes (MP4/MOV/3GP or MKV/WebM only), so playlist or "concat" files that point to other files or websites are refused; ffmpeg may only read local files; only one picture and one sound stream are kept (subtitles, data, attachments, chapters and metadata dropped); a faint grain turns hidden bits in the frames into noise; the finished MP4 is checked; ffmpeg runs at lower priority with time limits. |

## Speed (measured)
- 12-megapixel phone photo → stored copy: 452 ms → 539 ms (SEC-001 noise and checks).
- 15-second 1080p chat video → stored copy: 3.0 s → 4.1 s (in the background worker; the chat stays quick).

## Changed for testers
- A picture that is really a BMP, TIFF or GIF (even if renamed .jpg/.png) is now refused with a clear message.
- Demo passwords are different on every PC: FindIT.cmd → menu 2 shows yours. The old published passwords stop working once menu 2 or the demo data is run on v1.1.2.
- Developer test scripts in `tools/testing/` read the passwords from `demo-logins.txt`.

## Database migrations
None so far.

## New packages
None so far.

## Tests
`python manage.py test core`: 235 tests (202 from v1.1.1 + 33 new in `core/tests/test_v112.py`).

## Not included / still open
- `FindIT.cmd` still has to be run once on a real Windows PC (it cannot be run in Claude's Linux workspace).
- Real-phone and real-people tests are still open from v1.1.1.
