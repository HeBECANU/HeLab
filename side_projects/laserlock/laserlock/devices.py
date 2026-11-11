"""The two instruments: a HighFinesse wavemeter (frequency in) and a Rigol DG1022 (DC offset out).

Both are small and typed against `FrequencySource` and `VoltageOutput`, which `sim.py` also implements.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger("laserlock.devices")

# Hard limits of the DG1022's offset, whatever the lock's settings say (lab rule, 2026-11-11).
HARD_V_MIN = 0.0
HARD_V_MAX = 7.0


@dataclass(frozen=True)
class Reading:
    t: float  # monotonic time it was first seen
    thz: float | None
    status: str  # "ok" or the wavemeter's error name
    seq: int  # +1 for every new measurement


class FrequencySource(Protocol):
    def read(self) -> Reading: ...
    def describe(self) -> str: ...
    def close(self) -> None: ...


class VoltageOutput(Protocol):
    min_interval: float

    def get(self) -> float: ...
    def set(self, volts: float) -> float: ...  # returns what was applied
    def readback(self) -> float: ...
    def output_on(self) -> bool: ...
    def describe(self) -> str: ...
    def close(self) -> None: ...


class DeviceFault(RuntimeError):
    """An instrument stopped answering."""


# ---------------------------------------------------------------- HighFinesse wavemeter (wlmData.dll)

WLM_ERRORS = {0: "no value", -1: "no signal", -2: "bad signal", -3: "low signal", -4: "big signal",
              -5: "wavemeter missing", -6: "not available", -8: "no pulse", -13: "div0", -14: "out of range"}
_cCtrlWLMHide, _cCtrlWLMExit, _cCtrlWLMWait = 2, 3, 0x10
_cMeasurement = 2


class HighFinesse:
    """Reads one channel's frequency through wlmData.dll.

    The DLL only talks to the WLM server program (wlm_ws8.exe, installed with the wavemeter); if it isn't
    running it is started hidden (about 15 s) and, by default, closed again on `close`. A new measurement
    is told by a changed value: the server repeats the last one until the next exposure."""

    def __init__(self, dll: str = r"C:\Windows\System32\wlmData.dll", channel: int = 1,
                 close_server: bool = True, start_timeout_ms: int = 30000) -> None:
        self.channel = channel
        self.close_server = close_server
        w = ctypes.WinDLL(dll)  # type: ignore[attr-defined,unused-ignore]
        L, D, US, SZ = ctypes.c_long, ctypes.c_double, ctypes.c_ushort, ctypes.c_ssize_t

        def sig(name: str, res: Any, *args: Any) -> None:
            f = getattr(w, name)
            f.restype, f.argtypes = res, list(args)

        sig("Instantiate", SZ, L, L, SZ, L)
        sig("ControlWLMEx", L, L, SZ, L, L, L)
        sig("ControlWLM", L, L, SZ, L)
        sig("GetFrequencyNum", D, L, D)
        sig("GetOperationState", US, US)
        sig("Operation", L, US)
        sig("GetWLMVersion", L, L)
        self._w = w
        self.started = False
        if w.Instantiate(-1, 0, 0, 0) == 0:
            log.info("starting the WLM server hidden")
            res = w.ControlWLMEx(_cCtrlWLMHide | _cCtrlWLMWait, 0, 0, start_timeout_ms, 1)
            if not res & 1:
                raise DeviceFault(f"the WLM server didn't start (flags {res:#x})")
            self.started = True
        if w.GetOperationState(0) != _cMeasurement:
            w.Operation(_cMeasurement)
        self.version = w.GetWLMVersion(1)
        self._last: float | None = None
        self._reading = Reading(time.monotonic(), None, "no value", 0)

    def read(self) -> Reading:
        f = float(self._w.GetFrequencyNum(self.channel, 0))
        now = time.monotonic()
        if f > 0:
            if f != self._last:
                self._last = f
                self._reading = Reading(now, f, "ok", self._reading.seq + 1)
        else:
            status = WLM_ERRORS.get(int(f), f"error {int(f)}")
            if self._reading.status != status or self._reading.thz is not None:
                self._last = None
                self._reading = Reading(now, None, status, self._reading.seq + 1)
        return self._reading

    def describe(self) -> str:
        return f"HighFinesse WS{self._w.GetWLMVersion(0)} #{self.version}, channel {self.channel}"

    def close(self) -> None:
        if self.started and self.close_server:
            self._w.ControlWLM(_cCtrlWLMExit, 0, 0)
            self.started = False


# ---------------------------------------------------------------- Rigol DG1022 (USB, VISA)

DG1022_ID = "0x0400::0x09C4"


class DG1022:
    """Sets one channel's DC offset, and nothing else (never output on/off, waveform or amplitude).

    The DG1022's USB stops answering (until it is power-cycled) when commands come too close together:
    reliably at < 5 ms, once at 20 ms, and twice more in lab use on 2026-11-11 (cause unclear; both times
    soon after offset writes). Every command here waits `min_interval` (100 ms) after the previous one. Offsets are kept to 0.1 mV (its resolution) and within the hard 0-7 V."""

    def __init__(self, resource: str = "auto", channel: int = 1, min_interval: float = 0.1,
                 timeout_ms: int = 1000) -> None:
        import pyvisa

        self._errors = pyvisa.errors.VisaIOError
        rm = pyvisa.ResourceManager()
        if resource == "auto":
            found = [r for r in rm.list_resources() if DG1022_ID in r.upper().replace("0X", "0x")]
            if not found:
                raise DeviceFault("no DG1022 on USB (is it on, and seen by NI-VISA?)")
            resource = found[0]
        self.resource = resource
        self.channel = channel
        self.min_interval = max(min_interval, 0.05)
        self._suffix = "" if channel == 1 else f":CH{channel}"
        self._io = rm.open_resource(resource, timeout=timeout_ms, write_termination="\n")
        # Exclusive VISA lock: another program's commands slipped between ours would break the spacing and
        # hang it (2026-11-11). Other VISA programs are refused while laserlock runs.
        try:
            self._io.lock_excl(timeout=500)
        except self._errors as e:
            self._io.close()
            raise DeviceFault(f"another program is using the DG1022 ({e}); close it first") from e
        self._lock = threading.Lock()
        self._last_cmd = 0.0
        self.idn = self._query("*IDN?")
        if "DG1022" not in self.idn:
            raise DeviceFault(f"{resource} is not a DG1022: {self.idn}")
        self.state = self._query(f"APPL{self._suffix}?")
        self.output = self._query(f"OUTP{self._suffix}?")
        self._volts = self.readback()

    def _wait_turn(self) -> None:
        gap = self._last_cmd + self.min_interval - time.monotonic()
        if gap > 0:
            time.sleep(gap)

    def _write(self, cmd: str) -> None:
        with self._lock:
            self._wait_turn()
            try:
                self._io.write(cmd)
            except self._errors as e:
                raise DeviceFault(f"DG1022 didn't take {cmd!r} ({e}); power-cycle it if this repeats") from e
            finally:
                self._last_cmd = time.monotonic()

    def _query(self, cmd: str) -> str:
        with self._lock:
            self._wait_turn()
            try:
                self._io.write(cmd)
                time.sleep(0.02)  # it answers late if read at once (1-2 ms was enough; margin)
                return str(self._io.read()).strip()
            except self._errors as e:
                raise DeviceFault(f"DG1022 didn't answer {cmd!r} ({e}); power-cycle it") from e
            finally:
                self._last_cmd = time.monotonic()

    def get(self) -> float:
        return self._volts

    def set(self, volts: float) -> float:
        v = round(min(max(volts, HARD_V_MIN), HARD_V_MAX), 4)
        self._write(f"VOLT:OFFS{self._suffix} {v:.4f}")
        self._volts = v
        return v

    def readback(self) -> float:
        return float(self._query(f"VOLT:OFFS{self._suffix}?"))

    def output_on(self) -> bool:
        self.output = self._query(f"OUTP{self._suffix}?")
        return self.output == "ON"

    def describe(self) -> str:
        return f"DG1022 CH{self.channel}: {self.state}, output {self.output}"

    def close(self) -> None:
        try:
            self._io.unlock()
        except Exception:
            pass
        try:
            self._io.close()
        except Exception:  # closing a hung session
            pass
