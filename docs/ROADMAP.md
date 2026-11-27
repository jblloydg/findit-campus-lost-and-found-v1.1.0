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
| V2-I | School account verification | ❌ **Not done** | — | Only the `YYYY-NNNN` format is checked. Needs a decision on how DOrSU can confirm enrollment/employment (registrar list, school email, ID upload + staff check…). |
| V2-J | Performance and uptime evidence | 🟡 Partly | Sessions 1 + 4 | Session 1 measured 15–181 ms medians locally on 3,000 posts (see `docs/handoffs/session-1.md` §D). `/health/` exists. Real proof needs hosting + an uptime monitor. |

**So the real remaining V2 work is V2-I and the hosted half of V2-J**, plus anything new the owner adds.

## Planned next

- **v1.1.1** — bug fixes, reports from testers, interface changes. Branch `release/1.1.1`. Log in `docs/BUG_REPORTS.md`.
- **v2 (maybe)** — after 1.1.1 is stable. Candidates: V2-I, hosting + V2-J evidence, the dormant campus-map location (DOrSU map in segments), finishing PostgreSQL testing, Redis for multi-process chat.

## Known open items carried into 1.1.1

- First real run on Windows not yet done by the team.
- Browser/UI behaviour, phone layouts, camera QR scanning and two-user live tests not yet done by people.
- PostgreSQL untested. Password-reset email needs SMTP settings when hosted.
- Paper updates needed: see `docs/handoffs/session-4.md` §9 and `HANDOFF.md` §8.
