# Run context and results

`compute` gets an `AnalysisContext`: the read-only data (`view`), the plot's parameter values
(`parameters`), the physical constants the run uses, and a way to stop when the user cancels
(`check`, `cancelled`). `render` and `update` get an `AnalysisResult`, whose `data` is what
`compute` returned, together with the record the plot dock shows.

::: helab.analysis.results.AnalysisContext

::: helab.analysis.results.AnalysisResult
    options:
      filters: ["!^_", "!^of$"]

::: helab.analysis.results.Cancelled

::: helab.analysis.results.Coverage

::: helab.analysis.results.CoverageDiff
