# Labcam

Watches the lab rack camera (an MJPEG stream, e.g. the Raspberry Pi's ustreamer at `:8081`) and checks each instrument:

| Instrument | Kind | Says |
|---|---|---|
| Left top / left middle scope | `trace` | the signal's shape (flat thin line, wavy, block, empty screen) and height (0 top, 1 bottom); `ok` = a flat line within `tolerance` of the middle |
| Wavemeter, Power | `wavemeter` | the wavelength (nm) or frequency (GHz), and the power, by OCR; unsure digits show as `?` |
| Lock-in needle | `needle` | the needle's offset from the centre (-1 … 1); `ok` within `tolerance` |
| Lock-in reading | `segments` | the 7-segment number beside the needle, read segment by segment (no sign); `ok` within ±`tolerance` (0.3) |
| Scope dot | `dot` | whether the spot moved more than `still` (a fraction of the screen's width, 0.1) in the last `window` s, or disappeared (`ok` = still, `want`) |
| People | `motion` | movement outside the instruments' regions (`off` = someone moving, drawn blue; `moved`: the share of the view that changed; how sure: how clearly its largest moving patch is above or below `min_area`) |

It serves a page with the overlay stream, a table of every reading (with how sure it is), the log, and a
region editor. Statuses: `ok`, `off` (amber), `unknown` (grey: couldn't tell; never a guess).

**Timescales.** The camera sends 25 fps; labcam decodes 10 a second (`stream_fps`, also the overlay's rate) and
checks the instruments 5 times a second (`analysis_hz`), each time on the average of the last 3 decoded frames
(`average_frames`: camera noise and a single odd frame fade; an oscillating trace smears into the band it
covers, which reads as not flat). Each instrument's result is then voted over its last second of checks
(`smooth`): the most common status and shape win, with the medians of their numbers, so a stray
misdetection is outvoted. A new status shows once it has lasted 1 s (`settle`); a laser shows lost after
1.5 s and locked after 10 s. The wavemeter reads each field every 0.5 s (low power 5 s), or at every check on up to 4 cores with
"read the wavemeter at every check" ticked (Debug), and votes over the last
10 s by itself; reads without the right number of digits don't vote but lower how sure.

## Power and the Debug section

The page's **Debug** section (closed by default) holds the power mode, the wavemeter's "read at every check"
and the overlay's text size and line width; they're saved in `config.local.json` → `settings`.

- **Full:** each wavemeter field read every 0.5 s, 5 checks a second, 10 frames decoded a second.
- **Low power:** every 5 s, 2 checks and 5 frames a second. Locks still show lost after 1.5 s and locked after
  10 s, and history still gets a row every 5 s.
- **auto** (default) goes low after 10 min with no page in focus, or 1 h with no input on a page, and back at
  the next focus or input; **Low power now** goes low until the next input. "keep full speed" and "keep low
  power" stay as set.
- The overlay is drawn and encoded only while someone watches the stream (or `/frame.jpg` was asked for in
  the last 10 s); each OCR read uses one core.

## Laser locks

`config.json` → `locks` names each laser's signs (see `labcam/locks.py`):

- **He3**: the left middle scope shows a flat thin line in the middle (`left_middle:ok`). A block, a wavy or
  spiky trace, or an empty screen means it isn't locked.
- **He4**: the left top scope shows a flat line in the middle, the scope dot is still, the lock-in needle
  is in the middle and the lock-in's number is within ±0.3 (`left_top:ok`, `scope_dot:still`, `lockin:middle`,
  `lockin_value:middle`). An unsure last digit doesn't matter when it can't change that (0.0? is within).

A laser is `locked` only once its signs have held for 10 s, `lost` as soon as one fails for 3 analyses (about
1.5 s). A sign that can't be told (unreadable, covered) is left out when the laser has other signs, so one
unknown He4 sign doesn't make He4 unknown; the laser is `unknown` only when none of its signs can be told (or
its only sign can't). Each comes with how sure it is (its surest failing sign; or, when locked, its least sure
sign told, times the share of its signs told) and why. The banner on the page shows them; changes are logged (a loss as a
WARNING).

**Someone in front.** Before reading an instrument, labcam checks whether it may be hidden: movement over its
region (from the People check), or its surroundings (a band around the region: the scope's frame, the
meter's case) unlike usual. "Usual" is a running average taken while nothing is in front, so slow changes
don't count; a change lasting 10 minutes becomes the new usual (logged). A hidden instrument reads
`covered?` (`unknown`), and a locked laser whose signs can't be told only because of that stays locked,
half as sure, with "now covered: …" as the reason. A failing sign while someone is moving (People) or one of
the laser's instruments is covered makes it `unknown` ("lost? can't tell while …"), not `lost`: it's lost once
the room is quiet (People holds movement 5 s) and nothing is covered. Alignment, too, waits while someone is
moving, and a covered box keeps its own transform. Its surroundings' change is in `/state.json`
(`surround_change`, usually 2–4; `cover_change`, default 15, is the limit).

A trace's shape is measured against its empty screen's colour (`background`, [B, G, R], taken from a frame
with a thin line), since a block can cover most of the screen. If the light or the scope's display changes,
take it again from a locked frame.

## History

Under `data/`, a row every 5 s and at every lock change (so no loss falls between rows; about 2.5 MB a day,
earlier days gzipped to about a tenth at start and at midnight; days older than 7 are deleted):
- `locks-<date>.csv`: each laser's state, how sure, and why;
- `history-<date>.csv`: the locks, then each instrument's status, how sure (0–1) and numbers (trace shape, level, thickness and
  waviness; wavemeter value; power; needle offset; dot spread and position; movement 0/1 and the share of the view that changed).

The page plots them with Plotly (served by labcam from the plotly package, no internet needed; 15 min to 7
days, one figure on a shared time axis, hover for each point's time, value, status and, for a lock, why; drag to
zoom): the locks as coloured bands (paler when less sure), then people's movement (blue bars, how sure on the right),
the wavemeter and power, trace thickness and level, the needle and the dot's movement. `/locks.csv` and
`/history.csv` download today's files.

## Set up (once)

Needs [uv](https://docs.astral.sh/uv/). The wavemeter is read with RapidOCR, installed with labcam;
Tesseract is optional, used only where RapidOCR can't be installed.

macOS:

```bash
cd side_projects/labcam
uv venv --python 3.13 .venv && uv pip install -p .venv -e '.[test]'
```

Windows (PowerShell or cmd):

```bat
cd side_projects\labcam
uv venv --python 3.13 .venv
uv pip install -p .venv -e .[test]
```

Without RapidOCR, labcam finds Tesseract on the PATH, in `Program Files\Tesseract-OCR` or `%LOCALAPPDATA%\Programs\Tesseract-OCR`,
or wherever `LABCAM_TESSERACT` names. Its startup line says which it uses ("tesseract not found" turns the
wavemeter off).

Then tell it where the camera is: create `config.local.json` beside this README (not in Git, so the lab's
addresses stay out of the repository):

```json
{ "source": "http://<camera host>:8081/stream" }
```

## Run

```bash
.venv/bin/python -m labcam                 # Windows: .venv\Scripts\python -m labcam
```

Open `http://localhost:8090/`. Other machines (the tailnet, the lab network) open `http://<this machine>:8090/`
once the system's firewall lets the venv's Python accept connections: macOS and Windows both ask the first
time. If that is refused on a Mac, `tailscale serve --bg --http=8090 http://127.0.0.1:8090` proxies the
tailnet to it instead (open it by the machine's tailnet name then; the bare IP gets the proxy's 404). Stop
labcam with Ctrl+C.

Options: `--port` (8090), `--host` (0.0.0.0; `127.0.0.1` keeps it to this machine), `--source` (a stream URL,
or a JPEG to try it without the camera), `--debug` (DEBUG lines, e.g. every OCR read, also in the log file).

Tests: `.venv/bin/python -m pytest` (two of them need a camera frame at `tests/sample_mirrored.jpg`, kept out of
Git, and skip without it). HeLab's own pytest skips this folder: its environment has no OpenCV.

## First use

1. Open the page and check each instrument's outline sits on its screen or meter.
2. If one doesn't, press its **Edit region** and click the four corners, or drag a box.
3. Watch the table for a minute: each row says what it sees and how sure it is; `unknown` rows say why.
4. After moving the camera on purpose, press **Set reference frame**, then check the outlines again.

## The page

- **Overlay stream** (`/stream`), every reading and lock (`/state.json`), the log (`/log`), the history
  (`/history.json?hours=N`, `/history.csv`, `/locks.csv`), the un-mirrored camera frame (`/raw.jpg`).
- **Edit region**: click an instrument's four corners (top-left, top-right, bottom-right, bottom-left) on the
  picture, or drag a rectangle. Four corners follow a screen seen at an angle: the region is straightened
  before it is read, so "middle" is the middle of the screen itself. Edits go to `config.local.json` (not in
  Git); `config.json` holds the defaults.
- **Set reference frame**: regions are drawn on a reference frame (`reference.jpg`, taken at the first start).
  Every 5 s the frame is matched to it (ORB features), and the regions follow a nudged camera. The page says
  when the camera moved, or when matching failed (then the last regions are kept). After moving the camera
  on purpose, set the reference again and check the regions.

## Files

`logs/labcam.log` (a file per day, the last 7 kept), `data/locks-<date>.csv`, `data/history-<date>.csv`, `reference.jpg`, `config.local.json`, all
beside this README and ignored by Git.

## Limits (2026-10-30)

- **Wavemeter OCR is at its limit at 720p.** The digits are about 13 px tall, bold, slanted and blurred
  together. RapidOCR (2026-11-01) reads them where Tesseract can't (the power: about half the frames against
  none), in about 5 ms a read, but still mixes 8 and 6. Each frame is read four ways and every digit is voted
  on over the last 10 s; a digit without 60 % agreement shows as `?` and the reading is `unknown`. A digit can still be wrong *and* agreed on. The wavemeter's own data port,
  or a camera closer to it, is the real fix; a reader taught this display's digits from labelled frames is
  the next software step.
- **Lock-in needle:** the needle is faint at this resolution; check the region covers the meter you mean.
- **People** is movement, not person recognition: a moving cable or a light change counts too.
- **On the Pi:** the Pi 2 (4 × 900 MHz) could run it at `analysis_hz` 1 and `stream_fps` 2, with
  `apt install python3-opencv tesseract-ocr`, reading ustreamer at `http://localhost:8081/stream`. Untested;
  the wavemeter's OCR (about 0.3 s per field on an M-series Mac) would be the slowest part there.
- **Windows:** checked 2026-10-30 on a lab Windows 11 PC (Python 3.13 via uv): tests pass, a live run reads the
  stream (decode 8 ms, analysis 30 ms a frame) and serves the page. Tesseract wasn't installed there, so the
  wavemeter's OCR is untested on Windows.
