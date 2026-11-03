# Fixed-mount seam: handoff (Rivet, 2026-11-03)

Branch `agent/fixed-mount-seam` from `origin/dev/v0.0.8` `413b2a0`; one fix commit, `ee4bbdf`. CoCo's go
after a read-only investigation of Ground CI 41587336570.

## Cause

On the runner image of both red runs, `/tmp` is a mount of its own, not part of `/`. The tests'
folders are under `/tmp`.

- **What HeLab does there.** `data_roots.fixed_mount()` trusts only the system volume (`/`,
  `/System/Volumes/Data`, `/home`; Windows' system drive). On any other mount, a local-lane cached
  read refuses a folder (`VolumeUnverified`) until this session's volume check has run
  (`verified_volumes`).
- **gw0's tests:** `test_result_cache_plots` gives each plot a fresh FolderCache of its own, which
  never runs that check. So every lookup and save waited for a `volumesVerified` that never came, and
  `saved()` timed out at `:238` on every rerun. The log shows "Read cached analysis failed: … The
  volume of /tmp/… is not yet verified" and "its volume wasn't verified within 120 s".
- **gw1's test:** `test_preset_folder_live::…[at_once]` goes offline before the window's startup
  check answers. The preset then says "can't be opened now (The volume of /tmp/…/run is not yet
  verified)", not "not listed while online".
- **Not an earlier test.** Each failing test fails alone (repro below). Reruns kept failing because
  each one meets the same mount table, not some state left behind.
- **Not store-v4 either:** one of the two red runs predates the switch-on.

The app is right to ask for the check: a disk swapped in at the same mount path could otherwise
inherit the old disk's volume hint, and its cached data. The tests assumed `/tmp` is on the
system volume. That holds on macOS, on Windows (`HELAB_TEST_LOCAL_MOUNT`) and on the newer
ubuntu-26.04 image, but not on the older one.

## Evidence

| CI run | Commit | Job | Image version | Result |
|---|---|---|---|---|
| 41587336570 | `a51176f` (after the `92f9d1a` switch-on) | Ubuntu Tests 3/3, 125755838908 | ubuntu-26.04 **20261018.50.1** | 4 failed, 3 errors, 30 reruns; the session timeout (720 s) ended it |
| 41570883747 | `b1a16d3` (**before** the switch-on) | Ubuntu Tests 1/3, 125703300662 | ubuntu-26.04 **20261018.50.1** | 7 failed, 3 errors, 53 reruns |

- **Image versions.** In the last 25 Ground runs, these are the only two Ubuntu jobs on image
  20261018.50.1. Every other Ubuntu job ran 20261025.179.1 and none failed these tests.
- **What failed, per run:**
  - 41587336570: `test_result_cache_plots` (gw0) and `test_preset_folder_live` (gw1).
  - 41570883747: `test_result_cache_plots`, `test_result_cache_badge` and `test_offline_browsing`.
  - In every case the log has "The volume of /tmp/… is not yet verified".
- **Worker orders.** These come from the job log; the junit has no worker field.
  - gw0: `test_typing`, `rga_visualiser`, `test_accessible_names`, … `test_convert_backend_cython`, `test_result_cache_badge`, `test_result_cache_keys`, `test_result_cache_plots` (32 files).
  - gw1: `test_typing`, the converter backends, … `test_plot_txy_saved`, `test_preset_folder_live` (24th of 41).
  - Neither failure depends on what ran before.
- **Repro, yes.** I put `TMPDIR` and `--basetemp` on a mounted macOS RAM disk, then on a sparse
  disk image (an 8 GB image, because 1 GiB filled).
  - `test_result_cache_plots::test_a_reopened_plot_shows_its_exact_saved_result_without_computing`
    alone times out at `:238` with CI's warning.
  - `test_preset_folder_live::test_offline_a_folder_never_listed_is_named_as_such[at_once]` alone
    gives CI's notice.
  - Control: on the normal temp folder, the same tests pass 3/3.
  - The full suite on Ground `413b2a0` with `/tmp` on its own mount: **63 failed, 20 errors** in
    `test_result_cache_plots`, `_review`, `_unverified`, `_quit` and `_badge`, `test_result_lifecycle`
    (29), `test_offline_browsing`, `test_preset_folder_live`, `test_cache_admin` and
    `test_saved_listings`.

## Fix

**Seam:** `helab/utils/data_roots.py`, `fixed_mount()`.
- It also trusts the mount named by `HELAB_TEST_FIXED_MOUNT` (`TEST_FIXED_MOUNT_ENV`).
- It acts only when the variable is set, and only `tests/conftest.py` sets it, never HeLab. The
  docstring says so.
- It follows the existing `HELAB_TEST_VOLUME_ID` seam in `_volume_id`.

**Conftest:** `tests/conftest.py` sets the variable at import, beside the other test variables, so
helpers inherit it.
- Its value is the longest psutil mountpoint holding `realpath(tempfile.gettempdir())`.
- It isn't set on Windows, where `HELAB_TEST_LOCAL_MOUNT` already stands in for the drives.
- On macOS and the newer image it names a mount that is already trusted (`/System/Volumes/Data`,
  `/`), so nothing changes there.

**Tests:** in `tests/test_root_discovery.py`.
- `test_the_mount_the_tests_name_needs_no_verification_and_only_when_named`:
  - with the variable unset, a USB-like mount isn't trusted, and its cached read raises
    `VolumeUnverified`;
  - named, it is trusted and the read answers;
  - another mount is still not trusted.
  - It fails on the old code (`assert False` once the variable is named).
- `test_the_tests_folders_are_on_a_mount_that_needs_no_verification`: the mount holding `tmp_path` is
  trusted whatever the runner's layout. It fails on the old code when `/tmp` is on its own mount.

**Test-only change.** The seam is the only line HeLab reads, and only under tests. No test relied on
`/tmp` needing verification: `test_result_cache_unverified` uses its own fake mounts and passes either
way.

## Checks

In this worktree, with `PYTHONPATH` set to it so that both pytest and the helpers import its helab:

- **New tests:** on the fix, 2 passed, on both the normal `/tmp` and one on its own mount. On the old
  code, the seam test failed on the normal `/tmp`, and both failed with `/tmp` on its own mount.
- **Full suite, normal tmp:** `pytest -n 12 --reruns 5 --reruns-delay 1`: 9231 passed, 673 skipped, no
  RERUN.
- **Full suite, `/tmp` on its own mount:** `TMPDIR` and `--basetemp` on a mounted 8 GB sparse disk image,
  `pytest -n 8 --reruns 5 --reruns-delay 1`: 9231 passed, 673 skipped, no RERUN (Ground's code on the
  same mount: 63 failed, 20 errors).
- **Type checks:** `mypy helab/ --strict`, `mypy tests --strict`, `mypy helab/ --strict --platform win32`,
  `pyright helab tests` and `pyright --pythonplatform Windows helab tests` are clean.
- **CI:** below.

## Proposed `roadmaps/known-issues.md` entry (to Fixed once landed)

- [x] **A runner whose /tmp is a mount of its own failed the result-cache, lifecycle and offline
  tests.** Seen on Ground CI 41587336570 (`a51176f`, Ubuntu Tests 3/3, job 125755838908) and
  41570883747 (`b1a16d3`, Ubuntu Tests 1/3, job 125703300662), both on ubuntu-26.04 image
  20261018.50.1.
  - Why: the tests' folders under `/tmp` weren't on the system volume there. So a cached read
    waited for a volume check that tests' own FolderCaches never run (`VolumeUnverified`, "its volume
    wasn't verified within 120 s"). Every rerun failed the same way, and the session timeout ended the
    job.
  - Fixed: conftest names the temp folder's mount in `HELAB_TEST_FIXED_MOUNT`, and
    `data_roots.fixed_mount` trusts it only when it is set (`agent/fixed-mount-seam`).
  - Repro: `TMPDIR` on a mounted disk image; without the fix, 63 failed and 20 errors.

## Proposed AI_TODO item (A~1): CachedRuns' verification timer outlives a closed plot

Seen in the leaked plots after 41587336570's timeouts. These are knock-on effects, not causes, and
both are logged with HeLab going on.

1. `cached_results.CachedRuns._verification_due` runs `_unchecked`, which calls `_note("")`, which
   calls `AnalysisInstance._cached_status`. That raised `RuntimeError: wrapped C/C++ object of type
   QLabel has been deleted`:
   - a plot closed while its save waited for the volume check (up to `SAVE_VERIFY_WAIT`, 120 s);
   - `_closed()` didn't say closed;
   - the timer still fired into the plot's deleted widgets.

   Fix: when the plot closes (or its dock is deleted), CachedRuns stops `_verify_timer` and forgets
   the plot's callbacks, keeping only the pending save's own bookkeeping. Alternatively, `_closed()`
   also checks `sip.isdeleted(status_label)`. Test: a plot whose save is refused as unverified, closed
   and deleted, then `_verification_due` called, raises nothing.
2. `AnalysisInstance.close` (`instance.py:1699`, `self.runner.results.unpin(...)`) raised
   `AttributeError: 'AnalysisRunner' object has no attribute 'results'` in a later test.
   - Likely: a plot leaked from an earlier attempt closed after its test's runner was stopped and
     released (`test_result_cache_plots`' `RUNNERS`). Its sip wrapper then had no Python attributes.
   - Check whether `close` should skip the runner once it is gone (the runner held as a weakref, or
     `sip.isdeleted`), or whether the test should close its plots before stopping the runner.

## Proposed doc change: `.ai/architecture/testing.md`

In the paragraph listing the production code's test seams, after `HELAB_TEST_VOLUME_ID (a fixed volume
ID)`, add:

> `HELAB_TEST_FIXED_MOUNT` (`data_roots.fixed_mount`: the mount it names is trusted as the system volume
> is, so the tests' folders under the temp folder need no volume check; conftest sets it, not on Windows,
> to the mount holding the temp folder; it acts only when set, and HeLab never sets it. A runner whose
> /tmp is a mount of its own, such as ubuntu-26.04 image 20261018.50.1, once failed every result-cache
> test without it)

A sentence for the isolation section: "To check a change against a runner whose /tmp is its own mount,
run the suite with `TMPDIR` and `--basetemp` on a mounted disk image (macOS: `hdiutil create -size 8g
-type SPARSE -fs APFS`)."

## Test files touched

`tests/conftest.py` and `tests/test_root_discovery.py`. App code: one function, `helab/utils/data_roots.py`.

## CI 41604355924 (`c133e41`): success, all 15 job logs read, no RERUN

- **Jobs:** Tests 1/3, 2/3 and 3/3, Converter backends and Build all succeeded on macOS, Windows and
  Ubuntu. No log has a RERUN, a rerun reason or a crashed worker.
- **New tests:** both passed on each OS: Ubuntu Tests 1/3, macOS Tests 1/3, Windows Tests 1/3.
- **Image:** every Ubuntu job ran image 20261025.179.1, so CI didn't meet the old image's /tmp this
  time. The local runs with /tmp on its own mount are the evidence for that layout.
- **Windows pytest per group:** 9.9, 9.5 and 10.9 min.
