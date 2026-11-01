"""`python -m labcam.get_model`: downloads PaddleOCR's server recognition model (91 MB) for the wavemeter.

Saved as `models/ch_PP-OCRv4_rec_server_infer.onnx` beside the README (ignored by Git); labcam uses it from its next
start (see wavemeter.py). Delete the file to go back to RapidOCR's built-in model.
"""

from __future__ import annotations

import urllib.request

from .wavemeter import SERVER_MODEL, SERVER_URL


def main() -> None:
    if SERVER_MODEL.exists():
        print(f"already there: {SERVER_MODEL}")
        return
    SERVER_MODEL.parent.mkdir(exist_ok=True)
    partial = SERVER_MODEL.with_suffix(".partial")
    print(f"downloading {SERVER_URL}")
    urllib.request.urlretrieve(SERVER_URL, partial)
    if partial.stat().st_size < 50_000_000:
        partial.unlink()
        raise SystemExit("download too small; not a model")
    partial.replace(SERVER_MODEL)
    print(f"saved {SERVER_MODEL} ({SERVER_MODEL.stat().st_size / 1e6:.0f} MB); restart labcam to use it")


if __name__ == "__main__":
    main()
