# Settings persistence

Reference detail for agents working in this area. It moved here verbatim from `AGENTS.md` on
2026-10-28, when AGENTS.md was cut to rules and a map ([index](README.md)). AGENTS.md keeps the
rules every task must follow; this file keeps the mechanics, names and behaviour. Keep it true:
on Ground, update it in the same commit as the code; on a floor, propose the change in your handoff. Settled decisions and Tony's wording live in
`.ai/memory/results/`; feature plans in `roadmaps/`.

## Settings persistence

**Settings persistence:** Uses `QSettings` with org `ANU_HE_BEC_GROUP`, app `HeLab`, opened only by `app_settings()` (`helab/utils/settings_store.py`; `tests/test_settings_store.py` fails if anything else in `helab/` constructs the native store, helpers aside, which reopen it from `settings_spec` with `open_settings`, both in `helab/utils/cache_setting.py`). macOS plist: `~/Library/Preferences/com.anu-he-bec-group.HeLab.plist` (Qt derives the name from the org). Tests must not create native settings stores: `app_settings()` gives each test its own ini (`HELAB_TEST_SETTINGS_FILE`, `tests/conftest.py`), or pass a tmp-dir `QSettings(path, IniFormat)`. Lab parameters are `lab_constants/<key>` in SI units (`helab/utils/lab_parameters.py`): only values the user set (Restore removes the key, so a corrected default applies), never CODATA rows; Reset all settings clears them. Reset all settings reloads every tab, the TXY converter's included (`ConverterTab.load`), and the main window re-applies the conversion profile, the tabs' TXY source and result reuse after the dialog closes, by Save or Cancel (app-1, `2f8b2f1`; Work Offline: Q43.1). The plots to reopen are an arrangement record under `open_plots` (Reset all settings clears it); presets are in the disk cache store (Caching), not QSettings. `reuse_saved_results` (Settings → Cache › Reuse saved analysis results, default off since Q27.1: a new key, so the old `result_reuse`, saved on, no longer counts and is left unread; off: no lookups and no saves, and saved results stay until cleared) is a `settings_defaults.py` row. So is `work_offline` (File › Work Offline, default off, remembered across restarts). `HelabMainWindow` reads them through `app_settings()`, so tests that build a real window see their own ini, never the developer's settings. Every key HeLab reads is in `helab/utils/settings_defaults.py` (key, type, default, description; the `lab_constants/` prefix; `RETIRED` keys, removed when Settings saves), and reads go through `read_setting` (`tests/test_settings_defaults.py`). Read numbers untyped: PyQt's `type=int` is 32-bit and reads 8 GB wrong, so `read_setting` refuses typed reads of number rows. The disk budget's default is platform-dependent (`default_disk_budget()`, 8 GB / 8 GiB), evaluated once when the table is built; the RAM budget's minimum is 1 GiB. `settle_seconds` (Q33.7: Settings › General, float, default 5 s, 2–60 s, step 0.5; read by `read_settle_seconds` in `SettingsDialog.py`; its limits and default in `helab/utils/settle_time.py`, shared with the helpers) is sent with every I/O request ([io-and-browsing](io-and-browsing.md)). `main_window_split` (Q33.2: "<folders>,<settings>" in px, default 380,320; the folders 80–4000, the settings `MIN_SETTINGS_WIDTH` 250–4000, else the default; `HelabMainWindow.read_split`) is saved as HeLab quits (`save_split` in `closeEvent`; a collapsed panel saves the width it had).

## Converter rows

**Converter rows** (stage 4): `converted_txy_output` (cache/temp), `convert_profile` (default `matlab-2019`) and `convert_backend` (default `numpy`), edited in Settings → TXY converter and read by `read_convert_output`/`read_convert_profile`/`read_convert_backend` (`helab/utils/constants.py`); user profiles are files in `<app folder>/profiles`, not settings. `txy_source` (default `helab-priority`; `read_txy_source`; Settings → TXY converter "Tabs and Live read", applies when a folder loads again). Live: `live_launch_folder` (one folder that starts Live and auto-convert at launch, `live_launch`; `live_launch_folders`, the old list, is read once to move its first folder over, then removed, A23.3) and `convert_low_hits` (100; 0 never).

## Caching v2 rows

`store_v4` (bool, default off, no control; `STORE_V4_SETTING`) picks the store layout once per process
([cache-store](cache-store.md#store-v4-caching-v2-behind-the-switch)); it stays off until Tony's check, then
turns on in the v0.0.8 PR (Q28.3, Q47.4), and is kept one release after that as a hidden fallback to store-v3,
then goes (Q50.14). `cache_policy` (`CACHE_POLICY_SETTING`, default `raw+used`; stage 2, landed
`1cd586c`) is the global cache policy (Q45.1), edited by Settings › Cache's Cache policy combo (store-v4
only) and read lazily by `FolderCache.cache_policy`; it is sent as `policy` with store-v4 requests only. A
folder's own policy and TXY source are store rows (`cache_policy`, `txy_source_prefs`), not settings.

## Script rows

**Script rows** (Live scripts, landed `971f4af`): `script_folders` (`SCRIPT_FOLDERS_SETTING`, a JSON list of the
folders added with Load Scripts…, loaded at start after the window shows; removed only by Remove from the list;
a folder skipped at start stays listed) and `script_auto_reload` (`SCRIPT_AUTO_RELOAD_SETTING`, bool, default
off: Reload when a script is saved, in Load Scripts…'s menu)
([plots-and-scripts](plots-and-scripts.md#script-system)). The loading marker `<app folder>/scripts-loading.json`
is a file, not a setting.
