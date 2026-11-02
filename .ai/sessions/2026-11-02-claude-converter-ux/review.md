# Review: Converter UX (`agent/converter-ux`): A37.1, A39.5, Q38.1

Reviewer: Strata (Claude Opus 5.5), 2026-11-03. Range `a0bc26d...e388d87` (the code; `e3309ad` after it is
the handoff only). Read: the brief, the handoff, `AGENTS.md`, `converter.md`, `data-roots.md`, `live.md`,
`app-runtime-and-ui.md`, `io-and-browsing.md`, and the whole diff.

**No blocker.** Six findings: 1 medium, 4 low, 1 nit. MATLAB TXY stay byte-identical. Nothing is
written beside the raw files unless the user chooses it (finding 1 is the opposite case: the user chooses
beside and doesn't get it). Tests never touch a real share.

## Checks rerun

- Full suite at `e3309ad` (code as `e388d87`): `pytest -n 4 --reruns 5 --reruns-delay 1
  --basetemp=.ai/temp/pytest-strata`: **9036 passed, 673 skipped, 2 warnings in 146 s; no RERUN** (log
  `.ai/temp/review-suite.log`, local).
- `mypy helab/ --strict` (204 files), `mypy tests --strict` (193), `mypy helab/ --strict --platform win32`
  (204): no issues. `pyright helab tests`: 0 errors. `pyright --pythonplatform Windows helab tests`: 0 errors.
- `dev/txy/check_samples.py --positions all`, from the files and `--via-layer` (samples read only): 309
  checked, 303 identical + 1 cut, 2 variant and 3 empty (the 6 proved exceptions), 0 unexplained, both ways.

## Converter, raw layer, event (A37.1): agreed

- `_parse_textscan` only adds a line counter and a `ReadStop` where it already broke out of the loop.
  Rows, NaN fills and the break point are unchanged, so `parse_raw`'s arrays are the same for every input.
  `fastio.parse_strict` is untouched apart from its docstring. Line counting matches the read's own endings
  (`\r\n` as one; in `\n` mode a `\r` stops the read, which is right).
- **No `RAW_PARSER_VERSION` bump: agreed.** The version guards `parse_raw`'s output, and that hasn't changed.
  `stop_line` is additive in the facts JSON, which is a TEXT column in store-v4 (`raw_layers.facts`, and the
  switch is off): no migration is needed. `from_json` uses `.get` (an older layer reads as None), and an older
  HeLab reads named keys only, so it ignores the new key. Bad values are refused. `decode` doesn't rebuild
  `RawPulses.stop`, and the docstring says so. Nothing decides from the stored value.
- `shot_converted.read_stop` is set from the worker pool too (`Converted` pickles), and the tests cover 1 and 2
  workers. `beside_refused` is typed in `events.py` and listed in `KINDS`.

## Findings (most severe first)

### 1. Medium: Folder details' "Convert beside on the share…" isn't gated, and starts before the flag is known

`helab/views/explorer_convert.py:278-285` (`_offer_answered`) and `:300-304` (`_pass`).

- The Live menu's "Write TXY beside the raw files in this folder…" is disabled when the disk cache is off,
  when there is no `.helab-root`, or when the root is pending (`explorer_live.py:722-727`). The offer's beside
  button is always offered.
- After the modal confirmation, which says "Saved for this folder", `_offer_answered` ignores
  `set_write_beside`'s return value ("" when nothing could be saved) and calls `start(path, "beside")` at once.
- `_pass` then calls `FolderCache.convert(beside=None)`, which reads the **memory** flag. That flag is still
  False until the store's `convert_prefs` answer arrives, so the request has `beside: False`.

What this does:

- **On a share folder without a data root** (likely on the lab share), the user confirms beside, and every
  pass converts to HeLab's temp folder. The row says "converted to HeLab's temp folder", and the reason
  appears only in the tooltip's `fallback`. That is close to the silent fallback Q38.1 rules out.
- **With a root**, the first pass is planned for the setting's output. The first pass normally only records.
  But when this session already has the folder's lists (a re-offer after an earlier conversion), the first pass
  writes there.

`tests/test_explorer_convert.py:307` asserts only `"beside" in payload`. There, `payload["beside"]` is False.

Suggested fix:

- Offer beside only when the menu's `why` is empty. Otherwise disable the button or leave it out, and give
  the reason in the informative text.
- Start the beside conversion once `folderPrefsChanged` reports the flag on, or keep the
  `set_write_beside` owner and start when its answer arrives. If the save fails, say so.
- In the test, assert `payload["beside"] is True` after the flag's answer.

### 2. Low: Live's converter question outlives Live and blocks a later session

`helab/views/explorer_live.py:219, 797, 804, 918`. `LiveController.box` is cleared only by its answer.
Stopping Live, turning auto-convert off, or starting Live elsewhere leaves the question open. While it stays
open, every `_convert_tick` returns early (`self.box is not None`), so a new Live session's auto-convert in
another folder converts nothing until the stale box is answered. That answer then does nothing
(`session.path != path`).

`ExplorerConverter.close` closes its box. Do the same here: close and clear `self.box` in `_convert_off`
and `stop_live`. A test: start Live, open the share question, stop Live, and check that a new session's tick
queues a convert.

### 3. Low: Q38.1's "for this session" holds only for Live's choice

`explorer_convert.py:139-147` (`ask_after_refusal`'s text) and `:288-294`.

- From Live, the choice sets `AutoConvert.destination` for the session.
- From Folder details, it restarts only that one conversion. Live's auto-convert of the same folder then
  writes beside again, is refused again, and asks again.
- The module docstring says "that conversion, Live's auto-convert or this one, for the rest of the session".
  The dialog says "for this session".

Either word Folder details' question as "this conversion", or keep the choice per folder for the session (a
FolderCache-keyed map like `beside_confirmed`) that both places read. This is the kind of question Q~5 asks
Tony; one line in Q~5 would cover it.

### 4. Low: `share_of` is imported by value in `helab convert`; the patched-names list isn't updated

- `helab/convert_cli.py:299` does `from helab.utils.cache_location import share_of, share_warning`.
- `tests/test_convert_helab.py` patches `cache_location.share_of`, and it works only because that import runs
  inside the function at call time.
- `AGENTS.md`: "A name tests patch is called as `module.name` from other modules, never imported by value
  (list in the area file)".

Call `cache_location.share_of(...)`. Also propose adding `cache_location.share_of` (and
`explorer_convert.confirm_beside_on_share`, patched in `test_explorer_convert.py`) to the list in
`io-and-browsing.md`. The handoff doesn't propose that.

### 5. Low (docs): the GUI now reads the OS mount table itself

`helab/utils/cache_location.py:82-95`. Before this branch, only helpers (`infra._mounts`) and the start-up
cache-folder check (`constants` → `cache_location_problem`) listed mounts in the app. Now Folder details'
render and Live's ticks do too, at most every 10 s. The tools are psutil's `getfsstat` with MNT_NOWAIT on
macOS, `/proc` on Linux, and `GetDriveTypeW` / `WNetGetConnectionW` on Windows.

None of this reads a source folder, and `share_of` is lexical (`abspath`, no stat or realpath; the tests
refuse `realpath`). So this is within "the GUI never touches source folders". Since that rule is the
area's main invariant, `io-and-browsing.md` should say it: "the GUI may read the OS mount table
(`cache_location.mount_table`, cached 10 s) and nothing below a mount point". Today the handoff proposes
only `data-roots.md`'s pointer.

### 6. Nit (Q~1 wording): the stop line's own values are read

`helab/convert/raw.py:106-110` (`ReadStop.detail`). The detail says the TXY "holds only the hits of the rows
before that line". A token stopping the read mid-line keeps the values read before it on that line:
`0,12abc` gives the row (0, 12) (`tests/test_convert_raw.py`'s `STOPS`). The test data's
`not,a,number` starts its line, so the sentence is true there. Suggest "only the hits of what was read
before it", or "the rows up to it", in Q~1's proposed wording.

## Also checked, no finding

- **Source-folder writes.** `FolderCache.convert(beside=False)` and `destination` override the folder's flag
  for cache and temp. The Live share question's default and its Esc choice write nothing to the share. `helab
  convert --output beside` on a share without a terminal or `--yes` goes to the setting's output (Q~3 as
  built). A Q38.1 refusal leaves only `d1.txt` in the folder, tested in the CLI and helper paths.
- **Q38.1 "never silent".** `unsafe_rename` matches only `_cannot_refuse`'s ENOTSUP "Not written:".
  `beside_refused` is sent before the re-raise. The app asks on the run's `error` (Live and Folder details);
  the CLI asks on a terminal, and otherwise logs the refusal and names `--output cache` / `--output temp`.
- **Tests and real shares.** Paths that don't exist, made-up mount tables, `realpath` refused, and
  `share_of` patched in the app and CLI tests. The CLI's real `share_of(resolve=True)` runs only on
  `tmp_path`.
- **Each test fails without its change.** Read hunk by hunk: each new assertion names a field, event, choice
  or text that doesn't exist before its commit. The exception is finding 1's weak assertion.
- **UI rules.** Questions are non-modal `open()`, except the beside confirmation, which answers a click as
  the old `QMessageBox.question` did. Every button is `identify`'d `<prefix>_<choice>` (A~2 tracks adding
  them to `test_accessible_names`). The closure on `box.finished` captures a box Python made, not one Qt
  made. The Convert row is one line, with detail in the tooltip.
- **Info, not a finding:** `ExplorerConverter.offered` doesn't see HeLab's TXY already in HeLab's cache or
  temp folders for a folder that isn't loaded (auto-load off, or a large folder refused). The offer can then
  show again; converting again only skips done shots. A~3 (keeping the stop in provenance) could carry this
  too.

## Doc changes the handoff should add

- `io-and-browsing.md`: the patched-names list (finding 4) and the GUI's mount-table read (finding 5).
- Q~5: whether Folder details' Q38.1 choice is per conversion or per session (finding 3).

## Re-check of the fixes (`be40694..baf7a1c -- helab tests`, 2026-11-03)

Fixes in `bc73f0c`, with the handoff in `baf7a1c`. **All six findings are fixed. No open findings.**

1. **Fixed.**
   - `explorer_convert.beside_unavailable` is now shared with the Live menu. The offer's beside button is
     disabled and gives the reason, and `_offer_answered` refuses beside before the confirmation.
   - A beside start saves the folder's flag first. It waits on `folderPrefsChanged`, which fires because the
     memory flag goes from False to True, and then asks with an explicit `beside=True`. In `FolderCache.convert`,
     `beside` now overrides the memory flag, and the helper still checks the store.
   - A save that can't be queued, or that answers `error` or `cancelled`, stops the conversion and says so in
     the row. That includes a folder without a root, where the helper raises.
   - Tests: gated, waits then beside, can't be saved.
2. **Fixed.** `_convert_off` closes and clears Live's box, and `stop_live` and auto-convert off both go through
   it. Tested both ways, and the test checks that a later auto-convert isn't held.
3. **Fixed.** `explorer_convert.instead` is a per-folder choice for the session. Live's auto-convert, its line
   and Folder details' refusal answer all read or write it, and choosing beside in Folder details clears it.
   The test fixture clears it too. Tested in both directions.
4. **Fixed.** `convert_cli` now calls `cache_location.share_of` and `share_warning` through the module. An AST
   test refuses importing `share_of` or `mount_table` by value anywhere in `helab/`.
5. The handoff (`baf7a1c`) now proposes the `io-and-browsing.md` lines. The code had nothing to change.
6. **Fixed.** `ReadStop.detail` now says "only the hits of what was read before it", and a test checks it.

Each new or changed assertion names behaviour the old code lacked: `beside_unavailable`, no job before the
flag, `payload["beside"] is True`, the box closed, `instead`, the AST check and the new wording. So each one
fails on `be40694`. The two older Live share tests set `ended_at` so that the answer's tick converts at once:
they were timing-dependent before, not weakened.

**Info, not a finding:** `_admin_result` stops every Folder details conversion waiting on its flag when
*any* `convert_prefs` job errors, because `cacheAdminResult` carries no path. Today the only other sender is
Live's read of its own folder after a refusal, and the row says "Click to try again". Filtering by path would
need the event's path. Leave it as it is unless it shows up.

**Rerun:**
- Touched tests: `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-strata` on
  `test_explorer_convert`, `test_share_detection`, `test_convert_raw`, `test_live_convert`, `test_convert_helab`,
  `test_accessible_names`, `test_destroyed_connections` and `test_helper_events`: **1698 passed, 1 skipped, no
  RERUN**.
- Type checks: `mypy helab/ --strict`, `mypy tests --strict`, `mypy helab/ --strict --platform win32`,
  `pyright helab tests` and `pyright --pythonplatform Windows helab tests`: all clean.
