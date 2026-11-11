# Laserlock

Locks a laser's frequency: reads a HighFinesse wavemeter (WS8) channel and steers the laser through a Rigol
DG1022's DC offset, with a PI loop. Windows only (the wavemeter's `wlmData.dll`).

| Part | What it does |
|---|---|
| `devices.HighFinesse` | reads one channel's frequency (THz) through `wlmData.dll`. The DLL only talks to the WLM server program (`wlm_ws8.exe`); if it isn't running, laserlock starts it **hidden** (about 15 s) and closes it again on exit. If it was already running, it is left alone. |
| `devices.DG1022` | sets one channel's DC offset, nothing else (never output on/off, waveform or amplitude). Offsets in 0.1 mV steps (its resolution), **hard limit 0–7 V**, at most one command every **100 ms**. |
| `controller.PILock` | the PI loop (pure Python, tested). |
| `engine.Engine` | the loop thread: a PI step on each new measurement, the newest voltage written when the DG1022's turn comes. |
| `gui.MainWindow` | readings, setpoint, gains, limits, Lock / Calibrate, plots of the error and the output. |
| `sim` | a simulated laser, wavemeter and DG1022 (`--sim`). |

## The DG1022's limits (measured 2026-11-11)

- Its USB **stops answering** when commands come too close together — always below 5 ms, once at 20 ms —
  and only a power cycle brings it back; it froze twice more in use on 2026-11-11. Laserlock keeps **100 ms**
  between any two commands (configurable as `min_interval_s`; write and verify
  at 50 ms: 50/50 correct, about 18 verified or 20 unverified updates a second).
- Laserlock holds an **exclusive VISA lock** on it while running: another program's commands between
  laserlock's would break the spacing (that hung it on 2026-11-11). Other VISA programs get
  "resource locked"; laserlock won't start while another program holds it.
- The offset keeps 4 decimals in volts (0.1 mV); finer values are rounded.
- While a program controls it, its screen stops updating and its keys are locked (remote mode); it still
  answers over USB. Its **Local** key (on Burst) gives the front panel back.
- Set CH1 up on the front panel (DC, or ARB DC, output on) before locking; laserlock only moves the offset.
  If it stops answering, the window says "fault" and the voltage stays where it was.

## The loop

The error is f − setpoint in MHz; the output is the integrator plus the P term, so engaging starts from the
voltage already applied. Each update:

- the output stays within **Output min/max** (inside 0–7 V) and moves at most **Max step** from the last;
- when a limit cuts the output the integrator is reset to what was applied (no windup);
- no reading (low signal, …) or an error beyond **Capture range** (a mode hop, a wrong reading: the WS8 here
  gave readings about 19.7 GHz off now and then, 2026-11-11) holds the voltage.

**Calibrate tuning** (unlocked only) steps the output to V − step and V + step, averages the frequency at
each, returns to V, and sets the tuning sign and gains from the slope: P corrects a fifth of an error per
update, I closes it in about 10 updates (at least 1 s). Start there, then tune by hand. The step moves the
laser by `slope × step`: keep it small enough not to hop modes.

## Sweep and auto-lock

**Sweep** ramps gently (50 mV per write, 0.5 V/s) to *From*, steps to *To*, and plots the frequency at each step (the
median of the largest group of readings within 1 GHz of each other, so far outliers drop out); then
ramps back.

**Auto-lock to setpoint** sweeps the same way, then:

1. splits the sweep into hop-free stretches (a stretch ends at a missing reading or a jump well off the
   trend: more than 5× the typical step and at least 300 MHz);
2. picks where the setpoint is crossed inside a stretch with the most room on both sides;
3. ramps back to *From* and up to that voltage (the sweep's direction, for the piezo's hysteresis);
4. sets the sign and gains from the local slope, **limits the output to that stretch** (so the loop can't
   push it over a mode hop), and locks.

Both refuse (and write nothing) while the DG1022's output is off. Abort stops them and ramps back.

## Set up (once)

Needs [uv](https://docs.astral.sh/uv/), NI-VISA (or Keysight VISA) and the HighFinesse software installed.

```bat
cd side_projects\laserlock
uv venv --python 3.13 .venv
uv pip install -p .venv -e .[test]
```

## Run

```bat
.venv\Scripts\python -m laserlock          :: the lab's wavemeter channel 1 → DG1022 CH1
.venv\Scripts\python -m laserlock --sim    :: try it without the lab
```

Options: `--wm-channel N`, `--out-channel 1|2`, `--resource <VISA resource>` (default: the DG1022 found on
USB). Defaults are in `laserlock/config.py`; a `config.json` beside this README overrides them, and the
window saves its last setpoint, gains and limits to `config.local.json` (not in Git). Closing the window
releases the lock and leaves the output where it is. **Log to CSV** writes `logs/laserlock-<time>.csv`; the
log is `logs/laserlock.log`.

## Tests

```bat
.venv\Scripts\python -m pytest
```

They use the simulator and a fake VISA session, never the instruments.
