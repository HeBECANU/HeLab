# Write an analysis script

An analysis script is a Python file with a class that derives from `DatasetAnalysis`. HeLab lists
it in the Scripts panel; clicking one of its actions runs it on the data the current tab shows and
draws the result in a new plot.

## Load and reload your scripts

Keep your scripts in a folder of your own, anywhere on your computer.

1. In the Scripts panel, click **Load Scripts...** and choose the folder.
2. Pick your script's group in the **Group** drop-down. Each script is listed with a button for
   each of its actions (the first two).
3. Select a folder in a tab and let its data show, then click the action's button.

HeLab imports every `.py` file directly in the folder (not its subfolders), in name order. One
file may hold several scripts. A file with no script in it that your scripts import is a helper
module: put shared code there and `import` it as usual. Your scripts can also import the
packages HeLab itself runs with, such as NumPy, SciPy and Matplotlib.

HeLab remembers the folder and loads it again at each start, once the window has shown. A folder
on a network share, or one HeLab was loading when it last stopped, waits for **Reload** instead,
and an amber line under the buttons says so.

After you edit a script, click **Reload**: HeLab imports the folder's scripts and helper modules
again, and open plots of them run again on the new code. If any of their runs is still computing,
the button reads **Reload (waiting)** until it ends. To reload whenever you save a file, turn on
**Reload when a script is saved** in the menu on the arrow beside **Load Scripts...**. That menu
also lists your script folders, each with **Reload** and **Remove from the list**.

A file that doesn't load is listed at the end of the scripts, under
`⚠ N script files didn't load`: hover over its line for the traceback, or double-click it for a
window with the details. Fix it and click **Reload**. A plot whose script didn't reload keeps
running the code loaded before, and says so in amber.

## A complete example

This script plots the mean arrival time (T) of each shot's events against shot number:

```python
"""Mean arrival time per shot: an example HeLab analysis script."""
from dataclasses import dataclass
from typing import Any, List, Optional

import numpy as np
import numpy.typing as npt
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QWidget

from helab.analysis.backends import MatplotlibPane, matplotlib_pane
from helab.analysis.follow import LivePolicy
from helab.analysis.parameters import ParameterSpec
from helab.analysis.results import AnalysisContext, AnalysisResult
from helab.analysis.selection import SHOT_SPECS, select_shots
from helab.scripts.base import DatasetAnalysis, ScriptMetadata

MIN_EVENTS = ParameterSpec(
    "min_events", "Minimum events", "int", 10, (1, 1_000_000), group="Mean T",
    tip="Shots with fewer events than this are left out.")


@dataclass(frozen=True)
class MeanT:
    shots: npt.NDArray[np.int64]
    mean_t: npt.NDArray[np.float64]  # seconds after the trigger
    skipped: int


class MeanArrivalTime(DatasetAnalysis):
    def get_metadata(self) -> ScriptMetadata:
        return self.create_metadata(
            name="Mean arrival time",
            description="Mean T of each shot's events, against shot number",
            group="My scripts",
            file_path=__file__,
            analysis_id="mylab.mean_arrival_time",
            version="1",
        )

    def get_actions(self) -> List[str]:
        return ["Plot"]

    def parameters(self, action_name: str) -> List[ParameterSpec]:
        return [*SHOT_SPECS, MIN_EVENTS]

    def live_policy(self, action_name: str) -> LivePolicy:
        return LivePolicy(every_shots=5)

    def compute(self, action_name: str, context: AnalysisContext) -> MeanT:
        # Worker thread: no Qt here, and the view's arrays are read-only.
        minimum = int(context.parameters[MIN_EVENTS.name])
        shots: list[int] = []
        means: list[float] = []
        skipped = 0
        for shot in select_shots(context.view, context.parameters):
            context.check()  # stops here if the user cancelled the run
            events = context.view.shots[shot]  # (n, 3): T in s, X and Y in m
            if len(events) < minimum:
                skipped += 1
                continue
            shots.append(shot)
            means.append(float(events[:, 0].mean()))
        return MeanT(np.array(shots, dtype=np.int64), np.array(means, dtype=np.float64), skipped)

    def render(self, result: AnalysisResult, parent: Optional[QWidget] = None) -> QWidget:
        # GUI thread: build the plot from what compute returned.
        figure = Figure(layout="constrained")
        draw(figure, result)
        return MatplotlibPane(figure, parent)

    def update(self, widget: QWidget, result: AnalysisResult) -> bool:
        # A rerun (e.g. Live's next shots) redraws in place, keeping the user's zoom.
        pane = matplotlib_pane(widget)
        if pane is None:
            return False
        pane.redraw(lambda figure: draw(figure, result))
        return True


def draw(figure: Any, result: AnalysisResult) -> None:
    data: MeanT = result.data
    axes = figure.add_subplot()
    axes.plot(data.shots, data.mean_t * 1e3, "o-", markersize=3)
    axes.set_xlabel("Shot number")
    axes.set_ylabel("Mean T (ms)")
    note = f" · {data.skipped} shots below the minimum" if data.skipped else ""
    figure.suptitle(f"{result.input.short()} · {len(data.shots)} shots{note}", fontsize=9)
```

What each part does:

- **`get_metadata`** names the script. `name` is what the Scripts panel and the plot show,
  `group` the section it is listed under. `analysis_id` is a stable ID that never changes, even
  if you rename the script; bump `version` whenever the output changes. Every result records
  both, with a hash of the script's file.
- **`get_actions`** lists the actions, each a button in the Scripts panel. HeLab passes the
  action's name back to every other method as `action_name`.
- **`parameters`** declares the plot's settings, shown in the Settings panel. A `ParameterSpec`
  gives the key, the title, the kind (`"float"`, `"int"`, `"bool"`, `"choice"` or `"text"`), the
  default, and optionally limits, a unit suffix, a tooltip and a `group` (its section). In
  `compute`, `context.parameters` holds a value for every parameter you declared, checked and
  clamped to its limits.
- **`compute`** does the numerical work and returns anything `render` can draw; a small dataclass
  works well. It reads the data only from `context.view`, a `DatasetView`: `view.shots` maps each
  shot number to its events, an (n, 3) array of T (s after the trigger), X and Y (m), in
  ascending shot order. `view.events(shots)` joins chosen shots into one array.
- **`render`** builds the plot's widget from the result; `result.data` is what `compute`
  returned. `MatplotlibPane` shows a Matplotlib figure with its toolbar.
- **`update`** (optional) shows a newer result in the plot already drawn. Return `False` to have
  `render` draw it anew instead.

!!! warning "Dataclasses and `from __future__ import annotations`"
    In a script file that starts with `from __future__ import annotations`, a `@dataclass` with a
    field such as `count: int` stops the file from loading, with
    `'NoneType' object has no attribute '__dict__'`. Leave out the `__future__` import, as the
    example does, or define the dataclass in a helper module beside the script.

## Threads and shared data

- **`compute` runs on HeLab's analysis worker thread.** Don't create or touch Qt widgets there,
  and don't read files or watch folders: everything the run needs is in `context`.
- **`render` and `update` run on the GUI thread.** Keep them quick: do the heavy work in
  `compute`.
- **The view's arrays are shared and read-only.** HeLab and other plots use the same arrays, and
  NumPy refuses to write to them. Call `.copy()` on an array before changing it.
- **Let a long run stop.** Call `context.check()` between steps or in long loops: it ends the run
  when the user cancels it. Or test `context.cancelled()` and return early.
- **Use Matplotlib's `matplotlib.figure.Figure`, never `pyplot`.**
- **Errors don't stop HeLab.** If `compute` or `render` raises, the plot says it failed and why
  (a plot already showing a result keeps it, with the error above it); if another method raises,
  HeLab logs it and goes on.

## Choose shots with the shared Shots settings

Adding `SHOT_SPECS` from `helab.analysis.selection` to your parameters gives your plot the same
**Shots** section as HeLab's own plots: all shots, the last N or a range of shot numbers, from a
first shot. `select_shots(context.view, context.parameters)` returns the chosen shot numbers in
ascending order, and HeLab records them as the shots the run used.

## Follow Live

While [Live](live.md) watches a folder, its plots run again on the newest shots. A run is never
cancelled for new data: shots that arrive meanwhile wait, and the next run takes them all. By
default a plot runs again on every new shot. A slow analysis can ask for fewer reruns from
`live_policy`: `LivePolicy(every_shots=5, min_delay=10.0)` reruns once five new shots have come,
and no sooner than 10 s after the last run ended. Each plot's **Live** settings (**Follow Live**,
**Rerun every N new shots**, **Wait after a run**) start from your policy and can change it.

`context.live` is `True` for a rerun that follows Live, so a costly analysis can do less then.
A view can have no shots at all (Live started before the folder's first shot), so make sure
`compute` and `render` handle empty data.

## More in the API reference

The [API for script writers](../reference/api/index.md) documents every hook and helper:

- [the script contract](../reference/api/script.md): `DatasetAnalysis`, `ScriptMetadata` and the
  optional hooks, such as `describe_run` (the plot's source lines), `minimum_size` and
  `parameter_warnings`;
- [the dataset view](../reference/api/dataset-view.md): `DatasetView` and its shot times;
- [parameters](../reference/api/parameters.md): `ParameterSpec`, including SI units and
  settings that show only under one choice;
- [shot selection](../reference/api/selection.md): the Shots, View range and newest-shot settings;
- [fits](../reference/api/fits.md): the fit helpers HeLab's own plots use.
