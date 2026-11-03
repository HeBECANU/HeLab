# Handoff: v0.0.8 follow-ups (`agent/followups`): Q48.2, Q48.3, Q49.3 (b), Q56.3, Q56.1

Worker: Mend (Claude Opus 5.5). Brief: [brief.md](brief.md) (CoCo, `efb0d03`; base `6a0fb25`, `dev/v0.0.8`).
Design for Q49.3 (b): [design.md](design.md) (CoCo's ◆ answers below). Zensical check: [zensical.md](zensical.md).

## Commits

| Commit | What |
|---|---|
| `2da8d5a` | Q48.2: a raw read stopped early sends a system notification once per file (Live's auto-convert, `helab/views/explorer_live.py`, where the read-stopped line is handled; `events.READ_STOPPED_RAW`) |
| `c114e2c` | Q48.3: `helab convert --output beside-forced` replaces `--yes` (a hidden `--yes` is an argparse error naming it) |
| `59d274d` | Q49.3 (b): the try-import's design (◆) |
| `fdd895c` | Q49.3 (b): each script folder is test-imported in a separate process first (`helab/scripts/probe.py`, `script_tree.FolderProbes`, the frozen `--helab-script-probe` dispatch) |
| `53ec411` | Q56.3: the site's versions (`docs/publish/site_versions.py`, `no-stable.html`; `docs-site.yml` runs it) |
| `563bf40` | Q56.1: the Zensical check (◆; no switch: Tony chose (b)) |
| `c942613` | The bundled manual's search works offline: iframe-worker's shim vendored (`docs/js/`), `docs/publish/check_offline.py` in the Docs job |
| `2eac45a` | CI: `ci-build.yml` runs the packaged app's script probe on each OS |

**Paths beyond the brief's list, each approved by CoCo:** `tests/test_headless_imports.py` (`helab.scripts.probe`
in `PURE`, P5) and `.github/workflows/ci-build.yml` (the probe step only, 2026-11-03). Also touched, as "their
tests": `tests/test_live_scripts.py` (an autouse `no_probe`), `tests/test_script_system.py` (waits for the load),
`tests/test_docs_workflows.py`, `tests/test_user_manual.py`, `tests/test_live_convert.py`,
`tests/test_convert_helab.py`; new `tests/test_script_probe.py`. `HeLab.spec` untouched (the probe module and the
offscreen plugin are collected without it).

## Checks

Full suite (macOS, M4 Max), `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`:
**9275 passed, 673 skipped, 2 warnings in 160 s at `2eac45a`; no RERUN** (the warnings: pyqtgraph's NumPy
`arr.shape` DeprecationWarning, known). Earlier runs: 9262 at `c114e2c`, 9268 at `fdd895c`, 9272 at `53ec411`, all
without a RERUN. One run during step 3 had **5 RERUNs then FAILED** for
`tests/test_script_system.py::test_load_scripts_adds_a_working_group` ("rerun reasons": its group selector still
had 2 groups): not flaky, the test assumed Load Scripts… loads synchronously, which the probe made asynchronous;
fixed in `fdd895c` (it waits for the load).

Type checks at `2eac45a`: `mypy helab/ --strict` (207 files), `mypy tests --strict` (210), `mypy helab/ --strict
--platform win32`: no issues; `pyright helab tests` and `pyright --pythonplatform Windows helab tests`: 0 errors.
Docs: `mkdocs build --strict` and `ruff check` clean (in a scratch docs venv, `.ai/temp/docs-venv`).

CI **41622979011** (at `fdd895c`): **success**, every job. Each Tests, Converter backends and Build job's log
read: **one RERUN**, Ubuntu Converter backends (job in that run, `test_convert_helab.py::test_watch_converts_new_shots_and_stops_on_ctrl_c`,
"rerun reasons": `AssertionError: assert -2 == 0` from `wait(20)`: `helab convert --watch` killed by the SIGINT),
passed on rerun. That is the open known-issues item from CI 41561765280; this branch didn't touch the watch loop or
its signal handling (Q48.3 changed only argument parsing). Every other job: 0 RERUN (macOS 3,143 + 3,069 + 3,056
and 869; Ubuntu 3,142 + 3,067 + 3,056 and 869; Windows 3,135 + 3,052 + 3,045 and 867 passed). CI **41626693781**
(at `2eac45a`, the shim and the probe step): **success**, every job; each Tests, Converter backends, Build and
Docs job's log read: **0 RERUN** (macOS 3,144 + 3,072 + 3,059 and 869; Ubuntu 3,143 + 3,070 + 3,059 and 869;
Windows 3,136 + 3,055 + 3,048 and 867 passed). The probe step on each OS: `ready` with `application: offscreen`,
`done`, `frozen: True`, `gui: False`. The Docs job: "18 pages, every script a file of the site". This line's
commit is local only (a docs-only push would run CI again).

Frozen app (local PyInstaller build of `fdd895c` on macOS, `.ai/temp/dist`): `libqoffscreen.dylib` bundled;
`HeLab --helab-script-probe` answers `ready` (`application: offscreen`) and `done`, `sys.frozen` true, no GUI
module imported, a script making a `QLabel` at import works. The same check now runs in CI on all three OSes
(`2eac45a`).

## Q48.2: a read stopped early notifies

`LiveController._converted` calls `_notify_read_stopped` when `shot_converted` carries `read_stop`: title
"HeLab: raw file read stopped early", text `d3.txt in run: read stopped at line 1010, at "…", which isn't a number:
… (N bytes not read). Later shots go on.` (the stop's `detail()`), `desktop=True`, keyed
`(READ_STOPPED_RAW, folder, raw name, size, mtime_ns)` as the damaged notification is, so once per file per
session and again if the file changes. Data: `path`, `shot`, `line`. Only Live's auto-convert handles `read_stop`
in the app: Folder details' conversion (`explorer_convert.ExplorerConverter`, not owned) doesn't name a read stop
at all (A~2). Manual: `docs/how-to/live.md`.

## Q48.3: `--output beside-forced`

`BESIDE_FORCED = "beside-forced"` beside `CACHE_FORCED`. `--output beside-forced`: beside the raw files for this
run; on a share the share's warning is logged, then `Writing beside the raw files on the share anyway (--output
beside-forced)`, no question. `--output beside` on a share asks on a terminal; without one it converts to the
setting's output with `… (--output beside-forced writes beside without asking)`. `--yes` is kept as a hidden
`store_true` (`help=argparse.SUPPRESS`) only to fail: `--yes is gone: --output beside-forced writes beside the raw
files on a network share without asking` (exit 2). Manual: `docs/reference/command-line.md` (the option table and
the share paragraph, which mentions that older versions had `--yes`).

## Q49.3 (b): the try-import

As in [design.md](design.md), with CoCo's answers (P1 a constant; P2 Load Scripts… probes too; P3 an offscreen
QApplication, none without the plugin, said in the log; P4 a probe that can't start imports anyway, logged; P5 the
probe in `PURE`; and the tooltip says the folder was checked in a separate process):

- **`helab/scripts/probe.py`** (Qt-free at import): `main([FOLDER, RESPONSE])` makes an offscreen `QApplication`
  (`QT_QPA_PLATFORM=offscreen`, program name "HeLab script probe") when a `*qoffscreen*` plugin is found in Qt's
  plugin folders (a missing one would abort the process), else none; writes `{"kind": "ready", "application":
  …, "pid": …}`, runs `ScriptsManager().add_folder(folder)`, writes `{"kind": "done", "loaded": …, "seconds": …}`
  (each line fsynced), then `os._exit(0)`. `command(folder, response)`: `[sys.executable, "-P", "-m",
  "helab.scripts.probe", …]` from source (`-P`: no current folder on `sys.path`), `[sys.executable,
  "--helab-script-probe", …]` frozen.
- **`helab/main.py`**: the `--helab-script-probe` dispatch right after `--helab-io-helper`'s, before the `convert`
  dispatch and any GUI, cache or Dash import.
- **`script_tree.FolderProbes`** (`QObject`): one `QProcess` per folder (at most `PROBES_AT_ONCE = 2`), the
  package root on `PYTHONPATH`, stdout/stderr to files in a private `helab_probe_*` temp folder, stdin an open pipe
  never written (so `input()` at import waits and meets the limit). A 100 ms timer reads the response file only
  while probes run. `PROBE_SECONDS = 10` from `ready`; `PROBE_START_SECONDS = 60` to get ready. Killed on the
  limit; the answer comes on `finished` (exit confirmed), so a probe holds its folder until it has exited.
  `FailedToStart` answers "passed" with a warning. Failures: `its import didn't finish within 10 s`, `HeLab's
  test import didn't start within 60 s`, `its import stopped HeLab's test import (exit code N)`, `its import
  crashed HeLab's test import`; the stderr tail goes in the details. Each probe logs what it ran under
  (`QApplication: offscreen` or `none (…)`) and its outcome. `stop()` on `aboutToQuit` kills them, no wait.
- **The panel:** `restore_folders`, `_try_reload` (Reload, a folder's Reload, auto-reload) and `add_folder` (Load
  Scripts…, now through `reload_scripts`) go through `_probe_then`: one round at a time (`_probing`), the button
  "Reload (checking)" with the tooltip "Test-importing N script folders in a separate process first"; a reload
  asked meanwhile stays in `_pending` and gets its own round after. A failure at start joins `_skipped` (the start
  note; its tooltip adds `PROBED_NOTE`); later, `ScriptsManager.skip_folder` (new) lists the folder as
  `<folder>: didn't load: <reason>`, with `PROBED_NOTE` and the stderr tail in the tooltip and details, its
  scripts gone from the panel and its plots on their old code (`keep_script`), stamped so a save tests it again.
  Folders removed from the list while tested are dropped. Bundled analyses are never probed. `PROBING` (module
  flag) is the tests' seam.
- **The loading marker** stays as it was: the backstop for what the probe can't catch (a file changed between the
  test and the import, code that acts differently in the GUI process, a probe that couldn't start).
- **The double import**: `docs/how-to/write-a-script.md` says top-level code runs twice.
- Tests: `tests/test_script_probe.py` (the probe's answers with a raising, exiting and widget-making file and a
  missing folder; the frozen dispatch through `main.py`, no GUI module imported; a hang at start, its probe killed
  and reaped; a crash from Load Scripts…; `input()` on reload with a second reload queued, then fixed and adopted;
  a probe that can't start; the `ci-build.yml` step).

## Q56.3: the site's versions

`docs/publish/site_versions.py VERSION [--dry-run]` reads `mike list --json` and runs `plan(version, deployed)`:
`mike deploy --push --update-aliases VERSION [latest|pre-release]` (the alias when it is the newest stable, or the
newest PEP 440 pre-release; an older release published late moves no alias), then `mike set-default --push latest`
once a stable release exists, else `mike set-default --push --template docs/publish/no-stable.html pre-release`
(the "No stable release yet" page, light and dark, linking to the newest pre-release; "Help › User manual opens the
manual of the version you run"). `docs-site.yml` runs it (and skips, with its notice, a commit without it).
`mkdocs.yml` excludes `publish/`. `user_manual.py` unchanged: it already opens `<owner>.github.io/<repo>/<version>/`
(a test now says a pre-release opens its own page). README's User manual section: the site's versions, and no dev
channel ("build it locally with `mkdocs serve`"). Checked end to end with mike 2.2 against a local bare remote:
0.0.8a1, 0.0.8a2 (front page: no-stable), 0.0.8 (front page `latest/`), 0.0.7 (no alias moved), 0.0.9a1
(`pre-release` moves). No `gh-pages` exists yet, so nothing to migrate.

## Q56.1: Zensical, and the bundled manual's offline search

The check is [zensical.md](zensical.md). Tony chose **(b)** (CoCo, 2026-11-03): stay on Material for v0.0.8 with
the vendored shim; Zensical later (A~1). Found on the way, and fixed in `c942613`: **the bundled manual couldn't
search without a network** (Material's offline plugin loads the `file://` shim from unpkg.com; offline it stayed
at "Initializing search"). `docs/js/iframe-worker-shim.js` is iframe-worker 1.0.4's `shim/index.js` (byte for
byte from the pinned npm package, after a one-line header naming its source and licence; MIT, full text in
`docs/js/LICENSE-iframe-worker.txt`, which names its copyright holder as the licence requires); `extra.polyfills`
lists it. Over http it does nothing (it replaces `Worker` only under `file://`). Checked in Chrome from `file://`
with the network off: 6 documents for "converter". `docs/publish/check_offline.py SITE` fails on any page loading
a script from elsewhere (it failed the old build on every page); the Docs job builds the offline copy and runs it.
External stylesheets (Google Fonts) and the repo badge's GitHub API call stay: offline, the pages use system fonts
and no star count.

## Proposed doc changes (for CoCo)

- **AGENTS.md** (I/O and threads): "The frozen helper entry point in `helab/main.py` (after `freeze_support()`,
  before the `convert` dispatch)" → "The frozen helper entry points in `helab/main.py` (`--helab-io-helper`, then
  `--helab-script-probe`; after `freeze_support()`, before the `convert` dispatch)". Analysis and plots, one line:
  "A user script folder is test-imported in a separate process before each import (`helab.scripts.probe`,
  `script_tree.FolderProbes`, Q49.3 (b)); the real import stays on the GUI thread."
- **`.ai/architecture/plots-and-scripts.md`**, Live scripts: replace "imports stay on the GUI thread: Q49.3" with
  the try-import paragraph (the Q49.3 section above, shortened: probe, protocol, limits, rounds, skip, marker kept,
  `PROBING` seam).
- **`.ai/architecture/release-and-ci.md`**: the launch order line adds `--helab-script-probe` after
  `--helab-io-helper`; "The bundled manual" adds the vendored shim, `check_offline.py` in the Docs job, and the
  Build jobs' probe step; "The manual's site" replaces "with the alias `latest`, set as the default" by the
  Q56.3 plan (`site_versions.py`, `latest` newest stable, `pre-release`, the no-stable page, older releases move no
  alias) and the skip condition gains `docs/publish/site_versions.py`.
- **`.ai/architecture/converter.md`** line 545: "with a line naming `--yes`, which writes beside without asking"
  → "with a line naming `--output beside-forced`, which writes beside without asking and still logs the warning;
  `--yes` is an argparse error naming it (Q48.3)". The Live section: a read stopped early also notifies once per
  file (`READ_STOPPED_RAW`, Q48.2).
- **`.ai/architecture/testing.md`**: `script_tree.PROBING` (off in `test_live_scripts.py`, `no_probe`; on in
  `test_script_probe.py`, with `PROBE_SECONDS` 2 s); end-to-end panel tests wait for the asynchronous load.
- **`roadmaps/known-issues.md`**: the `test_watch_converts_new_shots_and_stops_on_ctrl_c` item gains CI
  41622979011 (Ubuntu Converter backends, `fdd895c`, `assert -2 == 0`, passed on rerun).
- **`.ai/DECISIONS_TODO.md`**: Q48.2, Q48.3, Q49.3 (b), Q56.3 built; Q56.1 decided (b) (A~1).

## Follow-ups (provisional IDs)

- **A~1 Zensical, later** (Tony, via CoCo, 2026-11-03: (b)). Move the manual to Zensical once its versioning is
  native or mike's Zensical fork is on PyPI, before Material's end of life (2027-05-05). The switch needs: (1) the
  version menu: native versioning, or the fork (`git+https://github.com/squidfunk/mike.git`, pinned by commit in
  `requirements-docs.lock`), first proven in a CI dry run; `docs/publish/site_versions.py` only calls `mike
  deploy/set-default/list`; (2) `docs/hooks/repo_links.py` doesn't run under Zensical: Zensical's built-in
  `macros` with `{{ config.repo_url }}` in the two pages that use `{repo_url}` (checked, a fork's URL right);
  (3) `zensical build` has no `-d`: `site_dir: !ENV [HELAB_DOCS_SITE_DIR, site]` and the variable in CI; keep
  `mkdocs.yml` (Zensical reads it; `!ENV` needs YAML); (4) `ci-build.yml`'s manual step (`mkdocs build --strict -d
  build/manual`), the Docs job and `docs-site.yml` move to `zensical build --strict`; (5) the shim: Zensical takes
  the same `extra.polyfills` entry (checked offline). Also: Zensical doesn't check pages missing from `nav`.
- **A~2** Folder details' conversion (`ExplorerConverter`) doesn't name a read stopped early nor notify; Live's
  auto-convert does. Route its `shot_converted` through the same stop handling.
- **A~3** The probe adds ~0.2–1 s per folder at start and on each reload (two at once). If a lab PC's cold frozen
  start makes it slow, reuse one probe process per round for several folders (needs a protocol change).
- **Q~1** The probe's wording: "Reload (checking)"; "didn't load: its import didn't finish within 10 s" / "…
  HeLab's test import didn't start within 60 s" / "… its import stopped HeLab's test import (exit code N)" /
  "… its import crashed HeLab's test import"; the note "HeLab first test-imports each script folder in a separate
  process, so a script that hangs or crashes at import can't stop HeLab." **Proposed:** as built.
- **Q~2** `PROBE_SECONDS` a constant (10 s, from the probe's start of the import) or a Settings › General row.
  **Proposed:** the constant until someone's import is legitimately slower.
- **Q~3** The `pre-release` alias stays on the newest pre-release even when a newer stable release exists (e.g.
  0.0.8a2 after 0.0.8). **Proposed:** keep (literal "newest alpha or beta"); alternative: drop the alias once a
  stable release is newer.
- **M~1** Windows lab PC: Load Scripts… of a folder, Reload, and a script with `input()` at import: the panel
  shows "Reload (checking)" then the skip line; no console window flashes; HeLab stays responsive.
- **M~2** Help › User manual with the network off on a packaged build: the bundled copy opens and its search finds
  results.
- **M~3** After the first published pre-release: the site's root shows "No stable release yet" linking to
  `pre-release/`, and the version menu lists it.
