# Run context and results

`compute` gets an `AnalysisContext`: the read-only data (`view`), the plot's parameter values
(`parameters`), the physical constants the run uses, and a way to stop when the user cancels
(`check`, `cancelled`). `render` and `update` get an `AnalysisResult`, whose `data` is what
`compute` returned, together with the record the plot dock shows.

`ram_budget` is HeLab's RAM budget in bytes (Settings › Cache) when the run was submitted, 0 when unknown. A
script may use it to say in its result's notes that the result takes a large share of it. A script that can
estimate a run's memory from its settings alone declares `estimated_bytes` (see the script API): the plot's
settings page then warns as the settings change, once the estimate reaches half the budget, with **Undo** and
**Cancel** buttons, and the run still goes ahead. Neither the budget nor the estimate is part of a result's
identity, so a change of budget never makes a saved result or a preset outdated.

::: helab.analysis.results.AnalysisContext

::: helab.analysis.results.AnalysisResult
    options:
      filters: ["!^_", "!^of$"]

::: helab.analysis.results.Cancelled

::: helab.analysis.results.Coverage

::: helab.analysis.results.CoverageDiff
