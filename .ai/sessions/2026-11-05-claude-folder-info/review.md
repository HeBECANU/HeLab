# Review: the Folder info window (`agent/folder-info`)

Reviewer (Claude, Opus 5.5), 2026-11-05, for CoCo. Diff `6140924...8620de5` (ten commits, no merges in the range),
read against the brief, `design.md` (with CoCo's answers), `handoff.md`, `roadmaps/folder-info.md` (Decided:
Q64.1–Q64.11), AGENTS.md's rules and the touched areas' architecture files. Read only: nothing in the tree was
edited; the repros below are scratchpad scripts, not committed.

## Checks rerun

- **Full suite**: `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-tally` (after
  `source .ai/local/floor-env.sh`) at `8620de5`: **9500 passed, 673 skipped, 2 warnings, no reruns** (no RERUN in
  the output; the warnings are pyqtgraph's NumPy 2.5 deprecation in `test_t_spectrum.py`). Output whole:
  `.ai/temp/review-suite.txt`. Matches the handoff's last run.
- **Type checks**: `mypy helab/ --strict`, `mypy tests --strict`, `pyright helab tests`,
  `mypy helab/ --strict --platform win32`, `pyright --pythonplatform Windows helab tests`: all clean; `ruff check`
  clean. Output whole: `.ai/temp/review-types.txt`.
- **Repros** (scratchpad, run with `-p tests.conftest` so conftest loads first; they reuse the branch's fixtures):
  - Live's save on stop: show the window, Live on, Live off (`live_path = ""`, as `stop_live` sets `live = None`
    before its save), then `saveEnded(path, "saved")`: **no read is submitted** (FI-1).
  - An unverified drive with the real opener (the setup of `test_store_migration`'s
    `test_constants_on_an_unverified_volume_wait_for_its_verification`, store-v4): `cache_admin("folder_info",
    verified_volumes=[[mount, source]])` → `root_state "rooted"`; `verified_volumes=[]` → **`root_state
    "no_root"`**, every store part `skipped: "Disk cache off: no data root for …"` (FI-2).
- CI: not rerun (the floor can't push; CoCo pushes from Ground).

## Summary

The read, the model and the window are careful and match the brief: the helper reads only the store (one read
transaction) and the converted-TXY indexes read only, its key resolution comes from the store's root rows (no
walk of the source folder; the helper test traces `os` calls), the event is bounded (200 results, 32 layers and
views, cut settings texts), each part answers found / missing / error / skipped, a failed job keeps the last
lines greyed with the reason, `Reads` keeps one read in flight with a newer ask replacing the queued one, and a
retarget drops the old answer. The per-folder Clears go through the existing removals scoped to the folder:
`remove_raw([path])` bumps the folder's `raw:` epoch (a folder with no rows too), `remove_results([path])` bumps
its results epoch and takes its waiting results, and `clear_converted_folder` fences the base's index first, lists
only that folder's `converted-txy/<name>` (never a link, never the source folder), forgets only the rows of the
files it removed (beside TXY's rows and files untouched), and never touches set-aside indexes or other folders.
Each sends `removed` with `paths: [path]`, which `FolderCache.removed` handles by path for every kind. Only copies
are named in each question; Keep is the default. The Windows time fix (9da2bee) routes every time through
`local_time`, which bounds the range and catches `OSError`. The ways in, the `identify` IDs and the
accessible-names walk (window with its detail pane open) are in place; no lambda captures a Qt-made sender and
nothing connects to `destroyed`.

**No blocker.** Two Majors: Live's save on stop doesn't refresh the window (the brief's Q64.4 and the manual say
it does), and a folder on a drive not verified yet this session reads as "RAM only … nothing is cached" (the
"never nothing saved" rule), because the helper only catches a `VolumeUnverified` the real resolver never raises
there; the tests pass because they fake `_path_key`. Both have small fixes.

## Findings

### FI-1 Major: no read after Live's save on stop

`helab/views/FolderInfoWindow.py:327` (`_save_ended`), with `helab/views/explorer_live.py:383` (`stop_live`).

**What is wrong.** `_save_ended` reads only `if outcome in ("saved", "superseded") and self.live()`. But
`stop_live` sets `self.live = None` *before* `_live_save(session)` submits the stop's save, so by the time that
save's `saveEnded` arrives, `watching()` is false for every tab and `_save_ended` falls to `_changed(path)`, which
reads only when an action armed it. `live_changed` on stop rebuilds memory only. The brief's refresh rule ("the
store read after each Live save (every 10 shots and on stop)"), `live_changed`'s own docstring ("Its last save,
on stop, reads again through `saveEnded`") and the manual (`docs/how-to/folder-info.md:74`, "and when Live
stops") all say it reads.

**Failure scenario.** Folder info open on a run during Live, 7 shots since the last autosave; the user stops
Live. The stop's save writes those 7 shots, but the window keeps "As of" the last autosave and the Disk cache
line's shot count and range stay 7 shots short until the user clicks Refresh. Reproduced (scratchpad test above):
no `folder_info` request after the save ends. `test_while_live_watches_it_reads_after_each_save_and_follows_checks`
covers only saves while Live is on.

**Fix.** Remember that Live watched the folder: in `live_changed`, when Live goes from on to off for `self.path`,
mark a one-shot "Live's last save pending" (or simply `self.arm()`), and in `_save_ended` read on `saved` /
`superseded` when either `self.live()` or that mark holds (then clear it). Add a test: Live on, Live off, then
`saveEnded` → one read.

### FI-2 Major: a drive not verified this session reads as "RAM only … nothing is cached"

`helab/io_ops/folder_info.py:58` and `helab/io_ops/admin.py:464` (`_converted_folders`); tests
`tests/test_folder_info_helper.py:184` and `:451`.

**What is wrong.** On a hinted mount not verified this session, the admin opener (`stores._cache_store` with
`verified_volumes`) leaves that mount out of the resolver and records it in `store._unverified_mounts`; it turns
`NoDataRoot` into `VolumeUnverified` only for `source_paths`, which admin jobs don't pass. So `store._path_key(path)`
raises plain **`NoDataRoot`** there, and `folder_info`'s `except VolumeUnverified` never fires: the read answers
`root_state "no_root"`. (The other admin actions that care check `store._unverified_mounts` themselves:
`admin.py:221–223` for `constants`, `listings.py:165` for the offline listing.) The two tests replace
`store._path_key` with one that raises `VolumeUnverified`, so they pass without exercising the real path.

**Failure scenario.** HeLab starts, the user selects a run on a USB disk with a full disk cache and presses ⌘I
before the drive's verification finishes (or while Work Offline keeps it unverified). The header shows the data
root (memory knows it), but Disk cache and Saved plot results say "RAM only: no .helab-root here or above, so
nothing is cached for this folder": the "never nothing saved" rule broken, contradicting the header. The Clears
are then safe but say the wrong thing: Clear raw pulses / saved results are greyed (parts skipped), and if
offered they fail with "Disk cache off: no data root …"; Clear converted TXY doesn't refuse as the handoff and
the manual (`docs/how-to/folder-info.md:115`) say, it falls back to the temp folder by path (`_converted_folders`
catches the `NoDataRoot` as `UnresolvedRemotePath`). Reproduced with the real opener (above).

**Fix.** In `folder_info` and `_converted_folders`, after a `NoDataRoot`, check
`any(_inside(_normal(path), _normal(mount)) for mount in store._unverified_mounts)` as `constants` does, and treat
it as unverified (the read: `root_state "unverified"`; the converted Clear: raise `VolumeUnverified`). Replace the
two tests' `_path_key` fakes with the real opener on a hinted mount with `verified_volumes=[]` (the setup of
`test_store_migration.py:233`), for the read and for all three Clears.

### FI-3 Minor: opening the detail pane moves the window down by its title bar

`helab/views/FolderInfoWindow.py:567–575` (`open_detail`).

**What is wrong.** `width, x = self.width() + …, self.x()` then `self.setGeometry(x, self.y(), width,
self.height())`. For a top-level window `x()`/`y()` are the **frame's** position, while `setGeometry` sets the
geometry **excluding** the frame (Qt's documented semantics), so each open places the client area where the frame
was: the window moves right by its border and down by its title bar.

**Failure scenario.** On macOS (title bar ≈ 28 px) the user opens and closes "All 40 saved results ›" a few times:
the window creeps ~28 px down per open, until its bottom (and the pane's) runs off the screen; `close_detail`
only resizes, so nothing moves it back. Not reproducible under the offscreen platform (no frames); from the Qt
docs and the code, not seen on a screen.

**Fix.** Keep position and size apart: `self.move(x, self.frameGeometry().y())` (frame coordinates, as `x()` is)
and `self.resize(width, self.height())`, or compute from `self.geometry()` throughout. Add it to M~1's checks.

### FI-4 Minor: Clear raw pulses' question doesn't say the pulses come back

`helab/utils/folder_info.py:678` (`clear_question`, raw).

**What is wrong.** The per-folder question says "Remove HeLab's cached raw pulses of <folder> (<size>)? Your d
files aren't touched." Settings › Cache's Clear raw pulses adds "their pulses are cached again from them after the
next load of each folder" (`CacheTab.py:782–784`); S4~1's question, which this wording follows, comes after "TXY
only", where they don't come back. Here, with the folder's policy keeping raw pulses, `raw_fill` caches them
again after the next load or Live save.

**Failure scenario.** The user clears a 1.8 GB folder's raw pulses during Live to make room; at the next Live save
(10 shots) `raw_fill` caches them all again and the window's next read shows them back, with nothing having said
so. Not a data risk (the only copies are named), but the space doesn't stay free.

**Fix.** The wording is Tony's (Q~6 (a)), so a provisional item for him rather than a change here: add "They are
cached again from your d files after the next load, unless the folder's cache policy is TXY only." (or link the
folder's Cache policy…), as Settings' question does.

### FI-5 Minor: minimised, the window stops following Live and doesn't catch up when restored

`helab/views/FolderInfoWindow.py:617–630` (`showEvent`, `hideEvent`).

**What is wrong.** Qt sends a spontaneous `hideEvent` when a window is minimised and a `showEvent` when restored.
`hideEvent` disconnects the cache's signals and stops both timers; `showEvent` reconnects but reads nothing.
(`hideEvent` also saves the size on every minimise; harmless.)

**Failure scenario.** The user minimises Folder info during Live; three autosaves pass; on restore the window shows
the pre-minimise read and This session lines until the next Live check or save. "As of" stays honest, so this is
staleness, not a wrong statement.

**Fix.** In `showEvent`, when it reconnects after a spontaneous hide (or whenever `self.path` is set and Live
watches it), `self.request_read()` and start the memory timer; or only disconnect on a non-spontaneous hide
(`a0.spontaneous()`).

### FI-6 Info: the converted-TXY Clear's fence is the base's one token (A~5)

`helab/io_ops/helab_txy.py:852` (`clear_converted_folder` → `_clear_folders`, `index.set_fence`).

As the handoff says and the manual's last paragraph tells users: a per-folder Clear sets the index's single fence,
so a conversion of *another* folder into the same base running at that moment stops writing and converts the rest
at its next check (nothing lost or brought back; its wait message names a Clear the user didn't make there). The
per-folder ordering is right: the folder is checked to exist before the fence, then fenced, then listed, so a TXY
renamed in before the fence is found. Agree with recording A~5 (a per-folder fence token) for later.

### FI-7 Info: store errors of flags, choices and constants aren't shown

`helab/utils/folder_info.py:467` (`_flags`), `:494` (`_choices`), `:516` (`_constants`).

Those sections show memory (what applies) and use the store's row only for the "(not saved yet)" comparison and
tooltips; a `prefs`, `convert_prefs`, `choices` or `constants` part that answered `error` is silently dropped (the
comparison skips it, correctly). Nothing says "nothing saved", so no rule is broken, but the user isn't told the
saved row couldn't be read. Optional: a tooltip line "Couldn't read the saved value: <why>" on the first row of the
section, as Scan history does for `history`.

### FI-8 Info: clamped to the screen only at the first show

`helab/views/FolderInfoWindow.py:607–621` (`fit_screen`, `_fitted`).

The window is made once at startup and clamped to its parent's screen at its first show only. If it was first
shown on a large monitor and later reopened (`show_folder`) after the main window moved to the laptop's screen,
it keeps the larger size until the user resizes it. Calling `fit_screen()` from `show_folder` (cheap, memory
only) would keep "never taller than its screen" on every open. Worth adding to M~1 (the laptop screen) either way.

## Doc changes the handoff should carry

- With FI-1 fixed, the manual's "and when Live stops" holds; until then it is wrong. With FI-2 fixed, the
  manual's "a drive not checked yet this session" refusal holds for all three Clears.
- The proposed `io-and-browsing.md` line ("`clear_converted_txy` … trusts only verified volume hints") should say
  how: through `store._unverified_mounts`, as `constants` (once FI-2 is fixed).
- FI-4 as a provisional `Q~` for Tony (the raw pulses question's wording); FI-3 and FI-8 into M~1 (open and close
  the detail pane several times on macOS and on Windows; reopen after moving to the laptop screen).
