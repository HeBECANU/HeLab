# AI to-do

This is the ongoing list of work agents may do without asking Tony: docs upkeep, release
preparation, repo hygiene, verification jobs and small fixes already agreed. Any agent may
raise an item. It is one of three living lists shared by every agent:

- [DECISIONS_TODO](DECISIONS_TODO.md): decisions for Tony, `Q` IDs;
- [MANUAL_TODO](MANUAL_TODO.md): checks that need Tony at a screen or the lab, `M` IDs;
- this file: work agents do, `A` IDs.

**IDs** are `<letter><block>.<item>[.<sub>]`. Blocks are listed in [ID_BLOCKS](ID_BLOCKS.md),
and the ID rules are in [DECISIONS_TODO](DECISIONS_TODO.md). Floors and cloud agents propose
`A~1`, `A~2`… in their handoff, and the Coordinator or the Assistant gives them final IDs when
merging.

How to use this list:

- Each item says where it runs (Ground, a floor or CI) and links to its evidence.
- An item that needs a decision first goes to DECISIONS_TODO, and comes back here once Tony has
  answered.
- Features stay in `roadmaps/_readme.md` and bugs in `roadmaps/known-issues.md`; an item here may
  point to them.
- Tick a done item with its commit, and drop ticked items at each release's tidy-up.

The usual rules still apply:

- ask before committing on Ground;
- floors work on their own branches;
- **tests never touch real data**: real-share items only prepare tools and fixtures, and running
  them on the share stays with Tony.

## Carried over from v0.0.6 (block 1)

- **A1.1 Tidy MANUAL_TODO** (Ground, docs only). Tick or merge the items later work replaced:
  the store-v2 / account-independent SMB-key instructions (now Q1.5), and duplicates between the
  v0.0.5a lists and the later ones. Link the smoke pass from each item it covers. Group what's
  left by where it's checked: Mac, lab PC, lab share, real-data physics. Give the older items
  M IDs as they're touched.
- **A1.2 Build the macOS app locally** (Ground). On the release commit, run
  `pyinstaller HeLab.spec --clean -y`, then check:
  - the zip is ~300 MB and holds only `HeLab.app`;
  - launched from outside the checkout, Help › About matches the version, commit and build stamp;
  - helpers run in the packaged app;
  - the SVG triangle and Qt's SVG icon plugin render.

  This is the macOS half of MANUAL_TODO's "native UI and packaged application" and "release
  evidence". The Windows build is checked on the lab PC with the smoke pass.

  Partly done: the smoke pass built the app at `41a6a7d` and its helpers ran
  ([results](sessions/2026-10-28-claude-smoke-mac/results.md)); About showed `0.0.5a1` there,
  before the bump, so the About check on a release commit is left.
- **A1.3 A picture sheet of every plot** (Ground or a floor). Render each Basic plots v1 and DLD
  port plot natively on macOS (not offscreen) in a 560 px dock, from a synthetic dataset in
  Tony's units, into one sheet that Tony can check in one look. It covers how "ms/mm
  everywhere", "titles wrap" and "the ħ glyph" look; behaviour stays in the smoke pass.
- **A1.4 Edge cases with disposable fixtures** (a floor). Under pytest with the real window
  (`HELAB_SHOW_GUI=1` where it helps), check each case and add a test where none exists:
  - a TXY file written halfway, then finished or repaired;
  - tabs switched and closed during shared listings and loads;
  - cancel and retry during I/O, never beside a helper that is still stopping;
  - a source folder removed mid-load.

  Most of these already have offscreen tests, so first list which ones.
- **A1.6 Hover-menu timing tests** (CI watch). Read each release CI run's logs for hover-menu
  reruns (≈200 ms slack). One that reproduces goes to known-issues with its logs.

### After the smoke pass

- **A1.7 Summarise Tony's I/O trace**, if he recorded one. Run
  `.ai/sessions/2026-10-19-claude-smb-io-audit/trace_summary.py <folder> --under <share> --minutes`.
  Expect:
  - no `roots_verify` bursts;
  - about 0 ops/min while idle;
  - one `load: shot time` per raw file of an uncached load, and none on a cached reload.

  Compare it with the 2026-10-19 audit (`compare_traces.py`). This covers MANUAL_TODO's trace
  items (Live, the DLD port's D7).
- **A1.8 Carry the results into the docs.**
  - Tick the MANUAL_TODO items the [smoke pass](MANUAL_TODO.md#release-smoke-pass) covered.
  - Move the problems it found to known-issues.
  - Move Tony's decisions into the roadmap and `.ai/memory/results/`.

  Partly done: the problems are in known-issues. Left: ticking or marking Mac-passed the
  MANUAL_TODO items the pass overlaps (Presets, Work Offline, Saved results).

## From the audit (block 2)

Finding numbers (#N) refer to the [audit](sessions/2026-10-28-claude-v0.0.6-checks/audit.md).

- **A2.1 Docs refresh** (Ground, docs only, one commit). Bring the docs up to date with what has
  landed, and in line with Tony's decisions where they contradict them:
  - the roadmap and plans' status lines (#8);
  - documents that contradict his decisions (#9, #10);
  - stale memory (#11), known-issues (#12), MANUAL_TODO (#13) and the README (#14);
  - handoff follow-ups that were never carried over, into known-issues, `refactoring.md` and the
    DLD plan (#16);
  - the Maestri note's decisions into `_readme.md`, and the "v0.0.6 changes" note (#7).
- **A2.2 Small app fixes** (a Quick Fixes floor, now that v0.0.6a1 is out):
  - set werkzeug's logger to WARNING (#20);
  - write the watchdog's stall stacks into the log (#19);
  - name the cause in "Disk cache unavailable" (#21);
  - retire the old `diskcache.*` settings keys (#22);
  - lower the back button's log line to DEBUG (#22).
- **A2.3 Idle CPU** (with A2.2): find what repaints at ~35 % CPU in an idle window (#18).
- **A2.4 Unclosed SQLite connections in tests** (with A2.2): run with `-W error::ResourceWarning`
  and tracemalloc to find what opens them (#23). They may explain the Windows file-lock
  failures.

## From the planning-docs audit (block 7)

Finding numbers refer to the [planning-docs audit](sessions/2026-10-28-claude-docs-audit/planning.md).

- **A7.1 Check Dependabot's graph run** (CI watch, from Q6.4). Once v0.0.7 is on `main`, check
  that Dependabot's dependency-graph run passes (no "not our ref" on the submodules) and that
  `dependency-graph.yml`'s snapshot of `requirements.lock` shows in the graph (#7).
- **A7.2 Refresh the lock with `--upgrade`** (a floor or Ground, its own CI run; Q1.9 item 6,
  #8). It brings python-dateutil 3.0 (the lock pins 2.9.0.post0); follow the README's
  "Updating dependencies", then the full suite and the three type checks.

## From the docs and Maestri audit (block 8)

- **A8.1 Call `folder_cache.store_options()` in `HelabMainWindow`** (architecture audit #6).
  `helab/views/HelabMainWindow.py` imports `store_options` by value and
  `tests/test_helabMainWindow.py` patches only `helab.utils.folder_cache.store_options`; once it
  is called as `folder_cache.store_options()`, drop the exception from `io-and-browsing.md`.

## Converter stage 2 (block 11)

From the backend floors' and the bench's handoffs (`sessions/2026-10-29-claude-txy-*/handoff.md`).

- **A11.3 A conftest-wide numba cache fixture**: a session-scoped autouse fixture calling
  `numba_backend.set_cache_folder(<session temp>/numba-cache)`, replacing the numba tests' own (which
  would raise if another file's in-process numba test loaded the kernels first on a worker).
- **A11.4 Faster text I/O** (optional, after stage 4): reading (~560 MB/s) and writing (~340 MB/s)
  are 80-83 % of a compiled conversion and hold the GIL. The rust floor's `parse_strict` (1,910 MB/s)
  and `format_txy` (596 MB/s) are byte-identical on all samples (report only today); wired in behind
  the same checks they'd take rust to ~300 MB/s per core and let threads scale. A vectorised exact
  `%.8g` in NumPy was ~1.5x slower per value than `%` (not worth it while conversions run in processes).

## Converter stage 4, HeLab core (block 12)

- **A12.1 Workers in a frozen app** (`agent/txy-packaging`): run a `convert` with `workers` 2 (spawned
  through `freeze_support`) in the built app on all three OSes; if it works, make `DEFAULT_WORKERS`
  the same as from source (1 frozen today).
- **A12.2 `HeLab.exe convert` on Windows** (`agent/txy-packaging`): the windowed exe has no console;
  check where its output goes, and consider a console launcher (`HeLab-convert.exe`) if the
  acquisition PC needs one.

## Quick Fixes 4 (block 13)

- **A13.1 Helpers start with an explicit working folder** (or, under `SOURCE_GUARD`, the working
  folder leaves the guard's denied list), so a test that `chdir`s can't make a helper's source access
  fail (known-issues, Tests and CI). From Quick Fixes 4's A~2 and Plover's review.

## Converter stage 4, UI and Live (blocks 14, 15)

- **A14.1 An end-to-end GUI test of a plot switching TXY sources** on a folder with real helpers
  (convert, load, Live): the plot's TXY row is checked by unit tests and offscreen rendering only.
- **A14.2 A pending Reload's flag on a source change** (Egret, round 3): `instance.py`'s
  `_reload_from_source` isn't cleared when `set_txy_source` changes the source while a Reload's load
  is pending, so the released picture can stay "loading its TXY source…" until the next run. Reset
  the flag (and the released state) in `set_txy_source`.
- **A15.1 Pace conversions on large shares**: each conversion lists the folder and stats its raw
  files every `live_interval` while auto-convert is on; if M15.1 shows it costs, convert only after a
  Live listing found new names.
- **A15.2 `PresetFolder` and empty folders**: check whether `PresetFolder.check` starts Live twice on
  a folder with no shots yet, as `LaunchFolder` did; same fix if so.
- **A15.3 `test_live.run_helper` sends every field `io_helper` does** (`txy`, `memory_origins`,
  `helab_since`, `listed_mtime`, `seen_names`, `identity_root`), so Live tests elsewhere exercise
  what the helper runs (`test_live_convert.py` already does).

## Caching after the converter (block 19)

Tony's go came on 2026-10-31 (Q28.1), on the Caching v2 floor.

- [x] **A19.2 Clear converted TXY vs a running conversion** (audit K4; done in `ce8eae7` and S0-1's fix,
  Caching v2 stage 0, landed `ad86bd3`): `clear_converted` takes a fence a conversion checks before each
  write, or the docs say a running conversion may write after it.

## Quick Fixes 6 (block 20)

- **A20.1 Correct the slow-first hook's comment** (`tests/conftest.py` ~205-209, and the floor's notes):
  workers never see the command line's `--dist` (xdist sets `dist = 'no'` on every worker), so the
  `spread` check is always true under xdist; drop it and fix the comment. Harmless today (Tern).

## TXY ship (block 21)

- **A21.1 Two stale backend strings** (not the ship floor's paths): `helab/convert/backends/numba_backend.py`'s
  docstring says the helper passes a cache folder under `cache_dir()` (now the temp folder, Q18.1);
  `helab/convert/backends/rust.py` (~:7, :80) says "build it with `maturin develop --release`", now
  `python native/build.py --only rust`.
- **A21.2 Developer venvs keep the unshipped packages**: `uv pip install -r requirements.lock` never
  removes numba, llvmlite, mlx, mlx-metal or maturin from Ground's or floors' venvs (harmless: builds
  exclude them, tests run where installed); `uv pip sync requirements.lock` then `uv pip install -e .`
  gives the shipped set. Say so in the README's "updating dependencies" if worth it.

## Store-v4 planning (block 22)

- **A22.1 Shot axes when numbers skip** (Q22.5): the TDC may skip shot numbers on pause/resume.
  Shot trends already plots against shot number or shot time (`shot_trends.py` `X_AXIS`); add a
  "shot index" (consecutive, gaps removed) and offer the same three axes in every per-shot plot.

## Converter follow-ups (block 23)

- **A23.1 Count HeLab's TXY of the tab's tag in folder status** (also A18.1). Waits for Q14.4.
- **A23.2 Colour only the no-hit part of the Live line** if `ElidedLabel` learns rich text (Q23.5).
- **A23.3 Remove the `live_launch_folders` row and its migration** a release or two after v0.0.7.

## Docs audit 2 (block 24)

- **A24.1 Enforce `helab/convert/` as Qt-free** (architecture audit 2, #6): extend
  `tests/test_headless_imports.py` to walk `helab.convert` (`pkgutil.walk_packages`) with
  `backends.numba_kernels` as optional only, so a converter module that imports Qt or
  `helab.utils.constants` fails CI; then `converter.md` and AGENTS.md can say it is enforced.

## Converted-TXY index (block 30)

From the TXY Index floor's [handoff](sessions/2026-10-29-claude-txy-index/handoff.md) (landed `460360b`).

- **A30.1 `events.ShotKeptEvent`'s docstring** still says "no local provenance record": reword to "a
  beside TXY that isn't current (older than its raw file) or written by another conversion meanwhile".
- **A30.2 `helab_txy.converted_usage` at scale**: it still lists each hash folder (names only; `stat`
  only for files the index doesn't know). If `converted-txy/` grows to tens of thousands of TXY,
  measure by the index alone and list folders only on Clear.
- **A30.3 One index connection per `helab convert` run** (not urgent; no starvation seen outside the
  test): `--watch` reopens the index each pass and the app's helper once per request. Keeping
  `helab convert`'s connection for its whole run (reopening after `IndexUnavailable` or a set-aside)
  stops the `-wal` being rebuilt between them; it doesn't make SQLite's lock fair. Cost (Tern): on
  Windows a long-held connection blocks the app helper's set-aside of a damaged index, so the app's
  conversions fail until `helab convert` reopens.
- **A30.5 Settings refuses a temp folder on a network drive or in a synced folder** (Q30.5): the
  cache folder's check (`cache_location.cache_location_problem`) and wording for Settings › General's
  temp folder; an existing such setting kept but warned about once.

## Byte units floor (block 32)

- **A32.1 `result_cache.LARGE_RESULT_BYTES` by OS** (optional): the 50 MB threshold could follow the
  disk unit like the log thresholds, if Tony wants every threshold by OS
  ([handoff](sessions/2026-10-29-claude-byte-units/handoff.md)).

## Smoke ready (block 34)

From the Smoke ready floor's [handoff](sessions/2026-10-30-claude-smoke-ready/handoff.md) (landed `4ad8ac5`).

- **A34.1 Screenshots of QtWebEngine panes on the lab PCs** paint black on screen and so in the grab
  ([memory](memory/results/lab-pc-qtwebengine-black-render.md)); the plot's HTML export covers them.
  No workaround built; the 3D scatter's OpenGL fallback view wasn't grabbed (M34.2).
- **A34.2 A test guard for Qt-made senders**: fail on `X.<signal>.connect(lambda …)` whose lambda
  refers to `X` where `X` comes from `findChildren`/`findChild`/`tabBar()`/`widgetForAction` (Wren's
  AST scan finds 14 such connections, all safe today). It backs AGENTS.md's rule; a sender reached
  through another name would escape it.

## Runner tools (block 35)

From the Runner Tools floor's [handoff](sessions/2026-10-30-claude-runner-tools/handoff.md) (landed `0316bae`).

- **A35.1 A `dev/` wait helper for runners** (`wait_milestone.py EVENT [key=value …] --log <file>
  --timeout S`, built on `app_log.parse_milestone`), if the runbook's waits want more than `grep`.
- **A35.2 `--geometry` through the dev stub**: `open …/HeLab-dev.app --args --geometry …` (Smoke ready
  has landed it); check once.

## UI polish (block 36)

From the UI polish floor's [handoff](sessions/2026-10-30-claude-ui-polish/handoff.md) and Ibis's
[review](sessions/2026-10-30-claude-ui-polish/review.md) (landed `c104502`). Its A~1, the Plotly SIGSEGV fix,
was done on the floor.

- **A36.1** `read_settle_seconds` could move from `SettingsDialog.py` to `constants.py`, beside
  `read_live_interval`.
- **A36.2** `events.ShotUnconvertibleEvent`'s docstring could name the path-too-long message among the
  "failed" reasons.
- **A36.3** (Ibis R3-1) `helab/analysis/panes.py` `update_figure` after `release_figure()` could put a
  released figure back on the Dash server; nothing calls it so today. A guard (ignore, or log) would close it.
- **A36.4** (Ibis R3-2) `tests/test_main_split.py` would accept a settings panel collapsed to zero width;
  check `0 < right` too.

## Live tests on the test data (block 37)

From the Assistant's Live tests on HeLab's test data (`tests/test_live_testdata.py`, 2026-10-31).

- [x] **A37.1** (done in `a37deb1`, `2c88b65`, `fd43431`, Converter UX, landed `ed7bcf9`: `raw.ReadStop`, `shot_converted.read_stop`, the Live line, Folder details and `helab convert` name it; the raw layer's `Facts.stop_line`) (Q37.1; v0.0.8, Tony 2026-10-31) Say when a raw file's reading stops early: the parser (`helab/convert/raw.py`, both
  `fastio.parse_strict` and `_parse_textscan`) reports the line where an unreadable token ended it, the
  conversion keeps MATLAB's TXY byte for byte and adds the stop to its event (a `shot_converted` field, or
  a warning kind in `helab/io_ops/events.py`), and the Live line, Folder details and `helab convert` name
  it ("read stopped at line N"). `test_damaged_files_during_live_are_said_once_and_the_run_goes_on` then
  checks the flag.

## Quick Fixes 7 (block 38)

From Quick Fixes 7's [handoff](sessions/2026-10-31-claude-quick-fixes-7/handoff.md) (Rivet on Ground, Codex's
review of PR #10, six rounds).

- **A38.1** Audit `helab/io_ops/live.py`'s matching paths for the two gaps Codex found in `save_held`: no
  test for a held HeLab shot whose TXY has gone, nor for a shadowed MATLAB TXY that has settled. Its
  `file_names`/signature shapes are the same, so the same two holes may be there.
- **A38.2** (display only) `AutoConvert.damaged` in `helab/views/explorer_live.py` keeps a file counted
  "damaged" while it stays unconvertible, even when a later profile fails it for another reason; on a new
  summary it could keep only names whose current message starts with `DAMAGED_TEXT`.

## The release check and Tony's answers (block 39)

- [x] **A39.1 Check release archives on PR builds** (done in `c201c01`, Quick Fixes 8; `release_draft
  --check` on every 3.13 build, passed on all three in its CI runs) (CI; Ground or a floor): `main`'s
  release job is the only place `release_draft --validate-only` runs, so 0.0.7a1's linked macOS build
  stamp showed only after the
  merge (run 41110274554; [known issues](../roadmaps/known-issues.md#fixed)). Run the archive check (the
  stamps, without the tag and the draft) on each PR's three builds against its build commit, so a
  packaging change that breaks it fails the PR.

- [x] **A39.2 Live takes HeLab's TXY for a shot held from MATLAB's** (done in `10a9c3c`, `f945f69`, IO
  Fixes, landed `471966b`) (Q38.2, Tony 2026-10-31; the I/O area):
  under HeLab priority, a HeLab TXY converted during Live replaces the shot held from MATLAB's TXY,
  read again as a changed shot (as a HeLab-held shot converted again is), instead of waiting for the
  folder's next load (`fefe6ab`).

- [x] **A39.3 One running HeLab per computer** (done in `0335768`, `f128623`, Quick Fixes 8; what only
  served several at once is listed in its [handoff](sessions/2026-10-31-claude-quick-fixes-8/handoff.md),
  not removed: A43.2, Q43.4) (Q39.1, Tony 2026-10-31): a second HeLab (source or build)
  started while one runs says so and stops before opening anything; the lock in the app folder, so an
  override (agents, tests) has its own. Then drop what only served several at once where the area
  review names it (`.ai/sessions/2026-10-31-claude-area-review/cache.md`).

- [x] **A39.4 Folder details: TXY left out and TXY per converter** (done in `915aff5`, Quick Fixes 8) (Q38.3, Tony 2026-10-31): the load line says
  "N left out (TXY source)" for shots the folder's TXY source leaves out (a `load_counts` key and
  `FolderExplorer.load_count_details`, `924109a`), keeping "removed" for files really gone; and a line with
  the folder's TXY counts by kind, from the listing's names only (memory, no I/O): MATLAB's
  `d_txy_forc` and each HeLab tag's `d_txy_helab_<tag>_` (e.g. "TXY: 120 MATLAB · 118 p19v1"; detail in
  the tooltip).

- [x] **A39.5 TXY and shares** (done in `186b7b0`, `7648e27`, `a36bc95`, `7a60998`, review fixes `bc73f0c`, Converter UX, landed `ed7bcf9`, with Q38.1's build; `cache_location.share_of`, `helab/views/explorer_convert.py`) (Q39.2, Tony 2026-10-31; the converter and I/O areas): writing TXY beside the
  raw files on a share (`helab/utils/cache_location.py` and the data roots' share detection) warns once
  per folder that conversion belongs on the machine that owns the data, the user confirming: the folder's
  beside setting, `helab convert --output beside`, and Live's auto-convert. A share folder with no TXY of
  any kind offers in Folder details to convert into HeLab's cache (recommended) or temp folder, says the
  converter should run on the acquisition PC, and keeps "Convert beside on the share…" behind the warning.

## I/O fixes (block 40)

From the IO Fixes floor's [handoff](sessions/2026-10-31-claude-io-fixes/handoff.md) (Conduit; landed `471966b`).

- [x] **A40.1 A helper still starting when HeLab quits** (done in `b34683e`, Quick Fixes 9, as a guard test: quitting cancels every request first, and `_run` already kills a cancelled one after `Popen`; no code change) (no `process` yet in `IOService._run`) is stopped
  only by `_run`'s daemon thread, so it may run until its first stdout write fails. Low risk. Fix: `_run`
  checks `self.closed` right after `Popen` and kills.
- [x] **A40.2 An unreadable new HeLab TXY in `live_check`** (done in `4e86094`, caching v2 stage 3, landed `d4f28f3`: the held data is kept and the file goes back as `live_failed`): a switched or HeLab-held shot whose new HeLab TXY
  turns out unreadable drops the held data and keeps the shot known-unreadable (as for a HeLab-held shot
  converted again). Unlikely (temporary name and rename); keeping the held data until a readable TXY is
  read would be safer (Probe agrees: a fresh load would take the same file). It joined caching v2's stage 2
  (design addendum §7) but wasn't built there; built in stage 3.
- [x] **A40.3 A signature-only change rewrites the whole dataset** (done in store-v4, caching v2 stage 2: `confirm_view`, `b691d26`, used by loads from `7d185eb`; it writes only the view's signature and TXY record, `txy.folders` included; store-v3 unchanged) (io-5; the cache area, best with caching
  v2's store work): every cached shot is unpacked and packed again, though no TXY is read.
  `CacheStore.confirm_dataset(..., signature=None)` merging a given signature into `info` (JSON, no schema
  change), and a confirm branch in `loading.load` for a cache whole but for the signature, would need
  neither the dataset nor a rewrite.
- [x] **A40.4 Cancel all loads and scans' tip** (done in `0f54c5e`, Quick Fixes 9) (Q40.1): set `MissingShotsWindow.CANCEL_TIP` to "Cancel every
  load and scan, running, paused or queued. Browsing, cached data, saves and Live go on; loads already
  saving their cached data finish."

## Plot identity (block 41)

From the Plot Identity floor's [handoff](sessions/2026-10-31-claude-plot-identity/handoff.md) (Prism; landed
`e3f94d9`).

- **A41.1 An outdated saved result has no view**: `AnalysisInstance._cached_found` shows it without one.
  If Release or the TXY row ever needs that result's own data, build a hollow view from the saved record
  (coverage and origins). Not needed now: open until Release or the TXY row needs it (Quick Fixes 9
  found no defect, 2026-11-02).

## Caching v2 (block 42)

From the Caching v2 floor's [handoff](sessions/2026-10-31-claude-caching-v2/handoff.md) (Vault; stage 0 and
checkpoint 2 landed `ad86bd3`). The floor's own remaining steps (5–7, and what step 5 owes) are in its
handoff and the [plan](../roadmaps/caching-v2.md#stages-each-needs-tonys-go).

- [x] **A42.1 store-v3's saved results under Keep** (done in `08895bc`, stage 2: copied into store-v4 as `result_find` returns them, within the budget, never over a newer one): copy a v3 result into v4 when it is used (the addendum
  said "by the next save of that folder's results"), or decide read-through is enough while v3 is kept
  (built: read-through only).
- [x] **A42.2 `trim` in Make room's order** (done in `b691d26`, with S2-1's fix `6b0f998` and the question from its plan `102c027`, stage 2: one planner, only copies only when named): a lowered budget in store-v4 removes datasets only; give it Make
  room's order (datasets, raw layers seen, only copies named).

## Quick Fixes 8 (block 43)

From Quick Fixes 8's [handoff](sessions/2026-10-31-claude-quick-fixes-8/handoff.md) (Rivet on Ground).

- [x] **A43.1 Toolbar icons in every test window** (done in `e784834`, Quick Fixes 9): without `IconsInitUtil.initialise_icons()` the side
  toolbars show their text, so a `HelabMainWindow`'s widths depend on which tests ran earlier on the xdist
  worker (the cause of `test_main_split`'s Windows failures). A conftest autouse fixture would remove it
  everywhere; it must take pytest-qt's `qapp` (icons before a `QApplication` abort the worker, `1f86ca2`).
- [x] **A43.2 "Another HeLab may have changed them"** (done in `e3faeb3`, Quick Fixes 9) before `read_presets()` (`PresetsInspector.py:207`,
  `views/plots/presets.py:267`, `:613`): with one app per computer (Q39.1) and `helab convert` writing no
  presets, keep the cheap re-reads and drop that reason from the comments.
- [x] **A43.3 Reset all settings while Work Offline is on** (done in `c9e64e6`) (Q43.1, Tony 2026-10-31; app-1; numbered at block
  44's docs pass): only while Work Offline is on, the Reset confirmation asks whether to keep Work Offline
  (the default button, as the cache folder's location is kept) or go online now. Rivet's, on Ground
  (Quick Fixes 8; in progress at numbering).
- [x] **A43.4 The cache move's refusal while a converter runs** (done in `4940a81`) (Q43.4, Tony 2026-10-31): `cache_locks.lock_for_move`'s
  "Another HeLab is running (N windows)." becomes "A HeLab converter (helab convert) is running (N). Stop it
  before moving the cache." (only `helab convert` can hold it now, Q39.1). Rivet's, on Ground (Quick Fixes 8).
- [x] **A43.5 The two other "Another HeLab is running" texts** (done in `42855ab`, Quick Fixes 9) (Q43.5, Tony 2026-11-01): `CacheTab.py:605`
  becomes "A HeLab converter (helab convert) is running. Stop it before clearing the older cache." and
  `CacheDialogs.py:106` "A HeLab converter (helab convert) is running. Stop it before clearing old stores."
  (Quick Fixes 9.)

## Quick Fixes 9 (block 46)

- [x] **A46.1 Process-wide fakes in tests** (done in `6fa8cd9`, Quick Fixes 9: `conftest.this_tests(fake, real)`; fakes acting only on the test's own paths left as they were) (Quick Fixes 9's A~1): sweep the tests that patch `os.stat`,
  `os.scandir` or `subprocess.Popen` for the whole process and make each fake act only on the test's own
  thread, the pattern behind both Windows flakes fixed in `3bafef1` and `eccb23c`.
- **A46.2 A runtime check for a nameless `QApplication`** (Quick Fixes 9's A~6, optional; after the Plotly worker
  deaths, `b0eb914`): a conftest check that fails a test whose worker's `QApplication` was made with an empty
  argument list (`QCoreApplication.arguments()` empty at the first `qapp`), for code `tests/test_qt_application.py`'s
  AST guard can't see. The guard covers the code today.

Done without IDs (2026-11-03): Quick Fixes 9's A~4, `--session-timeout` in CI (`457debc`), and A~5, every test job's
junit.xml kept (`5324a7f`).

## Caching v2 checkpoint 3 (block 44)

From the Caching v2 floor's [handoff](sessions/2026-10-31-claude-caching-v2/handoff.md) (Vault; checkpoint 3
landed `c2d0ece`, stage 1 complete, the switch off). A42.1 and A42.2 were done in stage 2 (`1cd586c`).

- [x] **A44.1 `helab cache export` of stage 2's TXY layers** (done in `a70d261`: `--kind txy [--layer]`) (`kind` `txy`): the same CLI, the layer's columns.
  With stage 2.
- [x] **A44.2 A Qt-free `helab cache`** (done in `a70d261`: `cache-folder.json` in the app folder, written by the GUI only, CoCo's option (b)): `helab cache export --folder` without `--cache` imports
  `helab.utils.constants` (QtCore) for `cache_dir()`; a Qt-free reader of the cache-folder setting would
  make all of `helab cache` Qt-free. Minor: no widgets and no GUI start either way.

## Caching v2 stage 2 (block 47)

From the Caching v2 floor's [handoff](sessions/2026-10-31-claude-caching-v2/handoff.md) ("Step 7", Vault;
stage 2 landed `1cd586c`, the switch off). The typing and accessible-names timeouts it proposed (A~10) were
done by Quick Fixes 9 (`e8a28a1`, `5f52068`).

- [x] **A47.1 Conversion from the raw layer for user profiles** (done in `912f928`, stage 3a, landed `d4f28f3`: `with_txy` sends the conversion profile whole, `profile_def`; a plot's own pick of another user profile still reads its text) (A~7): a load converts a HeLab shot from the raw
  layer (the loading order's second step, `6f57918`) only for built-in profiles, since the helper has no user
  profile library; other profiles read their text. Send the profile (or the library) with the request.
- [x] **A47.2 `FolderCache` learns a folder's choices with its listing** (done in `28d2112`, landed `1d91897`; A47-1's fix `65f98d0`: a root's change of identity drops its folders' choices) (A~8; Q47.2): `folder_choices` beside
  `folder_prefs` in `io_ops/metadata.py`, so Live and the first load follow a folder's own TXY source at once,
  not the global one until a load tells it. Before the switch goes on (Q47.2, Tony 2026-11-02): stage 3, the
  Caching v2 floor.
- [x] **A47.3 The GUI watchdog left running by quit tests** (done in `36b2224`, Quick Fixes 9: `_watch` ends once its QObject is deleted; `tests/test_gui_watchdog.py`) (A~9; known-issues): `HelabMainWindow.closeEvent`
  returns early, without stopping its `GUIWatchdog`, when a close waits for saves (`QuitSaveDialog`) or a quit
  dialog is open. Finish or cancel the dialog in `tests/test_quit_confirms.py` and
  `tests/test_txy_last_used_quit.py`, or stop the watchdog when the window is destroyed.
- [x] **A47.4 Purge by age per kind, plus everything** (done in `5cbf1d4`, landed `1d91897`: `purge_cached(cutoff, kinds)`, the helper's `purge` `what`, Settings › Cache's rows and "Everything not used…") (Q47.1, Tony 2026-11-02; the Caching v2 floor, Vault):
  Settings › Cache's store-v4 purge by age split per kind (datasets, TXY layers and their views, raw layers),
  each with its estimate and question, plus one "purge everything by age" button; only copies never go unless
  the question names them. Until then the purge takes all three and keeps only copies (S3-1).
- [x] **A47.5 Save a plot's TXY source and profile** (done in `63817b5`, review fixes `a18e4c9`, Live Scripts, landed `971f4af`: `TxyChoice` in records and script presets, the TXY row's Keep box) (Q14.2 = Q23.4, Tony 2026-11-02; the Live Scripts floor):
  with presets, arrangements and reopened plots (a format change in `analysis/presets.py`; today a reopened
  plot starts "As the folder's tab"), plus a plot-settings toggle that turns the saving off, for tweaking and
  exploring.
- [x] **A47.6 Convert from the raw layer with the app's backend** (done in `9e8c576`, landed `1d91897`: `with_txy` adds Settings' `backend`; `txy_cache.backend_for`, numpy when it can't run here or for numba) (block 47's docs pass; the Caching v2 floor,
  Vault): `txy_cache.py:215` calls `reconstruct(raw_layer.decode(layer), profile)` without a backend, so it
  runs `reconstruct.DEFAULT_BACKEND`, `reference` (readable, not fast), not `pipeline.APP_BACKEND` (numpy) or
  Settings' `convert_backend`. Pass the app's choice; the output is byte-identical by contract.

## Converter UX (block 48)

From the Converter UX floor's [handoff](sessions/2026-11-02-claude-converter-ux/handoff.md) (Ember; Strata's
[review](sessions/2026-11-02-claude-converter-ux/review.md); landed `ed7bcf9`). A37.1, A39.5 and Q38.1's build
are done.

- **A48.1 Live's test loads without `txy`**: `tests/test_live.py`'s `run_helper` passes a load no `txy` (nor
  `memory_origins`), so its loads never find HeLab's TXY. Give it the fields `io_helper` passes (as
  `test_live_convert.check` does for Live checks) and drop `test_explorer_convert.load_as_the_helper_does`.
- **A48.2 The converter's questions in the accessible-names walk**: add `convert_offer`, `live_share`,
  `beside_refused` and `share_beside_confirm` to `test_accessible_names.ASKS` or `INLINE_SKIPPED` (their IDs
  are checked in `test_explorer_convert.py` only).
- **A48.3 Keep a read stopped early**: the stop is kept only in Live's session and the logs. Record it in the
  provenance row (a column within schema 1), so Folder details can name it for a folder loaded later; the
  same row could tell `ExplorerConverter.offered` that HeLab's TXY already exist in the cache or temp folder
  for a folder not loaded (Strata's info note).
- **A48.4 The output setting's tooltip**: Settings › TXY converter's output tooltip (`ConverterTab.py`) could
  say that a folder on a share asks before writing beside.

## Live Scripts (block 49)

From the Live Scripts floor's [handoff](sessions/2026-11-02-claude-live-scripts/handoff.md) (Lumen; design
[note](sessions/2026-11-02-claude-live-scripts/design.md); Prismo's [review](sessions/2026-11-02-claude-live-scripts/review.md);
landed `971f4af`). A47.5 is done.

- **A49.1 A TXY choice in the Presets row's changes**: the row's dots and "Save N changes" don't count a TXY
  choice changed from the applied preset.
- **A49.2 Same-named helpers in two script folders** share the first one imported (Python's one module
  namespace): detect it and name it in the Scripts panel's error list.
- **A49.3 The presets inspector and TXY profiles**: `PresetsInspector` calls `check_plot` without `profiles`,
  so it doesn't name a preset's unknown TXY profile; pass `{name: file_tag(p)}` from
  `txy_source.known_profiles()`.
- **A49.4 The reopen setting's description**: `reopen_plots_at_start`'s row could name the TXY rule ("a plot
  with its own TXY choice loads it only once HeLab read its folder this session").
- **A49.5 The loading marker's two loose ends** (Prismo's optional notes, re-check 2): test `deliberate=False`
  end to end through `_check_changes` (today only by calling `reload_scripts(…, deliberate=False)`), and reset
  `_pending_deliberate` in `_stop_waiting` when nothing is pending, so a removed folder's waiting deliberate
  reload doesn't make the next auto-reload clear a marker. Both harmless today.

## Caching v2 A47 checkpoint and stage 3 (block 50)

From the Caching v2 floor's [handoff](sessions/2026-10-31-claude-caching-v2/handoff.md) ("Stages 3 and 4",
Vault; Assay's [A47 review](sessions/2026-10-31-claude-caching-v2/review-a47.md) and
[stage 3 review](sessions/2026-10-31-claude-caching-v2/review-s3.md); landed `1d91897` and `d4f28f3`, the switch
off). Done: A40.2, A47.1, A47.2, A47.4, A47.6 (above); A47-1 fixed on the floor. No new item; Tony's answers are
Q50.3–Q50.18, the open ones Q50.1 and Q50.2.

## Caching v2 stage 4 and the switch-on (block 51)

From the Caching v2 floor's [handoff](sessions/2026-10-31-claude-caching-v2/handoff.md) ("Stage 4" on, Vault;
Assay's [review](sessions/2026-10-31-claude-caching-v2/review-s4.md); landed `8071c04` and `9f92daf`, the switch
off). No new item: stage 4, the switch-on run's fixes and Q50.1's option (a) are done; Q51.1 (a) decided by Tony (2026-11-03); the
switch-on (V-2, V-3, V-5) waits on `agent/v4-switch-on` for the v0.0.8 PR.

## Live Scripts' follow-ups (block 52)

From the follow-up sessions on the Live Scripts floor (Lumen; Prismo's reviews): the reload-wait race (the Live
Scripts [handoff](sessions/2026-11-02-claude-live-scripts/handoff.md), landed `f534ede`), the
[plot crash](sessions/2026-11-03-claude-plot-library-crash/handoff.md) (landed `823589a`) and the
[preset hang](sessions/2026-11-03-claude-preset-modal-hang/handoff.md) (landed `566eed6`). All test-side.

- **A52.1 Test-made Scripts panels get a Qt parent** (the plot crash's A~2, Prismo's
  [assessment](sessions/2026-11-03-claude-plot-library-crash/review-crash.md)): about 45 test sites make
  `TreePanelWidget(...)` without one (17 in `test_analysis_gui`, 16 in `test_live_scripts`, 4 in
  `test_constant_layers`, the rest in 6 files); give them `TreePanelWidget(window.plots, window)`, the `plot()`
  helpers that drop the panel first. None crashes under forced collections today ([testing](architecture/testing.md)'s
  rule).
- **A52.2 The plot crash's two optional notes** (Prismo's N1, N2): say in the guard test's docstring and at
  `workspace.py`'s two `setParent(None)` sites that the replaced widget is Python's until the `deleteLater()`
  right after hands it back to Qt, and optionally guard `replace_plot_content` too (the RAM budget's release
  picture); make `test_a_dropped_scripts_panel_survives_a_collection_in_its_first_polish` assert its inner run's
  "3 passed", not only exit 0.
- **A52.3 A shared "wait for owed writes, then restart" test helper** (the preset hang's A~1, Prismo's N3):
  other tests that simulate a restart (shut the helpers down) should wait for owed preset writes as
  `test_presets_plots.stored()` now does. Its private reads (`_presets_again`, `_probe_owner`) could later become a
  public `FolderCache.presets_idle()` (an app change).
- **A52.4 Guard the presets' other modals** (the preset hang's A~2): `presets.ask_name` (`QInputDialog`),
  `presets.replace_or_add` and `presets.confirm` (`QMessageBox`, `exec`) open real dialogs unless a test stubs them
  (per instance today, `presets_for`). Make them fail in conftest as `warning_box` does, after checking every test
  that reaches them stubs them; or, broader, a conftest guard on `QMessageBox.exec` / `QDialog.exec` that fails
  unless a test allows it.

## Documentation (block 54; Q54.1, Tony 2026-11-03, before the v0.0.8 PR)

- [x] **A54.1 Docstrings for the script-facing API.** (done in `4c47227`, review fixes `9631294`, `results.py` in `aafcb9d`, Docs floor, landed `b0e3aac`) Every public name in `helab/scripts/base.py`,
  `helab/analysis/dataset_view.py` (the `DatasetView` class itself, `name`, `short`, `key`, `shot_numbers`,
  `event_count`, `ViewIdentity`, `Provenance`), `parameters.py`, `selection.py` and the fit helpers scripts use
  gets a docstring, with Google-style `Args:`/`Returns:` where they add something the types don't. A check keeps
  it: ruff's pydocstyle rules (`D1`) on those modules only, in CI. Counts on 2026-11-03: `base.py` 35/37,
  `DatasetView`'s module 21/30; all of `helab/` 60 % of public functions. These docstrings feed PyCharm's Quick
  Documentation and the manual's API reference (A54.2).
- [x] **A54.2 The user manual's frame.** (done in `9507d02`, `3462828`, `662a287`, review fixes `d0128ae`, `17239e0`, `ee6df99`, `ec9defd`, Docs floor, landed `b0e3aac`; the deploy on a published release only, DM-1 (a)) MkDocs with the Material theme in `docs/` (beside `hlb-format.md`),
  Diátaxis sections (getting started, how-to, reference, explanations), an API reference for script writers built
  by mkdocstrings from A54.1's docstrings, a CI job that builds it with warnings as errors, and Help › User
  manual. First pages: install and first folder, `.helab-root`, Live, converting TXY, writing a script, the cache,
  `helab convert` / `helab cache`, the settings. Written for users from `.ai/architecture/` and the memory
  notes; names no person or lab machine. Published on GitHub Pages per release (Q54.2), bundled in the app as an offline copy (Q54.3); the deploy workflow publishes from whichever repo it runs in, so `HeBECANU/HeLab` gets its own site; Help opens the site of the repo the build came from, else the bundled copy (Q54.4).

## TXY priority lists (block 55)

From the TXY Priority floor's [handoff](sessions/2026-11-03-claude-txy-priority/handoff.md) (design
[note](sessions/2026-11-03-claude-txy-priority/design.md); [review](sessions/2026-11-03-claude-txy-priority/review.md),
TP-1–TP-11 fixed on the floor; landed `9bf99ff`).

- **A55.1 A widget test of Live's offer**: the Live line's "not read here: convert with m23v1?" and the menu's
  "Convert with m23v1 (this folder reads m23v1 only)" have only FolderCache-level tests
  (`test_a_one_entry_folder_offers_its_profile_to_auto_convert`); add one in `test_live_convert.py`'s style.
- **A55.2 Retire the old composition**: `txy_sources.choose`, `helab_txy.compose` and `could_take` are kept for
  their tests and for MATLAB only (`compose(source, matlab, {})`); they can go once their tests move to
  `compose_list`.
- **A55.3 Time the any-HeLab stage**: the fallback's last stage reads provenance records of every tag in HeLab's
  folders for the shots no earlier stage has, so a large folder converted with several profiles reads more rows
  than before. Time it on a lab folder with M55.4.
- **A55.4 A manual convert beside Live's**: Convert this folder… is disabled while Live's Auto-convert converts
  that folder (TP-5). A manual convert with another profile could queue after Live's conversion instead; that
  needs FolderCache's convert jobs keyed by profile.

## Documentation follow-ups (block 56)

From the Docs floor's [handoff](sessions/2026-11-03-claude-docs-manual/handoff.md) (reviews D-1–D-3 and DM-1–DM-4
fixed on the floor; landed `b0e3aac`). Each runs on a floor or Ground; the manual's pages are public text, naming no
person, lab machine or internal ID.

- [x] **A56.1 `results.py`'s docstrings and its API page** (done in `aafcb9d`, Docs floor, landed `b0e3aac`).
- **A56.2 `dataset_view.py`'s module docstring, public-safe**: it names Q6.6, plots-1 and plots-3, and
  `root_key`'s docstring names a person and a review finding. Then `docs/reference/api/dataset-view.md` may render
  the module instead of naming its classes one by one.
- **A56.3 `docs/.ai-generated/`**: three old planning files in the public `docs/` folder (MkDocs skips dot-folders,
  so the site doesn't show them). Move them to `.ai/sessions/` or delete them.
- **A56.4 The built-in profiles' notes** shown in Settings › TXY converter carry internal IDs ("stage 3", "Q6.11"):
  make them user-facing text.
- **A56.5 Stale docs found while writing the manual**: `data-roots.md`, `cache-store.md` and `live.md` were
  corrected in the landing's docs pass; left: the comment above `STORE_V4_SETTING` in
  `helab/utils/settings_defaults.py` still says "off until stage 2", while its row is on from v0.0.8.
- **A56.6 Grow `ruff.toml`'s scope** to the rest of what scripts import (`follow.py`, `backends.py`'s panes,
  `stats.py`), each with an API page.
- **A56.7 `helab --help` starts the GUI**: `helab/main.py` handles `--version`, `convert` and `cache` before the
  GUI, but not `--help`/`-h`. Print a short usage (the app, `--version`, `--geometry`, `convert`, `cache`, each
  with `--help`) and exit 0, before anything starts.
- **A56.8 The manual's "Which TXY HeLab reads" section** (now a short note): the ordered TXY list (Settings › TXY
  converter › Edit…, a folder's and a plot's own lists, the fallback shots and how a plot's record names them),
  and the External label.

## Test isolation follow-ups (block 57; [handoff](sessions/2026-11-03-claude-fixed-mount-seam/handoff.md))

- [ ] **A57.1 CachedRuns' verification timer outlives a closed plot.** In 41587336570's leaked plots,
  `CachedRuns._verification_due` reached `AnalysisInstance._cached_status` on a deleted QLabel (a plot closed
  while its save waited for the volume check), and `AnalysisInstance.close` raised `'AnalysisRunner' object has
  no attribute 'results'` after its test's runner was released. Both are logged and HeLab goes on. Fix: stop
  `_verify_timer` and drop the plot's callbacks when it closes (or check `sip.isdeleted`), and let `close` skip a
  runner that is gone; a test for each.
- [ ] **A57.2 Windows tests with `--basetemp` on another drive than TEMP's.** conftest's
  `HELAB_TEST_LOCAL_MOUNT` lists only TEMP's drive, so a `--basetemp=.ai/temp/pytest-<name>` on `D:` has no mount
  in the tests' list. Check whether those tests then run as on CI; if not, let it list several drives.
- [ ] **A57.3 An inherited `HELAB_TEST_FIXED_MOUNT`** (Sieve's FM-4, Info): conftest appends to a value set in
  the shell or by a parent process, so that mount stays trusted for the run. Clear it at import before naming
  the temp folder's mount.

## Not AI work (stays in MANUAL_TODO)

These need a real share, lab hardware or a person in the lab:
- remounts, and two mounts of one folder;
- read-only shares, and mapped-drive spellings on Windows;
- the converter and the lab's MATLAB scripts ignoring `.helab-root`;
- the physics checks on real data: temperatures, condensate fits, g², release time, the QE
  calibration;
- release recovery in a disposable release;
- the self-update questions for ANU IT.
