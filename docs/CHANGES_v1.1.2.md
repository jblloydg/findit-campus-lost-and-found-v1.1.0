# Find-IT v1.1.2 — Patch notes (what changed and why)

v1.1.2 = **bug fixes and security updates** for v1.1.1, reported by testers and the owner.
No new pages or features for users; the program still runs on one Windows PC with `FindIT.cmd`
(no hosting). Plain text so it can be read in any Claude session.

Related files: bug log `docs/BUG_REPORTS.md`; tests and measurements `docs/TEST_REPORT_v1.1.2.md`
(written before v1.1.2 goes to `main`).

## Summary
| ID | Type | In one line |
| --- | --- | --- |
| BUG-009 | Bug | The start window no longer reopens the login page every 20 seconds. |
| BUG-010 | Bug | The design (colours, layout) now shows on every Windows PC. |
| BUG-008 | Bug | The category link on a post page works; the dormant location stays hidden. |
| SEC-001 | Security | Anything hidden inside a photo or video ends up as meaningless colour noise. |
| SEC-002 | Security | Tapping a notification can never send someone to another website. |
| CHG-008 | Security / privacy | No passwords or private instructions in the shared repository; demo passwords are made fresh on each PC. |
| — | Version | `VERSION` and all labels say 1.1.2; README updated (update steps with Git Bash). |

## Branches (rollback)
- `stable/v1.1.1` — frozen v1.1.1 (go back here if v1.1.2 causes trouble).
- `release/1.1.2` — all v1.1.2 work, newest. `main` — the released version (only with the owner's approval).
- Every fix is its own commit (`git log --oneline`), so any single one can be undone alone (`git revert <commit>`).
- From v1.1.2 the owner also keeps a private copy of every release with the same branches (see CLAUDE.md).

---

## Bug fixes

### BUG-009 — Login page reopened every 20 seconds
- **What people saw:** when Find-IT was opened twice (for example the shortcut double-clicked twice),
  a new browser tab with the login page opened about every 20 seconds.
- **Why it happened:** the second black window noticed Find-IT was already running, opened the browser
  and went back to the menu. The menu starts by itself after 20 seconds, saw "already running" again,
  opened the browser again — forever.
- **Fix (idea):** the 20-second automatic start happens **only the first time** the menu shows. In the
  "already running" case the extra window opens the browser **once** and then waits for a key.
- **File:** `FindIT.cmd`.

### BUG-010 — Design missing on some PCs
- **What people saw:** on a few PCs Find-IT showed as a plain white page with no colours or layout,
  while most PCs looked normal.
- **Why it happened:** Windows keeps a list of file types in its registry. Some programs change that list
  so `.css` (the design file) counts as plain text. Python reads that list, so Find-IT sent the design
  as "plain text", and browsers refuse to use a design sent that way.
- **Fix (idea):** when Find-IT starts, it sets the standard types for its own files (`.css`, `.js`, `.svg`,
  `.json`, `.webp`, `.woff2`). PCs that were fine already used these values, so nothing changes for them.
- **File:** `core/apps.py`.

### BUG-008 — Post page category link
- **What people saw:** the category tag on a post page was empty, and its link did not filter Browse.
- **Fix:** the tag shows the category name and opens Browse filtered by that category. The location
  (a dormant future feature) is shown only when `FINDIT_LOCATION_ENABLED=1`, like everywhere else.
- **Files:** `templates/core/post_detail.html`, `core/views.py`.

---

## Security updates

### SEC-001 — Hidden data in photos and videos becomes plain pixels
**The problem it protects against.** A picture or video can carry hidden data:
- *steganography* — a message hidden in the tiniest colour differences of the pixels;
- a file (for example a ZIP) glued to the end of the picture;
- hidden fields (EXIF, comments, colour profiles) or extra "streams" inside a video (subtitles,
  attachments, data);
- a fake "video" that is really a playlist telling the converter to read other files or websites.

Hidden data cannot run by itself; the danger is a program (for example a keylogger already on someone's
PC) that later reads it, or a converter tricked into reading files it should not. **The idea of SEC-001:
the stored copy contains only ordinary picture and sound data — anything hidden becomes meaningless
colour noise, so there is nothing left to read.**

**What Find-IT does with every photo** (post photos, profile pictures, status-request photos, chat
photos and video preview pictures):
1. **Only real JPEG, PNG and WebP pictures are opened.** The real type is checked from the file
   contents, not the name. A BMP, TIFF or GIF renamed to `.png` gets a clear "JPG, PNG, or WebP" message.
2. **The picture is redrawn from scratch** as a new JPEG, smaller (1600 px / 480 px previews). Anything
   glued to the end, and all hidden fields (EXIF incl. GPS location, comments, colour profiles), are
   left behind. Phone photos with a wide-colour profile are converted to normal colours first, so they
   look the same.
3. **The two lowest bits of every colour value are replaced by random noise.** Hidden messages usually
   live exactly there. The change is at most 3 of 255 colour steps — people cannot see it (measured:
   1.4 steps on average; the normal JPEG compression already changes about 2.5).
4. **The result is checked:** it must be exactly one clean JPEG with nothing after its end and no hidden
   fields; otherwise it is refused.

**What Find-IT does with every chat video:**
1. **Recognised by its first bytes**, not its name: only MP4 / MOV / 3GP and MKV / WebM are accepted.
   Playlists (HLS) and "concat" lists that point to other files or websites are refused before the
   converter (ffmpeg) even opens them.
2. **The converter may only read local files**, and Find-IT tells it exactly which reader to use.
3. **Only one picture stream and one sound stream are kept**; subtitles, attachments, fonts, data
   streams, chapters and all metadata are dropped. The video is always fully re-encoded (H.264 + AAC MP4).
4. **A faint moving grain** is added to the frames, so hidden bits in the frames become noise.
5. **The result is checked:** one H.264 video stream, at most one AAC sound stream, nothing else, no
   personal metadata; otherwise refused.
6. **Runs safely:** the converter is a separate program with a time limit, in a temporary folder,
   without a command shell, at lower priority than the website. The received file is deleted.

Files: `core/images.py`, `core/chat_media.py`, `core/validators.py`. Tests: 11 "hostile file" tests in
`core/tests/test_v112.py` (hidden pixel bits, appended ZIP, metadata and colour profile, disguised
formats, subtitle/attachment streams, playlist and concat files).

### SEC-002 — Notifications only open Find-IT's own pages
- **The problem:** a notification opens a page when tapped. A link written as `/\other.site` passed the
  old "is this our own page?" check, but browsers treat it as `//other.site` — another website.
- **Fix (idea):** a notification link must be a plain path of Find-IT itself. Full web addresses,
  `//other.site`, backslash tricks, hidden control characters and `javascript:` links are refused, both
  when a notification is created and when it is tapped (then the Notifications page opens instead).
- **Files:** `core/security.py`, `core/views.py`, `core/verification.py`.
- **Links in posts, comments and chats** stay plain text that cannot be clicked (no change), so nobody can
  be sent to another website by tapping something another user wrote.

### CHG-008 — No private data in the shared repository
- **The problem:** the shared (public) repository listed the demo passwords and explained the owner's
  special account.
- **Fix (idea):**
  - Demo passwords are **no longer written anywhere** in the code or docs. The first time the demo data is
    made on a PC, every demo account gets its **own random password**, saved in `demo-logins.txt` on that
    PC only (Git never uploads it). FindIT.cmd **menu 2** shows them. Older PCs get new ones the first time
    menu 2 is opened, so the old published passwords stop working.
  - Instructions for the owner's special account are kept only in the owner's private copy.
  - A test scans every shared file and fails if a password or those instructions ever come back.
  - Rule for every future version: two copies of each release — public (without private parts) and the
    owner's private copy (with them).
- **Files:** `core/demo_logins.py`, `core/management/commands/seed_demo.py`, `FindIT.cmd`, docs, test scripts.

---

## Speed (measured)
| What | v1.1.1 | v1.1.2 | Note |
| --- | --- | --- | --- |
| 12-megapixel phone photo → stored copy | 452 ms | 539 ms | SEC-001 noise and checks |
| 15-second 1080p chat video → stored copy | 3.0 s | 4.1 s | done in the background; the chat stays quick |

## Changed for testers
- Demo passwords are different on every PC: **FindIT.cmd → menu 2** shows yours.
- A picture that is really a BMP, TIFF or GIF (even if renamed .jpg/.png) is refused with a clear message.
- The 20-second automatic start happens only once; opening Find-IT twice no longer loops.
- Developer test scripts in `tools/testing/` read passwords from `demo-logins.txt`.

## Database migrations
None.

## New packages
None.

## Tests
`python manage.py test core`: **235 tests** (202 from v1.1.1 + 33 new in `core/tests/test_v112.py`), all passing.
`makemigrations --check`: no changes.

## Not included / still open
- `FindIT.cmd` (BUG-009) and the design fix (BUG-010) still need one check on a real Windows PC
  (they cannot be run in Claude's Linux workspace).
- Screenshots and PDFs attached to "Report a problem" are still stored as uploaded (private, only the
  reporter and staff see them) — owner to decide whether SEC-001 should cover them.
- Older versions of files on GitHub still show the old demo passwords (history is never rewritten);
  they no longer open anything set up with v1.1.2.
- Real-phone and real-people tests are still open from v1.1.1.
