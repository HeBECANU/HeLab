# See and manage what HeLab is doing

HeLab does a lot in the background: it lists and loads folders, saves their data to the disk cache,
follows folders live, converts raw files, keeps the cache tidy and runs your plots. The **Activity**
window lists all of it, says what each task is doing, and lets you stop, retry or pause it.

## Open it

- **Window › Activity**, or
- **click the status bar's message** at the bottom left (the part that ends with
  `2 running · 1 queued`).

It is an ordinary window: it stays open beside the main window while you work, and remembers its
size. While it is closed it does nothing at all.

## The Now tab

Tasks are grouped by kind:

| Group | What it holds |
|---|---|
| Loads and scans | loading a folder's data, reading cached data, listing folders, folder status checks |
| Saves | saving a folder's data to the disk cache, Live's new shots, folder settings, plot results |
| Live | each tab's Live session, with its checks, saves and auto-convert under it |
| Conversions | converting raw files to TXY from Folder details or **Convert this folder…**, and a converter question waiting for your answer |
| Cache upkeep | caching raw pulses, cleaning up and trimming the disk cache, moving the cache folder |
| Analysis | each plot's run, queued or computing |
| Scripts | test imports of your script folders, and a reload waiting for runs to end |

Each row is one line: **Task**, **Tab** (or the plot it is for), **Folder**, **State**, **Progress**
(files and per cent), **Elapsed** and **Left** (an estimate, while a load reads files). Hover over a
row, or select it, for the details: what it is, its folder, which lane of HeLab's work queue it is
in, its helper process, when it started and last made progress, and the file it is on.

The **State** column says one of:

- **running**, or what it is doing now (`checking for new shots`, `converting 2 of 5`);
- **queued**, with its place in the queue, or why it is held;
- **paused**, and why: while the current tab browses or loads, because cached data doesn't match
  several folders, or **by you** (below);
- **stopping**: it was cancelled or timed out, and its process hasn't exited yet. It keeps its place
  in the queue until it has, so nothing new starts beside it;
- **waiting for N files to settle**: files still being written are read once they have been
  unmodified for the settle time (Settings › General);
- **no progress for M:SS**: nothing has been heard from it for a while (a slow or unresponsive
  drive); HeLab stops it after a minute without progress;
- **failed**, in amber: Live or a conversion stopped on an error, waiting for **Retry**.

The status bar's counts and the Activity window's always agree: both count the same tasks.

## The History tab

The last 200 tasks that finished this session, newest first. Failed ones are marked
`✕ failed` in amber, with their error; select one to see the session's log warnings about its
folder. To keep the list useful, frequent small tasks that succeed (Live's checks, folder listings,
icons) aren't listed; every failure and every cancellation is.

## What you can do

Select a row, then:

- **Cancel** stops it the same way its own Cancel does (Live's auto-convert switch, the cache move's
  Cancel). A tab's selected load stops as the toolbar's Cancel stops it, so that tab's other
  background loads stop too. It then shows **stopping** until its process has exited. Saves of your
  data and settings can't be cancelled here: they finish by themselves, and stop on their own if they
  make no progress.
- **Retry** runs a failed task again through its own Retry (Live's, the Convert row's, the tab's, a
  plot's Run, a script folder's Reload). It waits until the attempt it replaces has exited. A failed
  load of a folder you've since left is retried by selecting the folder again: **Show in tab** takes
  you there.
- **Show in tab** shows the task's folder in its tab, or its plot.
- **Stop Live** turns Live off for that folder; its new shots are saved as always.
- **Open log** opens this session's log file.

For everything at once:

- **Pause background I/O** pauses background loads, scans and conversions, and starts no new ones,
  until you click **Resume background I/O**. The current tab, saves, Live and reading the local disk
  cache carry on. The status bar says `paused by you` meanwhile, and quitting HeLab resumes it.
- **Cancel all queued** cancels every queued task that can be cancelled, and never one that is
  running. A tab's selected load is left for that tab's own Cancel, which would stop the tab's other
  loads too. Saves stay queued.
