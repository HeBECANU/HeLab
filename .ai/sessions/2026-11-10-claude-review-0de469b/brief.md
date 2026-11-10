# Brief: bug review of dev/v0.0.9 f844c0f..0de469b (`review/v0.0.9-0de469b`)

Coordinator: CoCo, 2026-11-10. Tony asked for it (relayed by Side): he pushed six commits to `dev/v0.0.9` from
another computer and keeps editing that branch there, so the review and its fixes go on this branch, pushed once at
the end; **Tony merges it into `dev/v0.0.9` himself**. Nothing goes onto Ground. One Reviewer finds and verifies;
one Worker fixes; the Reviewer then reads only the fix diff.

## The range

Base: `0de469b` (branch `review/v0.0.9-0de469b`). Review `git diff f844c0f..0de469b` (22 files, +2266/-352):

| Commit | What |
|---|---|
| `91e1fd1` | Basic plots v2: one "XY, XT, YT histograms" plot (`helab.v2.plane_histograms`), shared space scale, one colour bar, blur filters (`helab/analysis/image_filters.py`), nested settings groups (`parameters.group_path`) |
| `61f5832` | Floating plots are ordinary windows that can minimise (`AnalysisDock.WINDOW_FLAGS`, `_as_window` polling `mouse_held`) |
| `96df3ed` | GUI watchdog and console tee can no longer freeze HeLab (stacks through a temp file; 60 s before the first beat; tee pumps write the file first, the terminal on its own thread; Windows console handles rebound) |
| `5570c94` | MANUAL_TODO M70.1 (record only) |
| `ceb7419` | 2D histograms: `histogram2d.MAX_BINS` 10,000 set bins; Image › Draw: dots mode with colouring and background |
| `0de469b` | Rate units (events/(mm²·shot), events/(mm·ms·shot)), colour bars, legends across the three backends |

## Read first

- `AGENTS.md`, above all "Analysis and plots" (`compute` on the worker, `render`/`update` on the GUI thread;
  read-only arrays and `.copy()`; Qt-free modules in `PURE`; `Figure`, never `pyplot`; PyQtGraph log axes; Basic
  plots v1 pinned byte for byte; units), "I/O and threads" (the GUI never waits), the UI rules (accessible names and
  `identify` IDs, no lambda capturing a Qt-made sender, no Python callable on `destroyed`), "Tests and typing".
- `.ai/architecture/plots-and-scripts.md` (Basic plots v2), `app-runtime-and-ui.md` (logging, the watchdog, the
  console tee, floating plots), `testing.md`.
- The commit messages above (each says what it claims and how it was checked).

## Focus (bugs first; style only where it hides a bug)

- **Correctness of the numerics:** histogram edges and bin counts at the 10,000 limit (memory: 3 planes × 10k × 10k
  float64 is 2.4 GB: is it bounded?), rate units and their scaling with mm/ms, the filters' chain and order, the
  Anscombe and adaptive-KDE maths, empty selections, one event, NaN/inf, zero-width ranges, log scales at zero.
- **Threads:** what runs in `compute` vs `render`/`update`; arrays mutated in place; dots mode's sampling
  (deterministic? bounded?); Live updates appending shots.
- **The watchdog and console tee (`96df3ed`):** can anything still block the GUI thread or hold the GIL on a full
  pipe; descriptor lifetimes and restore at stop; the temp file's clean-up; Windows-only paths (read them even though
  this Mac can't run them; typed with `--platform win32`); behaviour when stdout/stderr are `None` (pythonw, frozen).
- **Floating windows (`61f5832`):** the polling timer's lifetime, closing or deleting a dock mid-drag, restoring
  saved arrangements.
- **Saved results, presets and arrangements:** does a v2 result or preset saved before this range still open, or
  fail clearly? (The old three ids were "never released": check nothing on `dev/v0.0.9` before `f844c0f` saved them
  in a way that now breaks.)
- **The tests:** do they test what the commits claim, offscreen and on Windows CI (font-dependent sizes, timing)?
  CI run 42621021439 had one RERUN in "windows + py3.13 / Tests (2/3)": find which test when the CI API answers.

## Process

1. **Reviewer:** read the diff and the code around it; run the touched tests and anything you need to confirm a
   finding (`source .ai/local/floor-env.sh` first; never real data; `~/HeLab-samples` read only). Write
   `review.md` in this folder: numbered findings `RV-1`, `RV-2`… each with file:line, severity (High / Medium / Low /
   Info), a concrete failure scenario, how you confirmed it (a test, a run, or reading), and a proposed fix. Only
   verified findings; say plainly what you checked and found nothing in. Commit it on this branch. Report to CoCo.
   Don't fix.
2. **Worker** (recruited after the review): fix the High/Medium/Low findings CoCo passes on, one commit each (or
   grouped when they share a cause), each with a test that fails before the fix where one is practical. Questions
   for Tony as provisional `Q~1`…, things for an agent later `A~1`…, checks on a real screen `M~1`… in
   `handoff.md`. Proposed changes to `AGENTS.md`, `.ai/architecture/`, `roadmaps/` (known-issues too) and the TODO
   lists go in the handoff, never edited directly.
3. **Reviewer** re-reads only the fix diff; findings closed or reopened in `review.md`.
4. **Worker** runs the full suite (`pytest -n 8 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`) and the five
   type checks (`mypy helab/ --strict`, `mypy tests --strict`, `pyright helab tests`, `mypy helab/ --strict
   --platform win32`, `pyright --pythonplatform Windows helab tests`), output kept whole in this folder, every RERUN
   reported with its reason; then **one push** of `review/v0.0.9-0de469b` to `origin`, and reads every Tests and
   Converter backends job's log of that CI run for RERUN before reporting it.

## Rules

- **Never touch `dev/v0.0.9`**: no merge of it into this branch, no push to it, no rebase. Tony merges this branch.
- Owned: the files the findings name, their tests, and this session folder. Ask CoCo before changing behaviour an
  existing test pins, a store write path, or anything Basic plots v1 shows or saves (v1's plot files are pinned by
  SHA-256: never edit them).
- Strict typing (with `--platform win32` and `--pythonplatform Windows`). Tests never touch real data.
- Public text (the manual, docstrings, labels, tooltips) names no person except Tony and no lab machine, internal ID
  or `.ai/` path.
- Commit freely on this branch; push only once, at step 4. Never delete a branch. No version bump, release, tag, PR
  or merge. Commit messages end with "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>".
