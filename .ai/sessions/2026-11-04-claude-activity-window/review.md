# Review: the Activity window (`agent/activity-window`)

Gauge (Reviewer), 2026-11-04. Diff reviewed: `63b9a15..b2e996a`, without `cab0f3b`'s merge of `c0860ec` (its
`CacheTab.py` hunk is identical to `c0860ec`'s and was left out). Read against the brief, `design.md` (with CoCo's
answers), `handoff.md`, `roadmaps/activity-window.md` (Q62.1–Q62.5) and `AGENTS.md`.

## Checks rerun

- Full suite at `b2e996a`, `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-gauge`:
  **9382 passed, 673 skipped, no RERUN** (output kept whole in `.ai/temp/gauge-suite.log`).
- `mypy helab/ --strict`, `mypy tests --strict`, `pyright helab tests`, `mypy helab/ --strict --platform win32`,
  `pyright --pythonplatform Windows helab tests`: all clean (`.ai/temp/gauge-types.log`).
- Reproductions of AW-1 (offscreen, scratchpad scripts, not committed): with the real `IOService` and
  `FolderCache`, and with a fake snapshot source.

## Summary

1 Blocker, 1 Major, 9 Minor, 2 Info. **AW-1 must be fixed before landing**: the window stops working the
first time a task changes group while its old group empties, which happens on every load that writes the disk
cache. The rest of the diff holds up. Rendering reads memory only. The GUI never waits. A cancelled helper's row
says "stopping" until its exit flag, and Retry is refused until `unexited` clears. The user hold leaves the
foreground and local lanes, saves and Live checks running, and quitting lifts it. History is added to on the GUI
thread only, and each IOService request's end is reported once. The hot paths add only cheap memory work while the
window is closed. Windows paths are compared as folders, every new control has an `identify` ID, no lambda captures
a Qt-made sender, and nothing is connected to `destroyed`.

## Findings (most severe first)

### AW-1 · Blocker · `helab/views/ActivityWindow.py:977-1001` (`_render_now`, `_sync`)

**A row whose group or parent changes, while its old group or parent row leaves the list, breaks the window.**
`_sync(tree.invisibleRootItem(), groups)` calls `takeChildren()` and drops the returned list. A group item that
is no longer wanted is then deleted by sip, and the C++ side deletes its child items with it. Those children
include the task's own `QTreeWidgetItem`, which `wanted` / `self._items` still hold. The next
`_sync(group, tops[name])` passes that deleted item to `addChildren` and raises
`TypeError: index 0 has type 'QTreeWidgetItem' but 'QTreeWidgetItem' is expected`.

- `tree.blockSignals(False)` is never reached, so the Now tree's signals stay blocked: selection no longer updates
  the details pane or the buttons.
- `self._items` keeps the deleted item, so **every later refresh** (the 1 s tick) raises
  `RuntimeError: wrapped C/C++ object of type QTreeWidgetItem has been deleted` from `_fill`/`setData`.
  `app_log`'s excepthook then logs a traceback and posts a status notice each second, until that task's id
  leaves the snapshot.

**Scenario (reproduced):** the Activity window is open and one folder loads. When its helper delivers the data
(`loaded`, `completed`), it goes on writing the disk cache. `about()` now gives the same task id the group
"saves" (`finishing`), and "Loads and scans" empties. The refresh raises at once, the next one raises
`RuntimeError`, and `now.signalsBlocked()` is still True. With the real `IOService` and `FolderCache`:
`cache.submit("tab", 0, "/data/run_1", "load", {})`, refresh, set `service.active[0].completed = True`, then
refresh twice.

The same thing happens when a child loses its parent row: a GUI conversion finishes (`tab_tasks` skips it) while
its pass's I/O row (`_conversion_parent`) is still listed, or a Live session's row goes while its save or
convert child stays. A row moving between two groups that both stay listed can also go missing for a tick: if the
new group is synced first, `addChildren` ignores an item that still has a parent.

**Fix:** detach each wanted item from its current parent before re-parenting it, e.g. `old = item.parent();
if old is not None and old is not target: old.removeChild(item)` (for top-level items,
`tree.takeTopLevelItem`). Or, when any wanted item's parent changes, rebuild with `tree.clear()` while holding no
stale items. Keep the taken lists alive until the end of the render. Wrap the render in `try/finally` so
`blockSignals(False)` always runs, and drop `self._items` entries that fail. Add tests for a load becoming a cache
write as the only load, for a conversion finishing while its pass row stays, and for a Live session ending before
its save.

### AW-2 · Major · `helab/utils/activity.py:57` (`NOT_KEPT_WHEN_OK`), `helab/utils/io_service.py:1028-1048`

**Successful conversion passes and browse step 2 fill the 200-entry history within minutes**, pushing out the
failures it is meant to keep (Q62.4, and Q~2's "frequent small work left out"). `kept_in_history` keeps every
successful `convert` request:

- **Live's auto-convert** submits one pass with each Live check, at least a check interval after the last
  one ended (`LiveController._convert_tick`, `explorer_live.py:861-884`), whether or not new raw files came. At the
  default 3 s interval, that is one "Convert raw files to TXY · done" entry every few seconds, about 200 in 10 to
  15 minutes.
- **A GUI conversion's passes**: each is an extra entry beside the conversion's own `_report`. The handoff says
  "its passes are I/O entries too, kept only when they fail", but the code keeps them when they succeed too.
- **`details`** (browse step 2, `SnapshotFileSystemModel._request_details`) runs for every folder the user
  browses into, and each success is kept. So is every `cached` read.

**Fix:** leave out successful `convert` requests whose owner is a tab's Live or converter owner (their Live
session or conversion is the entry), or every successful `convert` pass, since the GUI conversions report their
own end. Add `details`, and probably `cached`, to `NOT_KEPT_WHEN_OK`. Then a test: auto-convert passes every few
seconds add no `ok` entries. Update the handoff's proposed architecture text and Q~2's wording to match.

### AW-3 · Minor · `helab/views/ActivityWindow.py:615-616`, `:637-643`; `docs/how-to/activity.md:62-63, 79`

**Cancel on a tab's selected load, and Cancel all queued, also stop the tab's other background loads,
including running ones.** The "select" role calls `FolderExplorer.cancel_loading()`, which calls
`_cancel_background()` (`FolderExplorer.py:2652-2657, 2672`) and cancels every `bg_owner` load. Scenario: the
user selects folder B while A's helper is still stopping, so B's load is queued. Cancel all queued cancels B, and
with it the tab's running background loads, though the page says it "cancels every queued task". On a single
row, Cancel also removes other rows the user didn't pick. This matches the toolbar's Cancel, as designed, but
nothing in the window or the manual says so.
**Fix:** for Cancel all queued (and perhaps Cancel), use `FolderCache.cancel(model.owner, op, path)` plus the
tab's own state update for that folder rather than `cancel_loading()`; or keep it and say so in Cancel's tooltip
and the manual. If the behaviour stays, it is CoCo's or Tony's call.

### AW-4 · Minor · `helab/views/plots/script_tree.py:819-830`

**The new methods were inserted between `@pyqtSlot()` and `_reload_clicked`.** The decorator now marks
`probe_activity`, a value-returning accessor called from Python, and `_reload_clicked` lost it. I checked that
`clicked` still reaches an undecorated no-argument method in PyQt6, so nothing breaks. But the decorator was
there on purpose (its comment: `clicked` must not pass `checked` as the folders), and a slot decorated with no
return type on a method that returns a list is wrong.
**Fix:** move `@pyqtSlot()` back onto `_reload_clicked` and drop it from `probe_activity`.

### AW-5 · Minor · `helab/views/explorer_convert.py:527-529, 559-563`; `helab/views/explorer_live.py:881-884`

**Some conversion failures never reach the history**, though "every failure is kept" (the manual's line 56,
Q~2). These set `conversion.error` or `convert.error` and show "failed" in Now, but never call `_report` /
`activity.record`:
- `start` when the beside flag can't be queued;
- `_pass` when the conversion can't be queued (or another profile's conversion of the folder runs), on the
  first pass or on a later one through `_next_passes`;
- Live's auto-convert "couldn't be queued".

**Fix:** report there too, or in one place where `error` is set.

### AW-6 · Minor · `helab/utils/activity.py:173-178` (`History.add`)

**An error in a history listener, or the thread assert, propagates into the owner's own end path.** Only
IOService wraps `record` in `try/except`. `CacheMover._end` records before `self.finished.emit(moved)`, and
`stop_live` before `logging.info` and `_live_changed()`; so do the probe, conversion and runner reports. A raising
listener, such as a window whose wrapper has gone while it is still listed, would skip those calls. Today the
listener is removed in `hideEvent` and the main window closes the window first, so this is only a robustness gap.
**Fix:** call each listener in `History.add` under `try/except Exception: logging.exception(...)`, so a view
can never break an owner.

### AW-7 · Minor · `docs/how-to/activity.md:41-42, 45-46, 76-78`

Accuracy:
- Lines 41-42: "**stopping** … It keeps its place in the queue until it has" exited. It keeps its **slot**
  (nothing new starts in it, and its retry waits), not a place in the queue.
- Lines 45-46: "HeLab stops it after a minute without progress". A load's file reads time out after 15, 20 and
  30 s, with retries, and a finishing cache write has its own limit. Say "after a while without progress (a
  minute for most work)" or similar.
- Lines 76-78: "The current tab, saves, **Live** and reading the local disk cache carry on". Live's checks
  and autosaves do, but its **auto-convert passes pause**: `convert` is in `PAUSABLE` and they run in the
  background lane. Say so, as the Pause button's own tooltip does ("conversions").
- If AW-3 stays as it is, line 62-63 should say that Cancel on a tab's load also stops that tab's other
  background loads.

Public-text rules: no person's name, internal ID or `.ai/` path on the page.

### AW-8 · Minor · `helab/views/ActivityWindow.py:383`

**An internal ID in user-visible text.** A test import's details line reads "Its own time limits end it
(Q49.3 (b))" (details pane and tooltip).
**Fix:** "Its own time limits end it (10 s to start, 20 s to import)" or just drop the parenthesis.

### AW-9 · Minor · `helab/views/ActivityWindow.py:466-474, 844`; `helab/utils/settings_defaults.py:180-182`

**The saved size isn't clamped to the screen**, though the settings row says "at most the screen's" and the
design said "clamped to the screen". A size saved on a large external monitor reopens larger than a laptop's
screen.
**Fix:** bound it by `self.screen().availableGeometry()` (or the main window's screen) when it first shows, or
correct the description.

### AW-10 · Minor · `helab/views/ActivityWindow.py:1017-1047`

**The History tab is rebuilt from scratch on every history change.** `tree.clear()` resets its scroll
position, and for each failed entry `_history_details` scans `LogLines` (up to 500 lines × 200 entries) for its
tooltip. With AW-2's rate, that is a full rebuild every few seconds while the user scrolls. Selection is restored
by entry id, but ids repeat: every Live session of a folder is `live:<owner>:<path>`, and repeated requests of one
owner and generation share `io:…`. So the selection jumps to the newest entry with the same id.
**Fix:** prepend only the new entries (the deque's `version` tells how many), build tooltips lazily (on
selection or hover), and give entries unique ids (a counter, or the start time as conversions and probes
already have).

### AW-11 · Minor · `tests/test_activity_window.py:169-205`, and the missing regroup test

**The tests miss AW-1, and the memory-only test covers only IOService rows.** `test_rendering_reads_memory_only`
has no tabs, so `_live_task`, `_auto_convert_task`, `_conversion_task`, `_question_task` and the history's
rendering (with entries and `LogLines`) never run under the source guard. No test changes a row's group or parent
between refreshes, which would have caught AW-1.
**Fix:** run the memory-only test with a fake tab that has a Live session with auto-convert, a conversion, a
question and a failed history entry. Add the regroup and reparent tests from AW-1.

### AW-12 · Info · `helab/utils/activity.py:219-228` (`LogLines.about`)

Lines are matched by substring, so a failure in `/data/run1` also shows warnings about `/data/run10`. Matching
the folder followed by a separator or the end of the path, or with the path quoted, would avoid it.

### AW-13 · Info · `helab/views/ActivityWindow.py:970`

A group heading counts every task of that group, including children shown under another group's parent: a Live
session's auto-convert pass (group "convert") or its save (group "saves"). So "Conversions (2)" can sit above one
visible row. Count `tops[group]` plus their descendants instead, or count by where rows are shown.

## Doc proposals the handoff should change

- The proposed `app-runtime-and-ui.md` paragraph's list of what the history leaves out must match AW-2's fix.
- `testing.md`: the proposed note on `fresh_activity` is right. It could add that `IOService` now records into
  the global `HISTORY` in **every** test (bounded, and harmless with no listeners), and that a test shown window
  must be hidden or closed so its listener goes.
