# Fixed-mount seam: landing review (Sieve, 2026-11-03)

Branch `agent/fixed-mount-seam` (Rivet), `git diff 413b2a0..ee4bbdf`: `helab/utils/data_roots.py`,
`tests/conftest.py`, `tests/test_root_discovery.py`. The commits after `ee4bbdf` (`c133e41`, `1c1e00b`)
touch only the handoff.

**Verdict: no blocker.** FM-1 and FM-2 are Low, FM-3 is Info. None of them needs to hold the landing.

## The four checks

1. **The seam acts only when `HELAB_TEST_FIXED_MOUNT` is set, and nothing in HeLab sets it.**
   - It is read only in `fixed_mount` (`data_roots.py:56`). `if test_mount and …` means an unset or
     empty variable does nothing.
   - `grep -rn HELAB_TEST_FIXED_MOUNT` over `helab/`, `tests/` and `.github/` finds only that read, the
     conftest line that sets it (`conftest.py:67`) and the new test.
   - `TEST_FIXED_MOUNT_ENV` names it but nothing else uses that name. The CI workflows don't set it.
2. **conftest's choice of mount on each OS.**
   - **macOS:** `realpath(gettempdir())` is `/private/var/folders/…/T`. The longest psutil mountpoint
     holding it is `/`, already trusted, so nothing changes. Checked on this Mac's mount table, where
     `/System/Volumes/Data` doesn't prefix `/private/…` (a firmlink).
   - **Linux, `/tmp` on `/`:** `/`, already trusted. **Linux, `/tmp` its own mount (tmpfs or a disk):**
     the mountpoint equals `realpath` (`temp == part.mountpoint`), so `/tmp` is named.
   - The value is a psutil mountpoint, and HeLab's `Mount.path` comes from the same psutil call
     (`cache_paths.current_mounts`), so the two strings compare equal.
   - `/`'s `rstrip(os.sep) + os.sep` is `/`, so the root mount matches as a prefix.
   - **Windows:** not set (`sys.platform != "win32"`); see FM-2 for the comment beside it.
   - conftest imports only psutil there, never helab, before its overrides (AGENTS.md's import rule
     holds). Helpers inherit the variable from `os.environ`.
3. **No test that needs an unverified volume is weakened.**
   - `test_result_cache_unverified` fakes the refusal at `cache.service.submit` (`REFUSED`). It never
     asks a mount, so the seam can't reach it.
   - `test_root_discovery`'s `usb_root` mounts its disk at `tmp_path/USB`: never the temp folder's
     mount, so `test_cached_read_waits_for_its_volume_to_be_verified` still raises `VolumeUnverified`.
   - `test_system_volume_hint_needs_no_verification`'s `/Volumes/USB` stays untrusted.
   - `test_helper_dispatch`'s `VolumeUnverified` case is a constructed exception.
   - The new test also checks that the case still holds with the variable unset, and that another mount
     is never trusted.
   - The fake `Mount("tmpfs", "/tmp", "tmpfs")` in `test_offline_browsing` (`:607`, `:690`): see FM-3.
4. **The new tests fail without the fix.** Checked on a copy of `ee4bbdf` with `413b2a0`'s
   `data_roots.py` and `conftest.py`:
   - `test_the_mount_the_tests_name_needs_no_verification_and_only_when_named` fails
     (`assert data_roots.fixed_mount(mount)`, `:335`).
   - `test_the_tests_folders_are_on_a_mount_that_needs_no_verification` passes on the normal `/tmp`,
     as the handoff says. It guards the own-mount layout. I put `TMPDIR` and
     `--basetemp` on a 2 GB sparse APFS image mounted in my scratch folder (since detached):
     - **old code:** it fails at `:348`, and `test_result_cache_plots::test_a_reopened_plot_shows_its_exact_saved_result_without_computing`
       times out at `:238`, as in CI;
     - **the fix:** both pass (2 passed).

## Findings

### FM-1 (Low): the seam names the temp folder's mount, not `--basetemp`'s

- **Where:** `tests/conftest.py:53-67`, and the docstring at `data_roots.py:51-53`.
- **What:** `_temp_mount()` names the mount holding `tempfile.gettempdir()`, and both docstrings say
  that is "where every test's folders are". But most tests' folders are `tmp_path`, under pytest's
  basetemp. With `--basetemp` on another mount, the seam doesn't cover them. This is the form the
  reviewer role uses, and AGENTS.md suggests it for concurrent Windows runs.
- **When it matters:** only when basetemp is on a mount that isn't a system volume (a checkout on
  `/mnt/…`, `/srv/…` or an external disk). The result-cache, lifecycle and offline tests then wait for
  a volume check, as on the old image. CI passes no `--basetemp`, and `/Users`, `/home` and `/` are
  trusted, so no CI or usual local run is affected. The new
  `test_the_tests_folders_are_on_a_mount_that_needs_no_verification` checks `tmp_path`'s mount, so it
  would fail loudly in that case rather than leave it unexplained.
- **Fix:** name basetemp's mount too, for example as an `os.pathsep`-separated list set in
  `pytest_configure` (it runs on each worker before any helper starts). Or say in both docstrings and
  in the testing.md text that `--basetemp` must sit on the temp folder's mount or a system volume.

### FM-2 (Low): the Windows comment overstates `HELAB_TEST_LOCAL_MOUNT`

- **Where:** `tests/conftest.py:58` ("Windows' HELAB_TEST_LOCAL_MOUNT above already stands in for its
  drives"), and the handoff's "isn't set on Windows, where `HELAB_TEST_LOCAL_MOUNT` already stands in".
- **What:** that variable replaces the mount list with the temp folder's drive (`cache_paths.py:41`).
  But `fixed_mount` on Windows trusts only `%SystemDrive%`. So a Windows machine whose `TEMP` is on
  `D:\` would wait for the volume check just as the old Ubuntu image did.
- **Why it's Low:** this gap predates the branch. GitHub's Windows runners keep `TEMP` on `C:` (the
  checkout is on `D:`, but CI passes no `--basetemp`), and the Windows jobs are green.
- **Fix:** set `HELAB_TEST_FIXED_MOUNT` to `Path(tempfile.gettempdir()).anchor` on Windows too. The
  seam runs before the `win32` branch, and `_normal` compares drives case-insensitively. Or reword the
  comment to say why Windows doesn't need it.

### FM-3 (Info): the seam reaches every `fixed_mount` caller, not only verification

- **What:** `fixed_mount` is also asked by `stores._mount_tops` (`stores.py:182`: no mount hint is
  recorded for a fixed mount) and `stores._transparent_mount` (`:225`: offline, a hint below a fixed
  mount survives).
- **Effect:** on a runner whose `/tmp` is its own mount, the temp mount therefore behaves exactly as `/`
  does on macOS, for all three callers. That is the intent ("as the system volume is"), and Rivet's
  own-mount full run passed.
- **One side effect:** on such a runner, `test_offline_browsing`'s fake `Mount("tmpfs", "/tmp",
  "tmpfs")` (`:607`, `:690`) is trusted through the seam before `TRANSPARENT_FILESYSTEMS` is asked.
  So that line no longer proves tmpfs is transparent there. `:690` still does, through
  `/run/user/1000`, and every other runner still checks `/tmp` itself.
- **Action:** none needed. The proposed testing.md line could say "trusted as the system volume is,
  wherever `fixed_mount` is asked".

## Checks I ran

All at `1c1e00b` (its code is `ee4bbdf`'s), with this floor's venv and `PYTHONPATH` set to the
branch's worktree (`helab.__file__` confirmed there).

- **Full suite:** `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-review`:
  **9231 passed, 673 skipped, no RERUN** (150 s). The summary has no rerun reasons.
- **Type checks, all clean:** `mypy helab/ --strict`, `mypy tests --strict`,
  `mypy helab/ --strict --platform win32`, `pyright helab tests` and
  `pyright --pythonplatform Windows helab tests`.
- **Old code against the new tests:** see check 4 above, on the normal `/tmp` and on its own mount.
- **FM-1 reproduced.** On the fix, with the normal `TMPDIR` and only `--basetemp` on the mounted image:
  - the guard test fails at `:348`;
  - the result-cache test times out at `:238`.
- **Not done:** I didn't read CI run 41604355924's logs myself (the handoff reports it green, with all
  15 job logs read and no RERUN). I didn't run the own-mount full suite either; Rivet reports
  9231 passed there.

## The handoff's proposals

- **known-issues entry:** accurate against the diff.
- **A~1 (CachedRuns' verification timer outliving a closed plot):** a fair separate item. It is not
  needed for this fix.
- **testing.md text:** fine. With FM-1, it should also mention `--basetemp`.


## Re-check of the fixes (ee4bbdf..21e614a)

Code: `21e614a`, the only commit that changes code. `helab/` and `tests/` are the same at `e629969`. Its
handoff commits after it (`f987747`, `e629969`) were read for A~2 and the testing.md proposal.

**Result: FM-1, FM-2 and FM-3 are closed. One new Info note (FM-4). No blocker, no open finding.**

- **FM-1 (Low): closed.**
  - `fixed_mount` takes several mounts, `os.pathsep`-separated. Empty items are skipped, and each item
    is compared through `_normal`, as before.
  - conftest's `name_fixed_mount` adds the mount holding the temp folder at import, and `--basetemp`'s
    in `pytest_configure`. It adds each mount once, appending.
  - **On xdist workers:** I checked `xdist/remote.py`. `setup_config` sets `config.option.basetemp` to
    the worker's `popen-gwN` folder before `pytest_cmdline_main`, so the worker's own `pytest_configure`
    sees it. Its helpers start later and inherit the variable.
  - **Old code:** with `ee4bbdf`'s `data_roots.py` under `21e614a`'s tests, the seam test fails at
    `:342` (the two-mount part). The other three pass, as expected: the naming test exercises conftest,
    not the seam.
  - **My repro of FM-1, now on the fix:** the normal `TMPDIR`, with `--basetemp` on a 2 GB sparse
    APFS image mounted in my scratch folder (since detached). I ran
    `tests/test_root_discovery.py tests/test_result_cache_plots.py` with `-n 2 --reruns 5
    --reruns-delay 1`: 50 passed, no RERUN. Before the fix, the same layout timed out at `:238`.
- **FM-2 (Low): closed.**
  - The wrong comment is gone. `mount_holding` gives the drive on Windows (`Path(real).anchor`, as
    `HELAB_TEST_LOCAL_MOUNT` names it), and the seam is now set there too. So a TEMP off
    `%SystemDrive%` is trusted.
  - For CI's Windows runners nothing changes: TEMP is on `C:`, which is already the system drive.
  - The docstring states what stays: a basetemp on another drive than TEMP's has no mount in the list.
    A~2 proposes that check, which is fair, and it predates this branch.
  - The naming test skips on Windows, fairly: its mount table is a POSIX fake. The seam and live-variable
    tests run there.
- **FM-3 (Info): closed.** The proposed testing.md text now says "wherever `fixed_mount` is asked", and
  it names the `test_offline_browsing` tmpfs side effect.

### FM-4 (Info, new): an inherited `HELAB_TEST_FIXED_MOUNT` is now kept

- **Where:** `tests/conftest.py`, `name_fixed_mount`, called at import.
- **What changed:** at `ee4bbdf`, conftest overwrote the variable on import (POSIX). Now it appends to
  whatever the process inherited. So a value exported in a developer's shell, or left by a parent
  process, stays trusted for the whole run.
- **Why it's Info:** it is still only a test seam, and nothing sets it outside conftest (I re-grepped
  `helab/`, `tests/` and `.github/`). CI's environment doesn't have it. xdist workers inheriting the
  controller's value is harmless, because they re-add the same mounts.
- **Fix if wanted:** clear it at conftest's import (`os.environ["HELAB_TEST_FIXED_MOUNT"] = ""`) before
  naming the temp folder's mount. Workers then rebuild it, and their basetemp is below the
  controller's.
- **Also noted, no action:** `os.pathsep` is `:` on POSIX, so a mountpoint whose name contains a colon
  would be split. That mount would then go untrusted, and a mount at one of the pieces' paths would be
  trusted instead. Temp and checkout mounts don't have such names.

### Checks

- **Full suite at `e629969`** (code `21e614a`): `pytest -n 4 --reruns 5 --reruns-delay 1
  --basetemp=.ai/temp/pytest-review` gave **9233 passed, 673 skipped, no RERUN**.
  - My image was mounted for a few seconds during this run (the FM-1 repro). No test failed.
- **Type checks:** `mypy helab/ --strict`, `mypy tests --strict`, `mypy helab/ --strict --platform win32`, `pyright helab tests` and `pyright --pythonplatform Windows helab tests` are all clean.
- **Not done:** I didn't read CI 41608759890's logs myself (the handoff reports all 15 green, no
  RERUN). I didn't run the full suite in the own-mount layouts either.
