# Find-IT roadmap

## Status of the paper's "Version 2" list in v1.1.0

The V2 list was written before v1.1.0. The four sessions already built most of it.

| Code | Item | Status in v1.1.0 | Built by | Notes |
| --- | --- | --- | --- | --- |
| V2-A | Match suggestions for LOST posts, ranked | ✅ Done | Session 3 | Scored by category, title, description; shown to the LOST author and staff; message after posting. |
| V2-B | More search filters (date, category) | ✅ Done | Sessions 3 + 4 | Date range + admin-managed categories (15 starter categories). |
| V2-C | Approximate time | ✅ Done | Session 2 | With date rules (time needs a date; nothing in the future). |
| V2-D | Approve/reject claims, decision shown to claimant | ✅ Done — **D1 + staff** | Session 4 | Finder or staff decide (D1 with staff able to decide). **D3 (automatic answer checking) rejected** by the owner. |
| V2-E | Profile editing (name, password) | ✅ Done | Session 1 | Plus contact number, profile photo, password reset by email. |
| V2-F | Staff/admin controls: verify moderators, change roles, item/system reports | ✅ Done | Session 1 | Moderator verification, admin account editing (role/status), chat + general reports. |
| V2-G | Guard-house intake form | ✅ Done (no condition notes) | Session 4 | Records received-by, time, method, handed-over-by. Condition notes left out by the owner's choice. |
| V2-H | Daily backups and restore | ✅ Done | Sessions 4 + 1 | Session 4 engine; session 1 admin page, scheduler scripts, OPERATIONS.md. |
| V2-I | School account verification | ✅ Done (local) in **v1.1.1** | v1.1.1 | Optional email code → ✔ Verified; Student ID locked on verification; ID reviews; unverified limits + warning; Report & block. Real email sending and ID-barcode checks → v3.0.0. |
| V2-J | Performance and uptime evidence (→ v3.0.0) | 🟡 Partly | Sessions 1 + 4 | Session 1 measured 15–181 ms medians locally on 3,000 posts (see `docs/handoffs/session-1.md` §D). `/health/` exists. Real proof needs hosting + an uptime monitor. |

**Remaining V2 work: all of V2-J in v3.0.0.** (V2-I done in v1.1.1.)

## Version plan (set by the owner)

| Version | Goal | Status |
| --- | --- | --- |
| **v1.1.0** | Sessions 1–4 integrated. Covers most V1 and V2 goals. | Released (`main`) |
| **v1.1.1** | V2-I school account verification + bug fixes + easier start. | Built on `release/1.1.1`, waiting for owner approval (rollback: `stable/v1.1.0`) |
| **v2.0.0** | Interface overhaul. Lead: *(to be named)* | Planned |
| **v2.1.0** | Fix bugs found in 2.0.0. | Planned |
| **v3.0.0** | Online hosting: put the app on the internet, move SQLite → PostgreSQL, all of V2-J (2.5-second and uptime evidence). | Planned |

### What v1.1.1 contains
- **V2-I school account verification**: optional email code (printed locally + Test inbox), sign-in with email, Student ID rules (shared until verified, 14-day grace, 3 IDs = disabled), ID reviews, unverified limits and warning, Report & block.
- **Developer role** (only it makes admins; `create_developer` command).
- **Easier start** (`FindIT.cmd` menu, `START-HERE.txt`).
- **Bug fixes** BUG-001…003 (`docs/BUG_REPORTS.md`).

### Moved to v3.0.0 (hosting)
- **Confirm the 2.5-second target and reliable uptime** (all of V2-J): needs measurement on the hosted app; the local app alone cannot show them.
- **Daily backups and restore in the online app:** the local command-line engine exists (`backup_now`, `restore_backup`, daily via the timer runner), but the hosted app needs its own scheduler, off-site backup storage and a tested restore procedure (no in-app restore yet).
- **Real email connection** for verification codes, welcome emails and password resets (SMTP / email service); the Test inbox turns off automatically.
- **How to verify an account properly:** read the **barcode on the back of the school ID** (find out what it contains; it can be copied, so combine it with other checks), and decide later security changes.
- **Two-step sign-in** (authenticator app such as Google/Microsoft Authenticator) for the Developer and administrators, set up once on the online site.
Also: PostgreSQL testing and switch, hosting provider, HTTPS, real email (SMTP) for password resets and verification, Redis for live chat across processes, uptime monitor (rest of V2-J), scheduled backups on the server.

### Not scheduled yet
The dormant campus-map location (DOrSU map in segments).

## Known open items (after 1.1.1)

- `FindIT.cmd` (new menu in 1.1.1) still needs a first run on a real Windows PC.
- Browser/UI behaviour, phone layouts, camera QR scanning and two-user live tests not yet done by people.
- PostgreSQL untested. Password-reset email needs SMTP settings when hosted.
- Paper updates needed: see `docs/handoffs/session-4.md` §9 and `HANDOFF.md` §8.
