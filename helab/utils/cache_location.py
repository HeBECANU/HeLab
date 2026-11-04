"""Where the disk cache may live: never on a network or synced folder. And which source folders are on a
network share (``share_of``, A39.5).

SQLite's WAL mode doesn't work on network filesystems (https://www.sqlite.org/wal.html),
and sync clients can move files to the cloud or create conflicts under the database.
"""
from __future__ import annotations

import os
import sys
from typing import Iterable

from helab.utils.cache_paths import Mount

NETWORK_FILESYSTEMS = frozenset({
    "smbfs", "afpfs", "nfs", "nfs4", "webdav", "cifs", "smb", "smb2", "smb3", "9p", "davfs", "sshfs",
    "fuse.sshfs", "fuse.rclone", "fuse.davfs"})
# Folder names sync clients use; OneDrive's carries the organisation ("OneDrive - ANU").
SYNCED_PREFIXES = ("OneDrive", "Dropbox", "Google Drive", "GoogleDrive", "iCloudDrive", "iCloud Drive", "Box Sync")
# macOS keeps iCloud Drive and File Provider clients' folders here.
SYNCED_PAIRS = (("Library", "Mobile Documents"), ("Library", "CloudStorage"))


def _parts(path: str) -> list[str]:
    rest = os.path.splitdrive(path)[1]
    return [part for part in rest.replace("\\", "/").split("/") if part]


def _synced(parts: list[str]) -> str:
    for name in parts:
        if name.startswith(SYNCED_PREFIXES):
            return name
    for first, second in zip(parts, parts[1:]):
        if (first, second) in SYNCED_PAIRS:
            return second
    return ""


def _filesystem(path: str) -> tuple[str, bool]:
    """The filesystem type of the volume holding ``path``, and whether the OS calls it remote."""
    import psutil

    def normalize(value: str) -> str:
        return os.path.normcase(value) if sys.platform == "win32" else value

    target = normalize(path)
    best: tuple[int, str, bool] = (-1, "", False)
    for partition in psutil.disk_partitions(all=True):
        mount = normalize(partition.mountpoint)
        inside = target == mount or target.startswith(mount.rstrip("/\\") + os.sep) or mount in ("/", "")
        if inside and len(mount) > best[0]:
            best = (len(mount), partition.fstype.lower(), "remote" in partition.opts.split(","))
    return best[1], best[2]


def cache_location_problem(path: str) -> str:
    """Why ``path`` can't hold the disk cache (e.g. "on a network drive (smbfs)"), or "" if it can."""
    real = os.path.realpath(os.path.abspath(path))
    if real.startswith(("\\\\", "//")):
        return "on a network drive"
    if synced := _synced(_parts(real)):
        return f"in a synced folder ({synced})"
    try:
        fstype, remote = _filesystem(real)
    except Exception:
        return ""  # Unknown: a folder we can't classify is allowed.
    if remote or fstype in NETWORK_FILESYSTEMS:
        return f"on a network drive ({fstype})" if fstype else "on a network drive"
    return ""


# Shares (A39.5, Q39.2): a source folder on a network share, where writing TXY beside the raw files warns
# once per folder, since the converter belongs on the computer that owns the data (the acquisition PC).
# What counts: a UNC path (``\\server\share``, ``//server/share``), or a folder whose mount the OS lists as
# remote or of a network file system (``NETWORK_FILESYSTEMS``): macOS smbfs, afpfs, nfs, webdav; Windows'
# mapped network drives (``GetDriveTypeW`` DRIVE_REMOTE); Linux cifs, nfs, nfs4, sshfs, davfs, rclone. Synced
# folders (OneDrive, …) aren't shares: their files are local copies.
MOUNT_TABLE_SECONDS = 10.0  # The mount table read at most this often (the GUI asks on every render).
_mount_table: tuple[float, list[Mount]] | None = None


def mount_table() -> list[Mount]:
    """The OS's mount table (``cache_paths.current_mounts``: it asks no source folder or server), read again
    after ``MOUNT_TABLE_SECONDS``; [] when it can't be read."""
    global _mount_table
    import time
    now = time.monotonic()
    if _mount_table is None or now - _mount_table[0] >= MOUNT_TABLE_SECONDS:
        from helab.utils.cache_paths import current_mounts
        try:
            mounts = current_mounts()
        except Exception:  # (psutil or ctypes: unknown counts as local, as in cache_location_problem.)
            mounts = []
        _mount_table = (now, mounts)
    return _mount_table[1]


def share_of(path: str, mounts: Iterable[Mount] | None = None, *, resolve: bool = False) -> str:
    """The share holding ``path``, as the user knows it (``//server/share``, ``server:/export``, or the
    file system's name), or "" when it is local or can't be told. Lexical (``abspath``), so the GUI may ask:
    no stat, no realpath of a source folder; ``resolve`` (the command line, a helper) follows links first.
    ``mounts``: the table to use (default ``mount_table()``)."""
    from helab.utils.cache_paths import _smb_source
    absolute = os.path.realpath(path) if resolve else os.path.abspath(os.path.expanduser(path))
    windows = sys.platform == "win32"
    spelled = absolute.replace("\\", "/")
    if spelled.startswith("//"):
        parts = [part for part in spelled.split("/") if part]
        return "//" + "/".join(parts[:2]) if parts else "a network share"

    def normal(value: str) -> str:
        value = os.path.normpath(value)
        return value.lower() if windows else value

    target = normal(absolute)
    best: Mount | None = None
    for mount in mount_table() if mounts is None else mounts:
        point = normal(mount.path)
        separator = "\\" if windows else "/"
        if (target == point or target.startswith(point.rstrip("/\\") + separator)) and (
                best is None or len(point) > len(normal(best.path))):
            best = mount
    if best is None or not (best.remote or best.fstype.lower() in NETWORK_FILESYSTEMS):
        return ""
    if smb := _smb_source(best.source, best.fstype):
        return "//" + smb.removeprefix("smb://")
    # (No account names: "user@host:/path". In a UNC source an "@" is WebDAV's "host@SSL", kept.)
    unc = best.source.replace("\\", "/").startswith("//")
    source = best.source.split("@", 1)[1] if "@" in best.source and not unc else best.source
    return source if source and source != best.path else f"a network drive ({best.fstype})"


def share_warning(folder: str, share: str) -> str:
    """Why converting beside the raw files of ``folder`` on ``share`` asks first (A39.5; Q~ of the handoff)."""
    return (f"{folder} is on the network share {share}. HeLab's TXY converter should run on the computer that "
            "owns the data (the acquisition PC), where the raw files are local: writing TXY beside them over the "
            "network is slower, depends on the share staying up, and another computer may be converting the same "
            "files. Converting to HeLab's cache folder on this computer (recommended), or its temp folder, writes "
            "nothing to the share.")
