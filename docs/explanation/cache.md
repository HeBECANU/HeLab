# How HeLab caches data

HeLab keeps the data you load in two places: in **RAM** for this session, and in a **disk cache**
on this computer so that a folder opens at once next time. This page explains both, the budgets
that keep them in check, and what HeLab will and won't delete.

Caching never changes your data folders: your raw `d` files and TXY files are never touched by
anything on this page.

## RAM and the disk cache

When you load a folder, its shots are held in RAM. If the folder is inside a data root, HeLab
also saves them to the disk cache in the background. Without a data root the folder is **RAM
only**: nothing about it is saved (see [Mark a data root](../how-to/data-root.md)).

Next time you select a cached folder, its data shows straight away ("Cached data found" or
"Cached data loaded"), while HeLab checks the folder for changes ("Checking for changes…").
If the folder wasn't modified, the check looks only at a few of its files; how many is
**Settings › General › Check of cached data** (default **Medium**). Right-click a folder ›
**Retry / Refresh** to compare every file.

Besides each folder's TXY data, the disk cache keeps a copy of the raw pulses (filled in the
background after a folder's data is cached), each folder's counts and status, and, if you turn
on **Settings › Cache › Reuse saved analysis results** (off at first), the results of costly
plots. **Settings › Cache › Cache policy** chooses what new saves keep: **Raw + what you load
(default)**, **Raw only, convert on load**, or **TXY only (no raw)**. Changing it removes
nothing. Right-click › **Cache policy for this folder…** sets it for one folder.

## Files still being written

A file modified within the last few seconds may still be being written by the acquisition
computer. HeLab never reads, caches or counts such a file; it picks it up on a later check.
The time is **Settings › General › Read files unmodified for**: 5 s by default, from 2 to 60 s.
Files dated in the future count as still being written too. The summary line shows
"N still being written" while any are waiting.

## The disk budget

The disk cache has a budget: by default 8 GB on macOS and Linux, 8 GiB on Windows (at least
1 GB or 1 GiB). Set it in **Settings › Cache**, which also shows how much is used. It counts
cached data, cached analysis and the records; data you removed doesn't count while it waits out
its 10-minute grace period before deletion.

Near the budget, HeLab asks rather than deletes:

- **At 80 %**, a "Disk cache nearly full" window appears once. Automatic loading of folders
  without cached data pauses ("Auto-load paused — disk cache 80% full"); cached folders still
  open, and right-click › **Load data** still works. Choose **Open purge settings**, or
  **Ignore this time** (it asks again if usage rises by another 10 % of the budget).
- **A save that doesn't fit** asks "Disk cache full": **Make room** removes the least recently
  used cached data of other folders until it fits (the window says how much it removes), or
  **Don't cache this folder now**.
- **An update that grows a cached folder** while the cache is 80 % full asks "Save the cache
  update?": **Save update** or **Don't cache this update now**.

Either way, the loaded data stays in RAM. HeLab asks one question at a time.

## The RAM budget

**Settings › Cache › RAM budget** is a share of the computer's RAM, in steps of 1/128: 1/8 by
default, at least 1 GiB, at most half. When loaded folders go over it, HeLab drops those no tab
is showing, least recently used first. Folders shown in tabs are never dropped, so HeLab can
use more than the budget.

Plots count too. At 50 % of the budget the status bar says so; at 75 % a window lists the
biggest plots and folders; above 80 % plots you haven't viewed lately are **released**: each
keeps a picture of itself and draws again from RAM or the disk cache when you show it (**Reload
a released plot when it is shown again**, on by default). HeLab never closes a plot, and never
releases the shown, running or Live plot.

**Large folders.** Before loading, HeLab estimates a folder's size from its TXY files. Above the
RAM budget or 10 % of RAM, a folder isn't loaded automatically: the line says
"Large folder · ~X in RAM" with **Load anyway…** and **No auto-load**. Loading it anyway asks
you to tick "I understand this may slow down or stop HeLab". Above 30 % of RAM it doesn't load.

## Your choices per folder

Right-click a folder for:

- **Don't cache this folder**: its data stays in RAM only; its tooltip says "Not cached: your
  choice".
- **Don't auto-load this folder**: selecting it no longer loads it; use **Load data**.

Each applies to that folder only, not its subfolders, and needs a data root. Clear all and
purges keep them; **Settings › Cache › Folder preferences › Clear…** resets them.

## Clearing the cache

Everything below asks first and says what goes and what stays. Loaded data stays open.

- **Settings › Cache** clears by kind (**Cached data**, **Folder summaries**, **Scan failures**,
  **Subfolder status**, **Folder listings**, **Cached analysis**, and the raw pulses and TXY data
  rows), or everything with **Clear all…** (which keeps cached analysis, folder preferences and
  presets). **Remove old entries** removes what you haven't used for a number of days.
- **Settings › Data roots › Clear cached data…** clears one data root.
- Right-click a folder › **Clear loaded data cache** clears that folder.

## What HeLab never deletes without asking

HeLab never removes your data, cached data, records, folder choices, folder constants or presets
unless you ask. The only things it tidies by itself are:

- files of cached data you removed or that a newer save replaced, after a grace period, and
  stray cache files no record refers to, once over an hour old;
- saves still waiting for your answer (Make room), after an hour;
- at startup, cache folders from older HeLab versions and log files beyond **Log files to keep**
  (Settings › General, 300 by default);
- the oldest entries of lists kept only for this session;
- loaded folders and plots, to stay within the RAM budget, as described above;
- the converter's own unfinished temporary files, once over an hour old.

## The cache folder

Each computer has its own disk cache. By default it is in `~/Library/Caches/HeLab/caches` on
macOS, `%LOCALAPPDATA%\HeLab\caches` on Windows and `~/.cache/HeLab/caches` on Linux.
**Settings › Cache** shows where, with **Open**.

To move it, use **Settings › General › Cache folder › Change…**. The new folder must be empty
or new, writable, with enough free space, and not on a network drive or in a synced folder.
HeLab pauses loading and folder checks while it moves, and keeps the cache's contents. If the
move is interrupted, HeLab finishes or undoes it at the next start.

If the cache folder also holds an older HeLab's cache, the **Older cache (store-v3)** row in
**Settings › Cache** lets you keep reading it, ignore it or clear it.

While **File › Work Offline** is on, HeLab browses and analyses cached data only, reading no
data folder or server.
