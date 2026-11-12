# Handoff: Live stops picking up shots after a conversion (`agent/live-stall`)

Worker: Pulse (Claude Code, Opus 5.5), 2026-11-12. Base `d2bd306`, brief `9e75d77`. Not pushed (CoCo: push only
after Lookout's clean read and a merge of the latest `dev/v0.0.9`). Evidence and measurements: [notes.md](notes.md).

## Summary

**Cause found and reproduced.** A Live check that answered `live_unchanged` stayed in `FolderCache.jobs` until its
helper's `done`, and that `done` can reach the GUI one `IOService._drain` later (8 ms of events per tick; Live's
slow repaints on the lab PC use that up). A converted shot asks for the next check at once (`check_soon`, or
`_live_next(0)` just after the answer). Started in that gap, `FolderCache.submit` found the owner's old request
(`has_request`) and returned True without starting anything. `session.request` then stayed "check" for good, so
Live neither checked nor converted again (`_convert_tick` runs only from `_live_tick`). This matches both stops:
the last `convert_done converted=1` came during a GUI stall, no `load_done` followed, and no helper ran.

## What changed (commits)

| Commit | What |
|---|---|
| `997e4e5` | **The fix.** `FolderCache._event`: a `live_unchanged` takes the job off the list and clears its subscribers, as a `loaded` already does, so the next check is its own job and a late `done` or `error` of the answered one reaches no one. |
| `0a90050` | **Backstop.** `LiveController._live_watch` runs every 10 s while Live is on (`LIVE_WATCH_SECONDS`). A check or save Live thinks is in flight with nothing behind it in FolderCache (not queued, running or waiting its turn: `has_request`, the new `FolderCache.save_deferred`), or no check timed at all, for `stall_seconds()` = max(60 s, 4 × interval) since the last was asked for (`check_started_at`), logs one WARNING naming the state (request, reading, check_soon, timer, counts, auto-convert's request, error, open question, last end) and how old it is, then starts a check. A conversion asked for (`requested_at`) with no job behind it for as long logs the same way and ends, so the next tick converts. A request whose job still exists is left to IOService's no-progress timeouts, never replaced beside itself. Live stopped on an error still waits for Retry. The numbers are log-only (CoCo approved). The backstop would also have recovered the lab's stall within about a minute. |
| `c24bd5d` | **The waiting-file rule (step 3).** The format reasons already ended as damaged after 20 s since first seen (the GUI does send each waiting entry's first-seen field back in `seen`), and settling, changed and future all end on their own. The one that didn't was `read_failed` (an `OSError` reading a settled, unchanged file), which waited for good and was re-read every pass. Now, unchanged and still unreadable for `DAMAGED_SECONDS` (20 s, the same two clocks as damaged), it is `shot_unconvertible` with reason `read_failed` and "Couldn't be read for N s: <error>", skipped while unchanged. It is tried again when its size or mtime changes, by a new Live session (or auto-convert off and on), and by Convert this folder… (`FolderCache.convert_unreadable` records when; `convert(..., retry_unreadable_since=<asker's start>)` leaves the files found unreadable before it out of `skip`). Rule and 20 s approved by CoCo (Q1). |
| `871afff` | **The two GUI stall sources (step 4).** `low_hits_threshold()` is read once per settings store and then kept in memory until `set_low_hits_threshold` (the Auto-convert menu) or Settings close (`HelabMainWindow._apply_live_settings` → `forget_low_hits`, after Save or Reset all). It is keyed by `HELAB_TEST_SETTINGS_FILE`, so each test's own file reads it afresh, with no conftest change. `_update_plot_source_label` works out the line, tooltip and error from the dock's properties first, sets the labels only when those change (a key on their wrapper, which `_wrap_plot` replaces), and finds them with `FindDirectChildrenOnly` on the wrapper, never through the plot's widget tree. |
| `88e96ce` | **Activity (step 5).** `AutoConvert.summary_at`. The Auto-convert row's "waiting for N raw files to settle" gets " (as of HH:MM:SS)" once that summary is older than `stall_seconds()` with no conversion since (CoCo approved, Q2). |

### Review fixes (Lookout's read of `7c28fc1`: no blockers; F1–F4 from CoCo)

| Commit | Finding | What |
|---|---|---|
| `5a35599` | F2 | Every answer that ends a load for its subscribers (`ANSWERS` = `shots_missing`, `too_large`: a load's, a Live check's or save's, a cached read's) goes through `FolderCache._answered`, shared with `live_unchanged`. The job leaves `jobs`, its subscribers get the answer and nothing after, and `_producers` keeps it so the late `done` finds the orphan (a deferred save still starts at that `done`). The helpers stop right after these answers (`live.py`, `save_held.py`, `loading.py`), so no store write path is touched. Test: Live stopped by either answer, Retry clicked before the `done`: a check of its own runs. It fails with the change disabled. |
| `28d072a` | F1 | The Live row's "waiting for N files to settle" (`session.unsettled`, from the last check) gets " (as of HH:MM:SS)" once `checked_at` is older than `stall_seconds()`. This is most likely the text Tony saw, since both stops' last conversions logged waiting=0. The Auto-convert row's test docstring no longer claims to be the lab's text. |
| `3b6624b` | F3 | The Live tooltip (and so Folder details' Auto-convert row) adds "<files>: couldn't be read; Live off and on, or Convert this folder…, tries it again." (CoCo's wording). A `FileNotFoundError` on read (removed or renamed after the listing) waits as `changed` ("Gone when it was read (removed or renamed): looked at again at the next check"), never `read_failed`. |
| `e578c47` | F4 | Only `read_failed` creates a folder's `convert_unreadable` entry (bounded like `convert_reasons`). Another reason removes the file, and the entry once it's empty, so a conversion cancelled before its summary leaves none. |

### Review round 2 (Lookout: F1–F4 closed, no blockers; G1 and H1 from CoCo)

| Commit | Finding | What |
|---|---|---|
| `efa21be` | G1 | On Windows a raw path of 260+ characters fails to open as `FileNotFoundError` (WinError 3); since `3b6624b` it waited as `changed` for good, silently. The `FileNotFoundError` branch now asks `path_too_long`, as the TXY's write does. While the folder is there, the file is unconvertible ("failed", "Path too long for Windows (N characters …)"), skipped while unchanged. With the folder gone too, it waits. Test with `PLATFORM` patched to win32. |
| `8e882fa` | H1 | `build_info._git` runs every git call with `GIT_OPTIONAL_LOCKS=0`. Every process importing `helab.utils.constants` (the app, each helper, each test worker) runs `get_build_info()`, whose `git status` refreshed the index under `index.lock`; the 2 s timeout's kill under load left the stale, empty lock seen twice on this floor (Lookout: 8 of 150 samples in a parallel suite; on Ground too). Tests: every call gets the variable; in a temporary repository with a stat change, `_git`'s status leaves the index unwritten while plain `git status` rewrites it (both fail without the change). `helab/build_info.py` (CoCo's brief said `helab/utils/build_info.py`; the module is `helab/build_info.py`) was added to my owned files for this only. |

**Merge with `dev/v0.0.9`**: fetched `origin/dev/v0.0.9` at 12:40. It is still `d2bd306`, this branch's base, and
Ground's local `dev/v0.0.9` (`9e75d77`, the brief) is already in the branch, so there was nothing to merge and
there is no merge commit. The checks below are on the branch's head, `8e882fa`.

### Files outside the brief's owned list (each approved or required by CoCo's answers)

- `helab/io_ops/convert.py`: the `read_failed` rule (CoCo's Q1 approval). `READ_FAILED`; `unchanged_for` shared by `unfinished_or_damaged` and the new `unreadable`; module docstring.
- `helab/views/explorer_convert.py`, one line: `_pass` passes `retry_unreadable_since=conversion.started_at` (CoCo's condition: Convert this folder… tries unreadable files again).
- `helab/views/HelabMainWindow.py`, one line plus an import: `_apply_live_settings` calls `explorer_live.forget_low_hits()`, so a Reset all reaches the cached threshold.
- `helab/views/ActivityWindow.py`: the "(as of …)" note (CoCo's Q2 approval).
- `helab/io_ops/events.py` is **not** changed (`reason` is a `str`); its docstrings are proposed below.

## Measurements (this Mac, offscreen; scripts in `.ai/temp/measure_*.py`)

| | Before | After |
|---|---|---|
| `low_hits_threshold()` (ini store) | 3.4 µs, one settings read a call | 0.3 µs, no read after the first |
| `_update_plot_source_label`, unchanged text, plot of 84 widgets | 70 µs | 15 µs |
| the same, plot of 1,110 widgets | 78 µs | 13 µs |

Of the 70 µs before, each `findChild` took about 9 µs and `ElidedLabel.setText` of unchanged text about 24 µs.
The lab's Windows registry store and its slower PC weren't measured (M~1). Across the 217 stalls in the three logs,
the GUI thread was in `low_hits_threshold` in 62 and in `_update_plot_source_label` in 71 (table in notes.md).

## Tests

New: `tests/test_live_stall.py` (7 tests):
- the stall in both orders: failed before `997e4e5`, pass after;
- a late error of an answered check doesn't stop the next;
- the backstop: a lost check, a running check left alone, a lost conversion, a lost timer, and the watch stopping with Live;
- an unreadable file in Live: unconvertible on the line, skipped by the same auto-convert, tried again after off/on;
- the threshold read once, set from the menu, re-read as Settings close after a Reset;
- a plot's source line set only on a change, and anew for replaced content.

Also added:
- `tests/test_convert_helab.py::test_a_raw_file_unreadable_for_20_s_is_unconvertible_and_holds_nothing_up`
- `tests/test_convert_folder.py::test_convert_this_folder_tries_again_the_files_found_unreadable_before_it`
- `tests/test_activity.py::test_an_auto_convert_rows_waiting_note_says_when_it_was_once_no_conversion_followed`

Changed:
- `tests/test_live_convert.py`: the low-count test sets 0 through `set_low_hits_threshold`, as the menu does.
- `tests/test_activity.py`: `fake_explorer`'s `live_control` gains `stall_seconds`.

Full suite (`pytest -n 8 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`):
- on `88e96ce`: 9,931 passed, 674 skipped, no RERUN;
- on `e578c47`: 9,936 passed, 674 skipped, no RERUN;
- on the head `8e882fa`: **9,939 passed, 674 skipped, 10 warnings, no RERUN**, and no `index.lock` left after the run.

The output of the head's run is whole in [full-suite.txt](full-suite.txt). The 10 warnings are PyQtGraph's NumPy 2.5
deprecation notices from plot tests; their count varies with the workers, and they're not this branch's. The skips are the private test data, not
checked out on this floor.

**RERUN on record** (Lookout's run of `7c28fc1`: 9,931 passed, 1 RERUN):
`tests/test_convert_helab.py::test_a_killed_helpers_workers_exit` ("the pool started / assert []", line 1145).
It is already in known-issues (line 474), not caused by this branch, and it didn't rerun in my two runs.

Twice during this work, git found a stale, empty `index.lock` in this worktree's git folder (11:45 and 12:05,
each during or just after a test run; no process held it), and I removed it. Lookout traced it to
`build_info._git`'s `git status`, killed by its timeout under load; fixed by H1 (`8e882fa`).

The five type checks, all clean on `8e882fa` (output in [type-checks.txt](type-checks.txt)):
- `mypy helab/ --strict` and `mypy tests --strict`: no issues;
- `pyright helab tests`: 0 errors;
- `mypy helab/ --strict --platform win32`: no issues;
- `pyright --pythonplatform Windows helab tests`: 0 errors.

## Seen by users (for CoCo to tell Tony)

- **Live no longer stalls after a conversion**, and if it ever loses a check again, it starts a new one within about
  a minute and logs a warning that says why.
- **A raw file HeLab can't read stops being waited on** (Tony's "we shouldn't hang on to waiting … after say 15s
  timeout?"). After 20 s unchanged and still unreadable, it shows as unconvertible ("Couldn't be read for N s: …") on
  the Live line, in its tooltip and in Folder details, and later shots go on. It is tried again when it changes, in
  a new Live session (or auto-convert off and on), and by Convert this folder…, so a lock never loses a shot for good.
  It's 20 s, not 15 s, the same as damaged files.
- **Activity's Auto-convert row** says when its "waiting for N raw files to settle" was true, "(as of 16:38:50)",
  once no conversion has followed for over a minute.

## Proposed items (provisional IDs)

- **A~1** (follow-up, evidence in notes.md): the mount table's refresh (`cache_location.mount_table`, every 10 s,
  GT-7 b) still runs on the GUI thread, from `_convert_tick` → `explorer_convert.share_to_confirm` whenever beside
  is on. In 3 of the first log's stalls the GUI thread was blocked in `cache_paths._windows_unc`. Proposal: refresh
  the table on a worker thread (or ask a helper) and read the last one from memory; `tests/data/gui_thread_allowed.txt`
  lines 11–15 would then lose their reason.
- **A~2**: `HelabMainWindow._update_folder_details` runs on most Live events (each `_update_activity` and
  `loadStateChanged`), so every event re-renders Folder details and every plot's source line. Coalescing it to
  once per event-loop turn (a 0 ms single-shot) would cut the GUI work per drain. In 65 of the 217 stalls only the
  event loop was on the stack.
- **A~3**: `IOService` delivers a helper's answer and its `done` in different drains under load. F2 covered loads'
  answers (`ANSWERS`). Live's conversion ends on `done` (after `_forget_job`), and scans replay their snapshot at
  `done`. A short audit of the other `has_request` callers (results, admin, icons) would close it.
- **A~4** (H1's follow-up; Lookout's evidence: a stale `index.lock` in 8 of 150 samples of a parallel suite run,
  and on Ground): every process importing `helab.utils.constants` still runs `get_build_info()`'s four git calls
  (each up to 2 s), including each I/O helper and each test worker. Cache the build info once per app run and pass
  it to helpers (as `settle_seconds` is), or read it lazily where it's shown (About, the log's header). This would
  also help "Commit: unknown" in the lab's log (A73.6), which may be the 2 s timeout on the slow PC.
- **M~1** (the lab PC): the next time Live runs with auto-convert there, check that the log has no "Live: no check
  started for" warning. If one appears, the backstop fired: send the log. Also see whether GUI stalls are fewer
  than the 70 of 2026-11-11.
- **M~2** (any machine): lock a raw file in a Live folder (Windows: open it exclusively; macOS: `chmod 000`) and
  check it shows as "Couldn't be read for 20 s: …" unconvertible within about 25 s, that later shots go on, and
  that it converts after Live off and on once unlocked.

No `Q~`: CoCo approved the 20 s, the backstop's numbers and the Activity wording.

## Proposed doc changes (for the Coordinator to apply when landing)

- **`.ai/architecture/live.md`**, Live paragraph, after "Errors stop the checks but keep Live and the data …":
  > A check's answer ends it for its subscribers: `live_unchanged`, like `loaded`, takes the job off
  > `FolderCache.jobs`, so a check asked for before the helper's `done` reaches the GUI (a converted shot's
  > `check_soon`) is a job of its own (`997e4e5`; the lab's stall of 2026-11-11). **Backstop** (`_live_watch`,
  > every `LIVE_WATCH_SECONDS` = 10 s while Live is on): a check, save or conversion Live thinks is in flight with
  > nothing behind it in FolderCache (`has_request`, `save_deferred`), or no check timed, for
  > max(`LIVE_STALL_SECONDS` = 60 s, `LIVE_STALL_INTERVALS` = 4 × interval), logs a WARNING with Live's state and
  > starts a check (a conversion ends and the next tick converts); a request whose job exists is its helper's to time
  > out.
- **`live.md`**, Auto-convert paragraph, where the waiting reasons are listed: "…and unconvertible (a file
  unreadable for 20 s: `read_failed`, tried again by the next auto-convert or Convert this folder…), …". Also: the
  low-count threshold is read from memory (`low_hits_threshold`; `forget_low_hits` as Settings close).
- **`.ai/architecture/converter.md`**, settle rules: the `read_failed` rule as in `convert.py`'s module docstring,
  and `FolderCache.convert`'s `retry_unreadable_since` (`convert_unreadable`).
- **`.ai/architecture/app-runtime-and-ui.md`**, Activity: the Auto-convert row's "(as of HH:MM:SS)" once its summary
  is older than Live's backstop limit; and plots' source lines set only on a change (`plotSourceShown` on the
  wrapper).
- **`.ai/architecture/io-and-browsing.md`**, FolderCache jobs: a shared job whose answer was delivered (`loaded`, and
  through `_answered`: `live_unchanged`, `shots_missing`, `too_large`) leaves `jobs` at once, keeping `_producers`
  for the late `done`. Until then `submit` joins it (`has_request` says yes and starts nothing), so a new answer
  kind that ends a request must go in `ANSWERS`.
- **`helab/io_ops/events.py`** (docstrings only, CoCo to approve): `ShotWaitingEvent`'s "couldn't be read now
  (`read_failed`)" gains "…; unconvertible once unchanged and unreadable for 20 s". `ShotUnconvertibleEvent`'s
  reasons gain "`read_failed` (unchanged and unreadable for `DAMAGED_SECONDS`, by its mtime and since first seen)".
- **`roadmaps/known-issues.md`**: no new RERUN entry; Lookout's one RERUN (`test_a_killed_helpers_workers_exit`) is
  line 474's. If Live stalling is listed there, it can be closed by `997e4e5`. A new line, closed by H1:
  > **Stale `index.lock` in checkouts** (2026-11-12, fixed `8e882fa`): `build_info._git`'s `git status`, run by every
  > process importing `helab.utils.constants`, refreshed the index under its lock, and its 2 s timeout's kill under
  > load left an empty `index.lock` that stopped the next commit (floors and Ground). Now run with
  > `GIT_OPTIONAL_LOCKS=0`; the per-process git calls remain (A~4).
- **`converter.md`**: G1, a raw path past Windows' limit is unconvertible ("failed"), not waited for.
- **`AGENTS.md`**: optionally one invariant under "I/O and threads": "A shared job leaves `FolderCache.jobs` as its
  answer is delivered (`loaded`, `live_unchanged`, `ANSWERS`), never only at `done`: a request joined after the
  answer waits for good."
- **`app-runtime-and-ui.md`**, Activity: the Live row's "waiting for N files to settle (as of HH:MM:SS)" too (F1).
- **`converter.md`**: a raw file gone when read waits as `changed`, never `read_failed` (F3).
