# Notes: Live stops picking up shots (Pulse, 2026-11-12)

Evidence read from the lab logs (`.ai/local/live-stall-logs/`, read only; paths shortened to `dld_output`).

## The two stops

- `helab-8896.log`: the usual cycle every ~25 s (`convert_done … waiting=1`, then `convert_done converted=1`, then
  `load_done … live=true`). Last one: 16:38:45 `convert_done … waiting=1`; a 3.89 s GUI stall from 16:38:46 (the GUI
  thread in `FolderDetailsPanel._folder_rows` → `convert_line` → `low_hits_threshold` → `read_setting`, an IOService
  reader thread running a helper); 16:38:50.885 the low-count notification for shot 2391; 16:38:50.985
  `convert_done converted=1`. Then no `load_done` and no `convert_done` until Live off at 18:08:09. At 16:39:20
  there is no IOService reader thread in the stacks: no helper running, nothing asked for. "Memory while Live: …
  1,014 shots, revision 29" unchanged from then on.
- `helab-14688.log.1`: the same at 13:56:06 (`waiting=1`), a 2.09 s stall from 13:56:13, 13:56:16.632
  `convert_done converted=1`, then nothing until Live off/on at 15:50 (262 shots converted at once).
- No "Live stopped" warning in either: `session.error` was never set. Note that `convert_done` is logged only when a
  count changes, so the silence after the last `converted=1` (whose counts were `0,0,0`) alone wouldn't prove no
  conversion ran; the next shot's `waiting=1` would have logged, and none did.

## The cause (reproduced)

`FolderCache._event` forgot a Live check's job only on `loaded` or on the helper's `done`/`error`/`cancelled`; a
check answering `live_unchanged` stayed in `FolderCache.jobs` until `done`. The helper sends `done` right after it
(`io_helper.py`), but `IOService._drain` handles at most 8 ms of events per 20 ms tick, and each Live event's
handlers (`_update_activity`, `loadStateChanged` → `_update_folder_details`) were slow on the lab PC: the two can
reach the GUI in different ticks. A converted shot asks for the next check at once: `_converted` sets `check_soon`
while a check runs (then `_live_unchanged` → `_live_next()` times the next tick at 0 ms), or calls
`_live_next(0.0)` just after the answer. That 0 ms tick ran between the two drains: `FolderCache.submit` →
`has_request(live_owner, "load", path)` found the answered check's request and returned True without starting
anything. `session.request` became "check" and stayed so: the old job's `done` came, Live ignores `done`, and
`_live_tick` (the only caller of `_convert_tick`) returned early from then on. No check, no conversion, no timer.

`tests/test_live_stall.py::test_a_check_started_between_an_answer_and_its_done_is_its_own` delivers the answer and
the `done` with `qtbot.wait(30)` between them, for both orders: it failed before the fix (no check ever reached a
helper again) and passes after. Control: without the wait, the next check reached a helper (so the split is the
cause). The held check runs with its convert on read off: store-v4's Live check would otherwise convert the raw
file itself and answer `loaded`.

## The GUI thread's stall stacks (all 217 in the three logs)

| Innermost HeLab frame of the GUI thread | 8896 | 14688.1 | 14688 |
|---|---|---|---|
| `low_hits_threshold` (→ `read_setting`, `app_settings`; all 57 settings reads were this one's) | 28 | 31 | 3 |
| `_update_plot_source_label` (`workspace.py:305`, `:328`: the two `findChild`) | 30 | 39 | 2 |
| `cache_paths._windows_unc` (the mount table's refresh, from `_convert_tick` → `share_to_confirm`) | 0 | 3 | 0 |
| only the event loop (`main.py:293`: painting, Qt) | 19 | 43 | 3 |
| others (`gui_watchdog._beat`, `FolderTabWidget.set_tab_switching_enable`, `_spinner_pixmap`) | 6 | 10 | 0 |

## Measurements (this Mac, offscreen, `.ai/temp/measure_*.py`)

- `low_hits_threshold()`: 3.4 µs a call before (an ini store; QSettings keeps the file in memory), 0.3 µs after,
  no settings read after the first. The lab's store is the Windows registry, not measured here (M~1).
- `PlotWorkspace._update_plot_source_label`, text unchanged between calls: a plot of 84 widgets 70 µs → 15 µs, of
  1,110 widgets 78 µs → 13 µs. Of the 70 µs before: each `findChild` ~9 µs, `ElidedLabel.setText` of the same
  text ~24 µs. The lab PC (Sandy Bridge) is several times slower, and it runs once per plot per Folder details
  update, which itself runs on most Live events.
