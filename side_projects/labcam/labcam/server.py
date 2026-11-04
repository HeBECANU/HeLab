"""HTTP: `/` the page, `/stream` the overlay as MJPEG (`?overlay=0` without it), `/frame.jpg` one overlay frame, `/raw.jpg` the
un-mirrored camera frame, `/state.json` every reading and lock, `/log` the recent log, `/history.csv` and `/locks.csv` today's
data, `/history.json?hours=N` the last N hours for the plots;
POST `/api/region` {name, corners} and `/api/reference` change the boxes and the reference frame;
`/api/settings` {ocr_every_check, power_mode, overlay_font, overlay_line} (saved in config.local.json);
`/api/presence` {focused, active}, a page's heartbeat for the auto power mode; `/api/lowpower` low power now."""

from __future__ import annotations

import collections
import gzip
import json
import logging
import time
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any

import cv2
import numpy as np

from . import history
from .engine import Engine, latest_csv

log = logging.getLogger("labcam.server")


class RingHandler(logging.Handler):
    """The last `size` log lines, for the page."""

    def __init__(self, size: int = 500) -> None:
        super().__init__()
        self.lines: collections.deque[tuple[int, str]] = collections.deque(maxlen=size)
        self.seq = 0
        self._lock2 = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        line = self.format(record)
        with self._lock2:
            self.seq += 1
            self.lines.append((self.seq, line))

    def since(self, seq: int) -> list[tuple[int, str]]:
        with self._lock2:
            return [item for item in self.lines if item[0] > seq]


def make_handler(engine: Engine, ring: RingHandler) -> type[BaseHTTPRequestHandler]:
    page = resources.files("labcam").joinpath("page.html").read_bytes()
    # Plotly's browser library, from the plotly package (the page needs no internet), gzipped once.
    from plotly.offline import get_plotlyjs

    plotly_js = gzip.compress(get_plotlyjs().encode("utf-8"))

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            log.debug("%s %s", self.address_string(), format % args)

        def _send(self, body: bytes, kind: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: Any, status: int = 200) -> None:
            self._send(json.dumps(data).encode(), "application/json", status)

        def do_GET(self) -> None:
            path, _, query = self.path.partition("?")
            if path in ("/", "/index.html"):
                self._send(page, "text/html; charset=utf-8")
            elif path == "/state.json":
                self._json(engine.state())
            elif path == "/log":
                after = int(query.split("after=")[1]) if "after=" in query else 0
                self._json(ring.since(after))
            elif path == "/frame.jpg":
                # The overlay is drawn only while wanted: ask for it, and wait for a fresh one.
                engine.overlay_wanted_until = time.time() + 10
                deadline = time.time() + 2
                while time.time() - engine.overlay_at > 1.5 and time.time() < deadline:
                    time.sleep(0.05)
                if engine.overlay_jpeg is None:
                    self._send(b"no frame yet", "text/plain", HTTPStatus.SERVICE_UNAVAILABLE)
                else:
                    self._send(engine.overlay_jpeg, "image/jpeg")
            elif path == "/raw.jpg":
                frame = engine.raw_frame
                ok, data = cv2.imencode(".jpg", frame) if frame is not None else (False, None)
                if ok and data is not None:
                    self._send(data.tobytes(), "image/jpeg")
                else:
                    self._send(b"no frame yet", "text/plain", HTTPStatus.SERVICE_UNAVAILABLE)
            elif path in ("/history.csv", "/locks.csv", "/readings.csv"):
                csv_path = latest_csv("locks" if path == "/locks.csv" else "history")
                if csv_path is None:
                    self._send(b"no readings yet", "text/plain", HTTPStatus.NOT_FOUND)
                else:
                    self._send(csv_path.read_bytes(), "text/csv; charset=utf-8")
            elif path == "/history.json":
                params = urllib.parse.parse_qs(query)
                try:
                    hours = min(24 * 14, max(0.05, float(params.get("hours", ["1"])[0])))
                except ValueError:
                    hours = 1.0
                self._json(history.series(hours))
            elif path == "/plotly.min.js":
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(plotly_js)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(plotly_js)
            elif path == "/stream":
                self._stream(plain="overlay=0" in query)
            else:
                self._send(b"not found", "text/plain", HTTPStatus.NOT_FOUND)

        def _stream(self, plain: bool = False) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            seen = -1
            if plain:
                engine.plain_viewers += 1
            else:
                engine.overlay_viewers += 1
            try:
                while True:
                    with engine.changed:
                        engine.changed.wait_for(lambda: engine.frame_seq != seen, timeout=5)
                        jpeg, seen = (engine.plain_jpeg if plain else engine.overlay_jpeg), engine.frame_seq
                    if jpeg is None:
                        continue
                    self.wfile.write(
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(jpeg)).encode()
                        + b"\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                if plain:
                    engine.plain_viewers -= 1
                else:
                    engine.overlay_viewers -= 1
            self.close_connection = True

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._json({"error": "not JSON"}, HTTPStatus.BAD_REQUEST)
                return
            if self.path == "/api/reference":
                self._json({"message": engine.set_reference()})
            elif self.path == "/api/snap":
                name = body.get("name")
                if name not in engine.config.instruments:
                    self._json({"error": "unknown instrument"}, HTTPStatus.BAD_REQUEST)
                    return
                self._json({"message": engine.snap(name)})
            elif self.path == "/api/region":
                name, corners = body.get("name"), body.get("corners")
                try:
                    points = [(float(x), float(y)) for x, y in corners]
                except (TypeError, ValueError):
                    points = []
                if name not in engine.config.instruments or len(points) != 4:
                    self._json({"error": "need name and corners [[x, y] × 4]"}, HTTPStatus.BAD_REQUEST)
                    return
                if abs(cv2.contourArea(np.array(points, np.float32))) < 9:
                    self._json({"error": "region too small"}, HTTPStatus.BAD_REQUEST)
                    return
                engine.set_corners(name, points)
                self._json({"message": f"{name} region saved"})
            elif self.path == "/api/settings":
                said = []
                if "ocr_every_check" in body:
                    engine.ocr_every_check = bool(body["ocr_every_check"])
                    engine.config.save_setting("ocr_every_check", engine.ocr_every_check)
                    said.append("wavemeter read " + ("at every check" if engine.ocr_every_check else "on its schedule"))
                if body.get("power_mode") in ("auto", "full", "low"):
                    engine.power_mode = body["power_mode"]
                    engine.config.save_setting("power_mode", engine.power_mode)
                    said.append(f"power: {engine.power_mode}")
                if "overlay_font" in body:
                    engine.style.font = min(1.5, max(0.25, float(body["overlay_font"])))
                    engine.config.save_setting("overlay_font", engine.style.font)
                    said.append(f"overlay text {engine.style.font:g}")
                if "overlay_line" in body:
                    engine.style.line = min(6, max(1, int(body["overlay_line"])))
                    engine.config.save_setting("overlay_line", engine.style.line)
                    said.append(f"overlay lines {engine.style.line} px")
                for line in said:
                    log.info("setting: %s", line)
                self._json({"message": "; ".join(said) or "nothing changed"})
            elif self.path == "/api/presence":
                engine.presence(bool(body.get("focused")), bool(body.get("active")))
                self._json({"low": engine.power()[0]})
            elif self.path == "/api/snap_preview":
                try:
                    drawn = [(float(x), float(y)) for x, y in body.get("corners", [])]
                except (TypeError, ValueError):
                    drawn = []
                if len(drawn) != 4:
                    self._json({"error": "need corners [[x, y] × 4]"}, HTTPStatus.BAD_REQUEST)
                    return
                self._json(engine.snap_drawn(drawn))
            elif self.path == "/api/autofit":
                said = engine.fit_boxes()
                self._json({"message": "; ".join(said) or "no screens to fit"})
            elif self.path == "/api/lowpower":
                engine.low_power_now()
                self._json({"message": "low power until the next input on a page" if engine.power_mode == "auto"
                            else f"power is set to {engine.power_mode}; choose auto to use this"})
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    return Handler


def serve(engine: Engine, ring: RingHandler, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(engine, ring))
    server.daemon_threads = True
    log.info("serving on http://%s:%d/", host, port)
    server.serve_forever()
