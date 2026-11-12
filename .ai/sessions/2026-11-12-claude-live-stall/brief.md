# Brief: Live stops picking up shots after a conversion (`agent/live-stall`)

Coordinator: CoCo, 2026-11-12. Tony in Chat: "there's a bug with live, where process can get stuck on waiting for a
d raw file to settle"; "live d raw kept coming in, but helab activity window shows waiting for a very old d raw to
settle"; HeLab ran on the same computer that writes the raw files (no clock skew); "we shouldn't hang on to waiting for
file to settle after say 15s timeout?". Then "ok go" to this floor. One Worker finds the cause and fixes it; one
Reviewer reads the fix; the floor lands on `dev/v0.0.9` with Tony's OK.

Base: `d2bd306` (`dev/v0.0.9`).

## The evidence

The TDC PC's logs (Windows 11, Live with auto-convert **beside** the raw files, a local folder
`…\my_read_tdc_gui_v1.0.1\dld_output`, about one shot every 25 s) are copied, read only, to Ground's gitignored
`/Users/tonyyan/GitHub-Local/HeLab/.ai/local/live-stall-logs/` (`helab-8896.log`, `console-8896.txt`,
`helab-14688.log.1`, `helab-14688.log`, `console-14688.txt`, `helab-1456.log`, `helper-crash-1252.txt`). Never copy
them into the branch or quote lab paths in commits; quote lines in your notes with paths shortened.

What CoCo read so far (check it, don't trust it):

- Normal cycle, every ~25 s: `convert_done … converted=0 … waiting=1` (the new raw file still being written), then
  `convert_done … converted=1`, then `load_done … shots=N+1 source=folder live=true` (Live's check picks up the new
  TXY), then plot_done lines.
- **It stopped twice** on 2026-11-11: `helab-14688.log.1`, last `convert_done converted=1` at 13:56:16, no
  `load_done` after it, nothing until Live off/on at 15:51 (which converted 262 shots at once); `helab-8896.log`, last
  `convert_done converted=1` at 16:38:50 (shot 2391), no `load_done` after it, no conversion or Live load until Live
  off at 18:08; "Memory while Live: … 1,014 shots, revision 29" unchanged throughout, while raw files kept arriving.
- Both times a GUI stall (2–4 s) was under way as that last conversion ended (13:56:13–16; 16:38:46–50). At 16:39:20
  the stall's stacks show no IOService reader thread, i.e. no helper running: nothing was in flight, yet nothing new
  was asked for.
- Live's loop: `explorer_live._live_tick` returns early when `session.request` (a Live check in flight) or
  `session.error`; `_convert_tick` (called only from `_live_tick` and two answer handlers) returns early when
  `convert.request`, `convert.error`, `self.box`, or within `live_interval` of `ended_at`. A request or end that is
  lost, or a timer not restarted, stops both for good. Hypothesis, unconfirmed: a race between the conversion's end,
  the Live check's end and `check_soon`/the Live timer while the GUI was stalled (events delivered in one `_tick`).
- The Activity window's "waiting for a very old d raw to settle" is probably the last `shot_waiting` of a conversion
  left on display; check how Activity shows a Live conversion that ended, and whether a waiting entry is ever cleared.
- 70 GUI stalls (2–5 s) between 16:39 and 18:08; the GUI thread's stacks: `workspace._update_plot_source_label` from
  `HelabMainWindow._update_folder_details` (29), `explorer_live.low_hits_threshold` → `read_setting` from
  `convert_line` (28; A73.4 (d)).
- The log says "Commit: unknown" (A73.6, out of scope).

## The work

1. **Find the cause** of Live stopping: reproduce it in a test that fails before the fix (Live and auto-convert on in
   a temp folder of fake raw files; the conversion's end and the Live check's events delivered in the orders a stalled
   GUI thread allows, e.g. both in one `_tick`, or `check_soon` set while no check is in flight). If it can't be
   reproduced, say what you tried, and add diagnostics that name the state next time (a log line when `_live_tick`
   or `_convert_tick` returns early for longer than a few intervals, with the flags).
2. **Fix it**, then a **backstop**: while Live is on, if no Live check has started for several check intervals (say
   max(60 s, 4 × the interval)), log a warning with the state and start one (cancelling a request that has made no
   progress, as the no-progress rules say: never a retry beside the attempt it replaces). Ask CoCo before choosing
   numbers users see.
3. **A file that waits for good**: check that the existing rule holds in Live: a raw file failing the format checks is
   damaged after `DAMAGED_SECONDS` (20 s) unchanged since this computer first saw it, which relies on the GUI sending
   each `waiting` entry's first-seen time back in `seen`. If any waiting reason (other than a file dated in the
   future) can wait indefinitely for an unchanged, old file, fix it so it ends as unconvertible with its reason, shown
   in Activity and Folder details, and never holds later shots. Tony asked about a ~15 s timeout; CoCo proposed
   keeping 20 s: if you change the number, it's a `Q~`.
4. **The two GUI stall sources**: `low_hits_threshold()` read from memory until its setting changes (a per-test reset
   so tests' own settings files still work), and `_update_plot_source_label` made cheap or called only when its input
   changed. Measure before and after.
5. The Activity window: a Live conversion's waiting note doesn't outlive the conversion that reported it (or says
   when it was).

## Read first

`AGENTS.md` ("I/O and threads", the GUI-thread rules added by block 73), `.ai/architecture/live.md`,
`io-and-browsing.md` (IOService, `_tick`, `gui_delivery`), `converter.md` (settle rules), `app-runtime-and-ui.md`
(Activity), `testing.md`; `helab/views/explorer_live.py`, `helab/io_ops/convert.py`, `helab/io_ops/live.py`,
`helab/utils/folder_cache.py` (`convert`, Live requests), `helab/utils/io_service.py`, `helab/utils/activity.py`;
known-issues entries on Live.

## Rules

- Owned: this session folder; `helab/views/explorer_live.py`, `helab/views/plots/workspace.py`, the Live and
  convert parts of `helab/utils/folder_cache.py` and `helab/utils/activity.py`, and the tests for them. Ask CoCo
  before changing `helab/io_ops/events.py`, a store write path, `helab/io_ops/convert.py`'s settle rules, or
  behaviour an existing test pins.
- Don't edit `AGENTS.md`, `.ai/architecture/`, `roadmaps/` (known-issues too), `.ai/memory/` or the three
  `.ai/*_TODO.md` lists: propose changes in `handoff.md` here, with `Q~`/`A~`/`M~` items.
- Strict typing (with `--platform win32` and `--pythonplatform Windows`). Tests never touch real data; `source
  .ai/local/floor-env.sh` before tests or a run.
- Public text (commits, docstrings) names no person except Tony and no lab machine, internal ID or `.ai/` path.
- Commit freely on this branch. Before pushing: merge the latest `dev/v0.0.9` (fetch from origin; Tony pushes from
  another computer), the full suite (`pytest -n 8 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`) and the
  five type checks, output kept whole here, every RERUN reported; push the branch once, and read every Tests and
  Converter backends job's log for RERUN. Never push `dev/v0.0.9`; never delete a branch; no version bump, release,
  tag, PR or merge into `dev/v0.0.9`. Commit messages end with "Co-Authored-By: Claude Opus 5.5
  <noreply@anthropic.com>".
