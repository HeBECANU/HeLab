# See everything HeLab knows about a folder

The **Folder info** window brings together, for one folder, what is otherwise spread over the folder
row's tooltip, Folder details, the right-click menu and Settings: what the disk cache holds for it
(and which of it is the only copy left), its saved plot results, its flags, TXY list, cache policy and
constants, its scan history, and HeLab's converted TXY of it.

Most of its buttons run the folder's usual actions, which ask first just as they do from the
right-click menu or Settings. Three are the window's own: they clear one kind of cached data for this
folder only, and each asks first ([Clearing one folder](#clearing-one-folder)).

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

Clear loaded data cache and Don't cache's "remove cached data" keep only copies. This window's
**Clear raw pulses…** removes the folder's only copies too, and its question says how many there are.
Settings › Cache's **Clear raw pulses** and **Clear all** remove every folder's along with everything
else.

### When a read fails

If HeLab can't read the disk cache (a busy or damaged store), the header says **Couldn't read the
disk cache** and why, and the sections keep what the last successful read showed, greyed out. The
window never says "nothing cached" unless a read worked and found nothing. A folder without a data
root has no disk cache at all, and the window says **RAM only**.

## Refreshing

The window reads when it opens, when you click **Refresh**, after each save of the folder to the disk
cache (a load's, or Live's), and after you start an action from it (once the folder has changed). It
doesn't read on a timer. Minimised, it reads once when you bring it back, if a read fell due meanwhile.

**While Live watches the folder**, the window keeps up by itself: its This session lines follow each
check that brings new shots, and it reads the disk cache again after each Live save (every few shots,
set in Settings › Cache, and when Live stops). The header then says **Live: refreshes by itself**. Raw
pulses are cached just after a save, so they show at the next read.

## The buttons

Each section's buttons are the folder's usual actions:

- **Disk cache:** **Clear loaded data cache** (as in the right-click menu), **Clear raw pulses…**
  (this folder's), and **Settings › Cache…** to clear any kind of cached data of every folder.
- **Saved plot results:** **Clear this folder's saved results…**, and **Settings › Data roots…**
  (with the folder's data root selected) to clear that root's cached analysis.
- **Flags:** the same toggles as the right-click menu; **Write TXY beside** asks first, as Live's
  Auto-convert menu does.
- **TXY list and cache policy:** **TXY for this folder…** and **Cache policy for this folder…**.
- **Constants:** **Folder constants…**.
- **Scan history:** **Retry / Refresh** lists the folder again.
- **HeLab's converted TXY:** **Convert this folder…** and **Clear this folder's converted TXY…**.
- **Header:** **Place .helab-root here…** for a RAM-only folder, or **Settings › Data roots…** for the
  folder's data root.

Actions that need a data root (the flags, the folder's TXY list and policy, clearing its cache) are
greyed out for a RAM-only folder, with the reason in their tooltip.

## Clearing one folder

Each of these removes one kind of HeLab's cached data of this folder, and nothing of any other folder.
Each asks first, naming the size and count from the window's last read, and the only copies among
them. The buttons are greyed out when there is nothing to remove, when the last read failed, or while
the Clear runs.

| Button | What it removes | What stays |
|---|---|---|
| **Clear raw pulses…** | HeLab's cached raw pulses of the folder, only copies included (they're cached again the next time the folder loads, unless it is set to Don't cache or its cache policy is TXY only: the question says which) | your `d<N>.txt` files, the folder's TXY data and loads saved |
| **Clear this folder's saved results…** | the folder's saved plot results | plots open on it (they keep what they show), its cached data and flags |
| **Clear this folder's converted TXY…** | the TXY HeLab converted from the folder into its cache or temp folder | your `d<N>.txt` files, and TXY written beside them: never touched |

For converted TXY, the question says how many are the only copy of that TXY: shots whose `d<N>.txt`
files were gone when HeLab last looked. HeLab knows that only for shots whose raw pulses it cached,
and it never lists the folder to find out.

A Clear that worked shows **Removed …** under the header, with the time. One that HeLab refused (a
drive not checked yet this session, a disk cache a newer HeLab wrote) or that failed shows **Couldn't
remove …** and why. Either way the window reads the folder again, so its lines show what is left.

A conversion running at the time of a converted-TXY Clear (into HeLab's cache or temp folder, of any
folder) stops writing and converts the rest at its next check, as it does after Settings › Cache's
Clear.
