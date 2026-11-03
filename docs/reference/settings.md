# Settings

Open the Settings window with File › Settings... or the **Settings** button on the left toolbar.
It has six tabs: General, Lab parameters, TXY converter, Scripts, Cache and Data roots.

The buttons at the bottom:

- **Save** keeps your changes and closes the window. Changes to converter profiles and the
  actions on the Cache and Data roots tabs (Clear, Remove, Forget and so on) take effect at once,
  without Save.
- **Cancel** closes the window without saving.
- **Reset all settings…** puts every setting back to its default, after asking: folders, load
  options, both cache budgets, window and view choices, and the list of plots to reopen. The
  cache folder's location, the disk cache's contents and your presets are kept. While you work
  offline, it asks whether to keep working offline or go online.

## General

| Setting | What it does | Default | Range |
|---|---|---|---|
| When selecting another folder | What happens to a folder's load when you select another folder: **Cancel the current load**, **Finish the current load in the background**, or **Queue folders kept selected for 3 s**. Also in View › When Selecting Another Folder. | Finish the current load in the background | |
| Simultaneous background I/O operations | How many background loads, folder checks and cache writes run at once, across all tabs. One more lane is always kept for browsing and loading the selected folder in the current tab. | 1 | 1 to 32 |
| Check of cached data | When a folder's cached data is shown and the folder wasn't modified since it was cached, which TXY files HeLab also checks (size and modified time) before trusting the cache: **Swift: the last file**, **Fast: the first and last files**, **Medium: first, last and at least 3 random files (1%)**, **High: first, last and at least 10 random files (3%)**, or **Full: every file (lists the folder)**. If any file differs, HeLab compares every file. | Medium | |
| Live: check again after | While [Live](../how-to/live.md) watches a folder, the time from the end of one check to the start of the next. | 3.0 s | 0.5 to 600 s, in steps of 0.5 s |
| Read files unmodified for | A file modified more recently than this may still be being written, so HeLab leaves it for a later read: when browsing, loading, following Live, checking cached data and converting. | 5.0 s | 2 to 60 s, in steps of 0.5 s |
| Automatically check folder status in view | Check the status of folders in view that have no saved results yet. Also in View › Automatically Check Folder Status in View. | Off | |
| Reopen plots at start | When HeLab starts, reopen the plots that were open when it last quit, with their settings and places. Each runs again on its folder's data in RAM or the disk cache, never reading the folder itself; without cached data it waits until a tab loads the folder. | On | |
| Log files to keep | HeLab writes a log file per session, started again every 1 MB (1 MiB on Windows). At startup it deletes the oldest log files beyond this number. Help › Show log folder shows them. | 300 | 1 to 100,000 |

Under **Directory Settings**:

| Setting | What it does | Default |
|---|---|---|
| Temp folder | Where HeLab keeps temporary files. **Browse...** picks another folder, **Open Path** shows it, **Reset to Default** puts the default back. A change applies at the next start. | `HeLab/temps` in your user cache folder: `~/Library/Caches` on macOS, `%LOCALAPPDATA%` on Windows, `~/.cache` on Linux |
| Cache folder | Where the disk cache is. You can't type a path: **Change…** moves the cache, with its contents, to an empty folder (HeLab pauses loading and folder checks while it moves). **Open Path** shows it. | `HeLab/caches` in the same user cache folder |

## Lab parameters

The physical constants every folder and plot starts from. A folder can set its own values
(right-click the folder › Folder constants…), and each plot can override any of them in its own
settings.

Each row shows the value, its source, and a status: `default`, or `set here` once you change it.
**Restore** puts the default back. Values marked `unconfirmed` (in amber) are borrowed from older
lab code: check them on the current setup. Lengths are shown in mm, times in ms and the
wavelength in nm.

| Constant | Default | Notes |
|---|---|---|
| Reduced Planck constant ħ | CODATA | Read only |
| Boltzmann constant k_B | CODATA | Read only |
| Atomic mass constant u | CODATA | Read only |
| He* mass | 6.6465 × 10⁻²⁷ kg (the He-4 atomic mass × u) | |
| Gravitational acceleration g | 9.79602 m/s² | |
| He* scattering length a | 7.512 nm | |
| Recoil wavelength λ | 1,083.331 nm | Unconfirmed |
| Detector quantum efficiency | 0.1 | Unconfirmed; at most 1 |
| DLD trigger | 20,500 ms | Unconfirmed; shown only: used to flag incomplete shots, never in a physics formula |
| DLD acquisition | 2,000 ms | Unconfirmed; shown only, as above |

Every editable value must be positive.

## TXY converter

The choices HeLab's own TXY conversions use (see [Convert raw files to TXY](../how-to/convert-txy.md)).

| Setting | What it does | Default |
|---|---|---|
| Conversions use the profile | The detector profile for conversions: a built-in one or one of yours. A profile that no longer exists shows as not found, and conversions use the default. | matlab-2019 |
| Backend | The converter code: **numpy (default; always available)**, **reference (plain Python, slow)**, **rust (optional, compiled)**, **cython (optional, compiled)**, **numba (optional)** or **mlx (optional; Apple GPU)**. Every backend writes the same TXY byte for byte; an optional one that can't run on this computer makes the conversion say why. | numpy |
| HeLab's TXY go to | Where converted TXY files go: **The disk cache's folder (by the folder's data root; else temp)** or **HeLab's temp folder**. Folders you set to write TXY beside their raw files do that instead. | The disk cache's folder |
| Tabs and Live read (when a folder loads again) | Which TXY files a folder's tab and Live load. This setting is changing in the next version. | |

Under **Profiles**, the list shows the built-in profiles (`matlab-2019`, `matlab-2023-lab-edit`,
`plates-2017`, `plates-2022` and `plates-2025`, the last marked uncalibrated) and yours. Built-in
profiles are read only. **Duplicate…** and **Export…** work on any selected profile, **Edit…**
and **Delete…** on yours only; **Import…** adds a profile from a file and **Show folder** shows
where your profiles are kept. Profile changes are saved at once, not with Save.

## Scripts

This tab has no settings yet. Your script folders, and **Reload when a script is saved**, are in
the Scripts panel: see [Write an analysis script](../how-to/write-a-script.md).

## Cache

What the disk cache holds, the actions that clear it, and both budgets. See
[How HeLab caches data](../explanation/cache.md). Every Clear and Remove asks first and says what
stays.

### Disk cache

The top line shows where the cache is (**Open** shows the folder; move it from the General tab)
and how much of the budget it uses.

| Setting | What it does | Default | Range |
|---|---|---|---|
| Budget | The most the disk cache may hold: cached data, cached analysis and the records database. Nothing is removed to make room without asking. At 80%, automatic loads of folders without cached data pause. | 8 GB (8 GiB on Windows) | At least 1 GB (1 GiB on Windows), in steps of 0.5 |
| Cache policy | What new saves keep, for every folder without its own choice: **Raw + what you load (default)** (raw pulses and each TXY a tab or plot uses), **Raw only, convert on load**, or **TXY only (no raw)**. Changing it removes nothing; switching to TXY only offers to remove the cached raw pulses of the folders that follow this setting. | Raw + what you load | |
| Reuse saved analysis results | A costly plot (Correlations, Release time) shows its result saved for the same data, script and settings instead of computing it again, and saves new ones. Off: plots compute every run and save nothing; saved results stay until cleared. | Off | |
| Live: save to the disk cache every | While Live watches a folder, new shots stay in RAM; once this many wait, the folder's cached data is saved again, and once more when Live stops. | 10 new shots | 1 to 100,000 |

The rows below the budget show what the cache holds, each with its own **Clear…** (or
**Forget…**): Cached data, Folder summaries, Scan failures, Subfolder status, Folder listings,
Cached analysis, Raw pulses and TXY data. **Clear all…** clears all of them except cached
analysis. Folder preferences, HeLab's converted TXY and Presets (**Presets…** lists, renames,
duplicates and deletes them) have their own rows, and Clear all keeps them. An older HeLab's
cache, if one is in the cache folder, has a row of its own, where you can ignore it or clear it.

### Remove old entries

Each row removes what wasn't used, checked or shown in the last N days (1 to 3,650; 90 when the
window opens): cached data, TXY data, HeLab's cached raw pulses, folder records, cached analysis,
or everything. **Include scan failures (automatic checks will try those folders again)** also
forgets folders whose scan failed. These choices aren't saved.

### Memory

| Setting | What it does | Default | Range |
|---|---|---|---|
| RAM budget | Loaded folders not shown in a tab are dropped from RAM, least recently used first, until the rest fit. Plots count too: from 50% the status bar says so, at 75% a window lists the biggest plots and folders, and above 80% plots not viewed lately are released (each keeps a picture). Folders shown in tabs and shown, running or Live plots are never dropped, so HeLab can use more than this. Shown as a size and a share of the computer's RAM, for example `16.0 GiB (1/8 of 128 GiB)`. | 1/8 of the computer's RAM | In steps of 1/128 of RAM, from 1 GiB (or one step, if larger) up to half of RAM |
| Reload a released plot when it is shown again | Showing a released plot again (its tab, its window or its settings) draws it again from RAM or the disk cache, never from its folder. Off: only its Reload button does. | On | |

## Data roots

The folders holding a `.helab-root` that HeLab has seen on this computer, with each one's
status, when it was last seen and how much is cached under it. The two lines below the list show
the selected root's path and ID. See [Mark a data root](../how-to/data-root.md).

This tab has no settings; its buttons act on the selected root: **Refresh**,
**Forget location…**, **Delete .helab-root…**, **Clear cached data…**,
**Clear cached analysis…**, and **Review…** for a location waiting for your answer to "same
folder or a copy?".

## Remembered outside the Settings window

HeLab also remembers these choices across restarts:

| Choice | Where | Default |
|---|---|---|
| Work Offline | File › Work Offline: browse and analyse cached data only, reading no source folder or server. | Off |
| Script folders | The folders loaded with **Load Scripts...** in the Scripts panel; **Remove from the list** in its menu forgets one. | None |
| Reload when a script is saved | The menu beside **Load Scripts...** in the Scripts panel. | Off |
| Start Live and auto-convert here when HeLab launches | The **Auto-convert** button's menu, for one folder. | No folder |
| Notify when a converted shot has fewer than N hits | The **Auto-convert** button's menu: a system notification, once per shot (0: never). | 100 |
