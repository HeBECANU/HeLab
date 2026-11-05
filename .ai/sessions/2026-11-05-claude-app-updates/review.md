# Review: app updates (`agent/app-updates`)

Reviewer (Sentry), 2026-11-05. Diff `127b1e8..43d22f4` (no merges of dev/v0.0.9 in the range), read against
the brief, design.md (with CoCo's answers), handoff.md, `roadmaps/app-updates.md` (Q65.1–Q65.3) and AGENTS.md.
Tony's decisions Q~1–Q~6 and Q~8 (as proposed) taken as settled.

## Checks rerun

- Full suite, `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-sentry` (after
  `source .ai/local/floor-env.sh`), on `43d22f4`: **9551 passed, 673 skipped, 2 warnings in 226.93 s, no RERUN**
  (output whole in `.ai/temp/review-suite.txt`).
- The five type checks, all clean (`.ai/temp/review-types.txt`): `mypy helab/ --strict` (223 files),
  `mypy tests --strict` (219), `pyright helab tests` (0 errors), `mypy helab/ --strict --platform win32` (223),
  `pyright --pythonplatform Windows helab tests` (0 errors).
- Reproduced in the scratchpad (nothing committed, nothing run against this checkout or its remotes):
  - `updater.running_from` against a real venv made from uv's base Python, with a process
    `<venv>/bin/python -c … -m helab.io_helper`: seen with a path without spaces, **not seen** with a space in the
    path (AU-3). With a Homebrew framework Python the venv's process isn't seen either (it re-execs as
    `Python.app`, so `ps` names the framework).
  - `git diff --name-only --diff-filter=A` misses a file the target renames into place; `git merge --ff-only`
    then fails with "untracked working tree files would be overwritten" (AU-9).
  - Three read-only GETs to `api.github.com` (`gh api`) to size AU-2 against the real history: GitHub's compare of
    `5af4a89^1...5af4a89` (the Activity window's landing) lists 34 commits, 33 of them the floor's; the floor's
    `de54fee`, `a2f040f` and `6f1b4f4` are **green** by `github.ci_state` on their own runs; `c0860ec`
    (dev before the landing) is an ancestor of `de54fee`. A compare of 1006 commits returns the newest 250, the
    tip last (so the 250 cap doesn't lose the tip).

## Summary

No blocker. The core safety holds as built and tested: the updater is a standard-library copy run by the base
Python outside the checkout; it opens a pid-reuse-safe handle before `ready`, waits for HeLab's exit, the locks and
the processes before touching a file, re-checks every refusal after HeLab quit, fast-forwards only (`merge
--ff-only`, ancestry checked both ways, target pinned to what the check saw), checks the release tag's commit is on
the fetched `main` and refuses a moved tag, builds the venv beside the old one only when the lock or `setup.py`
changed, keeps a symlinked venv a symlink, and rolls back code and venv on a failed build or a new version that
exits. The check sends only GETs to `https://api.github.com` (host checked in the transport, refused under the test
guard), `User-Agent: HeLab/<version>`, no cookies, ETags; the GUI never waits on it, the dry run or the updater.
Tests use temporary repos with a bare remote, `insteadOf`, an empty global config and `GIT_ALLOW_PROTOCOL=file`, and
the updater's own guard refuses any folder outside the test's root. UI controls have IDs and accessible names.

Two Major findings: the outcome of an update is never shown on the restart it concerns (AU-1), and branch mode's
candidates include commits merged in from other branches, so a lab PC's branch can be fast-forwarded onto a floor's
commit while the landing merge's CI runs (AU-2). The rest are Minor (gaps in the "nothing running" wait and the
error paths, Windows behaviour to watch in M~1) and Info.

Counts: **0 Blocker, 2 Major, 7 Minor, 3 Info.**

## Findings

### AU-1 · Major · `helab/main.py:263-264`, `helab/updates/updater.py:846-858`

**The outcome of an update never shows on the restart after it.** `main()` schedules `mark_started` with
`QTimer.singleShot(0, …)` and then calls `main_window.show_last_update()` synchronously, before the mark exists.
The updater writes `last.json` ("updated", "restored", "unconfirmed") only after it sees the mark
(`wait_started`, then `record`). So the relaunched HeLab reads the previous `last.json` (already shown, or absent)
and shows nothing; the new outcome is shown at the *next* start, possibly days later, or on the restart of the next
update. Only "refused", "failed" and "rolled back" (recorded before the relaunch) show at the right time.
`test_the_last_outcome_shows_at_start` writes `last.json` before calling `show_last_update`, so it doesn't see the
order.

*Scenario:* Update and restart on Tony's Mac: HeLab comes back on the new commit with no "HeLab was updated to …"
notice (M~1 expects one); a week later an ordinary start says "HeLab was updated to 4F02AA".

*Fix:* when started with `HELAB_UPDATE_TOKEN`, keep the token after writing the mark and poll (a `QTimer`, ~10 s,
no wait) for a `last.json` whose `token` matches, then show it; without a token, show as now. A test that runs the
real order (mark, then the updater's record, then the notice).

### AU-2 · Major · `helab/updates/github.py:291-303`, `helab/updates/versions.py:179`

**Branch mode can move the branch onto a commit that was never the branch's.** The candidates are every commit of
GitHub's `compare/{running}...{branch}` reversed, which includes all commits merged in from other branches, not the
branch's own (first-parent) commits. Floors push their branches with CI on every OS (`dev-cicd.yml` runs on all
branches), so their commits are often green.

*Scenario (real history):* a lab PC on `dev/v0.0.9` at `c0860ec`. The Coordinator lands the Activity window floor
(`5af4a89`, 34 commits ahead); its CI runs for ~20 minutes. A check in that time finds `5af4a89` pending, then
`de54fee` (the floor's tip) green, and offers "dev/v0.0.9 +33"; Update and restart fast-forwards the lab's
`dev/v0.0.9` to `agent/activity-window`'s tip. Here that tree happens to be close to the landing, but a landing
merge that resolves conflicts, or a floor whose older checkpoint commit is the newest green one checked, puts the
lab on a state `dev/v0.0.9` never had. Also, the "+N" label counts all compare commits (up to 250 listed, so a PC
1006 commits behind shows "+250").

*Fix:* keep `parents` in `trim_compare`, walk the first-parent chain from the tip (the compare's last commit) back to
the running commit, and take candidates only from it (count "+N" along it, or use `ahead_by` for the label). In the
updater, refuse a target not on `git rev-list --first-parent <fetched tip>`. A test with a merged side branch whose
tip is green and whose merge is pending.

### AU-3 · Minor · `helab/updates/updater.py:341` (and `tests/test_updates_updater.py:402-431`)

**The "no process from the venv" wait is blind when the path has a space.** On macOS and Linux `running_from` takes
the program as `command.split(" ", 1)[0]`, so for `/Users/x/My Projects/HeLab/venv/bin/python -m helab.io_helper`
the program is `/Users/x/My` and the source helper isn't seen (reproduced). A venv made from a Python that re-execs
(Homebrew's framework build) is never seen either. The test's stand-in helper carries `--helab-io-helper` in its
arguments, which matches by substring, so the source helper's real command line (`-m helab.io_helper`) isn't tested.
Mitigated today by `IOService.shutdown` killing helpers and by the lock waits, so this is the backstop that fails.

*Scenario:* a checkout under a folder with a space; a helper killed at quit is still exiting (or a stray
`venv/bin/python -m helab…` runs) when the updater checks; it merges and swaps the venv under it.

*Fix:* match `command.startswith(folder + os.sep)` for each venv/checkout folder instead of splitting, keep the
checkout path anywhere in the command as a second signal, and make the test's helper `[venv python, "-m",
"helab.io_helper"]`-shaped (a stub module in the temp checkout) in a folder whose name has a space.

### AU-4 · Minor · `helab/updates/updater.py:847-850`

**Rolling back after "exited" doesn't wait for the new version's processes.** When the new HeLab exits before its
mark, the updater moves the code back and swaps the venv at once. Helpers don't watch for their parent's death, and
a HeLab that crashes (rather than quitting) never kills them; a cache-move recovery helper started at startup also
holds `move.lock`. Narrow, but it is a code change while a helper may run.

*Fix:* before `rollback`, run the same wait as before the update (`helab_locks(app_dir, None)` and `running_from`,
up to `others`); if still busy, record "rolled back after …" only once they are gone, or leave the new version and
record why.

### AU-5 · Minor · `helab/updates/updater.py:840`, `:887`, `:917-921`

**An unexpected exception after the code moved isn't rolled back.** The update's `try` catches only `Failed`,
`OSError` and `SubprocessError`. Anything else after `move_code` (a `UnicodeDecodeError` from `text=True` output in
Windows' locale code page, a `KeyError`, a `ValueError` from `json`) reaches `main()`'s catch-all, which records
"failed" and relaunches **the moved code** with the old (or half-swapped) venv and no `previous.json`, so Restore
isn't offered either.

*Fix:* catch `Exception` in the update's second `try` and in `rollback`, so every failure after step 1 rolls back;
give the `subprocess.run` calls `encoding="utf-8", errors="replace"`.

### AU-6 · Minor · `helab/updates/launch.py` / `helab/views/HelabMainWindow.py:989-1001`

**"A restored commit is skipped by the startup reminder" (design §7) isn't built.** After Restore previous version,
the next check offers again the commit (or release) just left, with the status-bar mark and the Help entry.

*Fix:* on a "restored" outcome, store the restored-from key (`last.json`'s `from`: the commit in branch mode, the
version in releases mode) as `updates_skipped`, so only something newer shows; a test.

### AU-7 · Minor (plausible, Windows) · `helab/updates/updater.py:393-414`

**The in-use check can refuse because of another program.** `_windows_locked_files` opens every `.pyd`/`.dll`/`.exe`
in the venv for writing. uv links packages from its cache with **hard links** by default on Windows, so a DLL of the
same package version mapped by any other process (another uv venv's Python, a second checkout's HeLab) makes this
venv's file "in use", and the updater refuses after two minutes ("HeLab's helpers are still running: …dll is in
use"). It also walks the whole venv every 0.5 s while waiting. Not reproduced (no Windows here).

*Fix:* the design's rename probe of the venv folder (`venv` → `venv.probe-<token>` and back), which is what the swap
needs and isn't fooled by another path's handle, beside the image-path check; or only treat a file as in use when
the rename probe also fails. Add to M~1: update a lab PC while another uv venv's Python with numpy runs.

### AU-8 · Minor (plausible, Windows) · `helab/updates/updater.py:421`, `build_venv`, `running_from`

**Console windows flash during an update on Windows.** The updater runs under `pythonw.exe` (no console); each
`subprocess.run` of `git`, `uv` and the check's `python.exe` then gets a new console window (about 20–30 of them).
Cosmetic, but M~1 watches for consoles.

*Fix:* on win32 pass `creationflags=subprocess.CREATE_NO_WINDOW` to every `subprocess.run` in the updater.

### AU-9 · Minor · `helab/updates/updater.py:561`

**The untracked-files refusal misses renames.** `git diff --name-only --diff-filter=A` follows renames by default,
so a file the target renames into a path that exists untracked isn't named (reproduced). The dry run says "ok",
HeLab quits, and `git merge --ff-only` fails ("untracked working tree files would be overwritten"); the update
rolls back and the old HeLab restarts, so nothing is lost, but the refusal should have come first.

*Fix:* `git diff --name-only --no-renames --diff-filter=A`; a test with a rename.

### AU-10 · Info · `helab/updates/check.py` (`QtTransport.get`)

Qt 6's default redirect policy follows redirects (no less safe scheme, any host). GitHub only redirects within
`api.github.com` (a renamed repo), but to hold "only api.github.com" by construction, set
`RedirectPolicyAttribute` to `SameOriginRedirectPolicy` (or manual) on each request.

### AU-11 · Info · `helab/updates/updater.py:797-811`, `:733-735`

Two refusal paths relaunch while the old HeLab may still run: the test guard is checked after `ready` is written,
and "HeLab didn't quit" after 30 minutes. The relaunched HeLab then finds `running.lock` held and says another HeLab
is running. Suggest: check the guard before writing `ready`, and don't relaunch when the old HeLab hasn't exited.

### AU-12 · Info · several

- Provisional IDs (`Q~1`, `Q~5`, `Q~6`, `Q~8`) in comments and docstrings of `helab/updates/*.py`: to rename to
  the merged block's IDs at landing.
- Design §6 said HeLab refuses a base Python inside the checkout or its venv, and the updater runs `git`/`uv
  --version`; built: presence only, and no base-Python check. Harmless with the README's setup; say so in the
  architecture file or add the checks.
- `helab.updates.settings` reads this checkout's `git config` (`build_info.upstream_repository`) under tests, read
  only (it decided the CI failure the handoff mentions). Fine for the rule; worth a line in `testing.md`.

## The handoff's proposed docs

The proposed architecture section, the AGENTS.md invariant line and the housekeeping bullet match what was built.
With AU-2 fixed, the CI rule's text should add "the branch's own (first-parent) commits"; with AU-7, the Windows wait
should name the rename probe.
