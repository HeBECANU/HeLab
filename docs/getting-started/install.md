# Install and open your first folder

This page takes you from nothing to a first plot of your data. You do it once; after that you
only start HeLab.

## Install from source

HeLab needs Python 3.13. The simplest way to get it is [uv](https://docs.astral.sh/uv/), which
installs Python by itself: you don't need a system Python, conda or admin rights.

1. Install uv (once per computer), then open a **new** terminal so `uv` is found:

    ```bash
    # macOS / Linux
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

    ```powershell
    # Windows
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

2. Clone HeLab and create its Python 3.13 environment:

    ```bash
    git clone --recurse-submodules {repo_url}.git
    cd HeLab
    uv python install 3.13
    uv venv --seed --python 3.13 venv
    ```

3. Activate the environment and install HeLab with the pinned versions:

    ```bash
    source venv/bin/activate       # macOS / Linux
    venv\Scripts\activate          # Windows
    uv pip install -r requirements.lock -e .
    ```

4. Start it:

    ```bash
    helab
    ```

Next time, activate `venv` and run `helab`, or run `venv/bin/helab` (macOS and Linux) or
`venv\Scripts\helab` (Windows) without activating.

!!! note
    On a lab computer, a bare `python` may be a much older interpreter. Always use the one in
    `venv`. On Windows, start HeLab from the desktop, not over SSH: an administrator SSH session
    can leave cache folders that a normal start can't write to.

## Or download a release build

Each release on the [releases page]({repo_url}/releases) has a
ready-built HeLab for macOS (`HeLab.app`), Windows and Linux. Download the archive for your
system, unpack it and open HeLab. You don't need Python for a release build.

Only one HeLab runs on a computer at a time. If you start a second one, it says "HeLab is
already running on this computer" and closes; use the window that is already open.

## Find your data folder

The window has three parts: the folder panel on the left, the plot area in the middle, and the
plot settings and **Scripts** panel on the right. With nothing loaded, the plot area says
"Select a data folder to begin".

To go to your data:

- type its path in the box at the top of the folder tab (for example `/Volumes/Data/2026/run 1`
  or `D:\data\run1`) and press Return, or
- use **File › Open**, or
- double-click folders in the tree. **Up Dir** in the left toolbar goes one level up, and
  **New Tab** opens another folder tab.

## Read the folder tree

The tree shows **Name**, **Modified**, **Counts** (shots found) and **Status** for each folder.
Counts and status appear once a folder has been checked: select it, or use **Check folder
status** in the left toolbar (its small arrow chooses folders in view, the current folder, or
subfolders to a depth). **View › Automatically Check Folder Status in View** does this for you;
it is off at first.

The status icon compares the raw `d<N>.txt` and TXY files in the folder:

- a green tick: every shot has both its raw and its TXY file;
- a yellow, amber or red icon: some shots have only one of the two (hover the row for details);
- a grey circle with a dot: no data files here, but some subfolders have data;
- a dashed circle: no data files here, and what its subfolders hold isn't known yet;
- a small grey dot: no data here at all.

Small badges beside the status icon tell you more. The ones you meet first:

- a green box: the folder's data is loaded in RAM;
- a package: the folder's data is in the disk cache (with a clock: the folder may have changed
  since);
- a blue anchor: the folder holds a `.helab-root`, so it and its subfolders can use the disk
  cache (see [Mark a data root](../how-to/data-root.md)).

Hover any row for a tooltip that spells out what is known about it, and when.

## Load a folder's shots

Select a folder: HeLab loads its TXY files into RAM by itself (**View › Toggle Auto Load to
RAM** turns this off). You can also right-click a folder and choose **Load data**.

The lines under the path box show the selected folder, how many TXY files were found and
loaded, and the folder's cache state. **Folder details**, below the tree, shows a running load's
progress and time left. Press Esc, or **Cancel** on that line, to stop a load.

If a folder is already in the disk cache, its data shows at once and the line says
"Checking for changes…" while HeLab checks the folder.

## Open your first plot

In the **Scripts** panel on the right, choose a group (for example **Basic Plots** or **DLD
Front Panel Port**) and click **Plot** beside a script such as "Counts per shot". The plot opens
in the middle, on the data the current tab has loaded; its settings show in the panel above the
scripts. If no data is loaded yet, the status bar says "load a folder's data first". Basic Plots
lists its versions, newest first: see [Plot a folder with Basic Plots](../how-to/basic-plots.md).

## Next steps

- Let HeLab keep loaded data on disk between sessions: [Mark a data root](../how-to/data-root.md).
- How the RAM and disk cache work: [How HeLab caches data](../explanation/cache.md).
- Follow new shots as they arrive: [Live](../how-to/live.md).
- Convert raw files to TXY: [Convert TXY](../how-to/convert-txy.md).
- Write your own analysis: [Write a script](../how-to/write-a-script.md).
