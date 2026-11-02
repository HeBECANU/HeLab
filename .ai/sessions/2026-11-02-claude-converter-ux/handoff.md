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
beside confirmation above; yes turns the folder's flag on), Cancel. The text says the converter should run on
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
  temp folder instead (this session; the folder's flag stays), Not now (stopped; Live's Retry stays, and the
  tooltip adds that turning the beside setting off converts into HeLab's folder).
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
  the share question and Q38.1's question (non-modal, nothing converts while asked); `AutoConvert.destination`.
- **`data-roots.md`**: one line pointing at `cache_location.share_of` (shares for the converter, lexical +
  the mount table; distinct from the store's location keys, which `cache_paths` makes).
- **`app-runtime-and-ui.md`**: Folder details' Convert row (`details_offer`, clickable) and that converter
  questions are non-modal (`open`) with IDs `<prefix>_<choice>`.
- **`docs/hlb-format.md`**: the raw layer's facts gain `stop_line` (int ≥ 1 or null; absent in layers from
  before A37.1).
- **`testing.md`**: `test_live.replay` runs a load without its `txy` field, so a test of HeLab TXY loads runs
  the load itself (`test_explorer_convert.load_as_the_helper_does`), see A~1.

## Questions for Tony (provisional)

- **Q~1** The wording: Live line and Folder details `d3.txt read stopped at line 1010` (one) / `3 reads
  stopped early` (several), amber; the tooltip and `helab convert`: `read stopped at line 1010, at
  "not,a,number", which isn't a number: as MATLAB's converter reads the file, its TXY holds only the hits of
  the rows before that line (34,336 bytes not read)`. Line numbers ungrouped (1010, as editors show them).
  Proposed: as built.
- **Q~2** Should a read stopped early also send a system notification, like a damaged file (once per
  file)? Built: a log warning and amber text only. Proposed: notify once per file (it means lost hits).
- **Q~3** `helab convert --output beside` on a share without a terminal and without `--yes`: built as
  Q30.2 (converts to HeLab's folder, a warning names `--yes`). Alternative: refuse (exit 2) so a script
  expecting TXY beside notices. Proposed: as built.
- **Q~4** The share confirmation is per folder per session (the beside flag persists). Keep it, or save it
  with the folder's flag (store `convert_prefs`, a new column)? Proposed: session only.
- **Q~5** Live's share question: default Convert to HeLab's cache instead; closing turns auto-convert off.
  Q38.1's question: default HeLab's cache folder; closing is Not now. Choices apply for the session, the
  folder's beside flag unchanged. Proposed: as built.
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
