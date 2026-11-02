# Brief: Quick Fixes 9 (Rivet, Quick Fixer on Ground, `dev/v0.0.8`)

Coordinator: CoCo, 2026-11-02. Tony's go (Chat, via Side, 2026-11-02). All AI_TODO items; details in
`.ai/AI_TODO.md` under their IDs.

**Running beside you:** the Caching v2 floor (Vault), stage 2. It owns `helab/utils/cache_store.py`,
`store_v4.py`, `legacy_store.py`, `hlb.py`, `cache_move.py`, `folder_cache.py`, `helab/io_ops/` (loading,
save_held, live, helab_txy, convert, raw_fill, stores, admin), `helab/cache_cli.py`, `helab/convert/raw_layer.py`.
Stay out of those; if a fix needs one, stop and ask CoCo. (A40.2 and A44.2 went to Vault for that reason.)

## Items (one commit each, a test that fails before each fix)

1. **A43.5** (Q43.5): the two other "Another HeLab is running" texts, `CacheTab.py:605` and
   `CacheDialogs.py:106`, worded as recorded (a text change only; Vault may touch these files in stage 2's UI,
   so keep it to the strings).
2. **A40.4** (Q40.1): `MissingShotsWindow.CANCEL_TIP` set to Tony's wording.
3. **A40.1**: a helper still starting in `IOService._run` when HeLab quits is stopped (`_run` checks
   `self.closed` right after `Popen` and kills).
4. **A41.1**: an outdated saved result with no view (`AnalysisInstance._cached_found`).
5. **A43.1**: `IconsInitUtil.initialise_icons()` in an autouse fixture in `tests/conftest.py`, taking pytest-qt's
   `qapp` (icons before a `QApplication` abort the worker, `1f86ca2`); then drop `test_main_split`'s own.
6. **A43.2**: the "Another HeLab may have changed them" comments before `read_presets()`.
7. **known-issues `test_folder_icons.py::test_native_icon_delivery_is_shared_and_rendering_stays_memory_only`**:
   the I/O check counts only the GUI thread's calls (your own diagnosis), with a repro case kept.

## Rules

AGENTS.md throughout; every control named with an ID; strict typing (incl. `--platform win32`, `pyright
--pythonplatform Windows`); tests never touch real data. **Run the full suite and the five type checks before
each commit** (QF8's 915aff5 slip). Push once when all are done; read every Tests and Converter backends job's
log for RERUN before reporting. Handoff and doc proposals in this folder (provisional `Q~`/`A~`/`M~`). Ground is
shared: never stash or reset anyone's changes. No version bump, release, tag or PR.

When done: `maestri ask "CoCo" "QF9: done at <hash>, suite <N> passed, RERUNs <…>, CI <run>"`.
