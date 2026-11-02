# Brief: converter UX: TXY and shares (A39.5) and a raw read stopped early (A37.1) (`agent/converter-ux`)

Coordinator: CoCo, 2026-11-02. Tony's go (Chat, via Side, 2026-11-02) for A39.5 and A37.1 after caching v2's stage 2
(landed `1cd586c`). They share paths (`io_ops/convert.py`'s events, `explorer_live.py`'s Live line, Folder details,
`convert_cli.py`), so they are one floor, done in this order: part A (A37.1), then part B (A39.5). One Worker; one
Reviewer at landing. Beside you: Caching v2 (Vault; `cache_store.py`, loading, Settings › Cache) and Live Scripts
(plots). Docs only in `.ai/sessions/2026-11-02-claude-converter-ux/`.

# Part A: A37.1

### Read first

`AGENTS.md` (the converter rules: every backend gives `reference`'s output byte for byte; Qt-free `helab/convert/`);
`.ai/architecture/converter.md` (the parser, `fastio.parse_strict`, `_parse_textscan`, damaged files), `live.md`,
`cache-store.md`'s store-v4 section (the raw layer stores `parse_raw`'s output and `facts`, keyed by
`RAW_PARSER_VERSION`); Q37.1 and A37.1 in the lists; `tests/test_live_testdata.py`.

### Base and branch

Base `a0bc26d` (`dev/v0.0.8`). Branch `agent/converter-ux`. Part B (A39.5) follows on this floor.

### Objective (commit each separately)

1. **The parser reports where it stopped**: both `fastio.parse_strict` and `_parse_textscan` give the line where an
   unreadable token ended the read. The TXY output stays MATLAB's byte for byte (the converter's checks and
   `dev/txy/check_samples.py` on the sample set, read only). **The raw layer:** if `parse_raw`'s output or the
   layer's `facts` change, say whether `RAW_PARSER_VERSION` must bump (a bump re-reads every stored raw layer);
   prefer adding the stop line to `facts` additively without a bump, and say why that's safe.
2. **The event**: a `shot_converted` field (or a warning kind in `helab/io_ops/events.py`, checked by
   `tests/test_helper_events.py`).
3. **Where it shows**: the Live line, Folder details and `helab convert` say "read stopped at line N" (one line,
   detail in the tooltip). `test_damaged_files_during_live_are_said_once_and_the_run_goes_on` checks the flag.
4. **Docs proposals** in the handoff (`converter.md`, `live.md`); wording for Tony as provisional `Q~`.

### Rules

Owned paths: `helab/convert/raw.py`, `fastio.py`, `raw_layer.py` (facts only, if needed), `helab/io_ops/convert.py`
and `events.py` (the event), `helab/views/explorer_live.py` and Folder details (`FolderDetailsPanel.py`,
`explorer_text.py`) for the text, `helab/convert_cli.py` (its line), their tests. Ask CoCo before any other file.
Qt-free `helab/convert/`; strict typing (incl. Windows); tests never touch real data (`~/HeLab-samples` read only,
never written). The full suite and the five type checks before the handoff, every RERUN reported. Docs only in
`.ai/sessions/2026-11-02-claude-converter-ux/`. Push at checkpoints only; read every job's log for RERUN before
reporting a CI run. No version bump, release, tag or PR.

When part A is done (committed, touched tests and types pass), tell CoCo in one line and go straight on to part B; one push at the end.

# Part B: A39.5

### Read first

`AGENTS.md` (the source-folder write rule, Q12.4: a typed command overrides the folder's setting; UI rules);
`.ai/architecture/converter.md`, `data-roots.md` (mounts, shares, volume hints), `live.md` (auto-convert),
`app-runtime-and-ui.md`; Q39.2 and A39.5 in the lists.

### Base and branch

Base `a0bc26d` (`dev/v0.0.8`). Branch `agent/converter-ux`. Part A (A37.1) comes first on this floor.

### Objective (commit each separately)

1. **Share detection** for a folder (reuse what `cache_location.py` / data roots already know about mounts and
   shares; say what counts as a share on macOS, Windows and Linux, and how it is tested without a real share).
2. **A one-time warning per folder** when TXY would be written beside raw files on a share, the user confirming:
   the folder's "write beside" setting, `helab convert --output beside` (a terminal prompt as Q~2 of TXY Index
   did, `--yes` without one), and Live's auto-convert on a share (allowed after the same warning).
3. **A share folder with no TXY of any kind**: Folder details offers "Convert to HeLab's cache (recommended)" or
   temp, says the converter should run on the machine that owns the data (the acquisition PC), and keeps
   "Convert beside on the share…" behind the warning.
4. **Q38.1 (Tony, 2026-11-02):** when a beside write can't rename safely (no hard link and no no-replace rename
   on that file system, today refused, `txy._rename_new`), show a warning letting the user choose **Retry** or
   **write to HeLab's local cache or temp instead**; never a silent refusal and never a silent fallback. In
   `helab convert`, a terminal prompt (non-interactive: the refusal as today with a message naming the
   choice). A test for each path.
5. **Docs proposals** in the handoff (`converter.md`, `data-roots.md`, `live.md`, `app-runtime-and-ui.md`),
   wording for Tony as provisional `Q~`.

### Rules

Owned paths: `helab/utils/cache_location.py` (share detection), `helab/views/ConverterTab.py`,
`helab/views/FolderDetailsPanel.py` and `FolderExplorer.py` (the offer), `helab/views/explorer_live.py` (the
auto-convert warning only), `helab/convert_cli.py` (the prompt), the helper-side check in `helab/io_ops/convert.py`
if one is needed (smallest change), their tests. Ask CoCo before any other file. Every control named with an
ID; strict typing (incl. `--platform win32`, `pyright --pythonplatform Windows`); tests never touch real data or
real shares (paths that don't exist, patched detection). The full suite (`-n` with `--reruns 5 --reruns-delay 1`)
and the five type checks before the handoff, every RERUN reported. Docs only in
`.ai/sessions/2026-11-02-claude-converter-ux/`. Push at checkpoints only; read every Tests and Converter backends
job's log for RERUN before reporting a CI run. No version bump, release, tag or PR.

When done: `maestri ask "CoCo" "Converter UX: done at <hash>, suite <N> passed, RERUNs <…>, CI <run>"`.
