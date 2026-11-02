from __future__ import annotations
import hashlib
import importlib.machinery
import importlib.util
import inspect
import logging
import os
import sys
import sysconfig
import traceback
from dataclasses import dataclass
from importlib import invalidate_caches
from typing import Any, Dict, List, Optional, Tuple, Type

from types import ModuleType

from helab.analysis.identity import file_hash
from helab.scripts.base import HelabAnalysisScript, ScriptMetadata


def _described(error: BaseException) -> str:
    """An import's failure for one line: a syntax error with its kind and place, as Python writes it
    ("SyntaxError: invalid syntax (counts.py, line 12)"), else its message."""
    if isinstance(error, SyntaxError):
        return f"{type(error).__name__}: {error}"
    return str(error)


class ScriptLoadError(Exception):
    """Raised when there is an error loading a script; ``details`` is its traceback ("": none)."""

    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.details = details


@dataclass(frozen=True)
class LoadError:
    """A script file (or a remembered folder) that didn't load: what the Scripts panel shows, one
    line (``line``) with the traceback in its tooltip (``details``)."""
    path: str
    message: str
    details: str = ""

    def line(self) -> str:
        return f"{os.path.basename(self.path) or self.path}: {self.message}"


NO_SCRIPT = "No HelabAnalysisScript subclass found"  # (A file without script classes.)
Stamp = Tuple[Tuple[str, int, int], ...]  # (file, size, modification time in ns) of each file


def _normal(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def _protected_roots() -> Tuple[str, ...]:
    """Folders whose modules a reload never unloads, even inside a script folder: HeLab's package and
    the interpreter's standard library and site-packages."""
    roots = {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}  # helab/
    paths = sysconfig.get_paths()
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        if paths.get(key):
            roots.add(paths[key])
    return tuple(sorted(_normal(root) for root in roots))


def _inside(path: str, folder: str) -> bool:
    """Whether ``path`` is ``folder`` or below it (as the OS compares names)."""
    path, folder = os.path.normcase(path), os.path.normcase(folder)
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def _same(first: str, second: str) -> bool:
    return os.path.normcase(first) == os.path.normcase(second)


def _source_file(module: object) -> str:
    """A module's file, normalised ("" if it has none: a namespace package, a built-in)."""
    try:
        file = getattr(module, "__file__", None)
    except Exception:  # (A module object with an odd ``__getattr__``.)
        return ""
    return _normal(file) if isinstance(file, str) and file else ""


# The user's script folders (and below), whose modules import from source alone (``_SourceOnlyLoader``).
_SOURCE_ONLY: set[str] = set()


class _SourceOnlyLoader(importlib.machinery.SourceFileLoader):
    """Imports a module of a user's script folder from its source, never from ``__pycache__`` and
    never writing one: Python checks a cached ``.pyc`` by the source's whole-second time and size, so
    an edit saved within a second of the last load (``VALUE = 1`` to ``VALUE = 2``) would reload the
    old code; and HeLab writes nothing into the user's folders."""

    def get_code(self, fullname: str) -> Any:
        path = self.get_filename(fullname)
        return self.source_to_code(self.get_data(path), path)


def _source_only_finder(path: str) -> importlib.machinery.FileFinder:
    """``sys.path_hooks``' entry for the user's script folders and their packages (others: the next hook)."""
    if not isinstance(path, str) or not path or not any(_inside(_normal(path), folder) for folder in _SOURCE_ONLY):
        raise ImportError("not a script folder")
    return importlib.machinery.FileFinder(
        path, (importlib.machinery.ExtensionFileLoader, importlib.machinery.EXTENSION_SUFFIXES),
        (_SourceOnlyLoader, importlib.machinery.SOURCE_SUFFIXES))


def _source_only(directory: str) -> None:
    """Import ``directory``'s modules (and its packages') from source from now on."""
    _SOURCE_ONLY.add(directory)
    if _source_only_finder not in sys.path_hooks:
        sys.path_hooks.insert(0, _source_only_finder)
    for entry in [entry for entry in sys.path_importer_cache if isinstance(entry, str) and entry
                  and _inside(_normal(entry), directory)]:
        del sys.path_importer_cache[entry]  # (Finders made before: the hook makes them again.)


class ScriptsManager:
    """Manages loading and organizing HeLab analysis scripts.

    This class is responsible for:
    1. Loading Python script files containing HeLab analysis scripts
    2. Organizing scripts into groups for easy management
    3. Maintaining metadata about each script
    4. Providing access to script classes and their metadata
    5. Reloading the user's script folders (live scripts): their scripts and helper modules

    The manager maintains three main data structures:
    - _scripts: Maps script ids to script classes
    - _metadata: Maps script ids to script metadata
    - _groups: Maps group names to lists of script ids

    A script id uniquely identifies a HelabAnalysisScript subclass, since a
    single file may define more than one script class (and thus share a
    file_path).

    Scripts must be subclasses of HelabAnalysisScript and provide valid metadata
    through the get_metadata() method including a name and group.

    **The user's folders** (``folders``: those loaded with Load Scripts…) are recorded, and each is
    on ``sys.path`` while it is loaded, at its end (HeLab's and installed modules keep their names),
    so a script imports modules beside it (``import helpers``), at import or later in ``compute``.
    Those are the folder's **helper modules** (``helper_modules``): every ``sys.modules`` entry whose
    file is inside the folder, never HeLab's own nor the interpreter's (``_protected_roots``), even
    when the folder holds them. Loading a folder again (``load_directory``, ``reload``) unloads its
    helper modules first, so they import fresh from disk with its scripts. HeLab's bundled
    analyses (``load_module``) are never reloaded. The folder's modules (its scripts too) import
    from their source alone, never a ``__pycache__`` (``_SourceOnlyLoader``). When a folder's files imported helper modules,
    each of its scripts records as its ``file_hash`` the hash of its file's hash and every helper
    module's (D1: a helper's change is new code too, for result reuse and presets' notes).

    What didn't load is kept (``errors``) with its traceback, for the Scripts panel.
    """

    def __init__(self) -> None:
        self._scripts: Dict[str, Type[HelabAnalysisScript]] = {}
        self._metadata: Dict[str, ScriptMetadata] = {}
        self._groups: Dict[str, List[str]] = {}  # group -> list of script paths
        self._folders: List[str] = []  # The user's folders, as added (normalised)
        self._errors: Dict[str, LoadError] = {}  # File (or folder not found) -> why it didn't load
        self._protected = _protected_roots()

    # The user's folders (live scripts)

    def folders(self) -> List[str]:
        """The user's script folders loaded (or tried) so far, in the order added."""
        return list(self._folders)

    def errors(self) -> List[LoadError]:
        """What didn't load: each file (or a folder not found), in path order."""
        return [self._errors[path] for path in sorted(self._errors)]

    def folder_of(self, script_id: str) -> str:
        """The user folder a script was loaded from ("" for HeLab's bundled analyses, or not loaded)."""
        directory = os.path.dirname(script_id.rpartition("::")[0])
        return next((folder for folder in self._folders if _same(folder, directory)), "")

    def script_ids(self, directory: str) -> List[str]:
        """The ids of the scripts loaded from ``directory`` (by the file each was loaded from, its id's
        first part, not the path its metadata gives, which a script may set to anything)."""
        directory = _normal(directory)
        return [script_id for script_id in self._metadata
                if _same(os.path.dirname(script_id.rpartition("::")[0]), directory)]

    def script_classes(self, directory: str) -> List[Type[HelabAnalysisScript]]:
        """The classes of the scripts loaded from ``directory`` now."""
        return [self._scripts[script_id] for script_id in self.script_ids(directory)]

    def helper_modules(self, directory: str) -> Dict[str, str]:
        """The folder's helper modules now: name -> file (``sys.modules`` entries whose file is inside
        it, never ``helab``'s, the standard library's or site-packages')."""
        directory = _normal(directory)
        found: Dict[str, str] = {}
        for name, module in list(sys.modules.items()):
            if name == "helab" or name.startswith("helab."):
                continue
            file = _source_file(module)
            if file and _inside(file, directory) and not any(_inside(file, root) for root in self._protected):
                found[name] = file
        return found

    def watched_files(self, directory: str) -> List[str]:
        """The files whose change reloads ``directory``: its ``.py`` files and its helper modules'."""
        directory = _normal(directory)
        try:
            names = os.listdir(directory)
        except OSError:
            names = []
        files = {os.path.join(directory, name) for name in names if name.endswith(".py")}
        return sorted(files | set(self.helper_modules(directory).values()))

    @staticmethod
    def stamp(files: List[str]) -> Stamp:
        """Each file's (path, size, modification time in ns); one that can't be statted is left out."""
        stamps = []
        for file in files:
            try:
                status = os.stat(file)
            except OSError:
                continue
            stamps.append((file, status.st_size, status.st_mtime_ns))
        return tuple(stamps)

    def add_folder(self, directory: str) -> bool:
        """Record a user folder and load it. A folder that isn't there is recorded with an error ("folder
        not found"; it loads on a later ``reload`` once it is back). Whether it loaded."""
        directory = _normal(directory)
        try:
            self.load_directory(directory)
        except ValueError:
            if not any(_same(folder, directory) for folder in self._folders):
                self._folders.append(directory)
            self._clear_directory_scripts(directory)
            self._clear_errors(directory)
            self._errors[directory] = LoadError(directory, "folder not found")
            return False
        return True

    def reload(self, folders: Optional[List[str]] = None) -> List[str]:
        """Load every user folder again (or those of ``folders``); the folders that loaded."""
        chosen = list(self._folders) if folders is None else [_normal(folder) for folder in folders]
        return [folder for folder in chosen if self.add_folder(folder)]

    def remove_folder(self, directory: str) -> None:
        """Forget a user folder: its scripts, errors and helper modules, and its place on ``sys.path``
        (its files are untouched)."""
        directory = _normal(directory)
        self._clear_directory_scripts(directory)
        self._unload_helpers(directory)
        self._clear_errors(directory)
        self._folders = [folder for folder in self._folders if not _same(folder, directory)]
        sys.path[:] = [entry for entry in sys.path
                       if not (isinstance(entry, str) and entry and _same(_normal(entry), directory))]

    def load_directory(self, directory: str) -> None:
        """Load all Python files from a directory that contain valid analysis scripts.

        This method:
        1. Scans the given directory for .py files
        2. Clears any existing scripts from this directory, its errors and its helper modules
        3. Attempts to load each .py file as a script, in name order, the folder on ``sys.path``
        4. Organizes loaded scripts into groups

        Scripts must:
        - Be a .py file
        - Contain a class that inherits from HelabAnalysisScript
        - Provide valid metadata through get_metadata()

        Args:
            directory: Path to directory containing Python script files

        Raises:
            ValueError: If directory doesn't exist
            ScriptLoadError: If script loading fails
        """
        if not os.path.isdir(directory):
            raise ValueError(f"Not a directory: {directory}")

        # Normalize so re-loading the same directory via a differently
        # spelled (but equivalent) path is recognized as the same directory.
        directory = _normal(directory)
        if not any(_same(folder, directory) for folder in self._folders):
            self._folders.append(directory)

        # Clear existing scripts from this directory, and its helper modules: they import fresh.
        self._clear_directory_scripts(directory)
        self._clear_errors(directory)
        self._unload_helpers(directory)
        _source_only(directory)
        invalidate_caches()  # (A helper file added since the last import is found.)
        if not any(isinstance(entry, str) and entry and _same(_normal(entry), directory) for entry in sys.path):
            sys.path.append(directory)

        for filename in sorted(os.listdir(directory)):
            if not filename.endswith('.py'):
                continue

            file_path = os.path.join(directory, filename)
            try:
                self._load_script_file(file_path)
            except ScriptLoadError as e:
                logging.warning(f"Failed to load script {file_path}: {e}")
                self._errors[file_path] = LoadError(file_path, str(e).removeprefix("Failed to load script: "),
                                                    e.details)
            except Exception as e:
                logging.error(f"Unexpected error loading {file_path}: {e}")
                self._errors[file_path] = LoadError(file_path, f"{type(e).__name__}: {e}", traceback.format_exc())
        # A file without scripts that the folder's scripts import is a helper module, not a failure.
        helpers = {os.path.normcase(file) for file in self.helper_modules(directory).values()}
        for path, error in list(self._errors.items()):
            if os.path.normcase(path) in helpers and error.message == NO_SCRIPT:
                del self._errors[path]
        self._fold_helper_hashes(directory)

    def _fold_helper_hashes(self, directory: str) -> None:
        """D1: when the folder's files imported helper modules, each of its scripts' ``file_hash`` is the
        hash of its file's hash and every helper's (its path in the folder, and hash)."""
        helpers = sorted((os.path.relpath(file, directory).replace(os.sep, "/"), file_hash(file))
                         for file in set(self.helper_modules(directory).values()))
        if not helpers:
            return
        for script_id in self.script_ids(directory):
            metadata = self._metadata[script_id]
            text = "\n".join([metadata.file_hash, *(f"{name}:{digest}" for name, digest in helpers)])
            metadata.file_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _clear_errors(self, directory: str) -> None:
        for path in [path for path in self._errors
                     if _same(path, directory) or _same(os.path.dirname(path), directory)]:
            del self._errors[path]

    def _unload_helpers(self, directory: str) -> None:
        for name in self.helper_modules(directory):
            sys.modules.pop(name, None)

    def _clear_directory_scripts(self, directory: str) -> None:
        """Remove all scripts from the specified directory"""
        for script_id in self.script_ids(directory):
            self._remove_script(script_id)

    def _remove_script(self, script_id: str) -> None:
        """Remove a script and its metadata"""
        if script_id in self._scripts:
            metadata = self._metadata.get(script_id)
            if metadata and metadata.group in self._groups:
                self._groups[metadata.group].remove(script_id)
                if not self._groups[metadata.group]:
                    del self._groups[metadata.group]
            del self._scripts[script_id]
            if script_id in self._metadata:
                del self._metadata[script_id]

    def _load_script_file(self, file_path: str) -> None:
        """Load and validate a single script file"""
        try:
            # Hashed before it runs: the hash identifies the code that made a result.
            digest = file_hash(file_path)
            # Import the module
            name = f"helab.scripts.dynamic.{os.path.basename(file_path)}"
            spec = importlib.util.spec_from_file_location(name, file_path, loader=_SourceOnlyLoader(name, file_path))
            if not spec or not spec.loader:
                raise ScriptLoadError("Could not create module spec")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._register_module(module, file_path, digest)
        except (Exception, SystemExit) as e:
            # SystemExit too: a script that exits at import (sys.exit, argparse on HeLab's argv)
            # fails alone, never Load Scripts… or HeLab.
            details = traceback.format_exc()
            raise ScriptLoadError(f"Failed to load script: {e!r}" if isinstance(e, SystemExit)
                                  else f"Failed to load script: {_described(e)}", details)

    def load_module(self, module: ModuleType) -> None:
        """Register the scripts of an already imported module (HeLab's bundled analyses,
        imported normally so that packaged builds include them)."""
        file_path = os.path.normpath(os.path.abspath(module.__file__ or module.__name__))
        try:
            self._register_module(module, file_path, file_hash(file_path))
        except Exception as e:
            raise ScriptLoadError(f"Failed to load script: {e}")

    def _register_module(self, module: ModuleType, file_path: str, digest: str) -> None:
        # Find HelabAnalysisScript subclasses. A single file may define
        # more than one script class, so all matches are loaded.
        found_any = False
        abstract: List[str] = []
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and
                issubclass(obj, HelabAnalysisScript) and
                obj != HelabAnalysisScript and
                obj.__module__ == module.__name__):
                if inspect.isabstract(obj):
                    # A helper base class the file's scripts share, or a script missing a method.
                    abstract.append(f"{obj.__qualname__} (missing {', '.join(sorted(obj.__abstractmethods__))})")
                    continue

                # Create instance to get metadata
                script = obj()
                metadata = script.get_metadata()

                # Validate metadata
                if not metadata.name or not metadata.group:
                    raise ScriptLoadError("Script metadata missing name or group")

                found_any = True
                script_id = f"{file_path}::{obj.__qualname__}"
                metadata.script_id = script_id
                metadata.file_hash = digest

                # Store script class and metadata
                self._scripts[script_id] = obj
                self._metadata[script_id] = metadata

                # Update groups
                if metadata.group not in self._groups:
                    self._groups[metadata.group] = []
                self._groups[metadata.group].append(script_id)

                logging.info(f"Loaded script {metadata.name} from {file_path}")

        if not found_any:
            raise ScriptLoadError(NO_SCRIPT if not abstract
                                  else f"No complete script: abstract {'; '.join(abstract)}")
        if abstract:
            logging.info(f"Skipped abstract classes in {file_path}: {'; '.join(abstract)}")

    def get_groups(self) -> List[str]:
        """Get list of all script groups"""
        return list(self._groups.keys())

    def get_scripts_in_group(self, group: str) -> List[ScriptMetadata]:
        """Get metadata for all scripts in a group"""
        if group not in self._groups:
            return []
        return [self._metadata[path] for path in self._groups[group]]

    def get_script(self, script_id: str) -> Optional[Type[HelabAnalysisScript]]:
        """Get script class by script id"""
        return self._scripts.get(script_id)

    def get_script_metadata(self, script_id: str) -> Optional[ScriptMetadata]:
        """Get script metadata by script id"""
        return self._metadata.get(script_id)
