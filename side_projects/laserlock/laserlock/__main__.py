"""python -m laserlock [--sim]"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import asdict

from . import config
from .controller import HopDetector, LockSettings
from .devices import DG1022, DeviceFault, FrequencySource, HighFinesse, VoltageOutput
from .engine import Engine


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="laserlock", description=__doc__)
    ap.add_argument("--sim", action="store_true", help="a simulated laser, wavemeter and DG1022")
    ap.add_argument("--resource", help="the DG1022's VISA resource (default: found on USB)")
    ap.add_argument("--wm-channel", type=int, help="the wavemeter channel (default 1)")
    ap.add_argument("--out-channel", type=int, choices=(1, 2), help="the DG1022 channel (default 1)")
    args = ap.parse_args(argv)
    logs = config.HOME / "logs"
    logs.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(logs / "laserlock.log", encoding="utf-8")])
    log = logging.getLogger("laserlock")
    cfg = config.load()
    if args.resource:
        cfg["dg1022"]["resource"] = args.resource
    if args.wm_channel:
        cfg["wavemeter"]["channel"] = args.wm_channel
    if args.out_channel:
        cfg["dg1022"]["channel"] = args.out_channel

    source: FrequencySource
    out: VoltageOutput
    try:
        if args.sim:
            from .sim import SimDG1022, SimLaser, SimWavemeter

            laser = SimLaser()
            source, out = SimWavemeter(laser), SimDG1022(laser)
        else:
            dg = DG1022(cfg["dg1022"]["resource"], cfg["dg1022"]["channel"], cfg["dg1022"]["min_interval_s"])
            log.info("%s (%s); %s", dg.idn, dg.resource, dg.describe())
            log.info("connecting to the wavemeter (starts its server hidden if needed, ~15 s)")
            wm = HighFinesse(cfg["wavemeter"]["dll"], cfg["wavemeter"]["channel"], cfg["wavemeter"]["close_server_on_exit"])
            log.info("%s", wm.describe())
            source, out = wm, dg
    except DeviceFault as e:
        log.error("%s", e)
        return 1

    from PyQt6.QtWidgets import QApplication

    from .gui import MainWindow

    hops = HopDetector(float(cfg["hops"]["min_jump_mhz"]), int(cfg["hops"]["confirm"]),
                       min_hold_s=float(cfg["hops"]["min_hold_s"]))
    engine = Engine(source, out, config.lock_settings(cfg), log_dir=logs, hops=hops)

    def save(settings: LockSettings, calibration: dict[str, float]) -> None:
        cfg["lock"] = asdict(config.clamp(settings))
        cfg["lock"].pop("max_dt", None)
        cfg["calibration"] = calibration
        config.save_local(cfg)

    app = QApplication(sys.argv[:1])
    title = f"Laser lock — {source.describe()} → {out.describe()}"
    win = MainWindow(engine, cfg["calibration"], save, title, sweep=cfg["sweep"], presets=cfg["presets"], ui=cfg["ui"])
    engine.start()
    win.show()
    try:
        code = app.exec()
        cfg["sweep"] = win.sweep_settings()
        cfg["presets"] = win.presets()
        cfg["ui"] = win.ui_state()
        cfg["hops"]["min_jump_mhz"] = engine.hops.min_jump_mhz
        config.save_local(cfg)
        return code
    finally:
        engine.stop()  # holds the last voltage
        out.close()
        source.close()


if __name__ == "__main__":
    sys.exit(main())
