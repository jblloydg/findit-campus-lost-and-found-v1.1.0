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

## CHG-013 — "I found this – message the owner"
The team could not find how a finder contacts the owner of a LOST post.
- On **LOST** posts the button "Message poster" is now **I found this – message the owner** (green, with a chat
  icon) and a one-line hint: the chat opens privately and the ＋ menu there has *Ownership questions*.
  Signed out: **Sign in to message the owner**. **FOUND** posts keep **Claim this item** / **Message poster**.
- On **phones and tablets** the main buttons now appear **right under the title** (390 × 844 phone: about
  600 px from the top, in the first screen — before about 1,350 px, below photos and comments). On PC they stay
  in the Next step box on the right. Same buttons, one shared file
  (`templates/core/includes/post_primary_actions.html`), so they can never differ.

## CHG-014 — Tester accounts for chat testing (owner's private copy)
`python manage.py seed_demo` can make the owner's two **tester students**: one has posted a FOUND item
(*Gray backpack with keychain*), the other a LOST item (*Silver USB flash drive*), and they already chat with each
other on **both** posts (the FOUND tester is the finder in both chats, so they have **＋ → Ownership questions** and
the other tester answers).
- **Accounts are sensitive**, so this shared repository has no tester names, emails, Student IDs or passwords.
  They are in `tester-accounts.txt`, which Git ignores here and which only the owner's private copy contains
  (one line per account: `Student ID | email | first name | last name | FOUND or LOST | password`).
- Without that file `seed_demo` makes no tester accounts; everything else works as before.
- Running `seed_demo` again keeps the passwords and never duplicates the posts or chats.
- Team: ask the owner for the tester sign-ins. Test with two windows (normal + private), one per tester.

## DES-007 — Messenger-style chat bar and the chat window
**Chat bar** (full chat page and chat window): **＋ · message · Send**, nothing else.
- The round **＋** opens a small menu (a pop-up above the bar on PC, a bottom sheet on phones):
  **Photo or video** (the old 📎 button moved here; same limits, previews, progress, waiting / processing /
  failed states) and, **only for the finder**, **Ownership questions (N left)**, which opens the same
  question picker as before as a card above the bar (title row closes it).
- For a finder who has not sent questions yet, the ＋ has a soft green ring (it pulses 3 times unless the
  phone asks for less motion), and the hint line says *Tap ＋ → Ownership questions*.
- The message field grows with the text (up to about 6 lines). Esc, a tap outside or picking an item
  closes the menu; arrow keys move in it; focus goes back to ＋ (`aria-expanded`, `role="menu"`).
- "Jump to latest" stays hidden in an empty chat (the global `[hidden]` rule from BUG-019 already fixed
  this; checked again).

**Chat window over the post page** (owner: "partial cover, the post stays where they left off"):
- On a post, **💬 Chat**, **I found this – message the owner**, **Message poster**, **Open chat** (claim card),
  the claim list's **Chat** links and the author's **Chats about this post** open the chat in a big window
  over the post (PC: up to 60rem × 52rem with the post dimmed around it; phone: slides up, leaving the top
  bar visible).
- While it is open the address bar shows the chat's own link **`/conversations/<id>/`**, so the chat has
  the same address as always (a moderator can open that link for a manual review). **×**, **Esc**, a tap on the
  dimmed post, or the phone's **Back** button close it, and the post is exactly where it was (same scroll
  position). Ctrl/⌘-click or a reload opens the normal full chat page.
- Inside the window the chat is the full chat (search, question cards, ＋ menu, photos/videos, report links);
  ordinary links open in the main window.
- How: the chat page has a compact "window" mode without the sidebar (`templates/core/chat_embed_base.html`,
  chosen when the browser loads it in a frame — `Sec-Fetch-Dest: iframe` — or with `?embed=1`).
- Security: `X-Frame-Options` changed from DENY to **SAMEORIGIN** — Find-IT can show its own pages in a
  frame; other websites still cannot (clickjacking protection stays on).
- The old small chat panel on the post page was removed (it could only send text), so the post page no
  longer loads chat messages itself (one database query less).

**Also fixed:** in a scrolling question list (chat picker and Report an item), rows were squeezed to the
2.75rem minimum and the small "Choose from a list" line spilled out of the boxes; rows now keep their height.

Files: `templates/core/chat_room.html`, `templates/core/chat_embed_base.html` (new), `templates/core/post_detail.html`,
`templates/core/includes/icon.html` (image icon), `static/js/chat.js`, `static/js/app.js`, `static/css/findit.css`,
`core/views.py` (`_is_embedded`, `chat_room`, `post_detail`), `findit/settings.py` (`X_FRAME_OPTIONS`).

## BUG-024 — Sign-in problems the team ran into
Checked every way of signing in in Chrome (login page, landing page, the pop-up on a post, phone and PC,
`127.0.0.1` and `localhost`): signing in works. What confused people, now fixed:
- New student accounts are **not verified**, and a Student ID only works after the email is verified
  (decision 12). Typing the Student ID only said "Sign-in failed". Now: *A Student ID only works after your
  email is verified, so sign in with your email address instead.* (Shown for any Student ID, so it does not
  reveal whether an account exists.)
- Staff/admin usernames were case-sensitive (`Security.Demo` failed). Now any case works (only when exactly
  one account matches).
- The top **Log in** button on a post page went to the dashboard after signing in; it now comes back to the post.
Files: `core/auth.py`, `core/views.py` (`login_view`), `templates/core/base.html`.

## DES-008 — The chat window opens over any page
Owner: "just a chat window overlaying the interface the web is on". Any link to a chat — a row in
**Messages**, a chat notice in **Notifications**, a chat link in **My claims**, the post page buttons — opens
the chat window over the page you are on. The address bar shows the chat's link while it is open;
**× / Esc / Back** close it and you are back on that page as you left it. A reload or Ctrl/⌘-click opens the
full chat page. Files: `templates/core/base.html` (the window), `templates/core/post_detail.html`, `static/js/app.js`.

## CHG-015 — "Who sets At Guard House / Claim in Progress?"
The team could not find where to type a status. Nobody types it, and it is not AI: Find-IT changes the status from what
people do, and **At Guard House** can only be set by a guard (staff) who scans the finder's turn-in QR / code or records a
walk-in (decision 7, for security). This is now explained on every post (**How does the status change?** under the facts)
and in the reminder on Report an item. Files: `templates/core/includes/status_help.html` (new), `post_detail.html`, `post_form.html`, `findit.css`.

## CHG-016 — Bringing a found item to the guard house: easy to find
The team could not find where a finder asks to bring an item to the guard house. It existed only as a button in the
Guard house box far down the post. Now:
- **While posting** a FOUND item: a tick box **I'll bring this item to the guard house** (hidden for LOST). After
  Publish, staff are told and the finder sees the turn-in code.
- **On the post**, the finder's **I'm bringing it to the guard house** (or, once chosen, **Show my turn-in QR for the
  guard house**) is with the main buttons — under the title on phones, in Next step on PC.
- Then, as before, the guard scans the QR / types the code and the post becomes **At Guard House** (only staff can).
Files: `templates/core/post_form.html`, `templates/core/includes/post_primary_actions.html`, `templates/core/post_detail.html`,
`core/views.py` (`create_post`), `static/js/app.js`, `static/css/findit.css`.

## CHG-017 — Chats stay possible when the item is at the guard house
Owner: if the owner of a lost item contacts the author of an "At Guard House" post, the chat must still work so the
author can help. Before, new chats were refused once the item reached the guard house (only existing ones stayed open).
Now the message button stays on the post and starts a chat; only **Claimed** and **Closed** posts take no new chats.
Files: `core/views.py` (`_conversation_for_post`, `post_detail` → `can_message`), `post_primary_actions.html`.

## CHG-018 — Every status can be reached by clicking + a step-by-step guide
- **Guide:** `docs/STATUS_GUIDE.md` — for each status, which role (finder, owner/claimant, guard, admin) presses which
  button, in order, plus a small map.
- **Proof:** `tools/testing/status_journeys.py` plays 5 journeys in Chrome by clicking, as the demo finder, claimant,
  owner and guard: FOUND handed over in person; FOUND via the guard house (code typed at Scan turn-in QR);
  LOST with ownership questions in the chat; guard house and back; closed. **18 of 18 steps pass**, no script errors.

## Files
`templates/core/post_form.html`, `static/css/findit.css` (new section at the end), `core/tests/test_v210.py` (6 tests).

## Not included yet
- The other §10 pages (post page, chat room, profile pages, staff and admin pages …).
- Reports for the whole v2.1.0 (full bug hunt, performance) when the version is complete.
