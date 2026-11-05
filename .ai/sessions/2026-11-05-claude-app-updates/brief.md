# Brief: app updates, from source first (`agent/app-updates`)

Coordinator: CoCo, 2026-11-05. **Draft: the floor opens when a slot is free and Tony says go** (at most three
floors). Tony, in the live run (LR-14, relayed by Side): "keep track to latest with v0.0.9 and I can press a button
in helab to close app, pull, and start helab up again". Decided: **Q65.1 (b)**, source first: stage 1 (notify) plus
stage 2's source path in v0.0.9; frozen builds keep the stage-1 notice and link their download, and their
self-update comes later. **Q65.3 (decided):** a source checkout's "Update from" setting defaults to **the branch
HeLab runs from** (fast-forward only, to commits whose CI is green on all three OSes), with **releases** (tag to
tag) to choose; a checkout on a tag defaults to releases; a compiled build only checks and shows releases. Both
modes are built. One Worker; one Reviewer at landing.

## Read first

- `AGENTS.md`, above all "Working with Tony", the I/O and threads rules (the GUI never waits on a helper, a
  deadline or the network), "One HeLab app per computer" (`running.lock`), the frozen helper entry points in
  `helab/main.py`, and "Versions and releases".
- **The plan: `roadmaps/app-updates.md`.** Its Shared rules, Stage 1 and Stage 2 ("The updater process", "Source
  checkout", "Rolling back, cache and settings", the Acceptance and Risks) are the spec, as amended by Q65.1 (b),
  Q65.3 and this brief.
- The decisions: Q65.1–Q65.3 in `.ai/DECISIONS_TODO.md` (block 65), Q1.4 (the two repos).
- `.ai/architecture/release-and-ci.md` (versions, `_build_info.json`, the release job, tags) and
  `app-runtime-and-ui.md` (the status bar, the Help menu, Settings), `settings.md`, `testing.md`.
- The code: `helab/build_info.py` (version, commit, branch, dirty), `helab/_version.py`, `helab/main.py`
  (`running.lock` via `cache_locks.take_running`, the helper dispatch), `HelabMainWindow.show_about_dialog` and the
  Help menu, Settings › General.
- Memory: the lab machines' notes say never launch HeLab over SSH; HeLab runs from a uv Python 3.13 venv on each
  PC; on Tony's Mac `venv/` may be a symlink to `venv.nosync/`.

## Base and branch

Base: `dev/v0.0.9` at the commit CoCo names when the floor opens. Branch: `agent/app-updates`.

## Objective (commit each step separately; stop and report to CoCo at each ◆)

1. **◆ Design first (`design.md` in this folder), before any code.** It covers:
   - **Version status** (Release / Pre-release / Development version (based on X) / Update available) from
     `build_info` and the chosen repo's releases and tags.
   - **The check (stage 1):** where the request runs (`QNetworkAccessManager` on the event loop, or a helper),
     ETag reuse, the once-a-day startup check and its switch, the manual Help › Check for Updates…, Skip this
     version, the repo list (`HeBECANU/HeLab`, `TonyXTYan/HeLab`; found among the checkout's remotes **by URL**,
     never by remote name), "Include pre-releases", and how it shows (Help menu and a small status-bar mark, no
     banner, no vertical space).
   - **Q65.3's two modes for a source checkout** (both built; the default from what the checkout is on): (a) releases: fetch, check the tag's commit is on that repo's
     `main`, check out the tag (detached); (b) a branch: fast-forward only, to the newest commit whose CI is green
     on all three OSes (GitHub's check runs, read without a token), never past a red or unfinished one; how the
     setting reads and what each mode shows in About.
   - **The updater (stage 2, source path):** a separate, standard-library-only script run detached from the uv base
     Python (`sys._base_executable`), outside what it replaces; the handshake with HeLab (it opens a handle on
     HeLab's process before HeLab quits); waiting for HeLab, every `io_helper` and `running.lock`; `git fetch` and
     the checkout or fast-forward, `git submodule update`; **the venv rebuilt beside the old one only when
     `requirements.lock` changed** (`venv.new`, checked by importing HeLab, then swapped; the old one kept for
     Restore; a `venv` symlink kept a symlink), else reused; the relaunch, detached, in the same desktop session;
     a log the next start shows.
   - **Refusals with their reason:** local changes (or stash, offered: never dropped or popped), untracked files
     the update would overwrite, `git` or `uv` missing, a different Python minor version, other HeLab windows or
     helpers still running, an SSH or elevated session, a load, save or cache move that can't stop, a detached HEAD
     or branch other than the chosen mode's.
   - **Restore previous version** (the previous commit and venv), and "the new version started" marking with the
     roll back if it doesn't.
   - **What HeLab does before quitting** for an update (the quit window's rules: saves finished, Live stopped).
   - **The tests**: fake release feeds and check runs (no network), temporary git repos with a bare "remote" (never
     this checkout, never Tony's remotes), a fake venv builder, the updater script run as a subprocess against
     them on every OS; which existing tests you expect to touch.
   - Questions for Tony as provisional `Q~1`, `Q~2`… with options and a proposed answer.

   Send CoCo the design with `maestri ask "CoCo" …` and wait for the go.
2. **Stage 1:** the version status, the check, the Help menu and status-bar notice, Settings › General's rows,
   About; with tests.
3. **The updater** and its refusals, in both modes; with tests on temporary repos.
4. **Update and restart** from HeLab, Restore previous version, the started mark. ◆ Report after this step, with
   the suite, the type checks and a pushed branch with its CI run (Windows matters most here).
5. **Docs proposals** in your handoff (`handoff.md`): the architecture section (`release-and-ci.md` or a new
   area), AGENTS.md's line if any (at most one; likely an invariant: "HeLab never changes its own code while it or a
   helper runs"), the manual's page (you write `docs/` yourself), and `Q~`/`A~`/`M~` items, including an **M~ for
   Tony to run a real update on this Mac and on a lab PC (Windows)**, from source.

## Acceptance

- Stage 1's acceptance in the plan, for source and frozen runs.
- Stage 2's acceptance in the plan, for the source path: every refusal with its reason; the updater waits for HeLab
  and all its helpers before changing a file; a failed update leaves the previous version working; Update and
  restart comes back on the new commit; Restore previous version brings back the old commit and venv.
- Branch mode never moves to a commit without green CI on all three OSes, and never rewrites history
  (fast-forward only).
- **The invariants hold:** the GUI never waits on the network, a helper or the updater; nothing is sent but GETs to
  `api.github.com` with `User-Agent: HeLab/<version>` (no telemetry); no free-text repo; HeLab never changes code it
  or a helper is running; never launched from an SSH or elevated session; tests never touch this checkout's git
  state, Tony's remotes, the network or real data.
- **The UI rules hold** (accessible names and `identify` IDs, one-line rows, no vertical padding, gaps from
  `helab/views/gaps.py`).

## Rules

**Owned paths:** a new `helab/updates/` package (or `helab/utils/updates*.py`; say which in the design), the
updater script, `tests/test_updates*.py`, `docs/` (the manual's page and `mkdocs.yml`'s nav).

**Edits allowed, kept small:** `helab/views/HelabMainWindow.py` (Help menu, the status-bar mark, About, the quit
path for an update); Settings › General's module; `helab/utils/settings_defaults.py` (new rows only);
`helab/build_info.py` (read-only accessors); `helab/main.py` (the started mark, and an updater entry only if the
design shows one is needed, after the helper dispatch rules); `tests/test_headless_imports.py`,
`tests/test_accessible_names.py` (lists only).

**Ask CoCo before any other file**, before changing the quit window, `running.lock` or the release job, and
before changing behaviour an existing test pins.

**Checks and process:** as the other floors' briefs: strict typing (with `--platform win32` and
`--pythonplatform Windows`); `source .ai/local/floor-env.sh` before tests or a manual run; the full suite
(`pytest -n 8 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`) and the five type checks before each ◆ and the
handoff, output kept whole, every RERUN reported; docs only in this session folder (propose the rest); public text
names no person except Tony and no lab machine, internal ID or `.ai/` path; commit freely, push only at checkpoints;
read every Tests and Converter backends job's log for RERUN before reporting a CI run. **Never run the updater
against this checkout or the floor's**, and never `git push`, `git fetch` from Tony's remotes or change a remote
from a test. Never delete a branch. No version bump, release, tag, PR or merge.

When done: `maestri floor status "<summary>" --state review`, then
`maestri ask "CoCo" "App updates: done at <hash>, suite <N> passed, RERUNs <…>, CI <run>"`.
