# Paste-ready prompt for a new Claude Code session or chat

Copy everything inside the box into the new session as your first message.

---

```
I'm continuing work on Find-IT, a Django campus lost-and-found app (my capstone).

Repository to work in: https://github.com/jblloydg/findit-campus-lost-and-found-v1.1.0
- Clone it, then read CLAUDE.md first (project rules and decisions), then HANDOFF.md and docs/ROADMAP.md.
- Work only on the branch release/1.1.1. main is the stable v1.1.0 (tag v1.1.0 = rollback point).
- Do NOT change the read-only repos: jblloydg/findit-campus-lost-and-found and jblloydg/1, /2, /3, /4.

What I want in this session: <describe it, e.g. "fix the bugs below" or "plan interface changes">

Bug reports / changes (format in docs/BUG_REPORTS.md):
<paste them here>

How I like to work:
- Ask me questions before building if anything is unclear — I prefer many questions over a wrong implementation.
- Tell me if a request goes against a decision in CLAUDE.md, a role/status name, or the paper, and ask first.
- One commit per bug (message starts with the bug ID), keep all tests passing, add a test for each fix,
  log each fix in docs/BUG_REPORTS.md, and add a "Changes in 1.1.1" section to HANDOFF.md.
- Don't merge to main or tag v1.1.1 until I approve.
- I use Windows; explain things simply.
```

---

## Tips

- **Claude Code on your PC** is best for bug fixing: it can run `FindIT.cmd`, reproduce the bug on Windows and check the fix.
- **A Claude chat** is best for planning, design, Figma and paper writing. Give it the same prompt; it will work from GitHub.
- Start a **new session per batch** of bugs rather than one endless chat — it's faster and uses less of your plan.
