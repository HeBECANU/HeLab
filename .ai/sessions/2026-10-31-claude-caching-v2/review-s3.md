# Review: Caching v2 stage 3, convert on read (switch off): `65f98d0..4e14535`

Reviewer: Assay (Claude Opus 5.5), 2026-11-03. Read-only on code. The commits:

| Commit | What |
|---|---|
| `912f928` | 3a, loads convert on read, plus A47.1 |
| `4e86094` | 3b, Live converts on read, plus A40.2 |
| `0cd133f` | 3c, counts and wording |
| `4e14535` | 3d, the session |

Handoff-only commits are skipped. I read `design-stage3.md` (R~1 and R~2 accepted), the handoff's "Stage 3", Vault's
points in CoCo's message, and AGENTS.md's I/O rules.

**Verdict: no blocker while the switch is off. 2 findings: 0 High, 0 Medium, 2 Low.** Both are reachable only with the
`store_v4` switch on.
- **S3R-1 (Low):** the conversion's ticker also covers reading the raw file, against the converter's own rule.
- **S3R-2 (Low):** S3-5's "converted when loaded" count misses every shot that MATLAB's TXY also covers, which is
  where Q~16's open question bites.

## Findings

### S3R-1 · Low · The conversion's ticker also covers reading the raw file, so a stalled share read sends heartbeats

- `helab/io_ops/txy_cache.py:83-107` (`convert_raw_file`: `with _Ticker(send, "converting", compute_budget(size))`
  around `_read_raw` too).
- **Scenario.** A load or a Live check converts a shot on read from a share that stops answering mid-read (a hung
  SMB mount).
  - `_read_raw` already sends its own heartbeat after each 8 MB block, so a stalled read sends none.
  - But the ticker thread keeps sending heartbeats for the whole `compute_budget`: 60 s plus 1 s per MB.
  - IOService's no-progress timeout (60 s) can only start after that. A stall is caught after 2 minutes or more,
    not 1, for a shot of any size.
- This is the converter's own rule in `_Ticker`'s docstring: "Heartbeats … while this process or its workers
  compute (**not while reading: a stalled read must still time out**)". `convert_folder` keeps the read outside its
  ticker (`convert.py:808`), and AGENTS.md says timeouts measure time without progress.
- **Fix.** Read first, under `_read_raw`'s own `Heartbeat`, then run `not_done` and `convert_shot` under the
  `_Ticker`, as `convert_folder` does.
- **How verified.** By reading `convert_raw_file`, `_Ticker`'s docstring, and `convert.py`'s use of each.

### S3R-2 · Low · "Converted when loaded" misses shots MATLAB's TXY also covers, which HeLab priority converts

- `helab/utils/folder_cache.py:1036-1039` (`on_read_shots`: `max(0, raw - txy)`), used by the row tooltip, the
  explorer's count line, Folder details, the status bar, auto-load and Live launch's first load (3c).
- **Scenario.** The switch is on, with the default source, HeLab priority (or HeLab only). A folder has raw files
  and MATLAB's `d_txy_forc` for every shot, but no HeLab text.
  - For those sources `could_take` is `None` (every shot) and `compose` picks the on-read conversion over MATLAB's
    TXY. So its first load converts every shot. That is Q~16's behaviour, as built.
  - `on_read_shots` gives `raw - txy` = 0, because MATLAB's TXY files count as TXY. The tooltip, the count line
    and Folder details say nothing about conversion, while the load is the slowest kind. (The "not loaded"
    message and auto-load still act, since the folder's MATLAB TXY count as data.)
  - The formula counts only shots with no TXY of any kind: right for MATLAB priority, wrong for HeLab priority
    and HeLab only.
- **Fix.** Count by the source:
  - MATLAB priority: raw shots without MATLAB's TXY (as now, near enough);
  - HeLab priority and HeLab only: raw shots without a current HeLab TXY of the profile. Memory has HeLab's count
    (`txy_helab`) when the folder was listed.

  If Tony answers Q~16 with its alternative (convert only shots without MATLAB's TXY), the formula is right as it
  is, and the load is what changes. **Either way, the count and the load should agree once Q~16 is answered.**
- **How verified.** Scratch test (`.ai/temp/assay/test_zz_s3r.py`, using `test_convert_on_read.py`'s helpers, on
  an export of `4e14535`): a raw folder with MATLAB's TXY for both shots, loaded with HeLab priority, reports
  `converted == 2`, while `on_read_shots`' formula on its counts (2 raw, 2 TXY) gives 0.

## Checked, no finding

- **No text written by a load or Live (Q19.1).**
  - `convert_raw_file` runs `convert_shot` in memory and parses its text with `txy_array`. Nothing is written
    beside or into `converted-txy/`.
  - The test checks for no `d_txy_helab_*` anywhere.
  - No raw row is written (R~2).
- **Off the GUI thread, with heartbeats** (S3R-1 aside): conversions run in the load or Live helper, before any
  `file_started`, so the per-file 15/20/30 s window never covers them. They run under `_Ticker(compute_budget)`.
- **The Settings backend (A47.6):** `backend_for(txy["backend"], profile)` for loads, the raw layer and Live
  alike. Settings' choice when it runs here, else numpy; numba is always numpy.
- **Byte-identical to reference:** `convert_shot` is the converter's own pipeline, and every backend's output is
  the reference's by the converter's contract, proved per backend (`test_raw_layer`, `test_convert_*`, cython in
  CI's Converter backends job).
- **The contract behind "a held on-read shot is not read again when its text appears":**
  - Live keeps a held shot when its origin (`helab:<hash>`, the same profile) is unchanged and the raw file's
    stat equals the held fingerprint.
  - A text of the same profile hash made from that raw file is, by the converter's rule ("profiles with one hash
    convert every file alike", the provenance's `stale`), `format_txy` of the same hits. So its parse equals the
    held array.
  - The rule spans HeLab versions only as far as the converter's output never changes for a profile hash. It is
    the same rule `find` already relies on when it calls a text current.
- **A40.2:**
  - a held shot whose new HeLab TXY fails keeps its held data in the fingerprint and goes back as `live_failed`;
  - `LiveSession.held_failed` sends it with `known`;
  - `to_read` leaves out every candidate whose stat `failed` names, so it isn't read again unchanged;
  - a readable TXY later replaces it.
- **Unfinished raw files are never read:**
  - candidates are keyed by the raw file's stat, so the settle time applies;
  - `_read_raw` checks `fstat` before and after the read;
  - `not_done` makes a file late (waits), or damaged after a minute unchanged (problematic);
  - Live's `LATE` goes back to `waiting`.
- **A47.1:** FolderCache sends the conversion profile whole (`profile_def`). `profile_for` accepts it only when
  its content hash is the origin's, else a built-in, else no conversion (that shot's text is read).
- **S3-5 "memory only":** `converts_on_read` and `on_read_shots` read FolderCache's memory and `store_options()`
  (globals, and `live_layout` and the maker once per process, already read by then).
- **Switch off changes nothing:**
  - loads take on-read candidates only with `access.layered`;
  - Live only with `txy["on_read"]`, which `with_txy` sets only when the options carry `policy` (store-v4);
  - `converts_on_read` is False without `policy`;
  - `test_store_v3_never_converts_on_read`;
  - the extra `profile_def` in store-v3 payloads is read by no store-v3 path.
- **Fails without its change** (each commit exported, with its `helab/` files as they were at its parent):

  | Commit | Without its change | With it |
  |---|---|---|
  | `912f928` | the test file doesn't import (1 error) | 6 passed |
  | `4e86094` | 5 failed | 5 passed |
  | `0cd133f` | 3 failed | 3 passed |

## Checks (run by the reviewer)

On an export of `4e14535`, whose `helab/` and `tests/` equal the floor's `HEAD` `2247b69`:
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` (the full suite,
  `test_convert_on_read.py` and `test_caching_v2_session.py` included): **8951 passed, 673 skipped, 2 warnings, 3 failed, 15 rerun in 169.12 s.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests (the export has no `.git`; 5 reruns each).
  - In the floor checkout: **3 passed, no RERUN**.
  - No other RERUN.
  - The 2 warnings are the known pyqtgraph ones.
  - The totals match Vault's 8955 passed and 672 skipped, once the export's 3 and 1 are added back.
- `mypy helab/ --strict` (203 files), `mypy tests --strict` (192), `--platform win32`: no issues.
- `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
- Scratch, not committed: S3R-2 (`.ai/temp/assay/test_zz_s3r.py`).

On fix diffs I re-check only the fixes, their tests and the touched files' type checks.
