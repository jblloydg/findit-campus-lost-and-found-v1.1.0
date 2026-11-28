# Find-IT v1.1.1 — What changed (report)

Short report of everything new or fixed in v1.1.1 compared with v1.1.0. Plain text so it can be
read in any Claude session. Details: `HANDOFF.md` → "Changes in 1.1.1"; tests and measurements:
`docs/TEST_REPORT_v1.1.1.md`; bug log: `docs/BUG_REPORTS.md`.

## Branches (rollback)
- `stable/v1.1.0` — frozen v1.1.0 (go back here if v1.1.1 causes trouble).
- `stable/v1.1.1` — frozen first v1.1.1 release (before the media/performance additions below).
- `release/1.1.1` — all v1.1.1 work, newest.
- `main` — the released version; updated only with the owner's approval.
Every change is its own commit (`git log --oneline`), so any single one can be reverted.

## New features
| ID | Feature |
| --- | --- |
| V2-I | **School account verification:** optional 6-digit email code → ✔ Verified (emails printed locally + Test inbox; real email in v3.0.0). Sign in with email, or a verified Student ID. Student IDs shared until one account verifies, then locked (others: 14 days to change or appeal; 3 different IDs = disabled). ID reviews (impostor / lost access / appeal) by verified moderators and admins, with captcha and anti-flood limits. Welcome notices and emails. |
| V2-I | **Unverified limits:** 3 open claims, 3-day claim expiry, 1 post per day, 10 chat messages per 10 minutes (100 characters), 3 photos/videos per chat, smaller file sizes, and a red warning for the other person. Admin-adjustable in System settings. |
| V2-I | **Report & block** (one button, reason optional, "Block" report category; chats/claims closed; unblock from profile). |
| V2-I | **Developer role** above Admin: the only one who makes/removes admins and opens `/django-admin/`; created only on the owner's own computer (steps in the owner's private notes), never through a web page; no email password reset; `createsuperuser` no longer makes admins; demo data refuses to run online. |
| CHG-002 | **Easier start:** `FindIT.cmd` numbered menu (start, demo sign-ins, reset demo data, checks, backup, Developer account), offers to install Python, `START-HERE.txt`. |
| CHG-003 | **Chat message queue:** one-time id per message (never doubled); messages written offline wait on the device and are sent automatically; auto-reconnect. |
| CHG-004 | **Notification queue:** true unread counts on every reconnect, missed notices fetched, each shown once; live red Messages count. |
| CHG-005 | **Messenger-style chat history:** pages sized by bytes (~8 KB / max 50 messages), older messages load by themselves when scrolling up, "Jump to latest". **Search inside a chat** (waits for typing to pause, highlights matches, opens the message in place). |
| CHG-006 | **Photos and videos in chats:** re-encoded on upload (photo → JPEG, video → 720p MP4), fake/unsafe files refused, private files, upload queue saved on the device with progress and auto-retry, background video worker, heavy floods quietly slowed down. |

## Speed (measured — see the test report)
| ID | Change |
| --- | --- |
| PERF-001 | Chat stays smooth with long chats and bursts (9 → 54 fps on a slow phone; chat page 828 KB → 27 KB). |
| PERF-002 | Chat keeps up with many people at once (20.7 s → 0.18 s per message under heavy load; SQLite WAL mode, no lock errors). |
| PERF-003 | Photos compressed on upload, originals never stored or sent (e.g. 3.9 MB → 271 KB); previews in lists; all images load in the background. |

## Bugs fixed
| ID | Bug |
| --- | --- |
| BUG-001 | Chat never showed server errors; typed text was lost when refused. |
| BUG-002 | Damaged claim/student value crashed "Mark returned" and guard-house pickup. |
| BUG-003 | Impossible date in report filters crashed the report lists. |
| BUG-004 | Live notices were pushed before the database save was final. |
| BUG-005 | Chat connection crashed on non-object JSON. |
| BUG-006 | Timer-runner notices never reached open pages. |
| BUG-007 | Chat media files stayed on disk after a chat/post was deleted. |

## Database migrations (run `python manage.py migrate`; FindIT.cmd does it)
- `0012_v111_school_verification` — verification fields, Student ID records, codes, test inbox, ID reviews, blocks, unverified limits. Existing students become verified with a locked ID.
- `0013_v111_compressed_photos` — photo previews; compresses photos from v1.1.0 and deletes their originals.
- `0014_v111_chat_media` — chat photos/videos.

## New package
- `imageio-ffmpeg` (video converter, installs with the other packages; works offline afterwards).

## Not in v1.1.1 (see `docs/ROADMAP.md`)
Interface overhaul (v2.0.0), layouts that adapt from PC to phone with percentage-based sizes
(v2.1.0), online hosting + PostgreSQL + real email + 2-step sign-in + school-ID barcode +
performance/uptime evidence (v3.0.0).
