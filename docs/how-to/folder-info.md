# See everything HeLab knows about a folder

The **Folder info** window brings together, for one folder, what is otherwise spread over the folder
row's tooltip, Folder details, the right-click menu and Settings: what the disk cache holds for it
(and which of it is the only copy left), its saved plot results, its flags, TXY list, cache policy and
constants, its scan history, and HeLab's converted TXY of it.

The window only shows. Its buttons run the folder's usual actions, which ask first just as they do
from the right-click menu or Settings.

## Open it

- **Right-click a folder › Folder info…**, or
- **Folder info…** at the end of Folder details' **Disk cache** row, or
- **File › Folder info…** (**⌘I** on macOS, **Ctrl+I** on Windows and Linux) for the current tab's
  selected folder. This also works while the folder panel is hidden, for example during Live.

There is one Folder info window. Opening it for another folder shows that folder instead, and the
title bar shows the folder's path. The window remembers its size.

## What it shows

The header names the folder and its **data root** (the `.helab-root` the disk cache keys it by),
or says **RAM only** when there is none, and offers **Place .helab-root here…**. **As of 14:02:31**
is when HeLab last read the folder's disk cache. **Refresh** reads it again. **Copy as text** copies
everything shown, for a message or a log book.

The sections below the header:

| Section | What it holds |
|---|---|
| This session | the folder's data in RAM and its size, Live on or off, the plots open on it, the newest shot, and a line for its subfolders |
| Disk cache | raw pulses (HeLab's copy of the `d<N>.txt` files), each TXY layer by profile, the loads saved, and the **only copies** |
| Saved plot results | each saved result: its plot, action, settings, when it was computed and last used, and its size |
| Flags | Don't cache, Don't auto-load and Write TXY beside, for this folder only |
| TXY list and cache policy | which TXY the folder loads and what its saves keep: the folder's own choice, or Settings' |
| Constants | the folder constants in effect, each with the folder that sets it |
| Scan history | the last status check, any failed ones, and when HeLab last listed the folder |
| HeLab's converted TXY | the TXY HeLab converted from this folder, in its cache or temp folder or beside the raw files |

Each line is short; hover over it for the detail. A section with many lines, such as a folder with
many saved results, shows the first few and a link such as **All 37 saved results ›**. The link opens
the full list in a pane to the right, and the window widens instead of growing taller. Close the pane
with **×** and the window narrows again.

### The only copy

A line in amber marked ⚠ **Only copy** means HeLab holds data whose source files were gone the last
time it listed the folder: raw pulses whose `d<N>.txt` files are missing, or TXY layers whose TXY
files are gone and can't be rebuilt from raw pulses. HeLab learns that a file is gone only when it
lists the folder, so the line says when it **last looked**. If the files are back (a drive that wasn't
mounted, a folder restored), **Retry / Refresh** lists the folder again and clears the mark.

Clear loaded data cache and Don't cache's "remove cached data" keep only copies. Settings › Cache's
**Clear raw pulses** and **Clear all** remove them along with everything else.

### When a read fails

If HeLab can't read the disk cache (a busy or damaged store), the header says **Couldn't read the
disk cache** and why, and the sections keep what the last successful read showed, greyed out. The
window never says "nothing cached" unless a read worked and found nothing. A folder without a data
root has no disk cache at all, and the window says **RAM only**.

## Refreshing

The window reads when it opens, when you click **Refresh**, and after you start an action from it
(once the folder has changed). It doesn't read on a timer.

**While Live watches the folder**, the window keeps up by itself: its This session lines follow each
check that brings new shots, and it reads the disk cache again after each Live save (every few shots,
set in Settings › Cache, and when Live stops). The header then says **Live: refreshes by itself**. Raw
pulses are cached just after a save, so they show at the next read.

## The buttons

Each section's buttons are the folder's usual actions:

- **Disk cache:** **Clear loaded data cache** (as in the right-click menu), and **Settings › Cache…**
  to clear raw pulses or other kinds of cached data.
- **Saved plot results:** **Settings › Data roots…** (with the folder's data root selected) to clear
  that root's cached analysis, or **Settings › Cache…** to clear all of it.
- **Flags:** the same toggles as the right-click menu; **Write TXY beside** asks first, as Live's
  Auto-convert menu does.
- **TXY list and cache policy:** **TXY for this folder…** and **Cache policy for this folder…**.
- **Constants:** **Folder constants…**.
- **Scan history:** **Retry / Refresh** lists the folder again.
- **HeLab's converted TXY:** **Convert this folder…**, and **Settings › Cache…** to clear converted
  TXY.
- **Header:** **Place .helab-root here…** for a RAM-only folder, or **Settings › Data roots…** for the
  folder's data root.

Actions that need a data root (the flags, the folder's TXY list and policy, clearing its cache) are
greyed out for a RAM-only folder, with the reason in their tooltip.
