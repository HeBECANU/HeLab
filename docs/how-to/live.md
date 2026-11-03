# Follow a folder live

Live watches one folder while the experiment runs: each new shot joins the folder's data as soon as
its file is written, and the plots of that folder run again on the newest shots.

## Turn Live on

1. Select the folder in a tab and let its data show.
2. Click **Live** in the toolbar.

Live is also available for a folder that has no TXY files yet, before its first shot: select it
once its listing has shown it is empty, and click **Live**. The tab then shows data with no shots,
and the folder summary says `waiting for the first shot`.

Live is unavailable while the folder is still loading, while its cached data doesn't match the
folder (use **Review…** first), and while working offline (File › Work Offline). Hover over the
**Live** button to see why it is greyed out.

Live reads only the folder's own files, never its subfolders'.

## While Live is on

- **The left panel collapses**, giving its room to the plots. Live off, or an error, brings it back.
  If you had collapsed the panel yourself, it stays collapsed; open it with View › Toggle Left Panel.
- **The tab is locked**: its folder tree, path bar and Deselect, and the toolbar's Up Dir, Refresh
  and Check folder status can't be used, so the watched folder stays selected.
- **The folder summary's third line** shows Live's state, for example
  `Live · checked 2s ago · 12 new shots · 1 still being written · next check in 3 s`.
  Its tooltip has the details: checks so far, how long the last one took, and what isn't saved yet.
- **The status bar** says `Live: watching <folder> · N new shots`.

## How shots arrive

- **One check at a time.** The next check starts a fixed time after the previous one ends:
  Settings › General › **Live: check again after** (3 s by default, 0.5 to 600 s). While the
  folder hasn't changed, a check costs one look at the folder, so a slow drive isn't loaded down.
- **Files still being written are left alone.** A new file is read only once it has been
  unmodified for the settle time (Settings › General › **Read files unmodified for**, 5 s by
  default) and looks the same at two checks in a row. The line counts the others as
  `still being written`.
- **New shots stay in RAM** and are shown at once. Every 10 new shots (by default), and when Live
  stops, HeLab saves the folder to the disk cache in the background. Change the number with
  Settings › Cache › **Live: save to the disk cache every** (1 to 100,000 new shots). A folder that HeLab can't cache
  (no `.helab-root`, see [Mark a data root](data-root.md), or a folder set to Don't cache) keeps its
  new shots in RAM only, and the line says why.
- **A shot that changes soon after Live read it** (within 5 minutes) is read again, and the line
  says so for a minute. An older shot that changes, shots that disappear, or another folder now at
  the same path stop Live as a mismatch: the data no longer matches the folder.

## Plots following Live

Each plot of the watched folder reruns on the newest data. In the plot's settings, the **Live**
group decides when:

| Setting | What it does |
|---|---|
| **Follow Live** | On (the default): the plot reruns as new shots arrive. Off: the plot is pinned at the data it shows; turning it on again catches up. |
| **Rerun every N new shots** | Wait until this many new shots have arrived since the data of the last run. |
| **Wait after a run** | Rerun no sooner than this many seconds after the last run ended. |

Each analysis starts from its own defaults (the hover text on each setting names them), and a
plot never cancels a run in progress for new data. Shots that arrive meanwhile wait; the next run
uses the newest data, skipping the steps in between, so no backlog builds up. The plot's source line shows the state:
`following Live · 3 new shots waiting`, or `pinned (Follow Live off) · 5 newer shots`.

When Live stops (Live off, another tab, an error), every plot still holding shots back runs once
more at once, whatever its Live settings, so each plot ends up on the latest data.

Some plots have **Highlight the newest shot** in their settings, which marks the latest shot in its
own colour (red by default).

## When something goes wrong

If a check fails (the drive is unreachable, a mismatch, a save error), Live stops checking but
**stays on** and keeps the data: the folder summary line turns amber, reads
`Live stopped: <why>`, and offers **Retry**. Nothing retries by itself. **Retry** checks the
folder again and carries on; turning Live off instead saves the new shots it already has.

## Auto-convert while Live is on

Live can also convert the folder's raw files (`d<N>.txt`) to HeLab's TXY as they arrive. Click
**Auto-convert** on the folder summary's Live line, or in the toolbar below **Live** (it stays
there while the left panel is collapsed). Before Live starts, the same button reads
**Arm auto-convert**: Live then converts from the moment you turn it on in that folder.

- Each Live check also converts the raw files that have finished being written, using the profile
  and backend in Settings › TXY converter. The new shots join the data at the next check.
- Auto-convert is remembered for the folder until HeLab quits; Live started afresh in another
  session starts with it off.
- The Live line counts converted shots, shots still waiting, and **damaged** raw files (unchanged
  for 20 s and still failing the format checks). A damaged file gets one desktop notification, no
  TXY, and never holds up later shots. Shots converted with no hits are named in amber.
- A raw file whose read stopped early (at a line that isn't numbers, where MATLAB's converter stops
  too) is named in amber, `d3.txt read stopped at line 1010`, and gets one desktop notification:
  its TXY holds only the hits before that line.
- The arrow beside **Auto-convert** opens its menu: **Write TXY beside the raw files in this
  folder…**, **Start Live and auto-convert here when HeLab launches**, and **Notify when a
  converted shot has fewer than 100 hits…** (a desktop notification once per shot; 0 turns it off).
- A conversion error stops auto-convert, not Live: the line turns amber and **Retry** converts
  again.

See [Convert raw files to TXY](convert-txy.md) for where the TXY go and what the profiles are.

## Start Live when HeLab launches

From the **Auto-convert** menu, **Start Live and auto-convert here when HeLab launches** makes this
folder the launch folder. One folder only: choosing another replaces it. At the next launch HeLab
opens that folder alone, in one tab, turns auto-convert on and starts Live once its data shows (or
at once if it has no shots yet). If the folder can't be opened, a desktop notification says so and
HeLab doesn't retry. Working offline, the tab opens without Live.

Apart from that, Live never restarts by itself after HeLab quits.

## Turning Live off and quitting

Live turns off when you click **Live** again, switch to another tab, or close the tab. Its new
shots are then saved to the disk cache in the background.

When you quit while saves are running, a **Saving before quitting** window lists each one with how
long it has run, and closes by itself when they finish. **Quit now** quits without waiting: the
shots not yet saved stay in their files, and the next look at the folder reads them again.
