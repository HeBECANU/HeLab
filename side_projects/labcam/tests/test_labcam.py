"""Labcam's detectors on drawn images and on a saved camera frame.

Run from side_projects/labcam with its own environment (`uv run pytest`). HeLab's own pytest collects this
file too and skips it, since HeLab's environment has no OpenCV.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

HOME = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HOME))

from labcam import config, history, locks, region  # noqa: E402
from labcam.detectors import Dot, Needle, Reading, TraceLevel  # noqa: E402
from labcam.wavemeter import digits_for, vote, with_point  # noqa: E402

SAMPLE = HOME / "tests" / "sample_mirrored.jpg"  # a camera frame, kept out of Git
needs_sample = pytest.mark.skipif(not SAMPLE.exists(), reason="no sample camera frame (tests/sample_mirrored.jpg)")


def inst(kind: str, **options: float) -> config.Instrument:
    return config.Instrument("x", kind, "x", config.rect_corners(0, 0, 100, 60), dict(options))


def screen(trace_y: int | None = None, background: int = 40, colour: int = 220) -> np.ndarray:
    image = np.full((60, 100, 3), background, np.uint8)
    if trace_y is not None:
        cv2.line(image, (0, trace_y), (99, trace_y), (colour, colour, colour), 2)
    return image


@pytest.mark.parametrize(("y", "status", "word"), [(30, "ok", "middle"), (8, "off", "high"), (52, "off", "low")])
def test_trace_level(y: int, status: str, word: str) -> None:
    reading = TraceLevel(inst("trace", tolerance=0.15)).update(screen(y))
    assert reading.status == status
    assert word in reading.text
    assert reading.values["shape"] == "line"
    assert reading.values["level"] == pytest.approx((y + 0.5) / 59, abs=0.03)


def test_trace_block_and_wavy() -> None:
    block = screen(None)
    cv2.rectangle(block, (0, 15), (99, 45), (220, 220, 220), -1)
    reading = TraceLevel(inst("trace")).update(block)
    assert reading.values["shape"] == "block" and reading.status == "off"
    wavy = screen(None)
    points = np.array([(x, int(30 + 20 * np.sin(x / 6))) for x in range(100)], np.int32)
    cv2.polylines(wavy, [points], False, (220, 220, 220), 2)
    assert TraceLevel(inst("trace")).update(wavy).values["shape"] == "wavy"


def test_locks() -> None:
    instruments = {
        "top": config.Instrument("top", "trace", "Top", config.rect_corners(0, 0, 1, 1), {}),
        "dot": config.Instrument("dot", "dot", "Dot", config.rect_corners(0, 0, 1, 1), {}),
        "needle": config.Instrument("needle", "needle", "Needle", config.rect_corners(0, 0, 1, 1), {"tolerance": 0.2}),
    }
    readings = {
        "top": Reading("ok", "flat line", {"shape": "line", "level": 0.5}, 0.9),
        "dot": Reading("ok", "still", {"spread_px": 0.5, "limit_px": 10.0}, 0.8),
        "needle": Reading("ok", "middle", {"offset": 0.05}, 0.7),
    }
    specs = ["top:flat", "dot:still", "needle:middle"]
    lock = locks.evaluate(specs, instruments, readings)
    assert (lock.state, lock.confidence) == ("locked", 0.7)
    readings["top"] = Reading("off", "block", {"shape": "block"}, 0.95)
    lock = locks.evaluate(specs, instruments, readings)
    assert (lock.state, lock.confidence) == ("lost", 0.95) and "block" in lock.summary
    readings["top"] = Reading("unknown", "no signal", {"shape": "none"}, 0.5)
    assert locks.evaluate(specs, instruments, readings).state == "unknown"


def test_history_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(history, "DATA", tmp_path)
    instruments = {"top": config.Instrument("top", "trace", "Top", config.rect_corners(0, 0, 1, 1), {})}
    recorder = history.Recorder()
    for shape in ("line", "block"):
        readings = {"top": Reading("ok", shape, {"shape": shape, "level": 0.5, "thickness": 0.05}, 0.9)}
        lock = locks.evaluate(["top:flat"], instruments, readings)
        recorder.record(time.time(), instruments, readings, {"He3": lock})
    data = history.series(1)
    assert data["rows"] == 2
    assert data["columns"]["He3"] == ["locked", "lost"]
    assert data["columns"]["top.thickness"] == [0.05, 0.05]
    assert (tmp_path / f"locks-{time.strftime('%Y-%m-%d')}.csv").exists()


def test_trace_dark_on_light_and_missing() -> None:
    assert TraceLevel(inst("trace")).update(screen(30, background=200, colour=30)).status == "ok"
    assert TraceLevel(inst("trace")).update(screen(None)).status == "unknown"


def test_needle() -> None:
    meter = np.full((60, 100, 3), 235, np.uint8)
    cv2.line(meter, (75, 58), (80, 5), (20, 20, 20), 1)
    reading = Needle(inst("needle", tolerance=0.2)).update(meter)
    assert reading.status == "off"
    assert reading.values["offset"] == pytest.approx(0.55, abs=0.1)
    assert Needle(inst("needle")).update(np.full((60, 100, 3), 235, np.uint8)).status == "unknown"


def test_dot_still_then_moving() -> None:
    dot = Dot(inst("dot", still=0.1, window=60))

    def frame(x: int) -> np.ndarray:
        image = np.full((60, 100, 3), 120, np.uint8)
        cv2.circle(image, (x, 30), 2, (255, 255, 255), -1)
        return image

    for _ in range(4):
        reading = dot.update(frame(40))
    assert reading.status == "ok" and reading.text.startswith("still")  # still is what's wanted by default
    reading = dot.update(frame(60))
    assert reading.status == "ok"  # one odd position is outvoted
    for _ in range(3):
        reading = dot.update(frame(60))
    assert reading.status == "off" and reading.text.startswith("moving")  # 20 px of a 100 px screen
    gone = dot.update(np.full((60, 100, 3), 120, np.uint8))
    assert gone.status == "off" and gone.text == "dot gone"


def test_wavemeter_digits_and_vote() -> None:
    assert digits_for("1083.482nm", "####.###") == "1083482"
    assert digits_for("103.482", "####.###") is None
    assert with_point("10?3482", "####.###") == "10?3.482"
    winner, shares = vote(["1083482", "1083422", "1083482"])
    assert winner == "1083482"
    assert shares[5] == pytest.approx(2 / 3)


def test_region_round_trip() -> None:
    r = region.make([(10, 10), (110, 20), (110, 80), (10, 70)])
    points = [(0.0, 0.0), (50.0, 30.0)]
    assert np.allclose(r.unmap(r.map(points)), points, atol=1e-6)
    image = np.zeros((100, 200, 3), np.uint8)
    assert region.cut(image, r, 2.0).shape[:2] == (r.height * 2, r.width * 2)


def test_config_corners_and_box(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        '{"instruments": {"a": {"kind": "dot", "box": [1, 2, 3, 4]},'
        ' "b": {"kind": "trace", "corners": [[0, 0], [5, 0], [5, 5], [0, 5]], "tolerance": 0.1}}}'
    )
    cfg = config.load(path)
    assert cfg.instruments["a"].corners == [(1, 2), (4, 2), (4, 6), (1, 6)]
    assert cfg.instruments["b"].option("tolerance", 0.5) == 0.1


@needs_sample
def test_sample_frame_scopes() -> None:
    """The saved frame (2026-10-30): both left scopes' traces sit near the middle of their screens."""
    frame = cv2.flip(cv2.imread(str(SAMPLE)), 1)
    cfg = config.load(HOME / "config.json")
    for name in ("left_top", "left_middle"):
        inst_ = cfg.instruments[name]
        reading = TraceLevel(inst_).update(region.cut(frame, region.make(inst_.corners)))
        assert reading.status == "ok", (name, reading)
        assert 0.4 < float(reading.values["level"] or 0) < 0.6


@needs_sample
def test_sample_frame_dot() -> None:
    frame = cv2.flip(cv2.imread(str(SAMPLE)), 1)
    inst_ = config.load(HOME / "config.json").instruments["scope_dot"]
    dot = Dot(inst_)
    cut = region.cut(frame, region.make(inst_.corners))
    for _ in range(3):
        reading = dot.update(cut)
        time.sleep(0.01)
    assert reading.status == "ok"  # one frame again and again: still
    assert reading.values["x"] == pytest.approx(58, abs=4)


@needs_sample
def test_hand_in_front_holds_the_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A hand over the left top scope: it reads "covered?", and He4 keeps its last state, said so."""
    from unittest import mock

    from labcam import engine
    from labcam.source import FrameSource

    monkeypatch.setattr(history, "DATA", tmp_path)
    cfg = config.load(HOME / "config.json")
    cfg.analysis_hz = 100
    monkeypatch.setattr(engine, "ANCHORS", tmp_path / "anchors")  # not the real ones
    eng = engine.Engine(cfg, FrameSource(str(SAMPLE)))
    frame = cv2.imread(str(SAMPLE))
    hand = cv2.flip(frame, 1)
    corners = np.array(cfg.instruments["left_top"].corners)
    cx, cy = corners.mean(axis=0).astype(int)
    cv2.ellipse(hand, (int(cx) - 25, int(cy) + 20), (45, 60), 20, 0, 360, (120, 150, 200), -1)
    hand = cv2.flip(hand, 1)  # back to the camera's mirrored view
    clock = [time.time()]
    with mock.patch("time.time", lambda: clock[0]):
        for image, frames in ((frame, 40), (hand, 6)):
            jpeg = cv2.imencode(".jpg", image)[1].tobytes()
            for _ in range(frames):
                eng._frame(jpeg)
                clock[0] += 0.5
            if image is frame:
                he4 = eng.locks["He4"].state
    assert "left_top" in eng.covered
    assert eng.readings["left_top"].status == "unknown"
    assert eng.locks["He4"].state == he4 and "covered" in eng.locks["He4"].summary


def test_history_thins_rows_and_reads_gzip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import gzip

    monkeypatch.setattr(history, "DATA", tmp_path)
    instruments = {"top": config.Instrument("top", "trace", "Top", config.rect_corners(0, 0, 1, 1), {})}
    line = {"top": Reading("ok", "line", {"shape": "line", "level": 0.5}, 0.9)}
    block = {"top": Reading("off", "block", {"shape": "block"}, 0.9)}
    recorder = history.Recorder()
    start = time.time() - 60
    for i in range(20):  # 0.5 s apart: rows at 0, 5 s and the lock change at 7 s
        readings = block if i == 14 else line
        recorder.record(start + i * 0.5, instruments, readings,
                        {"He3": locks.evaluate(["top:flat"], instruments, readings)})
    data = history.series(1)
    assert data["columns"]["He3"] == ["locked", "locked", "lost", "locked"]
    # An earlier day's file, gzipped, is read too.
    old = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    with gzip.open(tmp_path / f"history-{old}.csv.gz", "wt", encoding="utf-8") as f:
        f.write("time,He3\n" + time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 3600 * 20)) + ",lost\n")
    assert history.series(24)["rows"] == 5


def test_old_days_deleted_and_compressed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import gzip

    monkeypatch.setattr(history, "DATA", tmp_path)
    day = lambda n: time.strftime("%Y-%m-%d", time.localtime(time.time() - n * 86400))  # noqa: E731
    (tmp_path / f"history-{day(0)}.csv").write_text("time\n")
    (tmp_path / f"history-{day(2)}.csv").write_text("time\nx\n")
    (tmp_path / f"locks-{day(9)}.csv.gz").write_bytes(gzip.compress(b"time\n"))
    history.compress_old()
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [f"history-{day(0)}.csv", f"history-{day(2)}.csv.gz"])


def test_compress_twice_at_once_keeps_every_day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Two compress runs at midnight (one per writer) once deleted each other's .gz (2026-11-01).
    import gzip
    import threading

    monkeypatch.setattr(history, "DATA", tmp_path)
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    body = "time,He3\n" + "".join(f"{day}T00:00:{i:02d},locked\n" for i in range(60)) * 200
    for kind in ("history", "locks"):
        (tmp_path / f"{kind}-{day}.csv").write_text(body)
    runs = [threading.Thread(target=history.compress_old) for _ in range(4)]
    for t in runs:
        t.start()
    for t in runs:
        t.join()
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"history-{day}.csv.gz", f"locks-{day}.csv.gz"]
    assert gzip.decompress((tmp_path / f"history-{day}.csv.gz").read_bytes()).decode() == body
    # A CSV whose .gz already exists with the same content (a run stopped before deleting it) just goes.
    (tmp_path / f"locks-{day}.csv").write_text(body)
    history.compress_old()
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"history-{day}.csv.gz", f"locks-{day}.csv.gz"]


def test_series_breaks_lines_across_gaps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(history, "DATA", tmp_path)
    now = time.time()
    stamp = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t))  # noqa: E731
    rows = [now - 3000, now - 2995, now - 100, now - 95]  # labcam off for about 48 min between
    (tmp_path / f"history-{time.strftime('%Y-%m-%d')}.csv").write_text(
        "time,He3\n" + "".join(f"{stamp(t)},locked\n" for t in rows))
    if time.strftime("%Y-%m-%d", time.localtime(now - 3000)) != time.strftime("%Y-%m-%d"):
        pytest.skip("just after midnight")
    c = history.series(1)["columns"]
    assert c["He3"] == ["locked", "locked", None, "locked", "locked"]


def test_duration() -> None:
    from labcam.detectors import duration

    assert [duration(s) for s in (0, 45, 192, 3600, 7500, 97200, 86400 * 3 + 59)] == [
        "0s", "45s", "3m 12s", "1h", "2h 5m", "1d 3h", "3d"]


def test_relocate_finds_a_moved_instrument(tmp_path: Path) -> None:
    from labcam import relocate

    rng = np.random.default_rng(1)
    scene = cv2.GaussianBlur(rng.integers(0, 255, (300, 400, 3), np.uint8), (0, 0), 3)
    scene = cv2.normalize(scene, None, 0, 255, cv2.NORM_MINMAX)

    def with_scope(dx: int, dy: int, screen: int) -> np.ndarray:
        frame = scene.copy()
        x, y = 150 + dx, 110 + dy
        frame[y - 25:y + 85, x - 30:x + 120] = 200  # the bezel
        cv2.putText(frame, "SCOPE", (x - 20, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 40), 1)
        for k in range(4):  # buttons
            cv2.circle(frame, (x + 105, y + 10 + 15 * k), 4, (60, 60, 60), -1)
        frame[y:y + 60, x:x + 90] = screen  # the screen; what it shows changes
        return frame

    corners = [(150.0, 110.0), (240.0, 110.0), (240.0, 170.0), (150.0, 170.0)]
    anchor = relocate.anchor(with_scope(0, 0, 90), corners)
    assert anchor is not None
    still = relocate.find(anchor, with_scope(0, 0, 30), corners)  # only the screen changed
    assert still is not None and not still.moved
    found = relocate.find(anchor, with_scope(14, -17, 30), corners)
    assert found is not None and found.moved and found.shift == (14.0, -17.0)
    gone = relocate.find(anchor, scene, corners)  # nothing like it nearby: the box stays
    assert gone is not None and not gone.moved
    relocate.save(anchor, tmp_path / "a.npz")
    again = relocate.load(tmp_path / "a.npz")
    assert again is not None and again.origin == anchor.origin
    assert relocate.find(again, with_scope(14, -17, 30), corners).shift == (14.0, -17.0)  # type: ignore[union-attr]


def test_seven_segment_display() -> None:
    from labcam import segments

    # Dark segments on a light LCD: "0", "1" and "8" side by side, 40 x 80 px cells, upright.
    image = np.full((80, 120), 190, np.float32)
    bars = {"a": (8, 2, 32, 8), "b": (30, 4, 36, 40), "c": (30, 40, 36, 76), "d": (8, 72, 32, 78),
            "e": (4, 40, 10, 76), "f": (4, 4, 10, 40), "g": (8, 37, 32, 43)}
    for k, on in enumerate(("abcdef", "bc", "abcdefg")):
        for seg in on:
            x0, y0, x1, y1 = bars[seg]
            image[y0:y1, 40 * k + x0:40 * k + x1] = 110
    read, contrast = segments.read_cells(image, [(0, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 1)], 0.0)
    assert read == "018" and contrast > 50
    within = inst("segments", point=1, tolerance=0.3)
    # Unreadable checks don't vote but lower how sure; an unsure digit shows as "?".
    reading = segments.tally(within, "018", ["018", "018", "???", "018"], contrast)
    assert reading.status == "ok" and reading.values["value"] == 0.18 and reading.confidence == 0.75
    assert segments.tally(within, "048", ["018", "048"], contrast).status == "unknown"  # 0.18 or 0.48?
    unsure_last = segments.tally(within, "013", ["012", "013"], contrast)  # 0.1? is within ±0.3 either way
    assert unsure_last.status == "ok" and unsure_last.text.startswith("0.1?")
    assert segments.tally(within, "048", ["048"], contrast).status == "off"  # 0.48 is beyond ±0.3


def test_power_modes() -> None:
    from labcam import engine

    eng = engine.Engine.__new__(engine.Engine)  # only the power state, no camera
    now = time.time()
    eng.power_mode, eng._low_until_input = "auto", False
    eng._last_focused = eng._last_input = now
    assert eng.power() == (False, "a page is in use")
    eng._last_focused = now - engine.UNFOCUSED_LOW - 1  # 10 min with no page in focus
    assert eng.power()[0]
    eng.presence(focused=True, active=False)
    assert not eng.power()[0]
    eng._last_input = now - engine.IDLE_LOW - 1  # in focus but 1 h without input
    assert eng.power()[0]
    eng.presence(focused=True, active=True)
    eng.low_power_now()
    assert eng.power()[0]
    eng.presence(focused=True, active=True)  # the next input ends "low power now"
    assert not eng.power()[0]
    eng.power_mode = "low"
    assert eng.power() == (True, "kept at low power")
    eng.power_mode = "full"
    eng._last_focused = 0.0
    assert not eng.power()[0]


def test_slanted_line_is_flat_and_corners_ordered() -> None:
    # A flat trace seen at a slant (the box a little steeper than the screen) is still a flat line ...
    image = np.full((60, 100, 3), 40, np.uint8)
    cv2.line(image, (0, 24), (99, 36), (220, 220, 220), 2)
    reading = TraceLevel(inst("trace", tolerance=0.15)).update(image)
    assert reading.values["shape"] == "line"
    # ... but a steep one (a ramp across the screen) isn't.
    steep = np.full((60, 100, 3), 40, np.uint8)
    cv2.line(steep, (0, 5), (99, 55), (220, 220, 220), 2)
    assert TraceLevel(inst("trace", tolerance=0.15)).update(steep).values["shape"] == "wavy"
    # Corners clicked in any order come out top-left, top-right, bottom-right, bottom-left.
    tl, tr, br, bl = (298.0, 274.0), (373.0, 302.0), (370.0, 352.0), (298.0, 326.0)
    assert config.ordered([bl, br, tr, tl]) == [tl, tr, br, bl]
    assert config.ordered([tr, bl, tl, br]) == [tl, tr, br, bl]


def test_screen_outline_found_from_a_rough_box() -> None:
    from labcam import screens

    frame = np.full((300, 400, 3), (170, 180, 185), np.uint8)  # a light bezel
    screen = np.array([[120, 90], [290, 105], [288, 215], [118, 205]], np.int32)  # seen a little at an angle
    cv2.fillPoly(frame, [screen], (90, 60, 40))
    cv2.line(frame, (125, 150), (285, 162), (230, 200, 120), 2)  # the trace across it
    rough = [(135.0, 100.0), (270.0, 110.0), (272.0, 200.0), (130.0, 195.0)]  # drawn a bit off
    found = screens.find(frame, rough)
    assert found.ok
    assert max(np.hypot(*(np.array(a) - b)) for a, b in zip(found.corners, screen)) < 4
    assert not screens.find(np.full((300, 400, 3), 128, np.uint8), rough).ok  # no screen: kept as it is


def test_drawn_box_snaps_to_the_screen_near_it() -> None:
    from labcam import screens

    frame = np.full((300, 400, 3), (170, 180, 185), np.uint8)  # a light bezel ...
    cv2.rectangle(frame, (60, 50), (340, 260), (60, 60, 60), 3)  # ... with a dark rim further out
    screen = np.array([[120, 90], [290, 105], [288, 215], [118, 205]], np.int32)
    cv2.fillPoly(frame, [screen], (90, 60, 40))
    cv2.line(frame, (125, 150), (285, 162), (230, 200, 120), 2)
    drawn = [(272.0, 200.0), (130.0, 195.0), (135.0, 100.0), (270.0, 110.0)]  # rough, clicked in any order
    snapped = screens.snap_drawn(frame, drawn)
    assert all(snapped.sides)
    assert max(np.hypot(*(np.array(a) - b)) for a, b in zip(snapped.corners, screen)) < 3  # the screen, not the rim
