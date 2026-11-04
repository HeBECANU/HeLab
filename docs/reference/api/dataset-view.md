# Dataset view

A `DatasetView` is the one input an analysis gets: `compute` reads it as `context.view`. It is a
read-only, immutable snapshot of the data a folder tab has loaded. Its arrays are shared with
HeLab and with other runs, and NumPy refuses writes to them: call `.copy()` before changing one.

Each shot is an `Events` array of shape (n, 3): T in seconds since the trigger, and X and Y in
metres. `events(shots)` joins chosen shots into one new array; `txy` gives a shot's T/X/Y columns.

While HeLab follows a folder live, each batch of new shots makes a new **revision** of the view
(`revision`, `added_shots`), with the same identity (`identity`).

::: helab.analysis.dataset_view.DatasetView
    options:
      filters: ["!^_", "!^chain_key$", "!^held$", "!^with_shots$"]

::: helab.analysis.dataset_view.ViewIdentity

::: helab.analysis.dataset_view.ViewKey

::: helab.analysis.dataset_view.Provenance

::: helab.analysis.dataset_view.DataRootRef

::: helab.analysis.dataset_view.Events

::: helab.analysis.dataset_view.Fingerprint

::: helab.analysis.dataset_view.txy
