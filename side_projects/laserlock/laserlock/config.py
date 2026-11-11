"""Settings: `config.json` beside the README holds the defaults; `config.local.json` (not in Git) what the
window last used. Lock limits are always kept inside the DG1022's hard 0-7 V."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .controller import LockSettings
from .devices import HARD_V_MAX, HARD_V_MIN

HOME = Path(__file__).resolve().parent.parent
DEFAULTS: dict[str, Any] = {
    "wavemeter": {"dll": r"C:\Windows\System32\wlmData.dll", "channel": 1, "close_server_on_exit": True},
    "dg1022": {"resource": "auto", "channel": 1, "min_interval_s": 0.1},
    "lock": {"setpoint_thz": 276.767676767677, "kp": 0.0, "ki": 0.0, "sign": 1, "v_min": 0.0, "v_max": 7.0,
             "max_step": 0.01, "capture_mhz": 1000.0},
    "calibration": {"step_v": 0.05, "settle_s": 1.0, "average_s": 1.0},
    "sweep": {"v_start": 0.0, "v_stop": 7.0, "step": 0.05, "settle_s": 0.1, "dwell_s": 0.2},
    # saved setpoints: {"thz": f} or {"nm": vacuum wavelength}, optional "name"; the window can add and remove
    "presets": [{"thz": 276.767676767677}, {"nm": 1083.33064456}],
    "ui": {"show_plots": True, "show_sweep": True},
    # a mode hop: a jump of at least min_jump_mhz that holds for `confirm` readings in a row
    "hops": {"min_jump_mhz": 1000.0, "confirm": 3},
}


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v  # lists replace
    return out


def load(home: Path = HOME) -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULTS)
    for name in ("config.json", "config.local.json"):
        path = home / name
        if path.is_file():
            cfg = _merge(cfg, json.loads(path.read_text(encoding="utf-8")))
    return cfg


def save_local(cfg: dict[str, Any], home: Path = HOME) -> None:
    keep = {k: cfg[k] for k in ("lock", "calibration", "sweep", "presets", "ui", "hops") if k in cfg}
    (home / "config.local.json").write_text(json.dumps(keep, indent=2), encoding="utf-8")


def lock_settings(cfg: dict[str, Any]) -> LockSettings:
    s = LockSettings(**{k: v for k, v in cfg["lock"].items() if k in LockSettings.__dataclass_fields__})
    return clamp(s)


def clamp(s: LockSettings) -> LockSettings:
    s.v_min = min(max(s.v_min, HARD_V_MIN), HARD_V_MAX)
    s.v_max = min(max(s.v_max, s.v_min), HARD_V_MAX)
    s.sign = 1 if s.sign >= 0 else -1
    return s
