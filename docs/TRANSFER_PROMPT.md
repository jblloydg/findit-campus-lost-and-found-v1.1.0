# Paste-ready prompt for a new Claude Code session or chat

Copy everything inside the box into the new session as your first message. Fill in the <...> parts.

---

```
I'm continuing work on Find-IT, a Django campus lost-and-found app (my capstone).

Version for this session: <e.g. v1.1.3 = bug fixes for v1.1.2>

TWO COPIES OF EVERY RELEASE (my rule since v1.1.2)
- PUBLIC repository (work here): https://github.com/jblloydg/findit-campus-lost-and-found-v1.1.0
  Full program, but NO sensitive data: no passwords, no sign-in lists with passwords, no Developer
  account instructions, no real personal data, no private instructions.
- PRIVATE repository (my own copy, only I can see it): <name of my private repo>
  Same branches, plus my private notes (start with PRIVATE-NOTES.md).
- Changes flow PUBLIC -> PRIVATE only: do the work in the public repo, then merge each public branch
  into the private branch with the same name. Never push or merge a private branch into the public repo.
- Branches in BOTH repos: main = released version (only with my approval), release/<version> = work
  in progress, stable/v<version> = frozen rollback copies (never change them).
- Anything sensitive a task needs goes only into the private repo. If unsure, ask me.

READ FIRST: CLAUDE.md (rules and decisions), then HANDOFF.md, docs/ROADMAP.md, the latest
docs/CHANGES_v<version>.md and docs/TEST_REPORT_v<version>.md, and docs/BUG_REPORTS.md.
Do NOT change the read-only repos: jblloydg/findit-campus-lost-and-found and jblloydg/1, /2, /3, /4.

What I want in this session: <describe it>

Bug reports / changes (format in docs/BUG_REPORTS.md):
<paste them here>

How I like to work:
- Ask me questions before building if anything is unclear (use question cards). Plan first for anything
  bigger than a small fix. Tell me if a request goes against a decision in CLAUDE.md, and ask first.
- Don't touch fragile parts unless needed; never break anything for other devices.
- One commit per bug (message starts with its ID), keep all tests passing (including the leak check),
  add a test for each fix, log each fix in docs/BUG_REPORTS.md.
- Example ID 2020-0001, example name Cruz, Juan D. (Dela). Never use the old example ID from the starter
  project anywhere (it's my real account). Never use real people's data.
- Change VERSION and the version labels with every version update.
- Don't merge to main until I approve. When I approve: merge into main and add stable/v<version> in BOTH repos.
- I use Windows; explain things simply. I'm a student.
```

---

## Tips

- **Claude Code on your PC** is best for bug fixing: it can run `FindIT.cmd`, reproduce the bug on Windows and check the fix.
- **A Claude chat** is best for planning, design, Figma and paper writing. Give it the same prompt; it will work from GitHub.
- Start a **new session per batch** of bugs rather than one endless chat — it's faster and uses less of your plan.

Every version I approve must come with docs/CHANGES_v<version>.md and docs/TEST_REPORT_v<version>.md
(bug hunt + performance on phone, web and backend, plain text), like the v1.1.1 ones, and every bug
logged in docs/BUG_REPORTS.md. Use and extend tools/testing/.
