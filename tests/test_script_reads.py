"""GT-6 (B): a user script folder's test import (``helab.scripts.probe``) answers what it read of the folder
(``FolderReads``: its ``.py`` names, each file's size, time and SHA-256, never its bytes), and HeLab's own import
right after, on the GUI thread, uses them instead of listing, statting and hashing the folder again. Missing,
stale or another folder's, the import reads the folder as before. The code itself still imports from the
folder on the GUI thread (AGENTS.md); its hash is that of the bytes the import read."""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any, Callable, Iterator, List

import pytest

from helab.scripts import scripts_manager
from helab.scripts.scripts_manager import FolderReads, ScriptsManager
from test_live_scripts import write_script
from test_scripts_reload import restored_imports  # noqa: F401  (a fixture)

pytestmark = pytest.mark.usefixtures("restored_imports")


@pytest.fixture
def folder_reads_seen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[List[str]]:
    """Every listing, stat, type check and hash HeLab's code makes of a file under ``tmp_path`` (the import
    machinery's own reads use ``posix`` directly, not these)."""
    seen: List[str] = []
    root = os.path.normcase(str(tmp_path))

    def watching(name: str, call: Callable[..., Any]) -> Callable[..., Any]:
        def run(path: Any, *args: Any, **kwargs: Any) -> Any:
            if isinstance(path, (str, os.PathLike)) and os.path.normcase(os.fspath(path)).startswith(root):
                seen.append(f"{name} {os.path.basename(os.fspath(path))}")
            return call(path, *args, **kwargs)
        return run
    for module, name in ((os, "listdir"), (os, "stat"), (os.path, "isdir"), (os.path, "isfile"),
                         (scripts_manager, "file_hash")):
        monkeypatch.setattr(module, name, watching(name, getattr(module, name)))
    yield seen


def probed(folder: Path) -> FolderReads:
    """As the probe answers, in its own manager (here, the same process: the helper isn't imported by it)."""
    reads = ScriptsManager().folder_reads(str(folder))
    assert reads is not None
    parsed = FolderReads.from_json(reads.to_json())  # (Through its JSON line, as the GUI gets it.)
    assert parsed is not None and parsed == reads
    return parsed


def test_fresh_reads_spare_the_gui_threads_reads_and_hash_what_was_imported(
    tmp_path: Path, folder_reads_seen: List[str],
) -> None:
    folder = tmp_path / "scripts"
    folder.mkdir()
    write_script(folder, "lab_reads_a", "one")
    reads = probed(folder)
    assert reads.names == ("lab_reads_a.py", "live.py") and len(reads.files) == 2
    folder_reads_seen.clear()
    manager = ScriptsManager()
    assert manager.add_folder(str(folder), reads)
    assert folder_reads_seen == []  # (Before: isdir, listdir, and a file_hash of each script and helper.)
    (metadata,) = manager.get_scripts_in_group("Lab")
    # The same hash as reading the folder now gives (D1: the script's and its helper's).
    again = ScriptsManager()
    assert again.add_folder(str(folder))
    assert any(seen.startswith("listdir") for seen in folder_reads_seen)
    (metadata_now,) = again.get_scripts_in_group("Lab")
    assert metadata.file_hash == metadata_now.file_hash != ""
    # Its stamp (auto-reload's), from the reads too.
    folder_reads_seen.clear()
    stamps = manager.stamp(manager.watched_files(str(folder), reads), reads)
    assert folder_reads_seen == []
    assert stamps == manager.stamp(manager.watched_files(str(folder)))


@pytest.mark.parametrize("which", ["missing", "stale", "another folder's", "from the future"])
def test_reads_missing_stale_or_not_its_own_fall_back_to_reading_the_folder(
    tmp_path: Path, folder_reads_seen: List[str], which: str,
) -> None:
    folder = tmp_path / "scripts"
    folder.mkdir()
    write_script(folder, f"lab_reads_{abs(hash(which)) % 10_000}", "one")
    reads: FolderReads | None = probed(folder)
    assert reads is not None
    if which == "missing":
        reads = None
    elif which == "stale":
        reads = FolderReads(reads.folder, time.time() - scripts_manager.READS_SECONDS - 1, reads.names, reads.files)
    elif which == "another folder's":
        reads = FolderReads(str(tmp_path / "other"), reads.taken_at, reads.names, reads.files)
    else:
        reads = FolderReads(reads.folder, time.time() + 60, reads.names, reads.files)
    folder_reads_seen.clear()
    manager = ScriptsManager()
    assert manager.add_folder(str(folder), reads)
    assert "isdir scripts" in folder_reads_seen and "listdir scripts" in folder_reads_seen
    assert "file_hash live.py" in folder_reads_seen
    (metadata,) = manager.get_scripts_in_group("Lab")
    assert metadata.file_hash


def test_a_file_changed_after_the_test_import_hashes_as_it_was_imported(
    tmp_path: Path, folder_reads_seen: List[str],
) -> None:
    """The hash is the bytes the GUI's import read (its loader's), never the probe's older copy's."""
    folder = tmp_path / "scripts"
    folder.mkdir()
    write_script(folder, "lab_reads_b", "one")
    reads = probed(folder)
    write_script(folder, "lab_reads_b", "two", version="2")
    manager = ScriptsManager()
    assert manager.add_folder(str(folder), reads)
    (metadata,) = manager.get_scripts_in_group("Lab")
    assert metadata.version == "2"
    again = ScriptsManager()
    assert again.add_folder(str(folder))
    (metadata_now,) = again.get_scripts_in_group("Lab")
    assert metadata.file_hash == metadata_now.file_hash


def test_the_answer_stays_small_and_malformed_ones_are_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "many"
    folder.mkdir()
    for index in range(6):
        (folder / f"s{index}.py").write_text("X = 1\n")
    monkeypatch.setattr(scripts_manager, "READ_FILES", 5)
    assert ScriptsManager().folder_reads(str(folder)) is None  # (Over the limit: no reads, read as before.)
    assert ScriptsManager().folder_reads(str(tmp_path / "gone")) is None
    bad: object
    for bad in (None, [], {"folder": "x"}, {"folder": "x", "taken_at": "soon", "names": [], "files": {}},
                {"folder": "x", "taken_at": 1.0, "names": [], "files": {"a": [1]}}):
        assert FolderReads.from_json(bad) is None
    digest = hashlib.sha256(b"X = 1\n").hexdigest()
    reads = FolderReads.from_json({"folder": str(folder), "taken_at": 1.0, "names": ["s0.py"],
                                   "files": {os.path.normcase(str(folder / "s0.py")): [6, 7, digest]}})
    assert reads is not None and reads.entry(str(folder / "s0.py")) == (6, 7, digest)


def test_the_probes_answer_is_kept_for_the_import_that_follows_once(qtbot: Any, tmp_path: Path) -> None:
    """``FolderProbes`` keeps a passed probe's reads for ``TreePanelWidget._load_folder`` (``take_reads``),
    once; a failed probe's are dropped."""
    import json
    from PyQt6.QtCore import QObject
    from helab.views.plots.script_tree import FolderProbes, ProbeFailure, _Probe
    folder = tmp_path / "scripts"
    folder.mkdir()
    (folder / "s.py").write_text("X = 1\n")
    reads = probed(folder)
    owner = QObject()
    probes = FolderProbes(owner)
    for failure in (None, ProbeFailure("its import didn't finish within 10 s")):
        item = _Probe(str(folder), response=str(tmp_path / "response.jsonl"))
        Path(item.response).write_text(json.dumps({"kind": "done", "loaded": True, "seconds": 0.1}) + "\n")
        probes._read(item)
        assert item.done and item.reads is None  # (The reads follow ``done``: GT-27.)
        with open(item.response, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"kind": "reads", "reads": reads.to_json()}) + "\n")
        probes._read(item)
        assert item.reads == reads
        probes._ended(item, failure)
        if failure is None:
            assert probes.take_reads(str(folder)) == reads and probes.take_reads(str(folder)) is None
        else:
            assert probes.take_reads(str(folder)) is None
    owner.deleteLater()


def test_forgetting_a_folders_digests_survives_a_digest_added_meanwhile(monkeypatch: pytest.MonkeyPatch) -> None:
    """GT-26 (the re-review): another folder's ``compute`` can import a helper, adding a digest from the worker
    thread, while a Reload drops this folder's. Here that write lands mid-iteration, from the per-key check: the
    clearing iterates a copy, so it neither raises nor loses the new digest."""
    digests = scripts_manager._READ_DIGESTS
    monkeypatch.setattr(scripts_manager, "_READ_DIGESTS", {os.path.normcase(f"/a/s{index}.py"): "x" for index in range(5)})
    inside = scripts_manager._inside
    added: List[str] = []

    def writing(path: str, folder: str) -> bool:
        if not added:
            added.append(os.path.normcase("/b/helper.py"))
            scripts_manager._READ_DIGESTS[added[0]] = "y"  # (As the worker's import would, meanwhile.)
        return inside(path, folder)
    monkeypatch.setattr(scripts_manager, "_inside", writing)
    scripts_manager._forget_digests(os.path.normcase("/a"))
    assert scripts_manager._READ_DIGESTS == {added[0]: "y"}
    assert digests is not scripts_manager._READ_DIGESTS
