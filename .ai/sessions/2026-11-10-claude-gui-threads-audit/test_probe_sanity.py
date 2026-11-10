"""The stall probe sees a slow slot (a sanity check of ``stall_probe``; run it with ``-p stall_probe``)."""
import os

from PyQt6.QtCore import QTimer


def test_a_slow_slot_is_seen(qtbot):  # type: ignore[no-untyped-def]
    namespace: dict = {}
    fake = os.path.join(os.getcwd(), "helab", "fake_slow_slot.py")
    exec(compile("import time\ndef slot():\n    time.sleep(0.8)\n", fake, "exec"), namespace)
    QTimer.singleShot(0, namespace["slot"])
    qtbot.wait(1200)
