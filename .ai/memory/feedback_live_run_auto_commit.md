---
name: feedback-live-run-auto-commit
description: "During Tony's live-run feedback sessions, small Ground fixes may be committed without asking; group pushes to save CI runs"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 839a6ef5-0afc-40b3-bf0f-0a9378eb2d7f
  modified: 2026-11-05T04:47:18.706Z
---

During a live run test (first one 2026-11-05), Tony allowed committing small Ground fixes from his feedback without asking each time ("yes allow auto commit, try to group pushes together to save CI runs"). Post each hash in Chat. CoCo and Mendy do the coding; the Assistant stays in conversation and logs items as LR-n in `.ai/sessions/<date>-claude-live-run/README.md`.

**Why:** he's testing live and wants fixes to flow without a prompt per commit, but each push runs the full CI on three OSes.

**How to apply:** commit tested fixes on Ground freely during a live run; push in batches (at a natural pause or when CI on all OSes is worth it), never per commit. Still never amend ([[feedback-no-amend-on-ground]]). Outside a live run, the usual ask-before-commit rule holds ([[feedback-ask-before-commit]]).
