# Find-IT — How each post status happens (step by step, v2.1.0)

Nobody types a status. Find-IT changes it when the right people press the right buttons. This guide lists, for
every status, **who** must do **what**, in order. Every path below was clicked through in a real browser with
`tools/testing/status_journeys.py` (18 of 18 steps pass, 2026-11-28).

**Roles**
| Role | Who | Can do |
| --- | --- | --- |
| **Finder** | The student who has the item: the author of a FOUND post, or the person who tapped "I found this" on a LOST post | Approve / decline the owner, mark returned, bring it to the guard house |
| **Owner / claimant** | The student who lost the item: claims a FOUND post, or is the author of a LOST post | Claim, answer ownership questions, confirm "I received it" |
| **Guard (Staff)** | A Staff account (security guard) | Confirm an item arrived at the guard house (QR / code / walk-in), release it, review status requests |
| **Admin** | Administrator | Everything staff can, plus settings |

To test, use **two or three browser windows** (normal + private window, or two browsers), one per role.

---

## 1. Open for Claim
Every new post starts here.
1. **Any student** → sidebar **Report found item** (or **Report lost item**) → category, photos → **Publish post**.
2. The post is **Open for Claim**.

It also comes back to **Open for Claim** when: the only claim is withdrawn, closed, declined or expires; or a guard
approves a finder's request to **take the item back from the guard house** (see 3c).

## 2. Claim in Progress
**FOUND post (someone claims it)**
1. **Owner** opens the post (Browse / Found items / search) → **Claim this item**.
2. Answers the ownership questions + description → **Submit private claim**.
3. The post is **Claim in Progress**. The finder gets a notice and sees the claim in **Claim applications**.

**LOST post (a finder checks the owner)**
1. **Finder** opens the LOST post → **I found this – message the owner** → the chat window opens.
2. In the chat: **＋ → Ownership questions** → tick at least 3 → **Send questions**.
3. The post is **Claim in Progress** (the first question starts the owner verification).
4. **Owner** (the LOST post's author) answers the question cards in the chat (Messages → the chat).

## 3. At Guard House
Only a **guard (Staff)** can set this, and only with the item in hand.

**3a. Finder brings it**
1. **Finder**: while posting a FOUND item, tick **I'll bring this item to the guard house** — or later, on the post,
   tap **I'm bringing it to the guard house** (LOST post finders: **Bring it to the guard house** in the chat).
2. The finder shows the **turn-in QR or code** (on the post: **Show my turn-in QR**).
3. **Guard** → sidebar **Scan turn-in QR** → scan the QR (camera) **or** type the code → **Look up code** →
   **Confirm turned in**. The post is **At Guard House**.
   (A guard can also open the post and use **Confirm received at guard house**.)

**3b. Someone hands it in at the counter (walk-in)**
1. **Guard** → **Walk-in item** → fill in the item → **Post and record at guard house**. The new FOUND post starts
   **At Guard House**.

**3c. Finder wants it back** (e.g. the owner contacted them directly)
1. **Finder** → on the post, Guard house box → **Request a status change** → *Take the item back from the guard house*
   (or *Close the listing*) → reason (+ optional photo) → **Send to staff**.
2. **Guard** opens the post → **Approve**. The post goes back to **Open for Claim** (or **Claim in Progress** if a
   claim is still active), or **Closed**.

While **At Guard House**, existing claims and chats stay open, and people can still **message the poster**.

## 4. Returned (handed over in person)
1. A claim must be **approved** first:
   - FOUND post: **Finder** → post → **Claim applications** → **View form** (read the answers) → **Approve**.
   - LOST post: **Finder** → chat → **Approve** (unlocks after at least 3 questions are all answered).
2. They meet **on campus**. **Finder** → **Mark returned** (FOUND: on the post; LOST: **Mark returned to owner** in the chat).
3. The post is **Returned**. The owner gets a notice to confirm.

## 5. Claimed (finished)
- **Handed over in person:** **Owner** → post (or chat) → **Confirm I received it**.
- **Picked up at the guard house:** **Guard** → post → **Release at guard house** next to the approved claimant
  (or **Release to student without an approved claim**, choosing the student).
- The post is **Claimed** and leaves the active listings (it stays viewable for reference).

## 6. Closed
1. **Author** (or staff) → post → Manage listing → optional reason → **Close listing**.
2. The post is **Closed**: no new claims, comments or chats; it stays viewable.
(A guard can also close it by approving a finder's *Close the listing* request at the guard house.)

---

## Quick map
```
            Publish post
                 │
          Open for Claim ──────────────── Close listing ──→ Closed
                 │ claim submitted (FOUND) / first ownership question (LOST)
        Claim in Progress
          │                     │ guard confirms QR / code
          │ finder approves     ▼
          │ + Mark returned   At Guard House ── guard approves "take back" ──→ Open / Claim in Progress
          ▼                     │ guard: Release at guard house
       Returned                 ▼
          │ owner: Confirm I received it
          └──────────────────→ Claimed
```
Also: a claim inactive for 7 days expires (the post goes back to Open for Claim if no other claim is active).
