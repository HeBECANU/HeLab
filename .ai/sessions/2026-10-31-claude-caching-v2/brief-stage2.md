# Brief: caching v2, stage 2 (`agent/caching-v2`, continued)

Coordinator: CoCo, 2026-11-02. **Tony's go (Chat, via Side, 2026-11-02): "I think we're ready for stage 2?"**,
with your stage 2 questions as proposed: **Q45.1–Q45.11** (your Q~3–Q~13, recorded on Ground at `66f1c21`,
`.ai/DECISIONS_TODO.md`), the 8 GB default kept (Q45.1). Also inside stage 2: **A40.3** (a signature-only
change rewrites the whole dataset: `confirm_dataset` takes the signature), **A42.1** (store-v3 results copied
into v4 on use), **A42.2** (`trim` in Make room's order, Q45.6), **A44.1** (`helab cache export` of TXY layers).
The original brief (`brief.md`), its Data safety section and stop conditions still apply. The switch stays
**off** (Q28.3; Q45.11: on only after Tony has used stage 2).

**Areas:** `cache` (owner); `io` for the loading order and Live's segments (`folder_cache.py`, `io_ops/loading.py`,
`save_held.py`, `live.py`, `helab_txy.py`); `convert` where layers are made from the raw layer. Two small floors
start **after your first checkpoint** (◆ 1 below): A39.5 (TXY and shares: the explorer and converter tab, a
helper check in `io_ops/convert.py`) and A37.1 (a raw read stopped early: the parser in `helab/convert/raw.py`,
events, Live line). Their briefs will name their paths; whoever lands second merges the first. If either needs
a change in your paths, CoCo sequences it.

## Read first

Your handoff's "Stage 2: open questions" (the decided answers), the plan `roadmaps/caching-v2.md` ("TXY layers
and the policy", stage 2), the store-v4 design note §1–§6, the readiness note (D7, gaps 2, 3, 10, 11),
`.ai/architecture/cache-store.md` (store-v4 section), `io-and-browsing.md`, `live.md`, and AGENTS.md's I/O and
cache rules.

## Base

Merge `dev/v0.0.8` first (Ground `66f1c21`: checkpoint 3's docs, Rivet's Quick Fixes 8, Tony's Labcam).

## Objective (in this order; commit each separately; stop and report to CoCo at each ◆)

1. **Stage 2 design addendum** (`design-stage2.md` in this session folder): the schema (`txy_layers`,
   `txy_segments`, `cache_policy`, the per-folder source override, per-shot fingerprint kinds), the loading
   order (layer → convert from raw → share), identity (raw fingerprint + profile hash), how each Q45.x is
   built, the `.hlb` `kind` `txy` (additive, format 1), Live's segments and compaction, pending parts, the
   v3 `matlab` seed on use, A40.3/A42.1/A42.2/A44.1, and the tests. ◆ **Send it to CoCo before code.**
2. **Store side** (no `folder_cache.py`): tables, segments, layer save/read with guards, Make room's and
   `trim`'s order (Q45.6, A42.2), Clear for TXY layers, pending parts (Q45.8), the sweep's existing rules over
   the new files, `helab cache export` of TXY layers (A44.1). ◆ **checkpoint 1: lands (inert).**
3. **Loading** (`io_ops/loading.py`, `helab_txy.py`, `folder_cache.py`): the loading order, layers made from
   the raw layer, every source mode disk cached (Q19.3, Q14.5), the per-folder override, A40.3, the v3 seed
   (Q45.5), A42.1, store-v4's `datasets` read-through (Q45.4).
4. **Live's segments** (Q45.7; `save_held.py`, `live.py`): one segment per save, compaction when it fits.
5. **UI** for what stage 2 adds (the per-folder policy and source override where Folder details or Settings ›
   Cache shows them; Make room naming layers); every control named with an ID.
6. **Integration check, switch on, in temp stores** (extend `test_caching_v2_session.py`): load → layers →
   convert from raw → Live segments → compaction → Clear → Make room's order → v3 unchanged → a cache move.
   ◆ **checkpoint 2: stage 2 lands (switch still off).**
7. **Docs proposals** in the handoff; provisional `Q~`/`A~`/`M~` from `Q~14` on.

## Rules

As in `brief.md` (owned paths now include `folder_cache.py`, `io_ops/loading.py`, `save_held.py`, `live.py`,
`helab_txy.py` for stage 2's parts; ask CoCo before any other file). Push only at checkpoints; read every Tests
and Converter backends job's log for RERUN before reporting any run. Each landing needs Assay with no open
findings and CI green on 3 OSes by run ID. No version bump, release, tag or PR. Never turn the switch on by
default.

At each ◆: `maestri ask "CoCo" "Caching v2 stage 2: <checkpoint> at <hash>, suite <N> passed, RERUNs <…>, CI <run>"`.
