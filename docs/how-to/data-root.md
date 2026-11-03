# Mark a data root (`.helab-root`)

HeLab keeps loaded data in a disk cache so that a folder opens at once next time. It does that
only for folders inside a **data root**: a folder holding a small hidden file named
`.helab-root`. This page shows how to place one and what changes when you do.

## Why a data root

Without a `.helab-root` in the folder or any folder above it, the folder uses **RAM only**: its
data, status and settings last for this session and are gone when you quit. Folder details then
shows, on its **Disk cache** row:

```text
RAM only · no .helab-root found here or above
```

The marker gives a drive or share an identity of its own. HeLab recognises the data by that
identity, not by the path it is mounted at, so the same data is the same cache entry whether a
computer reaches it as `/Volumes/Data`, `D:\` or a network share.

## Where to put it

Put the marker as high as possible: the **top folder of the drive or share** the data is on.
Every computer that uses that drive then sees the same marker. Put it lower only if that lower
folder is also shared on its own, so that other computers see it as a top folder.

## Place it

1. Right-click the folder in the tree and choose **Place .helab-root here…**, or use
   **File › Place .helab-root in “&lt;folder&gt;”…** for the current tab's selected folder (at first
   its top folder, which you can't right-click: for example the top of a drive).
2. HeLab checks the folder first and warns when it:
    - isn't the top of its drive or share: it offers **Place at &lt;top&gt;** as well as **Place
      here**;
    - is already inside another data root;
    - is a home folder (such as `/Users`, `/home` or `C:\Users`);
    - is the top of the startup disk, or the folder of mounted drives (`/Volumes` on macOS).

    With any warning, **Cancel** is the default button, so pressing Return writes nothing.
    On Windows, writing at the top of the system drive may need administrator rights; HeLab
    says so.
3. Confirm. HeLab writes the hidden file, and the folder's modified date changes once.

If the folder already has a valid `.helab-root`, HeLab uses it. It never overwrites a file it
can't read as a marker.

**No write permission?** HeLab opens **Place the data-root file manually** with the file's
exact contents. Use **Copy**, or **Save to folder…** to write `.helab-root` under its exact name
into a folder you choose, then move it into place and use **Retry / Refresh** on that folder.
The file is hidden because its name starts with a dot: press Cmd+Shift+. in Finder, turn on
**View › Show › Hidden items** in File Explorer, or press Ctrl+H in most Linux file managers.

## What you see afterwards

- The folder shows a blue **anchor** badge beside its status icon.
- Folder details' **Disk cache** row names the marker in use, for example
  `⚓ Data · /Volumes/Data/.helab-root`.
- Right-click options that need the disk cache (**Don't cache this folder**, **Don't auto-load
  this folder**, **Clear loaded data cache**) become available for its folders.

The label shown is the folder's name when the marker was made (a drive letter for a Windows
drive's top).

## Nested roots

A data root may sit inside another. Each folder uses the **nearest** `.helab-root` at or above
it. When you place one inside an existing root, HeLab warns that the inner folder gets its own
identity, and its subfolders' cached data moves to it.

## Moved or copied data

If HeLab finds the same `.helab-root` at a second location (another share or server name, a
different mapped drive, or a copied disk), it asks **Same folder or a copy?**:

- **Same folder**: both locations share one disk cache.
- **It's a copy…**: you pick which location keeps the cached data; the other gets a new
  `.helab-root` and starts with an empty cache.
- **Later** asks again the next time HeLab finds that location this session; **Remind me next
  session** stays quiet until then.

Until you answer, the new location uses RAM only. Its folders show an amber triangle beside the
status icon, the status bar shows "⚓ N to confirm", and the line under the path box offers **Review…** to
answer.

Inside a root, cached data follows each folder's path below the marker. A folder you rename or
move within the root is cached afresh.

## Settings › Data roots

In Settings (the **Settings** button in the left toolbar, or **File › Settings...**), the **Data
roots** tab lists every `.helab-root` location HeLab has seen on
this computer, with columns **Data root**, **Status**, **Last seen** and **Cached** (the size
cached below it on this computer). Select a row to see the marker's full path and its ID. Rows
for drives that aren't mounted are marked **Not mounted**.

For the selected row:

- **Show in Finder** (File Explorer, File Manager) and **Copy path** (right-click the row).
- **Clear cached data…**: removes what this computer cached below that root. The marker, folder
  flags and cached analysis stay.
- **Clear cached analysis…**: removes only the saved analysis results below that root.
- **Forget location…**: forgets this location. If its `.helab-root` is still there, the next
  listing finds it again.
- **Delete .helab-root…**: deletes the marker file. The folder and its subfolders then use RAM
  only on every computer that uses this drive, until a marker is placed again; a new marker
  starts with an empty cache.
- **Review…**: answers "Same folder or a copy?" for a waiting row.

Every one of these asks before it changes anything, with **Cancel** as the default.

See also: [How HeLab caches data](../explanation/cache.md).
