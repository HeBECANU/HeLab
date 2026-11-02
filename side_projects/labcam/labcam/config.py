"""Settings: `config.json` holds the defaults, `config.local.json` (not in Git) the boxes edited on the page."""

from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HOME = Path(__file__).resolve().parent.parent
DEFAULTS = HOME / "config.json"
LOCAL = HOME / "config.local.json"

Point = tuple[float, float]
Corners = list[Point]  # top-left, top-right, bottom-right, bottom-left, in the reference frame


@dataclass
class Instrument:
    name: str
    kind: str  # trace, wavemeter, needle, dot, motion, segments
    label: str
    corners: Corners
    options: dict[str, Any] = field(default_factory=dict)

    def option(self, key: str, default: float) -> float:
        return float(self.options.get(key, default))


@dataclass
class Config:
    source: str
    mirror: bool
    analysis_hz: float
    stream_fps: float
    jpeg_quality: int
    average_frames: int
    instruments: dict[str, Instrument]
    locks: dict[str, list[str]] = field(default_factory=dict)  # laser → its signs (see locks.py)
    settings: dict[str, Any] = field(default_factory=dict)  # the page's Debug settings (save_setting)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def save_setting(self, key: str, value: Any) -> None:
        """A page setting (power mode, overlay style…), kept in `config.local.json` → "settings"."""
        with self.lock:
            self.settings[key] = value
            local = _read(LOCAL)
            local.setdefault("settings", {})[key] = value
            LOCAL.write_text(json.dumps(local, indent=2) + "\n", encoding="utf-8")

    def set_corners(self, name: str, corners: Corners) -> None:
        """Changes one instrument's region and saves it to `config.local.json`."""
        corners = ordered(corners)
        with self.lock:
            self.instruments[name].corners = corners
            local = _read(LOCAL)
            entry = local.setdefault("instruments", {}).setdefault(name, {})
            entry.pop("box", None)
            entry["corners"] = [[round(x, 1), round(y, 1)] for x, y in corners]
            LOCAL.write_text(json.dumps(local, indent=2) + "\n", encoding="utf-8")


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def ordered(corners: Corners) -> Corners:
    """The four corners as top-left, top-right, bottom-right, bottom-left, whatever order they were clicked in
    (an upside-down region reads its trace's level upside down; left top was drawn so, 2026-11-01)."""
    cx = sum(x for x, _ in corners) / len(corners)
    cy = sum(y for _, y in corners) / len(corners)
    around = sorted(corners, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))  # clockwise on screen (y down)
    start = min(range(len(around)), key=lambda i: around[i][0] + around[i][1])  # the top-left one
    return around[start:] + around[:start]


def rect_corners(x: float, y: float, w: float, h: float) -> Corners:
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _corners(raw: dict[str, Any]) -> Corners:
    """`corners` (four [x, y]: top-left, top-right, bottom-right, bottom-left), else `box` [x, y, w, h]."""
    if "corners" in raw:
        corners = [(float(x), float(y)) for x, y in raw["corners"]]
        if len(corners) != 4:
            raise ValueError(f"corners {raw['corners']} must be four points")
        return corners
    x, y, w, h = (float(v) for v in raw["box"])
    if w <= 0 or h <= 0:
        raise ValueError(f"box {raw['box']} has no area")
    return rect_corners(x, y, w, h)


def load(path: Path | None = None) -> Config:
    """Reads the defaults (or `path`), then the page's edits on top."""
    data = _read(path or DEFAULTS)
    local = _read(LOCAL) if path is None else {}
    for key in ("source", "mirror", "analysis_hz", "stream_fps", "jpeg_quality", "average_frames"):
        if key in local:
            data[key] = local[key]
    instruments: dict[str, Instrument] = {}
    for name, raw in data.get("instruments", {}).items():
        edited = local.get("instruments", {}).get(name, {})
        merged = {**raw, **edited}
        if "corners" in edited:
            merged.pop("box", None)
        options = {k: v for k, v in merged.items() if k not in ("kind", "label", "box", "corners")}
        instruments[name] = Instrument(name, merged["kind"], merged.get("label", name), ordered(_corners(merged)), options)
    return Config(
        source=str(data.get("source", "")),
        mirror=bool(data.get("mirror", True)),
        analysis_hz=float(data.get("analysis_hz", 2.0)),
        stream_fps=float(data.get("stream_fps", 5.0)),
        jpeg_quality=int(data.get("jpeg_quality", 80)),
        average_frames=int(data.get("average_frames", 3)),
        instruments=instruments,
        locks={str(k): [str(v) for v in signs] for k, signs in {**data.get("locks", {}), **local.get("locks", {})}.items()},
        settings=dict(local.get("settings", {})),
    )
