# HeLab

HeLab, the **Helium Experiment Lab Analysis Board**, is a desktop app for analysing a helium BEC
experiment's delay-line-detector (DLD) data as it comes in. It browses the lab's data folders,
loads and caches each shot's TXY events, follows a folder live as new shots arrive, converts raw
detector files to TXY, and runs analysis scripts as interactive plots.

It runs on macOS, Windows and Linux.

## Where to start

- **New to HeLab?** [Install it and open your first folder](getting-started/install.md).
- **Doing something specific?** The how-to guides cover
  [marking a data root](how-to/data-root.md) so HeLab can cache a folder on disk,
  [following a folder live](how-to/live.md),
  [converting raw files to TXY](how-to/convert-txy.md) and
  [writing your own analysis script](how-to/write-a-script.md).
- **Looking something up?** See the [command line](reference/command-line.md), the
  [settings](reference/settings.md), the [`.hlb` file format](hlb-format.md) and the
  [API for script writers](reference/api/index.md).
- **Want to know why it works the way it does?** Read
  [how HeLab caches data](explanation/cache.md).

## A few things HeLab always does

- It never changes or deletes your raw data files or existing TXY files. It writes into a data
  folder only the `.helab-root` marker you ask for and, if you turn it on for that folder,
  converted TXY files.
- It never reads a file that is still being written: a file modified within the last few
  seconds waits until it settles.
- It never removes your cached data, settings or presets without asking, apart from the routine
  tidying described in [how HeLab caches data](explanation/cache.md).
