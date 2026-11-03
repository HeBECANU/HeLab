# API for script writers

These pages document the classes and functions an analysis script uses, generated from HeLab's
own docstrings. To get started, read [Write an analysis script](../../how-to/write-a-script.md)
first.

| Page | What it covers |
|---|---|
| [Script contract](script.md) | `DatasetAnalysis`, the class a script derives from, and `ScriptMetadata` |
| [Dataset view](dataset-view.md) | `DatasetView`, the read-only data a run gets, and its identity |
| [Parameters](parameters.md) | `ParameterSpec`, the settings a script declares |
| [Shot selection and view range](selection.md) | The Shots, view range and newest-shot parameters every plot can share |
| [Fits](fits.md) | Least-squares fits of histograms and the T/X/Y profile fits |

Everything here is plain Python with no Qt, so a script's `compute` and its tests run without
a display. Arrays a run receives are shared and read-only: call `.copy()` before changing one.
