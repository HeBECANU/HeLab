# Command line

HeLab installs one command, `helab`. Without a subcommand it starts the app; `helab convert` and
`helab cache` run in the terminal, without the GUI.

| Command | What it does |
|---|---|
| `helab` | Start the HeLab app. |
| `helab --version` | Print the version and build information, then exit. |
| `helab convert --watch FOLDER …` | Convert a folder's raw files to TXY, without the GUI. |
| `helab cache dump FILE.hlb` | Print a disk cache file's header. Read only. |
| `helab cache export …` | Export disk cache files to NumPy, MATLAB or CSV files. Read only. |

`python -m helab` works the same as `helab`, with the same subcommands and options. In the packaged
app, run the executable inside it with the same arguments: `HeLab.app/Contents/MacOS/HeLab convert …`
on macOS, `HeLab.exe convert …` on Windows. The Windows app has no console, so its lines go only to
the log file.

## helab

```bash
helab                                   # start the app
helab --version                         # print the version and build information
helab --geometry 1600x1000+0+0          # this run's window size and position
```

`--geometry WxH+X+Y` sets the main window's size and the top-left corner of its frame, for this run
only.

**One HeLab app per computer.** If HeLab is already running, a second start shows *HeLab is already
running on this computer … Use its window, or quit it before starting HeLab again.* and exits with
code 1. `helab convert` and `helab cache` don't count: they run beside the app.

## helab convert

```text
helab convert --watch FOLDER [--once] [--profile NAME|FILE.json] [--backend NAME]
              [--output temp|cache|cache-forced|beside|beside-forced]
              [--workers N] [--interval SECONDS] [--again]
```

Watches a folder and converts its raw files (`d<N>.txt`) to HeLab's TXY files
(`d_txy_helab_<tag>_<N>.txt`) as they finish being written. It uses the same converter, rules and
output folders as the app (see [Convert raw files to TXY](../how-to/convert-txy.md)), runs without
the GUI, and can run while the app is open. Its log goes to the terminal and to HeLab's log folder
(Help › Show log folder in the app).

The first check only records each raw file; a file is converted once it is unchanged between two
checks. Ctrl-C stops it between two writes: every TXY is written under a temporary name and then
renamed, so none is left half-written.

| Option | Meaning |
|---|---|
| `--watch FOLDER` | The folder of raw files. Required. |
| `--once` | Convert what is there now, then exit. Only files unmodified for a minute are read; the rest are reported as still waiting. |
| `--profile NAME` or `FILE.json` | A built-in detector profile's name, or a profile JSON file (for your own profiles, use the file). Default `matlab-2019`. |
| `--backend NAME` | The converter backend: `numpy` (default), `cython`, `reference`, or `numba`, `mlx`, `rust` where installed. |
| `--output temp` | Write the TXY to HeLab's temp folder. |
| `--output cache` | Write them to HeLab's cache folder. For a folder set to Don't cache, it warns and asks `Write to the cache folder anyway? [y/N]`; without a terminal, or on no, the temp folder. |
| `--output cache-forced` | The cache folder, even for a folder set to Don't cache, without asking. |
| `--output beside` | Write the TXY next to the raw files, for this run, whatever the folder's own setting. On a network share it asks first (below). |
| `--output beside-forced` | Beside the raw files even on a network share, without asking. The share's warning is still logged. |
| `--workers N` | Processes converting at once. Default: half the computer's cores, at most 4 (1 in the packaged app). |
| `--interval SECONDS` | Seconds between checks of the folder. Default 3. |
| `--again` | Convert every shot once more, current ones too (cache and temp folders only). |

Without `--output`, the TXY go where Settings › TXY converter › **HeLab's TXY go to** says (the
cache folder unless you changed it). A folder without a `.helab-root`, or set to Don't cache, goes
to the temp folder.

**Beside the raw files on a network share**, `--output beside` warns once and asks
`Write the TXY beside the raw files on the share anyway? [y/N]`. No, or no terminal, converts to
HeLab's own folder instead, and the log names `--output beside-forced`, which writes beside without
asking. (Older versions had `--yes` for this; it is now a usage error naming `beside-forced`.)

**If the share can't take a file safely** (its file system can't add a file without risking
replacing one), it asks
`[r]etry, write to HeLab's [c]ache or [t]emp folder instead, or [q]uit? [r/c/t/Q]`. A cache or temp
answer holds for the rest of the run. Without a terminal nothing is written beside, and the log
suggests `--output cache` or `--output temp`.

### Examples

```bash
# Follow a run's folder, converting each new shot into HeLab's cache folder
helab convert --watch "/Volumes/Data/2026/run 1"

# Convert what is there now with another built-in profile, then exit
helab convert --watch "/Volumes/Data/2026/run 1" --once --profile matlab-2023-lab-edit
```

On Windows, for example on the acquisition computer, writing the TXY beside the raw files:

```powershell
helab convert --watch D:\data\run1 --output beside
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Done, or stopped with Ctrl-C. |
| 1 | With `--once`, the conversion failed; or you answered quit after a refused write beside the raw files. Without `--once`, a failed check is logged and the next one goes on. |
| 2 | A usage error, a folder that doesn't exist, or a profile that can't be read. |

## helab cache

```text
helab cache dump FILE.hlb
helab cache export FILE.hlb [--to npz|mat|csv] [--out PATH] [--bin-time SECONDS] [--force]
helab cache export --folder FOLDER [--kind raw|txy] [--layer LAYER] [--cache DIR]
                   [--to npz|mat|csv] [--out DIR] [--bin-time SECONDS] [--force]
```

Looks into the `.hlb` files of HeLab's disk cache and exports them. It is **read only**: it never
writes into the disk cache or a source folder, never replaces a file without `--force`, refuses an
`--out` inside the disk cache, and works while the app is running. The file format is described in
[HeLab's .hlb files](../hlb-format.md).

### dump

`helab cache dump FILE.hlb` checks the whole file and prints its header as JSON: what the file is,
which HeLab made it, and each array's name, type, shape and compressed size.

### export

| Option | Meaning |
|---|---|
| `FILE.hlb` | Export one file: a raw layer (one raw file's pulses: columns `channel`, `time_bins`, `time_s`), or a TXY segment (columns `shot`, `t_s`, `x_m`, `y_m`). |
| `--folder FOLDER` | Instead of a file, export what the disk cache holds for this source folder. The folder needs a `.helab-root` at or above it. |
| `--kind raw` or `txy` | With `--folder`: raw pulses (default), one file `d<N>.<ext>` per shot; or TXY, one file `d_txy<N>.<ext>` per shot, columns `t_s`, `x_m`, `y_m`. |
| `--layer LAYER` | With `--kind txy`: which TXY to export, `matlab`, a profile tag such as `m19v1`, or `helab:<hash>`. Needed when the folder has more than one. |
| `--cache DIR` | The cache folder to read. Default: the one HeLab uses. |
| `--to npz`, `mat` or `csv` | NumPy `.npz` (default), MATLAB `.mat`, or CSV with one row per pulse or hit. `.npz` and `.mat` files also carry the header, as JSON text. |
| `--out PATH` | The output file (one file) or folder (`--folder`). Default: the current folder for one file, `./helab-export-<folder name>/` for a folder. |
| `--bin-time SECONDS` | Seconds per TDC bin, for raw layers' `time_s`. Default `25e-12`. |
| `--force` | Replace output files that already exist. |

### Examples

```bash
# What is in this file?
helab cache dump d1.hlb

# Every cached raw file of a run, for MATLAB
helab cache export --folder "/Volumes/Data/2026/run 1" --to mat

# The cached TXY of the matlab-2019 profile, as CSV
helab cache export --folder "/Volumes/Data/2026/run 1" --kind txy --layer m19v1 --to csv
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Done. |
| 1 | Nothing to export: the disk cache holds nothing of that kind for the folder. |
| 2 | A file damaged or of a newer format, a usage error, or anything else that stops the export (for example no `.helab-root` above the folder, or no disk cache to read). |
