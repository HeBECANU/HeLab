"""Which source folders are on a network share (``cache_location.share_of``, A39.5): lexical, from the
OS's mount table, never a stat of the folder. Paths here don't exist, and the mount tables are made up."""
from __future__ import annotations

import os
import sys
from typing import Any

import pytest

from helab.utils import cache_location
from helab.utils.cache_paths import Mount

WINDOWS = sys.platform == "win32"
# A made-up place for the mounts, in this OS's spelling.
BASE = "Q:\\" if WINDOWS else "/nonexistent-helab-share-test/"


def at(*parts: str) -> str:
    return os.path.join(BASE, *parts)


@pytest.fixture(autouse=True)
def no_stat(monkeypatch: pytest.MonkeyPatch) -> None:
    """The lexical path reads no file system: realpath (which stats every component) is refused."""
    def refused(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("share_of stat'ed a source path")
    monkeypatch.setattr(os.path, "realpath", refused)


def test_a_folder_on_an_smb_mount_is_on_its_share_named_without_the_account() -> None:
    # (Each OS's spelling: macOS's smbfs names the account; Windows' redirector gives a UNC path.)
    source = "\\\\LabServer\\Data" if WINDOWS else "//tony@LabServer/Data"
    mounts = [Mount("/dev/disk1", BASE, "apfs"), Mount(source, at("lab"), "smb" if WINDOWS else "smbfs", WINDOWS)]
    assert cache_location.share_of(at("lab", "2026", "run1"), mounts) == "//labserver/data"  # (The share as the cache keys it: lowercased.)
    assert cache_location.share_of(at("lab"), mounts) == "//labserver/data"  # (The share as the cache keys it: lowercased.)
    assert cache_location.share_of(at("local", "run1"), mounts) == ""


@pytest.mark.parametrize(("mount", "named"), [
    (Mount("server:/export/data", at("nfs"), "nfs4"), "server:/export/data"),
    (Mount("tony@host:/data", at("nfs"), "fuse.sshfs"), "host:/data"),
    (Mount("map auto_home", at("nfs"), "autofs", remote=True), "map auto_home"),
    (Mount(at("nfs"), at("nfs"), "webdav"), "a network drive (webdav)"),
    (Mount("\\\\host@SSL\\DavWWWRoot", at("nfs"), "remote", remote=True), "\\\\host@SSL\\DavWWWRoot"),
])
def test_other_network_file_systems_and_remote_mounts_are_shares(mount: Mount, named: str) -> None:
    assert cache_location.share_of(at("nfs", "run"), [Mount("/", BASE, "ext4"), mount]) == named


def test_the_nearest_mount_decides() -> None:
    mounts = [Mount("//server/share", at("lab"), "smbfs"), Mount("/dev/disk4", at("lab", "usb"), "exfat")]
    assert cache_location.share_of(at("lab", "usb", "run"), mounts) == ""
    assert cache_location.share_of(at("lab", "other"), mounts) == "//server/share"
    assert cache_location.share_of(at("labx", "run"), mounts) == ""  # (Not inside "lab".)


def test_a_unc_path_is_a_share_without_a_mount() -> None:
    assert cache_location.share_of("//server/share/run1", []) == "//server/share"
    if WINDOWS:
        assert cache_location.share_of("\\\\Server\\Share\\run1", []) == "//Server/Share"


@pytest.mark.skipif(not WINDOWS, reason="Windows' mapped drives and its case-insensitive paths")
def test_a_mapped_network_drive_is_its_share() -> None:
    mounts = [Mount("C:\\", "C:\\", "local"), Mount("\\\\labserver\\data", "Z:\\", "smb", True)]
    assert cache_location.share_of("z:\\Runs\\run1", mounts) == "//labserver/data"
    assert cache_location.share_of("C:\\data", mounts) == ""


def test_the_mount_table_is_read_at_most_every_few_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    from helab.utils import cache_paths
    reads: list[int] = []
    table = [Mount("//server/share", at("lab"), "smbfs")]

    def current_mounts() -> list[Mount]:
        reads.append(1)
        return table
    monkeypatch.setattr(cache_paths, "current_mounts", current_mounts)
    monkeypatch.setattr(cache_location, "_mount_table", None)
    assert cache_location.share_of(at("lab", "run")) == "//server/share"
    assert cache_location.share_of(at("lab", "run2")) == "//server/share" and len(reads) == 1
    monkeypatch.setattr(cache_location, "MOUNT_TABLE_SECONDS", 0.0)
    cache_location.share_of(at("lab", "run"))
    assert len(reads) == 2

    def broken() -> list[Mount]:
        raise OSError("no mount table")
    monkeypatch.setattr(cache_paths, "current_mounts", broken)
    assert cache_location.share_of(at("lab", "run")) == ""  # (Unknown: treated as local.)


def test_the_warning_names_the_folder_the_share_and_the_recommendation() -> None:
    text = cache_location.share_warning("run1", "//labserver/data")
    assert "run1" in text and "//labserver/data" in text and "acquisition PC" in text and "(recommended)" in text


def test_share_of_is_called_through_its_module() -> None:
    """Tests patch ``cache_location.share_of`` (the app's and ``helab convert``'s tests): every caller calls it
    as ``cache_location.share_of``, never imported by value (AGENTS.md; Strata's review, finding 4)."""
    import ast
    from pathlib import Path
    root = Path(__file__).parent.parent / "helab"  # (No resolve: this file's fixture refuses realpath.)
    by_value = []
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.ImportFrom) and node.module == "helab.utils.cache_location"
                    and any(alias.name in ("share_of", "mount_table") for alias in node.names)):
                by_value.append(f"{path.relative_to(root.parent)}:{node.lineno}")
    assert by_value == []
