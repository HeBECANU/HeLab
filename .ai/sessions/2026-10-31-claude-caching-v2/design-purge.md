# The purge follow-up (Tony on Q~14, 2026-11-02): design note

Tony: "split options to purge by each type of cache too? also just a button that purges anything by age". So:
a purge by age for each type of cached data, plus one purge of everything by age. Only copies are never taken
unless a question names them.

- **Store** (`cache_store.py`):
  - `purge_datasets(cutoff)` becomes `purge_cached(cutoff, kinds)`, where `kinds` is any of `datasets`, `txy` and
    `raw`.
  - `datasets` removes datasets. `txy` removes TXY layers with their segments and their folders' views (a view
    without its layer is incomplete, as in `_remove_txy_rows`). `raw` removes raw layers.
  - Layers count as old by `last_used < cutoff AND gone_at IS NULL`, as now, so only copies stay.
  - Everything happens in one transaction with the same epochs and generations as today, so a running save can't
    bring the data back.
  - store-v3 has only `datasets`, so a purge there does just what it does today.
- **Helper** (`io_ops/admin.py`): `purge` takes `what` = `datasets` | `txy` | `raw` | `records` | `results` |
  `all`, all with one `cutoff`.
  - `all` covers the cached-data kinds the store has, folder records (scan failures only with the checkbox, as
    now) and cached analysis.
  - It sends the same `removed` events as each purge on its own.
  - The GUI and the helper ship together, so there's no older `what` to keep; `datasets` becomes datasets only.
- **Estimates** (`purge_estimate`): one function returns each kind's folders and bytes, read from the inventory's
  ages (C2S2-2's `txy` and `raw` rows), and `all` adds them up. Each estimate uses the same comparison as its
  purge.
- **Settings › Cache, "Remove old entries"**:
  - In store-v4, the "Cached data" row splits into "Cached data", "TXY data" and "Raw pulses", each with its own
    days, estimate and Remove…. store-v3 shows only "Cached data", as today.
  - Folder records and cached analysis keep their rows.
  - A last row, "Everything not used or checked in the last [N days]", has an estimate and a Remove…. Its
    question names each part and its size, says "Only copies stay (Make room names them).", and says what
    happens to scan failures.
  - These are one-line rows with no added padding, each with an accessible name and ID (`purge_txy`, `purge_raw`,
    `purge_all`).
- **Tests:**
  - each kind's purge removes only that kind and keeps only copies;
  - `all` removes every kind;
  - each estimate equals what its purge removes (temp stores);
  - the question texts, including singular and plural;
  - the rows show only in store-v4;
  - accessible names.
- **Not changed:** only copies, Make room, trim, the budget, housekeeping, the switch (off), and no new setting.

## Questions (for CoCo; proposed answers built unless told otherwise)

- **P~1** Does "Everything" include folder records and cached analysis, or only the three cached-data types?
  Proposed: everything, since Tony said "anything", with the records' age read as "not checked" and the
  question saying so.
- **P~2** One days box for each row, or one shared box? Proposed: one each, as today, and "Everything" has its
  own.
