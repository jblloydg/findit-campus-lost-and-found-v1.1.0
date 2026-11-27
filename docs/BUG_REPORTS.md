# Bug reports and change requests — v1.1.1

Testers: add one entry per problem. Developers/Claude: fix on branch `release/1.1.1`, one commit per entry (`BUG-001: …` or `CHG-001: …`), then fill in the Fix and Status columns.

## How to report

Copy this block, fill it in, and paste it below (or send it to the developer/Claude):

```
ID:           BUG-0XX  (or CHG-0XX for a change request)
Reported by:  your name
Date:
Account used: e.g. 2026-0001 / security.demo / moderator.demo / findit-admin
Page:         e.g. /posts/new/ or "post page of Blue insulated bottle"
Device:       e.g. Windows 11 + Chrome, or Android phone + Chrome
Steps:        1. …  2. …  3. …
Expected:     what should happen
Actual:       what happened instead (copy any error text)
Screenshot:   attach if possible
Priority:     High (blocks testing) / Medium / Low (cosmetic)
```

For a change request (CHG), replace Expected/Actual with **What to change** and **Why**.

## Log

| ID | Summary | Priority | Reported by | Status | Fix commit | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| CHG-001 | Example Student ID changed to 2020-0001, example name Juan / Cruz (sign-in, sign-up, help text, Figma sign-in card) | High (privacy) | Owner | Fixed, also copied to main | 95ff430 (main: bd1bf55) | Old example was the owner's real account |
| V2-I | School account verification (optional email code, ✔ Verified, Student ID rules + ID reviews, unverified limits + warning, Report & block, Developer role) | High (last V2 goal) | Owner | Fixed (on release/1.1.1) | af4244d, ad56a17 | See HANDOFF.md → Changes in 1.1.1 |
| BUG-001 | Chat never showed server error messages (e.g. "read-only", limits) and cleared the typed text even when the message was refused | Medium | Claude (code review) | Fixed (on release/1.1.1) | b16efea | `connectionText` in chat.js was never set |
| CHG-002 | Running v1.1.0 was confusing: FindIT.cmd is now a numbered menu that installs Python if missing; new START-HERE.txt | High (usability) | Owner | Fixed (on release/1.1.1) | 0518e34 | Reviewed, not run, on Windows yet — please test menu 1–6 |
| CHG-003 | Chat: outgoing message queue + one-time id per message, so nothing is lost or duplicated when the connection drops (auto-reconnect, catch up on missed messages, queue survives a reload) | High (owner's condition for release) | Owner | Fixed (on release/1.1.1) | 4448655 | Tested in a real browser with the server stopped and restarted |
| CHG-004 | Notifications: server-side queue (true counts on every reconnect + missed notices), each notice shown/counted once, live red Messages count; chat and notices reconnect within 10 s | High (owner's condition for release) | Owner | Fixed (on release/1.1.1) | e441aa6 | Browser-tested across a server restart |
| BUG-004 | Live notices and chat updates were pushed before the database save was final (a failed save could show a notice that does not exist) | Medium | Claude (chat/notification bug hunt) | Fixed (on release/1.1.1) | 930f969 | Push now waits for the save |
| BUG-005 | Chat WebSocket crashed on valid JSON that is not an object, e.g. `[1]` | Medium | Claude (chat/notification bug hunt) | Fixed (on release/1.1.1) | 1e463bb | Answers "Invalid message" |
| BUG-006 | Notices made by the timer runner (claim expiry, cleared Student IDs) never reached pages that were already open | Low | Claude (browser test) | Fixed (on release/1.1.1) | e441aa6 | Open pages re-check about once a minute |
| BUG-002 | A damaged `claim_id` or student value crashed "Mark returned" and guard-house pickup (error 500) | Low (needs a tampered form) | Claude (form fuzzing) | Fixed (on release/1.1.1) | 115cd90 | Now 404 / clear message |
| BUG-003 | An impossible date such as 2026-99-99 in report filters crashed /staff/reports/ and /staff/general-reports/ (error 500) | Low | Claude (address fuzzing) | Fixed (on release/1.1.1) | e221ac3 | Invalid dates are ignored, like Browse |

Status values: Open → Confirmed → Fixed (on release/1.1.1) → Verified by tester → Released in v1.1.1.
