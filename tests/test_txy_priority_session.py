"""TXY priority lists' integration check (block 53, step 5): one session as the app runs it, FolderCache's
payloads into the helpers, in the test's own store; store-v4 on (the shipped default), and once under the hidden
store-v3 fallback (``store_v3``: no per-folder rows there, so Settings carries the list). A folder with External,
two HeLab profiles' TXY and raw-only shots, loaded under ``m23v1 › m19v1 › External``: each shot from the right
entry; the four modes' payloads, identities and data as before; a plot's own list beside the tab's; a restart
that keeps the folder's list (store-v4); an old preset that still opens. Temp folders only."""
from __future__ import annotations

from pathlib import Path
import time
from typing import Any

import numpy as np
import pytest

from helab.analysis.presets import TxyChoice, check_txy
from helab.convert.profile import MATLAB_2019, MATLAB_2023_LAB_EDIT
from helab.io_ops import stores
from helab.io_ops.admin import cache_admin
from helab.io_ops.loading import load
from helab.utils import txy_sources
from helab.utils.folder_cache import store_options
from helab.utils.txy_sources import CONVERSION, EXTERNAL

from test_txy_priority import H19, H23, M19, M23, converted, mixed_folder

EXTRAS = ("list", "tab", "fallback", "known", "conversion", "key_asked")


def run(path: Path, tmp_path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[int, Any]]:
    """The helper's load of a FolderCache payload: its ``loaded`` event and shots."""
    output = tmp_path / f"artifacts-{time.monotonic_ns()}"
    output.mkdir()
    sent: list[dict[str, Any]] = []
    load(str(path), str(output), sent.append, payload["cache"], txy=payload["txy"],  # type: ignore[arg-type]
         no_cache=bool(payload.get("no_cache")))
    loaded = next(event for event in sent if event["kind"] == "loaded")
    return loaded, {event["shot"]: np.load(event["artifact"]) for event in sent if event["kind"] == "shot"}


def strip(txy: dict[str, Any]) -> dict[str, Any]:
    """A load's options without what only lists and the tab add (the mode's own fields compared)."""
    return {key: item for key, item in txy.items() if key not in EXTRAS}


def value(shots: dict[int, Any], shot: int) -> float:
    return float(shots[shot][0][0])


@pytest.mark.parametrize("layout", ["store-v4", pytest.param("store-v3", marks=pytest.mark.store_v3)])
def test_a_session_under_priority_lists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, layout: str) -> None:
    from test_raw_fill import frozen
    service, cache = frozen(monkeypatch)
    try:
        options = store_options()
        assert options and Path(str(options["directory"])).name == layout
        source = mixed_folder(tmp_path)
        path = str(source)
        cache.set_convert_profile(MATLAB_2019)
        cache.set_tab_source("helab-priority")
        listed = (M23, M19, EXTERNAL)
        if layout == "store-v4":
            # The folder's own list, saved as the app saves it (the admin job), then read back after a restart.
            with stores._cache_store(str(options["directory"]), [path]):
                pass  # (The folder's data root, recorded as a load would.)
            sent: list[Any] = []
            source_text, tag = txy_sources.folder_row(listed)
            cache_admin(options, "folder_choice", sent.append, path=path, source=source_text, tag=tag,
                        set_at=time.time())
            with stores._cache_store(str(options["directory"]), [path]) as store:  # (A restart: a new open.)
                row = store.read_folder_choices([path])[path].value
            assert row is not None
            cache.remember_choices(path, row)
            assert cache.folder_list(path) == listed
        else:
            cache.set_tab_source(txy_sources.setting_text(listed))  # (No per-folder rows in store-v3.)
        tab = cache.with_txy(path, {"cache": options})
        assert tab["txy"]["source"] == "m23v1>m19v1>External" and tab["txy"]["tab"] is True
        loaded, shots = run(source, tmp_path, tab)
        # Each shot from the first entry with a TXY: 1 m23v1, 2 and 4 m19v1, 3 External; 5 (raw only) converted
        # on read with m23v1 in store-v4, absent in store-v3.
        assert (value(shots, 1), value(shots, 2), value(shots, 3), value(shots, 4)) == (1.23, 2.19, 3.1, 4.19)
        origins = {"1": "helab:" + H23, "2": "helab:" + H19, "4": "helab:" + H19}
        if layout == "store-v4":
            assert np.array_equal(shots[5], converted(5, MATLAB_2023_LAB_EDIT))
            origins["5"] = "helab:" + H23
        else:
            assert 5 not in shots
        assert loaded["txy"]["origins"] == origins and loaded["txy"]["source"] == "m23v1>m19v1>External"
        # A plot's own list beside the tab's: External only, its own dataset key.
        plot = cache.with_txy(path, {"cache": options, "no_cache": True, "txy": {"list": [EXTERNAL]}})
        assert plot["txy"]["source"] == txy_sources.MATLAB_ONLY and plot["txy"]["tab"] is False
        assert cache.payload_key_choice(plot) == "matlab-only" and cache.payload_key_choice(tab) is None
        _, plot_shots = run(source, tmp_path, plot)
        assert sorted(plot_shots) == [1, 2, 3] and value(plot_shots, 1) == 1.1
        # The four modes: a plot's mode list sends exactly the payload the mode sent before Q53.2.
        for mode in txy_sources.SOURCES:
            as_list = cache.with_txy(path, {"cache": options, "txy": {"list": list(txy_sources.list_of(mode))}})
            as_mode = cache.with_txy(path, {"cache": options, "txy": {"source": mode}})
            assert strip(as_list["txy"]) == strip(as_mode["txy"]), mode
            assert txy_sources.identity_source(as_list["txy"]["source"]) == txy_sources.identity_source(mode)
        # An old preset (before Q53.2: a mode, a profile's name and tag) still opens, as that mode.
        saved = TxyChoice.from_json({"source": "helab-only", "profile": "plates-2022", "tag": "p22v1"})
        choice, problem, _ = check_txy(saved, {"plates-2022": "p22v1", "matlab-2019": M19})
        assert problem is None and choice is not None and choice.tokens() == ("p22v1",)
        reopened = cache.with_txy(path, {"cache": options, "txy": {"list": list(choice.tokens() or ())}})
        assert (reopened["txy"]["source"], reopened["txy"]["profile_tag"]) == ("helab-only", "p22v1")
        assert saved is not None and TxyChoice.of_list(choice.tokens(), {"p22v1": "plates-2022"}) == saved
        # A list's preset round trips, and a renamed profile is found by its tag.
        mine = TxyChoice.of_list((M23, CONVERSION, EXTERNAL), {M23: "matlab-2023-lab-edit"})
        again = TxyChoice.from_json(mine.to_json())
        assert again == mine and again is not None and again.tokens() == (M23, CONVERSION, EXTERNAL)
        renamed, problem, note = check_txy(again, {"lab 2023": M23})
        assert problem is None and renamed is not None and "now “lab 2023”" in note
        gone, problem, _ = check_txy(again, {"matlab-2019": M19})
        assert gone is None and problem is not None and "isn't a known profile" in problem.text()
    finally:
        service.shutdown()
