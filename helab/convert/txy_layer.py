"""A TXY layer's segment as caching v2 stores it (stage 2 design addendum §3): one ``.hlb`` of ``kind``
``txy`` holding some shots of one folder's layer (``matlab``, or ``helab:<profile hash>``).

Arrays:
- ``shots`` (``<i8`` [k]): the shots, ascending;
- ``offsets`` (``<i8`` [k+1]): shot ``i``'s hits are rows ``offsets[i]:offsets[i+1]``;
- ``hits`` (``<f8`` [N, 3]): T (s), X (m), Y (m), the arrays a load holds;
- ``problematic`` (``|u1`` [k]): 1 where the shot's TXY had empty fields or couldn't be read whole, as a
  load records it.

Meta: ``layer``, ``profile_hash`` ("" for ``matlab``), ``tags``, ``precision``. The precision is ``g8``:
the values the 8-significant-figure text parses to (MATLAB's TXY, and ``m19v1``), or ``f64``: full float64
(newer tags, Q19.6). zstd 9 with no shuffle: the design note measured 0.32× the TXY text, against 0.58 with
a byte shuffle.

Qt-free; NumPy and ``helab.utils.hlb``.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from helab.utils import hlb

KIND = "txy"
MATLAB = "matlab"
HELAB_PREFIX = "helab:"
PRECISIONS = ("g8", "f64")


def helab_layer(profile_hash: str) -> str:
    """The layer a HeLab profile's TXY go in: one per profile content hash (Q22.2)."""
    return HELAB_PREFIX + profile_hash


def profile_hash_of(layer: str) -> str:
    """A HeLab layer's profile hash; "" for ``matlab``."""
    return layer[len(HELAB_PREFIX):] if layer.startswith(HELAB_PREFIX) else ""


def pack_segment(shots: Mapping[int, npt.NDArray[Any]], *, layer: str, problematic: Sequence[int] = (),
                 tags: Sequence[str] = (), precision: str = "g8",
                 maker: Mapping[str, Any] | None = None) -> bytes:
    """The ``.hlb`` of ``shots`` (shot → float64 (n, 3) hits) of one layer."""
    if precision not in PRECISIONS:
        raise ValueError(f"Not a TXY precision: {precision!r}")
    order = sorted(int(shot) for shot in shots)
    arrays = [np.asarray(shots[shot], dtype="<f8").reshape(-1, 3) for shot in order]
    offsets = np.zeros(len(order) + 1, dtype="<i8")
    if arrays:
        offsets[1:] = np.cumsum([len(array) for array in arrays])
    hits = np.concatenate(arrays) if arrays else np.empty((0, 3), dtype="<f8")
    flagged = set(int(shot) for shot in problematic)
    return hlb.pack({"shots": np.asarray(order, dtype="<i8"), "offsets": offsets,
                     "hits": np.ascontiguousarray(hits, dtype="<f8"),
                     "problematic": np.asarray([shot in flagged for shot in order], dtype="|u1")},
                    kind=KIND, maker=maker, shuffle=False,
                    meta={"layer": layer, "profile_hash": profile_hash_of(layer), "tags": list(tags),
                          "precision": precision})


def unpack_segment(data: bytes) -> tuple[dict[int, npt.NDArray[np.float64]], set[int], dict[str, Any]]:
    """A segment's shots (shot → read-only float64 (n, 3)), its problematic shots and header; ``hlb.HlbError``
    for anything that isn't a TXY segment this HeLab reads whole."""
    header, arrays = hlb.unpack(data)
    if header.get("kind") != KIND:
        raise hlb.HlbError("Not a TXY segment")
    try:
        shots, offsets, hits, flags = (arrays[name] for name in ("shots", "offsets", "hits", "problematic"))
    except KeyError as exc:
        raise hlb.HlbError(f"A TXY segment without its {exc.args[0]!r} array") from None
    count = len(shots)
    if (shots.ndim != 1 or offsets.shape != (count + 1,) or hits.ndim != 2 or hits.shape[1] != 3
            or flags.shape != (count,) or (count and (offsets[0] != 0 or offsets[-1] != len(hits)))
            or (count == 0 and len(hits)) or np.any(np.diff(offsets) < 0) or np.any(np.diff(shots) <= 0)):
        raise hlb.HlbError("A TXY segment whose arrays don't agree")
    hits = np.asarray(hits, dtype=np.float64)
    hits.setflags(write=False)
    found = {int(shot): hits[int(offsets[i]):int(offsets[i + 1])] for i, shot in enumerate(shots.tolist())}
    return found, {int(shot) for shot, flag in zip(shots.tolist(), flags.tolist()) if flag}, header
