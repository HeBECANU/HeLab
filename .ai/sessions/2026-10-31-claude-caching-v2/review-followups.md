# Review: the Follow-ups floor, `git diff 6a0fb25..2eac45a` (agent/followups, Mend)

Reviewer: Assay (Claude Opus 5.5), 2026-11-03. Read-only on code. This is a landing review.

- **Base:** `6a0fb25` (dev/v0.0.8).
- **Head:** `2eac45a`, which is `origin/agent/followups`'s tip.
- **Commits:** 9, from the brief `efb0d03` to the CI step `2eac45a`.
- **Decisions checked against:** DECISIONS_TODO's "Tony in Chat, 2026-11-03 evening": Q48.2, Q48.3, Q49.3 (b),
  Q56.3 and Q56.1 (b), plus the brief and `design.md`.

**Verdict: 1 Medium finding (FU-1, a blocker until fixed) and 3 Low (FU-2 to FU-4), all open.**
- FU-1 is a script folder whose test import answers "done" but then never exits. HeLab never kills that probe, so
  the folder never loads, and every later Reload or Load Scripts… waits behind it. At start, the saved plots
  never reopen. The fix is one line in `probe.py`, plus a deadline after `done`.
- Everything else CoCo listed holds: Q48.2, Q48.3, the rest of Q49.3, Q56.3, the shim and its offline check, and
  the CI step.
- The suite, the five type checks and the branch's CI run are clean, with no RERUN (below).
- There is no handoff yet: FU-4 lists the doc changes it should propose.

## Findings

### FU-1 · Medium · A probe that answers `done` and then doesn't exit holds its round forever

- **Where:**
  - `helab/scripts/probe.py:89-90`: `del application`, then `os._exit(0)`;
  - `helab/views/plots/script_tree.py:236`: `_poll` skips a probe once `item.done` is set
    (`if item.killed or item.done or item.process is None: continue`).
- **Scenario.** A script folder's file starts a never-ending task on Qt's global thread pool at import. It might
  be a background watcher, or a `QRunnable` loop.
  1. The probe imports the folder, writes `ready` and `done`, then runs `del application` to delete its
     offscreen QApplication.
  2. `~QCoreApplication` waits for `QThreadPool.globalInstance()`'s tasks to end, so the probe never reaches
     `os._exit(0)`.
  3. The GUI saw `done`, so `_poll` stops checking the limit for that probe. Nothing kills it.
  4. `FolderProbes` holds the folder until its exit is confirmed (rightly), so the round never answers:
     - **On Reload or Load Scripts…:** the folder never loads. The button stays "Reload (checking)", and every
       later Reload, auto-reload and Load Scripts… joins `_pending` behind the stuck round (`_try_reload`
       returns while `_probing`).
     - **At start:** `_restored` never runs. No remembered folder loads, not even the good ones,
       `foldersRestored` never fires, and `PlotReopen.restore` never reopens the session's plots.
  - The GUI doesn't freeze, but only quitting gets out of it (`stop` on `aboutToQuit`).
  - The real import in the GUI would have been fine: the task just runs there.
- **Fix:**
  - Drop `del application` (and `application` itself, or keep a reference until `os._exit`). The probe has
    nothing to tear down, and `os._exit` ends it at once.
  - Also give `_poll` a deadline after `done` (a few seconds). Kill the probe after it, and still count the
    folder as passed (it said `done`), so no other exit path can hold a round.
  - Add a test: a folder whose file starts a `QThreadPool.globalInstance()` task that outlives the limit.
- **How verified:**
  - **The probe alone:** `python -P -m helab.scripts.probe` on a folder with such a file (the task sleeps 40 s)
    wrote `ready` and `done`, then was still running when `timeout 25` killed it (exit 124).
  - **The cause:** a minimal script (offscreen QApplication, a pool task, then `os._exit(0)`) exits in 0 s
    without `del application`. With it, it was still running at 15 s.
  - **The panel:** a scratch test (`TreePanelWidget.add_folder`, with `PROBE_SECONDS` = 2) after 12 s, six times
    the limit:
    - the probe had `done` True, `killed` "";
    - the button read "Reload (checking)";
    - the folder's group wasn't loaded.

    It loaded only at 20.5 s, when the task (20 s) ended. With an endless task it never would.

### FU-2 · Low · Some of the try-import's paths are untested

- **Where:** `tests/test_script_probe.py`. Its 7 tests cover:
  - the probe's answers;
  - the frozen dispatch from source;
  - a hang at start;
  - an `os._exit` from Load Scripts…;
  - `input()` on Reload, with a queued second round and the fix adopted;
  - a probe that can't start;
  - the CI step's text.
- **Untested:**
  - The **offscreen fallback**: `_application` returns `none (no offscreen platform plugin)`, so a script that
    makes a widget at import aborts the probe and is skipped as a crash.
  - The **start limit**: `PROBE_START_SECONDS`, "HeLab's test import didn't start within 60 s".
  - A **crash by signal** (`CrashExit`, "its import crashed HeLab's test import"). Only a clean `os._exit(3)` is
    tested.
  - **`stop()` at quit**: probes killed, rounds dropped, no answer after.
  - **Auto-reload on save through the probe.** `tests/test_live_scripts.py` turns probing off for all its tests
    (`no_probe`), so the on-save path is covered only with `PROBING` False.
  - FU-1's **done-then-no-exit** case.
- **Fix:** add short tests for each. Patch `_plugin_folders` to `[]` for the fallback, `PROBE_START_SECONDS` to
  ~1 s with a probe command that sleeps, `os.kill(os.getpid(), SIGKILL)` at import on POSIX, and
  `QCoreApplication.aboutToQuit` or `stop()` directly. Also add one auto-reload test with `PROBING` True.
- **How verified:** by reading the tests, and `grep` for `PROBE_START_SECONDS`, `NO_APPLICATION`, `CrashExit`
  and `stop(` in `tests/`.

### FU-3 · Low · After a stable release, `pre-release` stays on an older pre-release

- **Where:** `docs/publish/site_versions.py:53-55`. `pre-release` moves only when a newer pre-release is
  deployed.
- **Scenario.** HeLab publishes 0.0.8a1, then 0.0.8b1, then 0.0.8. The version menu then lists:

  ```text
  0.0.8 [latest]
  0.0.8b1 [pre-release]
  0.0.8a1
  ```

  This holds until 0.0.9a1. A reader sees "pre-release" on a version older than the stable one, as if it were a
  preview of something newer.
- **Why Low:** it matches the brief's wording ("a pre-release alias for the newest alpha or beta"). Tony's "just
  stable and pre-releases" doesn't settle it. Whether `pre-release` should go once a stable release supersedes
  it is wording users see, so it is Tony's call (DECISIONS_TODO), not a code fix to guess.
- **Proposed:** a stable release newer than `pre-release`'s target removes the alias (or points it to `latest`),
  and the next pre-release brings it back.
- **How verified:** I ran the plan's commands, without `--push`, for 0.0.8a1, 0.0.8b1, 0.0.8, 0.0.9a1 and 0.0.7,
  in a clone with no remote, with mike 2.2.0 from the lock (`mike list` after each; below).

### FU-4 · Low · There is no handoff, so its doc proposals are missing

- **Where:** `.ai/sessions/2026-11-03-claude-followups/` has `brief.md`, `design.md` and `zensical.md`, and no
  handoff. The brief's step 6 asks for docs proposals and provisional `Q~`/`A~`/`M~` items in it.
- **What the Coordinator will need to apply when landing.** Each is stale after this change:
  - `.ai/architecture/converter.md:545`: still "a line naming `--yes`, which writes beside without asking". Now
    `--output beside-forced`, and `--yes` is a usage error.
  - `.ai/architecture/release-and-ci.md:119-120`: "mike deploys `<version>` … with the alias `latest`, set as the
    default". Now:
    - `site_versions.py`: `latest` is the newest stable release, `pre-release` the newest pre-release;
    - the "No stable release yet" template until there is a stable release;
    - the step's guard now also needs `docs/publish/site_versions.py`;
    - the Docs job's offline check (`check_offline.py`).
  - `.ai/architecture/release-and-ci.md:15`: the frozen dispatch list names `--helab-io-helper` and `convert`,
    not `--helab-script-probe`. Add `ci-build.yml`'s probe step too.
  - `.ai/architecture/plots-and-scripts.md`, the script system:
    - the try-import (`FolderProbes`, `helab.scripts.probe`, the limits, the outcomes);
    - `ScriptsManager.skip_folder`;
    - the marker staying as the backstop;
    - `PROBING` for tests.
  - `.ai/architecture/settings.md:33`: the loading marker's paragraph could say the probe comes first.
  - `roadmaps/known-issues.md:29-35`: "A user script that blocks at import freezes HeLab once" says Q49.3 is open.
    It is decided and built. The item narrows to what the probe can't catch (`design.md`'s "The loading marker:
    kept").
  - `AGENTS.md`'s frozen-dispatch invariant ("The frozen helper entry point in `helab/main.py`…") could name the
    probe's argument beside the helper's.
  - DECISIONS_TODO: FU-3, if CoCo agrees it is Tony's.
- **Fix:** the worker writes `handoff.md` with these, the checks and the CI run, as the brief asks.

## Checked, no finding

### Q48.2: a raw read stopped early notifies, once per file

- **The notification.** `LiveController._converted` (`explorer_live.py:1020-1023`) calls the new
  `_notify_read_stopped` for each `shot_converted` with `read_stop`. That sends `events.READ_STOPPED_RAW` with
  `desktop=True`.
- **Once per file.** Its key is `(kind, folder, raw name, raw size, raw mtime_ns)`, as `DAMAGED_RAW`'s is, so the
  same file again says nothing and a changed file says it again.
- **The text** names the file and folder, then `ReadStop.detail()`, then "Later shots go on."
- **The read-stopped line and Folder details** are unchanged.
- `helab convert` still logs the read stop (`convert_cli.py:189-191`), and the Convert dialogs don't show it, as
  before. Neither needs a system notification.
- **The test** (`test_live_convert.py`) checks:
  - the text;
  - the event's path, shot and line;
  - a second file;
  - the same file again (no new notification, with another sha);
  - a changed size (notifies again).
- The manual's Live page says so.

### Q48.3: `--output beside-forced`, and `--yes` errors

- **`beside-forced`** maps to `beside` (`_request`), and `_beside_anyway(folder, forced)` behaves as Tony said:
  - on a share it logs the share's warning, then "Writing beside the raw files on the share anyway (--output
    beside-forced)", and asks nothing;
  - off a share it asks nothing either.
- **Plain `beside` on a share** asks on a terminal. Without one, or on no, it converts to HeLab's folder with a
  warning naming `--output beside-forced`.
- **`--yes`:**
  - It is a hidden argument (`argparse.SUPPRESS`), and passing it gives `parser.error`: exit 2, with "--yes is
    gone: --output beside-forced writes beside the raw files on a network share without asking".
  - Abbreviations (`--ye`, `--y`) reach the same error, through argparse's prefix match.
  - Nothing in `helab/` or the manual uses `--yes` any more. Only `converter.md` still does (FU-4).
- **The share-refusal question** (`_after_refusal`, Q38.1) isn't skipped by `beside-forced`, rightly: it is a
  different safety question.
- **Help text, docstring and the manual's command-line page** follow.
- **The tests** cover beside and beside-forced:
  - on and off a share;
  - with and without a terminal;
  - no warning naming `--yes`;
  - the usage error and the help.

### Q49.3 (b), the try-import (besides FU-1 and FU-2)

- **Where it runs.** All of these go through `_probe_then`:
  - start (`restore_folders`, after the share and marker checks, as before);
  - Reload, the folder menu and auto-reload (all through `reload_scripts` and `_try_reload`);
  - Load Scripts… (`add_folder` now goes through `reload_scripts([folder])`).
- **The GUI never waits.**
  - `FolderProbes` uses `QProcess` signals and one 100 ms poll timer that runs only while probes run.
  - The response file is a small local temp file, read from its last offset.
  - No `waitFor*` anywhere.
  - `~QProcess` reaps a killed probe at teardown: milliseconds after `stop()`'s kill.
  - **Nit:** `_finished` reads the whole `stderr.txt` before keeping its last 4,000 characters. A script that
    floods stderr for the 10 s makes that one read large. Seeking to the tail would avoid it.
- **A slot is held until the exit is confirmed.**
  - A probe leaves `_running` only in `_ended`, which runs from `finished`, or from `errorOccurred(FailedToStart)`
    when there is no process.
  - A kill (the limit, the start limit, `stop`) only sets `killed` and calls `kill()`. The answer waits for
    `finished`.
  - One round at a time: a reload asked meanwhile waits in `_pending` and runs after `answered`, so a folder
    never has two probes. The test checks `len(_running) == 1` with a second reload queued.
  - A synchronous `FailedToStart` inside `start()` is safe: `_running` is set before `start`, and `_probing`
    before `probe()`.
- **The limit is counted from `ready`.**
  - `item.ready` is set when the `ready` line is read, and `PROBE_SECONDS` (10 s) is measured from it.
  - The probe writes `ready` after its QApplication and `ScriptsManager`'s import, so its own start doesn't
    count.
  - Before `ready`, `PROBE_START_SECONDS` (60 s) applies.
- **The offscreen QApplication and its fallback.**
  - `_application` first checks that a `platforms/*qoffscreen*` plugin exists (in Qt's plugin path,
    `libraryPaths()` or `QT_PLUGIN_PATH`), since a missing one would abort the process.
  - It then sets `QT_QPA_PLATFORM=offscreen` and makes the application, falling back to none with the reason on
    any exception. `ready` reports which.
  - The source test's script makes a `QLabel` at import, under `offscreen`.
- **The frozen dispatch** (`main.py:16-21`, the check at 18):
  - It comes right after `freeze_support()` and the `--helab-io-helper` block, and before `convert`, `cache`,
    `--version` and every GUI, cache or Dash import.
  - It imports only `helab.scripts.probe`, which imports only the standard library until `main`, then PyQt6 and
    `helab.scripts.scripts_manager`.
  - It never takes `running.lock`, since `main()` isn't reached.
  - **In CI's packaged app on all three OSes:** `ready` reported `offscreen`, `done` followed, the app was frozen,
    and the main window module was not imported.
- **stdin and `input()`.**
  - `QProcess`'s stdin pipe is never written or closed, so `input()` at import waits and meets the limit. Tested
    on Reload.
  - A script's prints go to files, so no pipe fills.
  - The answer is in the response file, not stdout, as the frozen helper does.
- **`skip_folder`'s message.**
  - `ScriptsManager.skip_folder` records the folder, clears its scripts and errors, and adds one
    `LoadError(folder, "didn't load: <reason>", details)`. Its row reads, for example, "crashes: didn't load: its
    import stopped HeLab's test import (exit code 3)" (tested).
  - The tooltip and details say it was checked in a separate process, plus the stderr tail.
  - At start, a failed folder waits for Reload in the start note instead, with `PROBED_NOTE` in its tooltip.
  - Plots keep their code with the reason (tested).
  - **Nit:** a signal gives "its import crashed HeLab's test import", without `design.md`'s "(killed by signal
    N)".
- **The loading marker is still kept.** `_load_folder` (`script_tree.py:591-605`) still marks and unmarks around
  the real import, unchanged. The marker remains the backstop for what the probe can't see.
- **PURE.** `helab.scripts.probe` is in `PURE` (`tests/test_headless_imports.py`), and that test passes.
- **Other edge cases:**
  - A file that raises or calls `sys.exit` at import is that file's error, not the probe's (`_load_script_file`
    catches `(Exception, SystemExit)`; tested).
  - A folder removed while it is tested is ignored (`_is_remembered`).
  - A Load Scripts… during the start round queues behind it.
- **Nit:** a probe killed at quit leaves its `helab_probe_*` folder in the system temp. `design.md` says so.
- **The manual's script page** says in one line that a script's top-level code runs twice, and names "Reload
  (checking)" and the 10 s message.

### Q56.3: the site's versions

- **The plan, simulated with mike 2.2.0** in a clone with no remote, without `--push`:

  | Release | Front page | Version menu |
  |---|---|---|
  | 0.0.8a1 | "No stable release yet", its link `pre-release/` | `0.0.8a1 [pre-release]` |
  | 0.0.8b1 | the same | the alias moves to 0.0.8b1 |
  | 0.0.8 | redirects to `latest/` | `0.0.8 [latest]` |
  | 0.0.9a1 | still `latest` | `pre-release` moves |
  | 0.0.7, published late | still `latest` | its version only, no alias moved |

  The template rendered `{{href}}`, and mike accepted `set-default --template … pre-release`.
- **Without a gh-pages branch,** `mike list --json` prints `[]` with exit 0.
  - **Nit:** `main` also treats a failing `mike list` as nothing deployed. A list error with the branch present
    would plan as if no stable release existed. A push wouldn't hide it, though: the deploy still has to push
    onto the fetched branch.
- **Deploy still only on a published release.**
  - `docs-site.yml`'s `on:` is still `release: types: [published]`, which pre-releases also fire.
  - It still checks out the released tag, and no other workflow runs mike (tests).
  - The guard now also needs `site_versions.py`. No published tag has `mkdocs.yml` without it, so nothing is lost.
- **Help › User manual** opens `<owner>.github.io/<repo>/<version>/`, a pre-release's own page included (new
  test).
  - A dev build has no page on the site, so the HEAD check falls back to the bundled copy, as reviewed in DM.
- `no-stable.html` names no person or host. The README says how to build the manual locally, and that there is no
  dev channel online.

### The vendored shim and the offline check

- **Byte for byte:** `docs/js/iframe-worker-shim.js`, without its one-line header, is identical (`cmp`) to
  `package/shim/index.js` of npm's `iframe-worker-1.0.4.tgz`.
- **The licence.**
  - `LICENSE-iframe-worker.txt` is identical to the package's `LICENSE`: MIT, "Copyright (c) 2020-2022 Martin
    Donath". `package.json` says `"license": "MIT"`.
  - The header names the source and the licence file.
  - Both files are copied into the built site (`js/`), so the copy bundled in the app carries the notice, as MIT
    asks.
- **Material's offline plugin** (9.8.0, `offline/plugin.py:43-47`) appends unpkg's shim only when no polyfill
  names "iframe-worker". With the vendored file listed, the built pages load `js/iframe-worker-shim.js`, and no
  page loads unpkg.
- **`check_offline.py`:**
  - On my strict offline and online builds: "18 pages, every script a file of the site", exit 0.
  - In the Docs job of run 41626693781: the same line.
  - **Limit, not a finding:** it reads static `<script src>` only. Material's bundle can still load from unpkg at
    run time: a ResizeObserver polyfill on browsers without one, and mermaid for diagrams, which no page uses.
- **Not checked:** the search working from `file://` with the network off. I didn't open a browser. The commit
  says the worker did, in Chrome.

### `ci-build.yml`'s frozen probe step

- **Its cost.** It runs after the backend check in each Build job, for one frozen start on a one-file folder.
  In run 41626693781 it took 1 s on Ubuntu, 1 s on Windows and under 1 s on macOS. Its subprocess timeout
  (300 s) sits under the job's 25 min.
- **The gate.**
  - It runs in every build, including the compatibility builds the release job needs, with no `if:` (the test
    asserts that). A broken frozen probe should block a release, and the cost is a second.
  - A commit without `helab/scripts/probe.py` (a recovery build of an older tag) exits 0 with a line.
  - It adds no job, and nothing new waits on it.

### Tests

The new tests cover what CoCo listed except FU-1 and FU-2's paths:
- `test_script_probe.py` (7 tests, all of which ran and passed on each OS in CI: 21 PASSED);
- `test_docs_workflows.py`: the plan in both phases, the workflow's call, the offline checker, the shim, licence
  and polyfill;
- `test_convert_helab.py`, `test_live_convert.py` and `test_user_manual.py`.

`test_script_system.py` now waits for the asynchronous load. The commit says an earlier run's 5 RERUNs of it were
this change's synchronous assumption, fixed in the same commit; no RERUN since.

## Checks (run by the reviewer)

On a `git clone --shared` of `2eac45a`, with testdata linked:
- **The suite:** `pytest -n 4 --reruns 5 --reruns-delay 1`: **9274 passed, 673 skipped, 2 warnings, 1 failed,
  5 rerun in 205 s.**
  - The failure and all 5 RERUNs are `test_versioning.py::test_frozen_metadata_survives_no_git_and_unrelated_cwd`
    ("commit 'unknown'"). My clone causes it: there `git status` exits 128, because `testdata` is a symlink where
    git expects a submodule.
  - With `testdata` an empty folder (`git status` exit 0), `test_versioning.py` and `test_release_recovery.py`
    gave **56 passed**, no RERUN. The diff touches neither those tests nor `build_info.py`.
  - No other RERUN. The 2 warnings are the known pyqtgraph ones.
- **The five type checks:**
  - `mypy helab/ --strict` (207 files), `mypy tests --strict` (210) and `mypy helab/ --strict --platform win32`:
    no issues;
  - `pyright helab tests` and `pyright --pythonplatform Windows helab tests`: 0 errors.
- **CI run 41626693781 (`2eac45a`): success.**
  - All 17 jobs that ran succeeded: Detect, Docs, three Builds, three Converter backends and nine Tests jobs
    (1/3–3/3 per OS). The compatibility jobs are skipped on a branch push.
  - I read every log for `RERUN`: 0 in each.
  - The frozen probe step's output on each OS: `exit 0`, `ready` with `application: offscreen`, then `done`, and
    `seen {'frozen': True, 'gui': False}`.
- **The docs:**
  - `mkdocs build --strict`, offline and online: both pass, and `check_offline.py` passes both.
  - The mike simulation and the shim comparison are above.
- **FU-1's checks:** the probe run under `timeout`, the minimal script, and the panel scratch test.
- Scratch files are in `.ai/temp/assay/` and not committed:
  - `test_zz_fu.py`, `fu-exit.py`, `fu-mike-run.py`;
  - the clones `fu-git` and `fu-mike`;
  - the sites `fu-site-off` and `fu-site-on`;
  - `fu-npm`, the job logs in `fu-jobs`.
