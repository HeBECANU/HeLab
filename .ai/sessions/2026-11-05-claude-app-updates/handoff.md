# Handoff: app updates (`agent/app-updates`)

Worker, 2026-11-05. Base `127b1e8` (dev/v0.0.9). Design: [design.md](design.md) (CoCo's go to its proposals,
2026-11-05, with two notes applied: Q~8's deletion behind one function and a switch; Q~2 (a) with the target's
own runs green on all three OSes and skipped or cancelled required jobs not green).

## Commits

| Commit | What |
|---|---|
| `166c64c` | design.md (step 1) |
| `bc71f84` | Stage 1: version status, the check, Help and status bar, Settings › General, About |
| `c543fe5` | Stage 2: the updater script and its refusals, both modes |
| `3be4698` | Update and restart, Restore previous version, the started mark (step 4 ◆, pushed, CI below) |
| `189790f` | Docs: the manual's how-to page and the settings rows |
| `1345e07` | CI fixes: `ps -ww` (procps cut a piped listing to 80 columns, hiding a helper on Linux); the window test's repo from its own build |
| `43d22f4` | The handoff (step 5) |
| `cbd42bb` | Sentry's review fixes, AU-1 to AU-11 (below) |
| `9ca5acf` | Merge of `dev/v0.0.9` at `8690a2f`, clean |
| `fc2906d` | The handoff, with the review fixes |
| `f951fc0` | macOS: a framework Python's venv processes (`ps -E`); a test's teardown (CI 42018998611's failure) |
| `c099caf` | The handoff, with CI 42022523164 |
| (this) | Re-check 1 (`4c8bbb5`): AU-13, AU-14 |

## What was built

- `helab/updates/` (new): `versions`, `github` (pure: status, channels, replies, the CI rule, ETag cache, the check
  as a generator), `updater` (standard library only), and HeLab's side `settings`, `settings_rows`, `check`,
  `launch`, `dialog`.
- Edits kept to the brief's list: `HelabMainWindow.py` (Help › Check for Updates…, the "is available" entry,
  Restore previous version…, the status-bar mark `update_available`, About's three lines, the dry run → Quit and
  update → normal close, the last outcome at start), `SettingsDialog.py` (two rows), `settings_defaults.py`
  (six `updates_*` rows), `build_info.py` (read-only `upstream_repository`), `main.py` (schedules the startup
  check, writes the started mark, shows the last outcome), and lists in `test_headless_imports.py` and
  `test_accessible_names.py` (a DIALOGS case for the update window, since `helab/updates` isn't a guarded
  package).
- Not changed: `io_helper`, the quit window, `running.lock`, the release job.
- **Why About and the Settings refresh use `getattr(self, "update_check", None)`** (CoCo: fine): two existing tests
  build a `HelabMainWindow` subclass that skips `__init__` (`test_helabMainWindow.py::test_about_displays_build_provenance`,
  which pins About's text to `APP_BUILD_INFO.description()`, and `test_load_queue.py::test_folder_io_menu_and_settings_apply_to_existing_and_new_tabs`,
  which reaches `show_settings_dialog`). With the guard, a window without a check shows exactly the provenance
  (the pinned text) and the refresh skips it, so neither pinned test had to change; a real window always has the
  check (made in `__init__`), and `test_updates_check.py::test_about_shows_the_status_the_mode_and_the_last_check`
  covers About's three lines.

## Checks (step 4)

- Full suite (`pytest -n 8 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`), final run on `3be4698`'s
  code: **9551 passed, 673 skipped, 2 reruns**, both `tests/test_convert_helab.py::test_a_killed_helpers_workers_exit`
  (`AssertionError: the pool started`, `assert []`, line 1099), with the machine's load average at 460–650 from
  other floors. Not in known-issues; it touches nothing this branch changed (proposed known-issues entry below).
- An earlier full run: 2 reruns, `test_gui_responsiveness.py::test_timeout_retry_releases_dead_helper_slot_while_artifact_reader_is_blocked[1]`
  (known issue, same `waitUntil` timeout, here locally on macOS) and **my** `test_updates_updater.py::test_a_second_update_deletes_only_the_venv_before_the_previous_one`:
  cause found and fixed in `3be4698` (the venv check read a stale `.pyc`: two updates in one second with a
  `_version.py` of the same size; the check now compiles into its own empty `PYTHONPYCACHEPREFIX`); reproduced
  2 in 3 before, 0 in 6 after.
- A first run failed `test_load_queue.py::test_folder_io_menu_and_settings_apply_to_existing_and_new_tabs`
  (a window built without `__init__` reached the new `settings_changed`): fixed before the commit.
- Type checks, all clean: `mypy helab/ --strict` (223 files), `mypy tests --strict` (219), `pyright helab tests`,
  `mypy helab/ --strict --platform win32`, `pyright --pythonplatform Windows helab tests`; the updater also
  checked with `--platform linux` / `--pythonplatform Linux`.
- Docs: `ruff check`, `mkdocs build --strict`.
- CI run 41997785484 on `3be4698`: **failed**, Tests (1/3) on all three OSes, two causes, both this branch's
  (fixed in `1345e07`): `test_updates_check.py::test_the_status_bar_mark_and_help_entry_show_an_available_update`
  (the fixture made its fake replies for the real build's default repo, which on CI is the branch's upstream
  `TonyXTYan/HeLab`, then switched the build) and, on Ubuntu, `test_updates_updater.py::test_the_updater_waits_for_helab_and_its_helpers_before_changing_a_file`
  ("it changed files while a helper ran": procps' `ps` cut its piped listing to 80 columns, so the updater
  didn't see the helper, a real bug the test caught). Every other job was green with no RERUN.
- CI run **42000073747** on `1345e07`: **success, every job** (3 × Tests 1–3, 3 × Converter backends, 3 × Build,
  Docs, detection); all 12 Tests and Converter backends logs read: **no RERUN**.
- Full local suite on `1345e07`: **9551 passed, 673 skipped, no rerun** (119 s).

## Review fixes (Sentry, `review.md` at `8090401`)

Each Major and Minor has a test that fails on the code before (the new updater tests ran against the previous
updater: 9 of 9 failed; the AU-1/AU-2/AU-6 tests against the previous `launch`/window/check code).

| ID | Fix | Test |
|---|---|---|
| AU-1 Major | `main` runs `HelabMainWindow.after_start` once the event loop turns: the started mark, then the outcome; a HeLab started by an updater polls (250 ms, up to `UPDATE_OUTCOME_WAIT_S` = 20 s, never waits) for `last.json` carrying its own token. Without a token, as before. | `test_updates_launch.py::test_a_helab_the_updater_started_shows_that_updates_outcome_on_this_start` (the updater's own `wait_started` + `record` in a thread) |
| AU-2 Major | `trim_compare` keeps parents; `github.branch_line` walks the first-parent line from the tip, keeping commits that contain the running one; "+N" counts it ("+250+" when GitHub's list was cut). The updater refuses a target not in `git rev-list --first-parent <tip> ^HEAD`. | `test_updates_github.py::test_branch_mode_never_moves_onto_a_commit_merged_in_from_another_branch` (old code offered the floor's tip), `…on_a_merged_side_commit…`, `…cut_at_250…`; `test_updates_updater.py::test_branch_mode_refuses_a_commit_merged_in_from_another_branch` (a `--no-ff` merge) |
| AU-3 | Matched by folder prefix (venv and checkout, raw and resolved), never split at spaces. Also dropped: the global `--helab-io-helper` marker. It only names frozen helpers, so it matched only *other* HeLabs, and it was the likely cause of one local parallel run where 16 updater tests were refused (shown: the old rule lists an unrelated `… --helab-io-helper` process and even the shell that started it; every run since clean). Also covered, after CI run 42018998611 (below): a venv made from a macOS framework Python (python.org's, Homebrew's, GitHub's macOS runners'), which re-execs as `Python.app`, so `ps` doesn't name the venv: macOS also reads `ps -E` for the venv stub's `__PYVENV_LAUNCHER__=<venv>/…` (matched only; the message and log show the plain command, never the environment), and the updater drops that variable at start so its own children (ps, git, the relaunch) never match. Before the review this case was only "seen" through the global marker. | the waiting test, now a real `<venv python> -m helab.io_helper`, parametrized `lab` / `My Projects` / `framework` (macOS: CI's own Python, or Homebrew's here; fails on `cbd42bb`'s updater, passes now) |
| AU-4 | After "exited", `wait_quiet` (locks + processes, up to `others`) before rolling back; still busy, the new version is left in place, recorded "failed" with how to go back, not relaunched. | `test_a_rollback_waits_for_the_new_versions_helpers` (a helper outliving the crashed HeLab sees 0.0.2's code to its end) |
| AU-5 | `update`'s second `try` and `rollback` catch `Exception`; every child runs through `_run` (UTF-8, `errors="replace"`, no stdin). | `test_an_unexpected_error_after_the_code_moved_rolls_everything_back` (in-process, a `KeyError` after the merge) |
| AU-6 | `previous.json` and a restore's `last.json` carry `mode` and `tag`; `launch.restored_key` gives the version (releases) or the commit left, stored as Skip this version. | `test_a_restore_skips_what_it_left…`; the releases test now restores too |
| AU-7 | Windows: the old write-open probe of every `.pyd`/`.dll`/`.exe` is gone. Instead: the image path as before, plus, for each `python*.exe`, its loaded modules by path (Toolhelp `TH32CS_SNAPMODULE`), so a hard link loaded through another venv's path doesn't count. No venv walk every 0.5 s. | `test_windows_counts_a_venv_module_a_python_loaded_not_its_hard_link_loaded_elsewhere` (Windows CI only; whether the old code failed it isn't shown: no Windows here) |
| AU-8 | `_run` passes `CREATE_NO_WINDOW` on Windows (git, uv, the venv check). The relaunch is unchanged (pythonw, detached). | `test_every_program_the_updater_runs_reads_utf_8_and_opens_no_console_window` (one `subprocess.run` in the file; the flags) |
| AU-9 | `git diff --no-renames --diff-filter=A`. | `test_a_file_the_update_renames_onto_an_untracked_one_is_named` |
| AU-10 Info | `check.network_request`: `SameOriginRedirectPolicy`. | `test_a_request_follows_redirects_only_within_api_github_com` |
| AU-11 Info | `guard` runs in `main` before the log, `ready` or anything else (prints to stderr, exits 2; `--check` prints the refusal); a refusal relaunches only once the old HeLab has exited. | `test_the_test_guard_refuses_before_writing_anything`; the never-quits test asserts no relaunch |
| AU-12 Info | Not changed: (1) the provisional IDs in comments (`Q~1`, `Q~5`, `Q~6`, `Q~8`) are for the landing to rename with the merged block; (2) the design's base-Python and `git`/`uv --version` checks: presence only is built, since the README's setup gives a base Python outside the checkout; a line for the architecture file below; (3) the `testing.md` line below. | n/a |

Checks after the fixes and the merge of `dev/v0.0.9` (`8690a2f`): full suite (`pytest -n 4 --reruns 5
--reruns-delay 1 --basetemp=.ai/temp/pytest`) **9565 passed, 674 skipped, 2 warnings in 199 s, no RERUN**; the five
type checks clean (`mypy helab/ --strict` 223 files, `mypy tests --strict` 220, `--platform win32` 223, `pyright
helab tests` and `--pythonplatform Windows` 0 errors; the updater also with `--pythonplatform Linux`); `ruff check`,
`mkdocs build --strict`.

CI run **42018998611** on `fc2906d`: **failure**, macOS Tests (1/3) and (2/3) only, all three from one cause (above,
AU-3: the framework Python's venv): `test_the_updater_waits_for_helab_and_its_helpers_before_changing_a_file[lab]`
and `[My Projects]` ("it changed files while a helper ran") and `test_a_rollback_waits_for_the_new_versions_helpers`,
each RERUN 5 times then FAILED (15 RERUNs, 3 FAILED). Every other job green; the other 10 Tests and Converter
backends logs read: no RERUN. Fixed in the next commit (the `framework` case reproduces it locally).

Before that commit: a full local run had **1 rerun**, `test_updates_launch.py::test_the_quit_note_names_live` at
teardown (`AttributeError: 'object' object has no attribute 'on'` in `explorer_live.stop_live`): my own step-4
test set a tab's `live` to a stand-in with `monkeypatch`, which the window fixture's close reached before the undo
(only when the window had a tab). Fixed: the test puts it back itself. Then the full suite: **9566 passed, 674
skipped, 2 warnings in 239 s, no RERUN**; the five type checks clean.

CI run **42022523164** on `f951fc0` (pushed): **success, every job** (3 × Tests 1–3, 3 × Converter backends,
3 × Build, Docs, detection); all 12 Tests and Converter backends logs read: **no RERUN**. The Windows-only AU-7
test ran and passed on Windows Tests (and was skipped elsewhere); the `framework` case ran and passed on macOS.

AU-7 and AU-8 can't be shown here as the reviewer read them (a real lab PC). The code is safe both ways: the
module check finds a venv module however the venv was linked, and `CREATE_NO_WINDOW` only hides windows. Known-issues
line and M~3 below.

### Re-check 1 (Sentry, `4c8bbb5`): AU-1 to AU-12 fixed or closed; two new

| ID | Fix | Test (fails on `c099caf`'s updater, passes now) |
|---|---|---|
| AU-13 Minor | On "started", `record(...)` first, then `discard_older` (the deletion's errors are ignored, so it never changes the outcome); the new HeLab's 20 s poll no longer races a slow `rmtree`. | `test_the_outcome_is_recorded_before_the_older_venv_is_deleted` (in-process, a slow delete reads `last.json`: "updated" with its token is already there) |
| AU-14 Info | (1) The `__PYVENV_LAUNCHER__` match now also needs `helab` in the plain command, as the plain match does: a helper re-exec'd as `Python.app` still runs `-m helab.io_helper`; a REPL, Jupyter or pytest from the venv doesn't hold up the update. (2) The `os.environ.pop` comment now calls it a safeguard (3.13 already drops the variable). | `test_a_framework_venvs_python_counts_only_when_it_runs_helab` (macOS, a framework Python's venv: `python -c …` not counted, `python -m helab.io_helper` counted) |

Checks: the touched tests; full suite **9568 passed, 674 skipped, 2 warnings in 191 s, no RERUN**; the five type
checks clean (and the updater with `--pythonplatform Linux`).

## Proposed doc changes (for the Coordinator)

**`.ai/architecture/release-and-ci.md`**, a new section "App updates" (or a new area file `updates.md` linked
from the index and the code map), with:

- The package map above; `versions`, `github`, `updater` in `PURE`.
- The check: `QNetworkAccessManager` on the event loop, 10 s transfer timeout, GETs to `api.github.com` only
  (`User-Agent: HeLab/<version>`), refused under tests (`HELAB_TEST_SOURCE_GUARD`: give `UpdateCheck` a
  transport); ETags with trimmed replies in `<app folder>/updates/github-cache.json`; the status at start from
  the cache alone; the startup check scheduled by `main` only (never by a test's window), 30 s after show, when
  the last success is over 24 h old; requests per mode (releases + tag refs + one compare to `main`; branch:
  compare and up to 5 check-run lookups).
- Branch mode's candidates (`github.branch_line`): the branch's own first-parent line from its tip down to the
  running commit, commits that contain it; never one merged in from a side branch; the updater refuses a target
  not in `git rev-list --first-parent <tip> ^HEAD` (AU-2).
- The CI rule (`github.ci_state`): GitHub Actions' runs only; per OS `<os> + py3.13 / Tests…` and `/ Build`
  present; every `<os> + py3.13 / …` name's newest non-skipped run completed success; a name only skipped, or
  whose newest run was cancelled, is not green; other jobs don't count; group count not fixed.
- The modes and defaults (settings rows; Q~1's default repo through `build_info.upstream_repository`).
- The updater: request fields, `--check`, handshake (`ready-<token>`), the waits (process handle, locks,
  processes from the venv: `ps` by folder prefix, and on macOS `ps -E`'s `__PYVENV_LAUNCHER__` for a framework Python's venv (both only when the command names `helab`); Windows image paths, plus each Python's loaded modules by
  path), refusals, order of the
  update, the venv rebuild (`REBUILD_FILES`, `uv venv --relocatable`, the check in its own bytecode folder,
  swaps, `DELETE_OLDER_VENV`), relaunch (`HELAB_UPDATE_TOKEN`, popped by `mark_started`), roll back, Restore
  via `previous.json` (a restore's outcome stored as Skip this version), `last.json` shown once (by the new
  HeLab on its own start: `after_start` polls for its token's outcome), `tidy`. Every child through `_run`
  (UTF-8, no console window). The guard first, before any file. What isn't checked: that the base Python is
  outside the checkout (the README's setup), or `git`/`uv` versions (presence only).
- The test seams: `HELAB_UPDATER_TEST_ROOT` (required under the guard), `HELAB_UPDATER_TEST_ELEVATED` (only
  under the guard; CI's Windows runners run elevated), `UpdateLauncher.start_detached`, `launch.checkout` /
  `venv_prefix`; `tests/test_updates_updater.py`'s `Lab` (bare remote, `insteadOf`, empty global config,
  `GIT_ALLOW_PROTOCOL=file`, fake uv, fake HeLab).

**`.ai/architecture/testing.md`**: one line: `helab.updates.settings` reads this checkout's `git config`
(`build_info.upstream_repository`, read only) to choose the default repository, so a test that depends on it
patches `build_info.upstream_repository` and clears `settings._upstream` (CI's branch tracks `TonyXTYan/HeLab`).

**`.ai/architecture/app-runtime-and-ui.md`**: Help's three new items, the status-bar mark (`update_available`,
before the resources label), About's three lines, Settings › General's two rows.

**`.ai/architecture/settings.md`**: the six `updates_*` rows.

**AGENTS.md** (one line, I/O and threads or Versions and releases): "HeLab never changes its own code while it or
a helper runs: only the updater (`helab/updates/updater.py`, a standard-library copy run by the base Python)
changes a checkout, after HeLab, its helpers and its locks are gone; never from an SSH or elevated session."

**AGENTS.md's housekeeping list** (Q~8, CoCo's note), one bullet: "an update that rebuilt the venv deletes the
venv kept before the previous one (`<venv>.previous-<UTC>`) once the new version has started
(`updater.DELETE_OLDER_VENV`); the updater's own `venv.new`/`venv.failed`/`pycache-<token>`, and at start its
copies, requests and marks over an hour old and update logs beyond 20 (`launch.tidy`)."

**The manual**: written (`docs/how-to/update.md`, nav, settings rows).

## Questions for Tony (from the design; CoCo has them in Chat)

Q~1–Q~10 as in design.md §11, all built to their proposals. Built so a change is small: Q~5 is `REBUILD_FILES`,
Q~8 is `DELETE_OLDER_VENV`, Q~3 is `wait_started`'s "unconfirmed" branch, Q~6 is `source_for`.

New:

- **Q~11 uv only when needed.** The plan says refuse when `uv` is missing; built: refused only when the venv must
  be rebuilt (a git-only update needs no uv). (a) As built (proposed). (b) Always refuse without uv.
- **Q~12 About's exact text** is still the provenance dialog plus three lines ("Version status", "Updates",
  "Last check"); fine as is, or a layout of its own later (proposed: as is).

## Follow-ups (provisional)

- **A~2** The frozen self-update (Q65.1 (b) later): `updater` has no frozen path; `UpdateWindow` shows
  Download only.
- **A~3** The update window's commit list shows CI for the commits looked at only (at most 5); the rest show none.

## Proposed known-issues entries

- [ ] `test_convert_helab.py::test_a_killed_helpers_workers_exit`: `AssertionError: the pool started` /
  `assert []` at line 1099 (no child of the converting helper seen by `psutil` once the first `shot_converted`
  arrived), twice in one local macOS run of `agent/app-updates` (2026-11-05, load average 460–650 from other
  floors); passed on retry. The Ledger floor saw the same RERUN (CoCo to merge the two). Not touched by this branch.

- [ ] Windows updater behaviour not yet seen on a lab PC (from the review, AU-7 and AU-8): whether a DLL uv
  hard-linked into HeLab's venv and loaded by another venv's Python is told apart (built: each Python's modules by
  path; a test on Windows CI), and whether git or uv flash console windows during an update (built:
  `CREATE_NO_WINDOW`). Until M~3.

## Manual checks

- **M~1** Tony: a real update from source on this Mac **and** on a lab PC (Windows), each in both modes: a
  branch with a newer green commit (Update and restart → back on the new commit, status bar "updated"), then
  Help › Restore previous version (back on the old commit, and the old venv if the lock changed); and a
  release-to-release update on a checkout at a tag. On Windows watch for the updater waiting on helpers, the
  venv rename and the relaunch without a console. Never over SSH.
- **M~2** The startup check on a lab PC's network (the plan's DNS/proxy risk): Help › Check for Updates… names
  the reason when it can't reach GitHub, and startup is quiet.
- **M~3** (the review's AU-7, AU-8) on a lab PC (Windows): update while another uv venv's Python with numpy runs
  (e.g. a second checkout's `python -c "import numpy, time; time.sleep(600)"`): the update goes ahead and isn't held
  by that venv's DLLs; and no console window opens during the update (git, uv, the venv check).
