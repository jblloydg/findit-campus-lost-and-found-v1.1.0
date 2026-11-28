# Find-IT v2.1.0 (in progress) — What changed (report)

Work for v2.1.0 happens on branch **`release/2.1.0`** (from `main` = v2.0.0). v2.1.0 = bug fixes for
2.0.0 + redesign of the pages that only got the new colours (`docs/CHANGES_v2.0.0.md` §10).
This file grows with each change; tests and measurements go to `docs/TEST_REPORT_v2.1.0.md`.
Earlier v2.1.0 changes (BUG-019 questions picker on LOST posts, BUG-020 sidebar highlight, CHG-010 to
CHG-012 finder questions in chat, VERSION 2.1.0) are logged in `docs/BUG_REPORTS.md` and CLAUDE.md.

## DES-006 — Report an item: use the whole screen (owner's request, 2026-11-28)
Owner: "In Report an item, use the space so it is not boring to keep scrolling; don't touch the
inputs, only redesign it." Page: `templates/core/post_form.html` (Create post, Edit post, Walk-in item).

| Before | After |
| --- | --- |
| One narrow column (36rem) in the middle of the screen, empty space on both sides | Wide page (up to 90rem; two short columns, so lines stay short) |
| Every field one under another | **PC:** left column "1 · About the item" (Post type and Category side by side, Title, Description, date and time) and "2 · Photos"; right column "3 · Pick ownership questions" (taller list), Meet-up reminder, Cancel / Publish |
| LOST posts: the questions box is hidden (BUG-019), leaving the right side empty | LOST: **Photos move to the right column**, so the whole form fits on one PC screen |
| Publish at the very bottom | Phones/tablets: Cancel / Publish stay at the bottom of the screen while scrolling |

**Not changed:** every field, label, help text, name and id; the photo preview, captcha, question
search / 5-question limit, locked questions on edit, walk-in "Handed over by", the meet-up reminder.
No Python, JavaScript or database changes.

**Scrolling needed to reach Publish** (Chrome, demo data):
| Screen | Before (v2.0.0; Found and Lost were the same length because of BUG-019) | After, Found | After, Lost |
| --- | --- | --- | --- |
| PC 1920 × 916 | 2.2 screens | 1.3 | 0.8 (no scrolling) |
| PC 1280 × 800 | 2.5 | 1.6 | 0.9 (no scrolling) |
| Phone 390 × 844 | 2.6 | 1.7 (button always visible) | 1.7 (button always visible) |

## BUG-021 — Messages icon on phones and tablets
The team said "there is no chat". Chat worked, but on screens up to 768 px the Messages icon in the top bar
was hidden by one CSS line, so Messages was only inside the ☰ menu. The line is removed: the icon and its
red count now show on every screen size (44 × 44 px tap target at 360 px; no sideways scrolling).
File: `static/css/findit.css`.

## BUG-023 — "We posted and still no chat"
The team made posts and waited for a chat. A chat only starts when **another account** taps the message
button on your post; you cannot message your own post. Nothing in the app said so. Now:
- **Messages page:** a line under the title says when a chat appears; with no chats, a new empty state explains
  it and offers **Browse lost items** / **Browse found items**.
- **Your own post** (Next step box): **Chats about this post** lists every chat about it (who, claim chat or
  "May have found your item", date). With none yet it says *No one has messaged you about this post yet* and
  which button the other person must tap.
Files: `core/views.py` (`post_detail`: `author_chats`), `templates/core/post_detail.html`, `templates/core/messages.html`,
`static/css/findit.css`. No database change.

**How the team tests a chat:** use two accounts — a normal browser window signed in as one student and a
private/incognito window signed in as another. Post with account A; open the post with account B and tap the
message button; the chat opens for B and appears under Messages (and on the post) for A.

## Files
`templates/core/post_form.html`, `static/css/findit.css` (new section at the end), `core/tests/test_v210.py` (6 tests).

## Not included yet
- The other §10 pages (post page, chat room, profile pages, staff and admin pages …).
- Reports for the whole v2.1.0 (full bug hunt, performance) when the version is complete.
