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
- The CI rule (`github.ci_state`): GitHub Actions' runs only; per OS `<os> + py3.13 / Tests…` and `/ Build`
  present; every `<os> + py3.13 / …` name's newest non-skipped run completed success; a name only skipped, or
  whose newest run was cancelled, is not green; other jobs don't count; group count not fixed.
- The modes and defaults (settings rows; Q~1's default repo through `build_info.upstream_repository`).
- The updater: request fields, `--check`, handshake (`ready-<token>`), the waits (process handle, locks,
  processes from the venv: `ps`; Windows image paths + in-use `.pyd`/`.dll`/`.exe`), refusals, order of the
  update, the venv rebuild (`REBUILD_FILES`, `uv venv --relocatable`, the check in its own bytecode folder,
  swaps, `DELETE_OLDER_VENV`), relaunch (`HELAB_UPDATE_TOKEN`, popped by `mark_started`), roll back, Restore
  via `previous.json`, `last.json` shown once, `tidy`.
- The test seams: `HELAB_UPDATER_TEST_ROOT` (required under the guard), `HELAB_UPDATER_TEST_ELEVATED` (only
  under the guard; CI's Windows runners run elevated), `UpdateLauncher.start_detached`, `launch.checkout` /
  `venv_prefix`; `tests/test_updates_updater.py`'s `Lab` (bare remote, `insteadOf`, empty global config,
  `GIT_ALLOW_PROTOCOL=file`, fake uv, fake HeLab).

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

## Proposed known-issues entry

- [ ] `test_convert_helab.py::test_a_killed_helpers_workers_exit`: `AssertionError: the pool started` /
  `assert []` at line 1099 (no child of the converting helper seen by `psutil` once the first `shot_converted`
  arrived), twice in one local macOS run of `agent/app-updates` (2026-11-05, load average 460–650 from other
  floors); passed on retry. The Ledger floor saw the same RERUN (CoCo to merge the two). Not touched by this branch.

## Manual checks

- **M~1** Tony: a real update from source on this Mac **and** on a lab PC (Windows), each in both modes: a
  branch with a newer green commit (Update and restart → back on the new commit, status bar "updated"), then
  Help › Restore previous version (back on the old commit, and the old venv if the lock changed); and a
  release-to-release update on a checkout at a tag. On Windows watch for the updater waiting on helpers, the
  venv rename and the relaunch without a console. Never over SSH.
- **M~2** The startup check on a lab PC's network (the plan's DNS/proxy risk): Help › Check for Updates… names
  the reason when it can't reach GitHub, and startup is quiet.
