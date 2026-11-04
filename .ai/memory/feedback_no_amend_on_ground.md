---
name: feedback-no-amend-on-ground
description: "Never amend or rewrite commits on Ground's dev branch: something on Tony's Mac may push them within seconds"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 5eeacb26-6362-4096-8436-8fa5952380db
  modified: 2026-11-04T01:25:24.670Z
---

Never `git commit --amend`, rebase or reset over a commit on Ground's dev branch, even one you believe is local only.
Always add a new commit.

**Why:** on 2026-11-04 CoCo committed aa78cc1 on dev/v0.0.9 without pushing. It reached GitHub 24 s later, pushed by
something else on the Mac. CoCo then amended it, and the amended commit was force-pushed (aa78cc1 → 3db8250) after
CoCo's own push had been rejected. Nothing was lost, but it was a force push on Tony's branch. The source wasn't known
when this was written; Tony was asked.

**How to apply:** treat every Ground commit as published. Run `git fetch` and compare with origin before any history
operation, and prefer a follow-up commit. Related: [[feedback-keep-branches-on-github]].
