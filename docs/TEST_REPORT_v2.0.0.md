# Find-IT v2.0.0 (draft) — Test report (bug hunts and performance)

Branch `design/v2-interface`. Tested on Linux with Chrome (Playwright), Python 3.13, Django 5.2,
demo data from `seed_demo`. Model: `docs/TEST_REPORT_v1.1.1.md`.

## 1. Summary
- **216 automated tests pass** (209 before + 7 new in `core/tests/test_v2_interface.py`). `makemigrations --check`: no changes.
- **Every page, every role, 6 screen widths:** 1,158 page views; the monument photo loaded on all of them; **0 px sideways scrolling** anywhere (BUG-009 fixed).
- **Bug hunts:** crawl (514 pages, 0 crashes), form fuzz (81 routes, 0 problems), address fuzz (0 problems).
- **Readability:** every text colour reaches WCAG 4.5 : 1 or more over the real photo.
- **Speed:** first visit heavier (photo + fonts); later pages as fast as v1.1.1.

## 2. Automated tests
`python manage.py test core` → 216 tests, OK.
New (`test_v2_interface.py`): sidebar and top bar on signed-in pages; sidebar sections per role
(student / guard / admin); dashboard counts; Lost and Found pages; "Report lost item" pre-selects
the type (bad values ignored); landing sections and the safe example ID; **the owner's real ID
never appears** on the landing, log-in, sign-up, password-reset or dashboard pages.
Updated: `test_campus_background.py` (checks `findit.css` and the font files);
`test_session1.py` query guard for `home` raised 11 → 13 for the two *constant* dashboard counts
(it still fails if the page ever does one query per post).

## 3. Bug hunt (whole program, after DES-003)
| Check | Tool | Result |
| --- | --- | --- |
| Every page as 7 roles, crashes (5xx) | `tools/testing/crawl.py` | 514 pages, none |
| Empty / hostile form data on every route | `tools/testing/form_fuzz.py` | 81 routes, 0 problems |
| Broken / hostile addresses (`?page=abc`, SQL text, impossible dates) | `tools/testing/address_fuzz.py` | none |
| Photo on every page, sideways scrolling, screenshots | `tools/testing/campus_bg_check.py` | 1,158 views at 320, 390, 430, 768, 1280, 1920 px × 6 roles: 0 problems |
| Phone drawer | Playwright script | opens from the menu button; closes with ×, Escape and a tap outside; `aria-expanded` updates; focus moves into the menu |
| Visual review | screenshots of all 47 page types (desktop) + key pages on phone | consistent look; issues below fixed |

**Bugs found and fixed during the work (before commit):**
1. Staff workspace heading 129 px too wide for admins at 1280 px (button row could not wrap).
2. Report / account / question filter bars cramped (fixed 5-column grid) → flexible wrapping layout.
3. Empty gap under page headings on phones (a width rule became a height in the stacked layout).
4. Raw inputs on staff pages (chat search, remarks, codes) kept the browser's default look → one base style for every text field.
5. Dashboard and log-in banners downloaded the photo a second time as JPG (+101 KB) → reuse the WebP.
6. Lightest grey text 4.4 : 1 → darkened to 5.3 : 1.

## 4. Readability (contrast, worst case over the real photo)
| Text | Where | Contrast |
| --- | --- | --- |
| Ink headings | light wash, phone + desktop | 10.9–11.1 : 1 |
| Grey body text `#4a5d55` | light wash / landing sections | 4.8–4.9 : 1 |
| Green links `#24574a` | light wash | 5.7–5.8 : 1 |
| White headline | green hero, desktop / phone | 10.5 / 7.3 : 1 |
| Light sage accent | green hero, desktop / phone | 7.3 / 5.1 : 1 |
| Grey text on white cards | cards | 7.0 : 1 (lightest grey 5.3 : 1) |
| Sidebar links / section labels | dark sidebar | 9.9 / 4.8 : 1 |
| Chips (Found, status, amber, violet) | on their own colour | 5.7–7.2 : 1 |
| White on green button | buttons | 8.3 : 1 |
Touch targets: buttons, links in menus and fields are at least 2.75rem (about 44 px) tall.

## 5. Performance (phone, simulated slow network: 1.6 Mbit/s, 150 ms delay, median of 5, local server)
| Page | v1.1.1 (`main`) first visit | v2.0.0 first visit | v1.1.1 next page | v2.0.0 next page |
| --- | --- | --- | --- | --- |
| Landing | 81 KB, 0.78 s | 300 KB, 1.99 s (first paint 1.14 s) | 0.20 s | 0.35 s |
| Log in | 79 KB, 0.77 s | 294 KB, 1.99 s (first paint 1.14 s) | 0.19 s | 0.19 s |
| Dashboard | 79 KB, 0.93 s | 317 KB, 2.08 s (first paint 1.18 s) | 0.34 s | 0.24 s |

What the first visit downloads: photo 116 KB (owner's requirement), fonts 61 KB, stylesheet 82 KB
(**16 KB in production**, where WhiteNoise compresses it), `campus-bg.css` 9 KB, `app.js` 20 KB.
All of it is kept by the browser, so later pages are as fast as before. Server work per page is
the same except 2 small count queries on the dashboard.

## 6. What was **not** tested
- Real iPhones (Safari) and real Android phones; Windows high-contrast mode; screen readers beyond
  the checks above.
- Printing every page.
- The chat with many media files on the new look (the chat code itself did not change).
- On the owner's Windows PC (`FindIT.cmd`) — please run menu 1 and look at the pages.

## 7. Round 2 — after DES-004 (the 9 remaining list items)
- `python manage.py test core`: **228 tests, all pass** (216 + 12 new in `core/tests/test_v2_remaining.py`: verification details, red-flag / verified / not-verified filters, hostile filter value, Developer view vs admin, admin dashboard numbers, withdraw only by the requester and only while open (404 for others, 405 for GET, decided reviews untouched), audit trail and system status for admins only (403 for students and staff, sign-in for visitors), audit action filter, location field hidden by default and shown when `FINDIT_LOCATION_ENABLED` is on, video badge text).
- `makemigrations --check`: no changes. (It caught one mistake during the work, BUG-010, fixed before commit.)
- **Bug hunt, whole program again:** crawl (every page per role, 0 crashes), form fuzz (84 routes, 0 problems), address fuzz (none).
- **Every page, every role at 320, 390, 768, 1280 and 1920 px:** 985 page views, photo on all, 0 px sideways scrolling, including the new Audit trail and System status pages.
- Visual check of the new screens (Accounts with red-flag panel, Edit account verification details, Audit trail, System status, My profile with Withdraw on a phone).
- Not tested: the video badge with a real uploaded video (tested with a rendered example; needs ffmpeg on the PC); the Developer view in a browser (tested in code; the Developer account is made only with `create_developer`).
