# Convert raw files to TXY

HeLab has its own TXY converter. It turns the delay-line detector's raw files, `d<N>.txt`, into
TXY files of hits (time and X, Y position), named `d_txy_helab_<tag>_<N>.txt`. With the default
profile its output matches the lab's MATLAB converter (`tdc_autoconverter`, which writes
`d_txy_forc<N>.txt`) byte for byte.

The `<tag>` in the name says which detector profile made the file, so TXY made with different
profiles never get mixed up. HeLab never modifies a raw file, and never replaces a TXY that is
already in a source folder.

## Ways to convert

- **While Live watches a folder**: turn on **Auto-convert**, and each new raw file is converted
  once it has finished being written. See [Follow a folder live](live.md#auto-convert-while-live-is-on).
- **From Folder details**, for a folder on a network share that has raw files and no TXY at all:
  Folder details shows a **Convert** row, `No TXY · on a share · Convert…`. Click it and choose
  **Convert to HeLab's cache (recommended)**, **Convert to HeLab's temp folder** or
  **Convert beside on the share…**. The row then shows the progress, for example
  `Converting to HeLab's cache folder… 3 of 40`, and the folder loads again when it is done.
  Files still being written after a few passes are left to Live's auto-convert.
- **Without the app**, from a terminal: `helab convert --watch FOLDER`. See
  [Command line](../reference/command-line.md#helab-convert).

A raw file is converted only once it has been unmodified for the settle time (Settings › General ›
**Read files unmodified for**, 5 s by default) and looks the same at two checks in a row. A raw
file that stays unchanged for 20 s and still fails the format checks is called **damaged**: it gets
no TXY, and later shots carry on. A shot whose raw file holds no hits gets an empty TXY (0 bytes),
so "converted, empty" is never mistaken for "not converted yet".

## Where the TXY go

Settings › TXY converter › **HeLab's TXY go to** chooses:

| Choice | Where |
|---|---|
| **The disk cache's folder** (the default) | A `converted-txy` folder inside HeLab's cache folder, filed under the folder's data root. A folder without a `.helab-root` (see [Mark a data root](data-root.md)), or set to Don't cache, goes to the temp folder instead. |
| **HeLab's temp folder** | A `converted-txy` folder inside HeLab's temp folder. |

These TXY don't count toward the disk cache budget, and nothing removes them except Settings ›
Cache › **HeLab's converted TXY** › **Clear…**, which asks first. See
[The disk cache](../explanation/cache.md).

### Beside the raw files

To write the TXY into the source folder itself, next to the raw files, turn it on for that folder:
Live line › **Auto-convert** menu › **Write TXY beside the raw files in this folder…**. HeLab asks
first, and the choice is saved for that folder only. It needs the disk cache and a confirmed
`.helab-root` for the folder.

Beside the raw files HeLab writes only the `d_txy_helab_<tag>_<N>.txt` files. Each is written under
a temporary hidden name and then renamed, so other programs never see a half-written TXY. HeLab
never replaces a file already there.

!!! warning "Scripts that read raw folders"
    A lab script that lists `d*.txt` in a raw folder also sees HeLab's TXY written beside the raw
    files. Make such scripts match `d<N>.txt` exactly.

If the folder's file system can't add a file without risking replacing one, HeLab doesn't write
there and asks: **Retry**, **Write to HeLab's cache folder instead**, **Write to HeLab's temp folder
instead**, or **Not now**. A cache or temp choice holds for that folder until HeLab quits.

## Profiles

A detector profile holds every constant the conversion uses. Settings › TXY converter ›
**Conversions use the profile** picks the one HeLab's conversions use; the default is
`matlab-2019`. The built-in profiles are read-only:

| Profile | Tag | What |
|---|---|---|
| `matlab-2019` (default) | `m19v1` | The lab's MATLAB converter, unchanged since 2017. |
| `matlab-2023-lab-edit` | `m23v1` | The 2023 lab edit of the MATLAB converter (an x1 dead time, other time sums). |
| `plates-2017`, `plates-2022` | `p17v1`, `p22v1` | One per set of MCP plates; the same output as `matlab-2019` until calibrated. |
| `plates-2025` | `p25t1` | The same, marked uncalibrated. |

The list under **Profiles** shows each one's notes, content hash and file name. **Duplicate…**
makes your own copy, which you can **Edit…**, **Export…** or **Delete…** (asked first);
**Import…** adds a profile JSON file. Your profiles are JSON files in HeLab's app folder (**Show
folder** opens it), and their TXY are tagged `u` followed by 32 hex digits of the profile's
content hash. Changes to profiles are saved at once; the choices at the top of the tab are saved
with the dialog's Save.

## Backends

Settings › TXY converter › **Backend** chooses the code that does the conversion. Every backend
writes the same TXY byte for byte; they differ only in speed.

- **numpy** is the default and always available.
- **cython** is an optional compiled backend. When running HeLab from source, build it with
  `python native/build.py` (it needs a C compiler); HeLab works without it.
- **reference** is a plain-Python version kept as the yardstick: correct but slow.
- The other entries are optional backends that need extra software installed.

A backend that can't run on this computer makes the conversion say why.

## Which TXY HeLab reads

!!! note "Changing in the next version"
    How HeLab chooses which TXY files to read for a folder (HeLab's, of which profile, or those of
    the external MATLAB converter) is changing in the next version. This section will describe it
    then.
