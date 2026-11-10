# Handoff: fixes for the review of dev/v0.0.9 f844c0f..0de469b (`review/v0.0.9-0de469b`)

Worker (Claude, Mender), 2026-11-10. Base `a151050` (`0de469b` + the brief, review and known-issues entries).
Findings from `review.md`; one commit each, each with a test that fails before its fix. **Not pushed yet**: the full
suite, the five type checks and the one push come after Probe re-reads the fix diff (brief, steps 3 and 4).

| ID | Commit | Status | What changed |
|---|---|---|---|
| RV-1 | `9bbc62d` | fixed (value is Tony's: Q~1) | `histogram2d.MAX_PLANE_BINS = 16_000_000`; `plane_bins` scales both axes down in proportion; `Histogram2D.wanted` and `.capped` (the note); the plane's title, the bins' tooltip and the manual say so |
| RV-2 | `14ef3f7` | fixed | `image_filters.levels` gives the σ step directly (in place); the factor computed in place; `apply(…, check)` called before each step and each adaptive σ step; `plane_counts` passes the run's `check` |
| RV-3 | `0f19fdf` | fixed | `planes_layout` includes each colour group's side (`left_colour_bar`), so a side change draws the plot anew |
| RV-4 | `b446775` | fixed | `docs/how-to/basic-plots.md`: the colour bars (counts one bar right; rates XY left, XT/YT right, each over its own planes) and the rate units (events / mm² / shot, events / (mm·ms) / shot) |
| RV-5 | `633c6ed` | fixed | `_Terminal._run` passes console output through an incremental UTF-8 decoder; `_Terminal(fd, console=None)` (tests give a stand-in), `_console(fd)` |
| RV-6 | `f931243` | fixed | `_swap_handler_streams` lists loggers and handlers under `logging._lock` (at most `LOGGING_LOCK_SECONDS` 2 s, then without it), swaps after releasing it; docstring's reason corrected |
| RV-7 | `bfe4009` | fixed | `tests/test_quit_confirms.py`: `join(5)` → `join(30)` |

## Notes on the fixes

- **RV-1, a test that pinned the old behaviour.** `test_bins_are_capped` asserted
  `histogram2d(…, bins=(10_000, 20_000)).counts.shape == (10_000, 10_000)`. That is the plane the cap exists for,
  so it now asserts `(4_000, 4_000)` with `wanted == (10_000, 10_000)` and the note's text, plus `(10_000, 1_000)` for
  a plane under the cap (10,000 an axis kept). I asked CoCo first, but CoCo's terminal was at a Claude Code setup
  dialog (Tony's to answer), so no reply came; CoCo's brief asked for exactly this cap. **CoCo: veto here if
  not wanted.**
- **RV-1, the cap is per plane.** With bins set unequally (e.g. X 10,000, Y 2,000, T 10,000), XY becomes
  8,944 × 1,788, XT 4,000 × 4,000 and YT 1,788 × 8,944, so T has different bins in XT and YT (each plane's title
  says so). Before, "an axis shown in two planes has the same bins in both" held always. See Q~2.
- **RV-1, int32 counts or a float32 image: not done.** float32 would change the numbers users see (colour bar
  ticks, Plotly hover, the totals the filters keep to ~7 digits), and int32 counts save only 64 MB a plane at 4,000²
  while `counts` is typed int64 across the plot. Both left as they are.
- **RV-1 memory at the cap:** a plane at 16 M bins holds 128 MB of int64 counts plus 128 MB of float64 image (about
  0.77 GB held for three planes), against 4.8 GB before at 10,000².
- **RV-2:** `levels` rounds half to even (`np.rint`) where the old `argmin` took the lower step on an exact tie. On
  60,000 random factors and on the ladder itself they agree (test). Peak memory of `apply` with the adaptive KDE is
  now about 8 images (scipy's `gaussian_filter` alone peaks at about 4), down from about 20 (tracemalloc, 600²; the
  test's bound is 12). scipy's filters themselves can't be interrupted: a cancel waits for the current Gaussian.
- **RV-5:** the old loop was also run, outside the suite, with the same stand-in console: it garbled 8 of the 16
  split points of "σ → · é 𝛼" (every split inside a character). The suite's tests fail before the fix only
  because the old `_Terminal` takes no console argument. Not run on a real Windows console (M~2).
- **RV-6:** cheap and safe. The lock is logging's own RLock (`logging._lock`, 3.11–3.14; typeshed doesn't declare
  it, so `getattr`), held only while two lists are built, never while a stream is flushed. The timeout is there so
  a thread stuck holding it can't hang the exit. Note that `threading.RLock` is a function at run time, so the
  `cast` takes the type as a string (unquoted, it would raise at run time on every Python).

## Questions for Tony

- **Q~1 (RV-1): how many bins may one 2D-histogram plane hold?** Set bins stay at most 10,000 an axis. Over the
  plane's cap, both axes are scaled down in proportion and the plane's title says so. Changing it is a one-line
  change: `helab/analysis/histogram2d.py`'s `MAX_PLANE_BINS`, plus the manual's number in
  `docs/how-to/basic-plots.md`; a test checks that the two agree.
  - (a) **16,000,000 (4,000 × 4,000)**: 0.26 GB held a plane (0.77 GB for three), plus about 0.5 GB a plane for
    a moment on the GUI thread while it draws (the colour mapping's temporaries, about 4 images, as Probe measured).
  - (b) 25,000,000 (5,000 × 5,000): 0.4 GB a plane held (1.2 GB for three), 0.8 GB a plane while it draws.
  - (c) Another number (e.g. 9,000,000 = 3,000²: 0.14 GB a plane held, 0.3 GB while it draws).
  - Proposed: **(a)**. Automatic bins are at most 1,000 an axis, so with (a) or (b) the cap applies only when both
    axes' bins are set by hand.
- **Q~2 (RV-1): when the cap applies, keep it per plane or scale every plane alike?** Per plane (as built), each
  plane keeps as many bins as the cap allows, but an axis can then have different bins in two planes (T in XT and
  YT above). Alike (one factor for every plane shown), an axis stays binned alike everywhere, but the smaller
  planes lose bins they could keep (above: XY 4,000 × 800 instead of 8,944 × 1,788). Proposed: per plane, as
  built: each plane's title gives its bins and the note.

## For an agent later

- **A~1:** the 2D histograms' memory isn't counted against the RAM budget (now at most about 0.77 GB for three
  planes at the cap). If the RAM budget should cover analysis results, that is a separate design item.

## Checks on a real screen

- **M~1 (RV-1):** in the XY, XT, YT histograms, set X, Y and T bins to 10,000: each plane's title says "bins
  capped for memory: 10,000 × 10,000 is over 16,000,000 a plane, 4,000 × 4,000 used", and HeLab's memory stays
  under about 1.5 GB more than before the plot. With Show › rate per shot and only XY on, switching Show between
  counts and rate per shot moves XY's colour bar between the right and the left (RV-3).
- **M~2 (RV-5):** on a Windows PC, run HeLab from a console (PowerShell or cmd) and trigger a long log line with
  "σ", "→" or "·" (e.g. a blur note on the XY, XT, YT histograms at DEBUG): the console shows the characters, and
  the console keeps printing afterwards.

## Proposed doc changes (for the Coordinator)

- `.ai/architecture/plots-and-scripts.md`, Basic plots v2's 2D histograms: after "`histogram2d.MAX_BINS` 10,000
  set by hand (2026-11-09, Tony; …)" add "; a plane over `histogram2d.MAX_PLANE_BINS` (16,000,000, Q~1) has both
  axes' bins scaled down in proportion (`plane_bins`; `Histogram2D.wanted`, its note `capped` on the plane's title),
  so an axis can then have different bins in two planes". For the filters: "`apply` takes the run's `check`, called
  before each step and each of the adaptive KDE's σ steps; the σ step comes from `levels` (log-spaced ladder, one
  image's memory)". And: "`planes_layout` includes each colour group's side, so a change of side (XY alone,
  counts ↔ rate) draws anew".
- `.ai/architecture/app-runtime-and-ui.md`, the console tee: "a console terminal's output goes through an
  incremental UTF-8 decoder (`_Terminal._run`), so a character split across two pump reads is written whole;
  `_swap_handler_streams` lists the handlers under logging's lock (at most `LOGGING_LOCK_SECONDS`)".
- `roadmaps/known-issues.md`, the `test_the_watch_ends_a_process_left_running_with_its_exit_code` entry: "Fixed
  in `bfe4009` (`join(30)`), on `review/v0.0.9-0de469b`"; close it once that change has been through a few Windows
  CI runs without a rerun.

## Checks run here

Per fix: the new tests fail before the fix and pass after; `tests/test_basic_plots_v2_hist2d.py` (121),
`test_density_images`, `test_headless_imports`, `test_basic_plots_v2_v1_frozen`, `test_accessible_names`,
`tests/test_crash_file.py` (36), `tests/test_quit_confirms.py` pass under `-n 4 --reruns 5 --reruns-delay 1`, no
RERUN; `ruff check` and `mkdocs build --strict` pass; mypy --strict, --platform win32 and pyright (both platforms) on
the touched files. The five whole-tree type checks at `f931243`: `mypy helab/ --strict` and `--platform win32` no issues (238
files), `mypy tests --strict` no issues (231), `pyright helab tests` and `--pythonplatform Windows` 0 errors
(output `.ai/temp/worker-types.txt`, gitignored; kept whole in this folder at step 4). The full suite runs after
Probe's re-read (brief, step 4).
