# Handoff: Converter UX (`agent/converter-ux`): A37.1, A39.5, Q38.1

Worker: Ember (Claude Opus 5.5). Brief: [brief.md](brief.md). Base `a0bc26d` (`dev/v0.0.8`, the brief at
`0003812`).

## Commits

| Commit | What |
|---|---|
| `a37deb1` | A37.1 (1): the raw parser says where its read stopped (`raw.ReadStop`, `RawPulses.stop`, `pipeline.Converted.read_stop`, the raw layer's `Facts.stop_line`) |
| `2c88b65` | A37.1 (2): `shot_converted.read_stop` (`events.ReadStopField`); `helab convert` logs it |
| `fd43431` | A37.1 (3): the Live line and Folder details name a read stopped early |
| `186b7b0` | A39.5 (1): share detection, `cache_location.share_of` and `share_warning` |
| `7648e27` | A39.5 (2) and Q38.1 for `helab convert`: `--output beside` on a share asks (`--yes`); `beside_refused` from the helper; the CLI's Retry / cache / temp prompt |
| `a36bc95` | A39.5 (2, 3) and Q38.1 in the app: `helab/views/explorer_convert.py`, Live's share question, the beside setting's warning, Folder details' Convert offer, Retry / cache / temp; `FolderCache.convert` overrides |
| `2915d53` | The offer's test also loads the folder afterwards |
| `7a60998` | Share names on Windows (CI 41449571421's failure): the test's mount in each OS's spelling; `@` kept in UNC sources |

Objectives 2–4 of part B share files (`convert_cli.py`, `explorer_convert.py`), so they are two commits by
side (command line, app) rather than one per objective.

**Files outside the owned paths, each approved by CoCo (2026-11-02):** `helab/convert/pipeline.py` (one
additive field, `Converted.read_stop`), `helab/utils/folder_cache.py` (`FolderCache.convert`'s keyword-only
`destination` and `beside` overrides, nothing else; Vault edits that file tonight, whoever lands second
merges), and the new module `helab/views/explorer_convert.py` with `tests/test_explorer_convert.py`.
`docs/hlb-format.md` was left alone (its line is proposed below).

## Checks

Full suite (macOS, M4 Max): `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`:
**9035 passed, 673 skipped, 2 warnings in 170.06s at `2915d53`; no RERUN** (the warnings: pyqtgraph's NumPy 2.5 `arr.shape` DeprecationWarning in `test_t_spectrum.py`, known). Log: `.ai/temp/full-suite.log` (local, gitignored).

Type checks at `2915d53`: `mypy helab/ --strict` (204 files), `mypy tests --strict` (193),
`mypy helab/ --strict --platform win32`: no issues; `pyright helab tests` and
`pyright --pythonplatform Windows helab tests`: 0 errors.

Converter output byte for byte: `dev/txy/check_samples.py --positions all`, from the files and
`--via-layer` (samples read only): 309 checked, **303 identical + the 6 proved exceptions** (1 cut, 2 variant,
3 empty), exit 0, both ways. None of the 309 sample raw files stops early (counted with `parse_raw`).

CI **41449571421** (at `28e46af`, the handoff's first commit): every job green but **windows Tests (2/2)**:
`tests/test_share_detection.py::test_a_folder_on_an_smb_mount_is_on_its_share_named_without_the_account`
RERUN 5 times then FAILED ("rerun reasons": `AssertionError: assert 'LabServer/Data' == '//labserver/data'`).
Not flaky: the test gave Windows a macOS smbfs source (`//tony@LabServer/Data`), which
`cache_paths._smb_source` reads as WebDAV on Windows, and `share_of`'s fallback cut it at the `@`. Fixed in
`7a60998` (the test spells each OS's mount; an `@` in a UNC source is kept). Every other job's log read:
**0 RERUN** (macOS Tests 1/2 and 2/2, Converter backends; Ubuntu Tests 1/2 and 2/2, Converter backends;
Windows Tests 1/2, Converter backends). CI **41451877093** (at `e388d87`, after the fix): **success**, every job; each Tests and Converter backends job's log read: **0 RERUN** (macOS 4,506 + 4,530 and 866; Ubuntu 4,502 + 4,530 and 866; Windows 4,490 + 4,511 and 864 passed). This line's commit is local only (a docs-only push would run CI again).

## Part A: A37.1, a raw read stopped early

- **The parser** (`helab/convert/raw.py`). `_parse_textscan` counts lines as the read does (each ending of
  the file's mode, `\r\n` as one, from 1) and, where the first token it can't read ends the read, returns
  `RawPulses.stop = ReadStop(line, offset, text, unread)`: `text` up to 24 bytes to the line's end with
  control and non-ASCII bytes escaped (`\r`, `\xef`), `unread` the bytes left. `None` when the read reached
  the end, a file cut mid-line included (everything was read). `fastio.parse_strict` reads only files with
  nothing unreadable (it returns None otherwise), so its pulses never stop: said in its docstring, tested.
  The arrays are unchanged: every existing parser test passes; new tests check 13 stops and, on every
  `TEXTSCAN` case and all 1,367 MATLAB probes, that the bytes before the stop read the same rows to their
  end. `ReadStop.summary()` ("read stopped at line N") and `detail()` (the token, that the TXY holds the
  hits of the rows before it as MATLAB's reading does, bytes not read) are the wording the three places
  share. The test data's `damaged/d3.txt` stops at line 1010 at `not,a,number`.
- **The raw layer, no `RAW_PARSER_VERSION` bump** (`raw_layer.Facts.stop_line`, `int | None`): added to the
  facts' JSON additively. Safe because (1) `parse_raw`'s arrays didn't change for any input, which is what
  the version guards (a bump would re-read every stored raw layer for nothing); (2) a layer without the
  key reads as `None`: for a `COMPACT` layer that is exact (the strict path never stops), for an older
  `FLOAT` layer it means "not said"; (3) an older HeLab reading a newer layer ignores the key
  (`Facts.from_json` reads named keys only); (4) nothing decides from it: conversions parse the raw text and
  their event carries the stop; the layer's value is for `helab cache dump` and later readers. Bad values
  (0, negative, bool, string, float) are refused like the other facts. `decode` doesn't rebuild a
  `ReadStop` (the offset and text aren't kept).
- **The event**: `shot_converted.read_stop` (`events.ReadStopField`: line, offset, text, unread; `None` when
  read to the end), from the worker pool too (`Converted.read_stop` pickles with the result).
- **Where it shows**: `helab convert` logs a warning, `d3.txt: read stopped at line 1010, at "not,a,number",
  which isn't a number: as MATLAB's converter reads the file, its TXY holds only the hits of the rows before
  that line (34,336 bytes not read)` (ASCII). Live's auto-convert keeps the stopped files
  (`AutoConvert.stopped`, by name, dropped when a file converts again to its end): the Live line says
  `d3.txt read stopped at line 1010` for one and `N reads stopped early` for several, amber, the tooltip
  lists each with the detail, and a log warning per file. Folder details' Auto-convert row shows the same
  (it reuses `convert_line`) and turns amber (`explorer_live.READ_STOPPED`).
  `test_damaged_files_during_live_are_said_once_and_the_run_goes_on` checks the event's line 1010, the
  text and the Live line.

## Part B: A39.5, TXY and shares; Q38.1

### What counts as a share (`cache_location.share_of`)

A UNC path (`\\server\share`, `//server/share`), or a folder whose nearest mount (lexically, the longest
mount point containing it) the OS lists as remote or of a network file system (`NETWORK_FILESYSTEMS`):
- **macOS**: `smbfs`, `afpfs`, `nfs`, `webdav` (psutil's `getfsstat` without waiting);
- **Windows**: mapped network drives (`GetDriveTypeW` DRIVE_REMOTE, the UNC from `WNetGetConnectionW`) and
  UNC paths;
- **Linux**: `cifs`, `smb*`, `nfs`, `nfs4`, `fuse.sshfs`, `fuse.rclone`, `davfs`, `9p`, or any mount psutil
  marks `remote`.

Synced folders (OneDrive, Dropbox, iCloud) aren't shares here: their files are local copies. The name shown
is the share as the cache keys it (`//server/share`, lowercased share, no account), else the mount's
source without an account (`server:/export`), else "a network drive (<fstype>)".

**GUI-safe:** lexical (`abspath`), never a stat or `realpath` of a source folder; the mount table
(`cache_paths.current_mounts`, which asks no source or server) is read at most every 10 s
(`MOUNT_TABLE_SECONDS`), so Folder details may ask on render; unreadable → "" (local), as
`cache_location_problem` treats the unknown. `resolve=True` (the command line only) follows links first.
**Tested without a real share:** made-up mount tables and paths that don't exist, `os.path.realpath`
refused in the lexical tests (`tests/test_share_detection.py`; the Windows mapped-drive case runs on
Windows CI); the app and CLI tests patch `cache_location.share_of` for the test's folder and assert the GUI
never asked with `resolve=True`.

### The one-time warning

- **The folder's beside setting** (Live's Auto-convert menu › Write TXY beside the raw files in this
  folder…): on a share, the share's warning replaces the plain question (modal, on that click; buttons
  `share_beside_confirm_beside` / `_cancel`); yes saves the flag and confirms the folder for the session.
- **`helab convert --output beside`** on a share: one warning naming the share and the acquisition PC, then
  on a terminal `Write the TXY beside the raw files on the share anyway? [y/N]`; no (or no terminal) → the
  setting's output (HeLab's cache unless changed) with a line naming `--yes`; `--yes` writes beside without
  asking. Asked once per run, before the first check (Q30.2's pattern).
- **Live's auto-convert** when the folder's flag is on and it is on a share not confirmed this session:
  nothing converts while a non-modal question asks: Convert beside on the share (confirms), Convert to
  HeLab's cache instead (recommended, the default: this session's auto-convert, the flag stays), Turn
  auto-convert off (also on closing). The tooltip then says "This session: TXY go to HeLab's cache folder
  instead of beside the raw files". A launch folder set to start Live with auto-convert asks at its first
  conversion the same way (non-modal).
- **Once per folder** is session memory (`explorer_convert.beside_confirmed`, FolderCache keys; CoCo: yes);
  the beside flag stays the persistent record (Q~4).

### Folder details' offer

A share folder with raw files and no TXY of any kind (the listing's MATLAB count, HeLab's beside TXY from the
last summary's `files`, no shown data with shots), not converted by Live, shows a **Convert** row:
`No TXY · on a share · Convert…` (clickable; the tooltip has the share's warning). Clicking it asks
(non-modal; `convert_offer_cache` / `_temp` / `_beside` / `_cancel`): **Convert to HeLab's cache
(recommended)** (default), **Convert to HeLab's temp folder**, **Convert beside on the share…** (then the
beside confirmation above; yes saves the folder's flag, and the conversion starts once the store says it is
on, asking for beside explicitly; disabled with the reason where the Live menu's beside setting is:
`beside_unavailable`, the disk cache off, no `.helab-root`, a root pending; review fix 1), Cancel. The text says the converter should run on
the computer that owns the data (the acquisition PC). `ExplorerConverter` (owner `<tab>:convert`, the
background lane) runs `FolderCache.convert(destination=…, beside=False)`: the first pass only records (as
every conversion's first), then passes a check interval apart while files settle (at most `MAX_PASSES` = 6;
files still being written then are left to Live's auto-convert, said in the tooltip). The row shows
`Converting to HeLab's cache folder… 3 of 40`, then `40 converted to HeLab's cache folder · 2 still being
written`; then the folder is listed and loaded again and HeLab's new TXY show (tested: both shots load).

### Q38.1: a beside write with no safe rename

The helper sends **`beside_refused`** (`events.BesideRefusedEvent`: shot, txy, message) when `write_atomic`
refuses a beside write for want of a hard link and a no-replace rename (`convert.unsafe_rename`: ENOTSUP with
txy's "Not written: …"; a cache-folder refusal or any other error isn't one), then the run fails as before.
- **App** (Live's auto-convert and Folder details' conversion): a non-modal question (`beside_refused_retry`
  / `_cache` / `_temp` / `_later`): Retry, Write to HeLab's cache folder instead (default), Write to HeLab's
  temp folder instead (the folder's for the session, `explorer_convert.instead`: Live's auto-convert and
  Folder details both follow it, review fix 3; the folder's flag stays), Not now (stopped; Live's Retry stays,
  and the tooltip adds that turning the beside setting off converts into HeLab's folder).
- **`helab convert`**: on a terminal `[r]etry, write to HeLab's [c]ache or [t]emp folder instead, or [q]uit?
  [r/c/t/Q]` (cache/temp for the rest of the run); without a terminal the refusal stands (`--once` exits 1)
  with a line naming `--output cache` and `--output temp`. Never a silent refusal or fallback.

## Proposed doc changes (for the Coordinator)

- **AGENTS.md code map**, `helab/views/` row: add "`explorer_convert.py` (conversions from Folder details,
  the converter's share and Q38.1 questions)".
- **`converter.md`**: the `raw` row: "…`RawPulses.stop` (`ReadStop`: line, offset, text, unread) where the
  general reader's read stopped at a token it can't read (A37.1; the strict path never stops)"; the
  `raw_layer` row: "`Facts.stop_line` (A37.1), added without a parser bump: absent reads as None";
  Events table: `shot_converted` gains `read_stop` (`ReadStopField` or None); new row `beside_refused` (a
  beside write refused for want of a safe rename, before the run's error; Q38.1); the paragraph on
  `write_atomic`'s refusal (In HeLab, stage 4): replace "the conversion fails with that reason (Q38.1; M38.1
  for the lab share)" with "the helper sends `beside_refused` and the conversion fails with that reason; the
  app asks Retry or HeLab's cache or temp folder instead (this session), `helab convert` asks the same on a
  terminal (Q38.1, `agent/converter-ux`)"; the `helab convert` section: `--yes` and the share question;
  a new subsection "Shares (A39.5)" with the definition above, the three warnings, Folder details' offer.
- **`live.md`**: auto-convert's line names a read stopped early (one by name, several counted, amber) and
  the share question and Q38.1's question (non-modal, nothing converts while asked, closed with auto-convert);
  the folder's choice instead of beside, for the session (`explorer_convert.instead`).
- **`data-roots.md`**: one line pointing at `cache_location.share_of` (shares for the converter, lexical +
  the mount table; distinct from the store's location keys, which `cache_paths` makes).
- **`app-runtime-and-ui.md`**: Folder details' Convert row (`details_offer`, clickable) and that converter
  questions are non-modal (`open`) with IDs `<prefix>_<choice>`.
- **`docs/hlb-format.md`**: the raw layer's facts gain `stop_line` (int ≥ 1 or null; absent in layers from
  before A37.1).
- **`io-and-browsing.md`** (Strata's findings 4 and 5): add `cache_location.share_of` (patched by the app's and
  `helab convert`'s tests; `tests/test_share_detection.py` checks no module of `helab/` imports it or
  `mount_table` by value) and `explorer_convert.confirm_beside_on_share` (patched in
  `test_explorer_convert.py`; `explorer_live` calls it as `explorer_convert.confirm_beside_on_share`, and
  `ExplorerConverter` bare, in its own module) to the list of names tests patch. And after "Source folders are never queried by the
  GUI model": "The GUI may read the OS mount table (`cache_location.mount_table`, cached 10 s: psutil's
  `getfsstat` without waiting on macOS, `/proc` on Linux, `GetDriveTypeW`/`WNetGetConnectionW` on Windows)
  to tell whether a folder is on a share (`share_of`, lexical: no stat or realpath), and nothing below a
  mount point."
- **`testing.md`**: `test_live.replay` runs a load without its `txy` field, so a test of HeLab TXY loads runs
  the load itself (`test_explorer_convert.load_as_the_helper_does`), see A~1.

## Review fixes (Strata, `be40694`; fixed in `bc73f0c`)

All six findings, each with a test that failed before its fix (seen failing, then passing):

| # | Finding | Fix | Test |
|---|---|---|---|
| 1 (medium) | Folder details' beside wasn't gated and started before the folder's flag was known | `beside_unavailable` shared with the Live menu; the button disabled with the reason; the conversion waits for `folderPrefsChanged`, asks `beside=True` (`FolderCache.convert`'s override passes True through, the helper still checks the store); a flag that can't be queued or saved stops it, said in the row | `test_the_offers_beside_is_gated_like_the_live_menu`, `test_the_offers_beside_waits_for_the_folders_flag_then_converts_beside` (`payload["beside"] is True`), `test_a_beside_flag_that_cant_be_saved_stops_the_offers_conversion` |
| 2 (low) | Live's question outlived Live, holding a later auto-convert | closed and cleared in `_convert_off` (so in `stop_live` too) | `test_lives_question_goes_with_auto_convert_and_a_later_one_converts`, `test_lives_question_goes_when_live_stops` |
| 3 (low) | Q38.1's "for this session" held only in Live | `explorer_convert.instead`, the folder's for the session, read by both | `test_the_choice_after_a_refusal_holds_for_the_folder_in_live_and_folder_details` |
| 4 (low) | `share_of` imported by value in `helab convert` | called as `cache_location.share_of` | `test_share_of_is_called_through_its_module` (AST over `helab/`) |
| 5 (low, docs) | the GUI's mount-table read and the patched names undocumented | proposed below (`io-and-browsing.md`) | — |
| 6 (nit) | the detail's "rows before that line" | "what was read before it" | `test_the_read_says_where_it_stopped` |

Also found while fixing: two older tests (`…asks_once_and_cache_instead…`, `…once_confirmed_or_turned_off[beside]`)
clicked Live's question within the 20 ms check interval of `cycle`'s conversion, so the tick the answer runs
could wait for a Live check the test never answers (one local failure, never in CI; the app is unaffected:
Live keeps ticking). They now set `ended_at` back first, as the Q38.1 test did; the file then passed 21 runs
in a row.

Checks at `bc73f0c`: the full suite (`-n 4 --reruns 5 --reruns-delay 1`) **9043 passed, 673 skipped, 2 warnings
(the known pyqtgraph one) in 170.64s; no RERUN**; the five type checks clean.

CI **41457940413** (at `baf7a1c`, the review fixes): **success**, every job; each Tests and Converter backends
job's log read. **One RERUN**, windows Tests (2/2) (job 125319510384):
`tests/test_io_trace.py::test_the_gui_process_never_touches_source_folders`, rerun reason
`pytestqt.exceptions.TimeoutError: waitUntil timed out in 20000 milliseconds` at `tests\test_io_trace.py:259`
(`wait_idle`: the I/O service idle within 20 s, real helper processes). The first attempt ran 34 s, the rerun
passed in 8 s; no other output was captured. Not explained by this branch as far as I can tell: the test builds
no Folder details panel and runs no Live or conversion, so `share_of` and the mount-table read aren't reached;
the branch's only code on its path is `FolderExplorer` constructing `ExplorerConverter` (a timer, two signal
connections) and one owner check in `_io_event`. It wasn't seen in the branch's two earlier runs (41449571421,
41451877093: that job 0 RERUN) nor locally (three full suites, no RERUN). Every other job: **0 RERUN** (macOS
4,510 + 4,533 and 866; Ubuntu 4,507 + 4,533 and 866; Windows 4,494 + 4,514 and 864 passed).
**Proposed known-issues entry** (A~5): "`test_the_gui_process_never_touches_source_folders`: `wait_idle`'s 20 s
timed out once on Windows CI (41457940413, `agent/converter-ux`), passed on rerun in 8 s; a slow runner's real
helpers, cause not found. If it recurs: log `service.pending/active/retired` and `_deliveries` on timeout."

## After landing: the switch-on CI's RERUN (CoCo, 2026-11-03)

CI **41482722171** (`agent/v4-switch-on`, macOS Tests 1/2, job 125405134241): one RERUN,
`test_explorer_convert.py::test_auto_convert_beside_on_a_share_once_confirmed_or_turned_off[off]`,
`waitUntil timed out in 5000 milliseconds` at line 114 (Live's share question never came); passed on rerun.

**Why (a race in the tests, not the app).** The tests set the folder's beside flag (`beside_flag`, the store's
answer as memory) right after `test_live_convert.cycle`, which ends by answering a Live check. On a slow runner
Live's next tick can run more than a check interval (20 ms) after `cycle`'s conversion ended *while `cycle`
still waits for that check*, before the flag is set: it queues the next conversion (beside False: the flag not
known yet, correctly) with its check. `cycle` answers the check; nothing ever runs that conversion, so
auto-convert stays "requested", every later tick returns early, and the question never opens. The same race
gave a second failure shape under load: `test_a_refused_beside_write_in_live_asks_retry_or_hellabs_folders[retry]`
read that stale conversion's payload after Retry (`assert False is (None is None)`, line 199). The app is right
both ways: a conversion queued before the flag was known converts as the store said then, and the helper checks
the store again before writing beside.

**Fix** (tests only, `tests/test_explorer_convert.py`): `beside_flag_in_live`, used by the six tests that set
the flag after `cycle`. It sets the flag, then runs a conversion still queued from before it (asserting its
payload is not beside, so a conversion queued *after* the flag would fail the test), answers a pending check,
and sets `ended_at` back, so Live's next tick asks at once.

**Seen failing, then passing**, with `store_v4` on (a local, uncommitted default flip, as on the switch-on
branch) and 14 busy-loop processes on the 16 cores, `-n 16`, no reruns, each round 48 to 200 runs of these
tests: the old tests failed in 4 of 13 rounds (`[off]` timing out at line 114 as in CI, with the state printed:
auto-convert requested, a conversion queued with `beside` False, the flag on; `…asks_once_and_cache_instead…`
timing out the same way; Retry's stale payload); the fixed ones passed 1,200 of 1,200 (six rounds of 200).

Checks after merging `dev/v0.0.8` (a fast-forward to `db6b32e`) with the fix: the full suite (`-n 4 --reruns 5
--reruns-delay 1`) **9157 passed, 673 skipped, 2 warnings (the known pyqtgraph one) in 231.03s; no RERUN**;
the five type checks clean (mypy strict 204 + 200 files, win32 204; pyright both platforms 0 errors).

CI **41489860538** (at `dc5219f`, the fix on `db6b32e`): **failure**, every Tests and Converter backends log
read. Both Windows failures are `test_convert_helab.py::test_two_writers_side_by_side_lose_nothing[a writer
missing its window]`, RERUN 5 times then FAILED, in windows Converter backends (job 125429900442) and
windows Tests (3/3) (job 125429900886). The rerun reasons are all `IndexUnavailable: HeLab's TXY index
couldn't be written|opened (database is locked) … attempt 4`. This is dev's, not this branch's: dev's own
run at `db6b32e` (41484513530) reran it on windows Tests (3/3), and dev fixed it after `db6b32e` in
`28d8973` ("a writer tries a busy-index shot again until it lands"). One more RERUN, in ubuntu Tests (2/3)
(job 125429900309): `test_plot_backends.py::test_2d_plots_draw_with_every_library[values0-Plotly-TxyHistograms]`,
"worker 'gw1' crashed", passed on rerun. That is dev's plot-library crash, merged since as `823589a`. Every
other job: **0 RERUN** (macOS Tests 3,113 + 3,029 + 3,015 and Converter backends 867; Ubuntu 3,112 + 3,027 +
3,015 and 867; Windows 3,105 + 3,012). Merged `dev/v0.0.8` again (`1e06fc2`, with both fixes): the full suite **9163 passed, 673 skipped, 2 warnings (the known pyqtgraph one) in 175.43s; no RERUN**, the five type checks clean; pushed.

## Questions for Tony (provisional)

- **Q~1** The wording: Live line and Folder details `d3.txt read stopped at line 1010` (one) / `3 reads
  stopped early` (several), amber; the tooltip and `helab convert`: `read stopped at line 1010, at
  "not,a,number", which isn't a number: as MATLAB's converter reads the file, its TXY holds only the hits of
  what was read before it (34,336 bytes not read)` (review nit 6: the values before the token on its line are
  read). Line numbers ungrouped (1010, as editors show them).
  Proposed: as built.
- **Q~2** Should a read stopped early also send a system notification, like a damaged file (once per
  file)? Built: a log warning and amber text only. Proposed: notify once per file (it means lost hits).
- **Q~3** `helab convert --output beside` on a share without a terminal and without `--yes`: built as
  Q30.2 (converts to HeLab's folder, a warning names `--yes`). Alternative: refuse (exit 2) so a script
  expecting TXY beside notices. Proposed: as built.
- **Q~4** The share confirmation is per folder per session (the beside flag persists). Keep it, or save it
  with the folder's flag (store `convert_prefs`, a new column)? Proposed: session only.
- **Q~5** Live's share question: default Convert to HeLab's cache instead; closing turns auto-convert off.
  Q38.1's question: default HeLab's cache folder; closing is Not now. A choice of HeLab's cache or temp folder
  instead (either question, Live or Folder details) is the folder's for the session, followed by both, the
  folder's beside flag unchanged; choosing beside again in Folder details clears it (Strata's finding 3).
  Alternatives: per conversion only; or saved with the folder. Proposed: as built.
- **Q~6** The offer's wording: row `No TXY · on a share · Convert…`; buttons "Convert to HeLab's cache
  (recommended)", "Convert to HeLab's temp folder", "Convert beside on the share…". Proposed: as built.

## Follow-ups (provisional)

- **A~1** `tests/test_live.py`'s `run_helper` passes a load no `txy` (nor `memory_origins`), so its loads
  never find HeLab's TXY; give it the fields `io_helper` passes (as `test_live_convert.check` does for Live
  checks) and drop `test_explorer_convert.load_as_the_helper_does`.
- **A~2** Add the new questions (`convert_offer`, `live_share`, `beside_refused`, `share_beside_confirm`) to
  `test_accessible_names.ASKS` or `INLINE_SKIPPED` (their IDs are checked in `test_explorer_convert.py`).
- **A~3** The read stop isn't kept anywhere a later load sees (only Live's session and the logs): record
  it in the provenance row (a column within schema 1), so Folder details can name it for a folder loaded later.
- **A~4** Settings › TXY converter's output tooltip could say that a folder on a share asks before writing
  beside (`ConverterTab.py`, owned but left alone: nothing there writes beside).

## Manual checks (provisional)

- **M~1** On the lab share (with M38.1): turn on beside for a folder there (the share's warning), Live with
  auto-convert (the question once), `helab convert --output beside` (the prompt), and Folder details' offer
  on a share folder without TXY (convert to cache; the folder then loads).
- **M~2** On a share without hard links (FAT USB stick shared, or the lab's SMB): Q38.1's question in Live
  and in `helab convert`, each choice.
- **M~3** A raw file with a garbage line during Live: the Live line, Folder details and the tooltip.
