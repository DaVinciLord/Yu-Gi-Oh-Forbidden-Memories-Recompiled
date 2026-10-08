"""Separate JSON recovery copies and rotating backups of saved mod folders.

A copy hard-links each file unchanged since the previous copy (same size and
time, and settled before that copy was made) instead of copying it again, so
a large mod's art costs its disk space once and an autosave takes no time.
Copies are never written into after they are made, so sharing is safe."""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import manifest, roster, settings
from .history import Snapshot


def root():
    return settings.path().parent / "recovery"


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SETTLE_SECONDS = 2      # a file this close to the previous copy's time is copied again


def _unchanged(item, old, settled):
    try:
        a, b = item.stat(), old.stat()
    except OSError:
        return False
    return (a.st_size == b.st_size and a.st_mtime_ns == b.st_mtime_ns
            and a.st_mtime < settled - SETTLE_SECONDS)


def fill(source, destination, previous=None, settled=0.0, skip=lambda rel: False, followlinks=False):
    """Copy the files of `source` that `destination` does not have yet. One
    unchanged since the copy in `previous` (made at `settled`) is linked to
    it; a file system without hard links gets a plain copy."""
    source, destination = Path(source), Path(destination)
    for directory, subdirs, files in os.walk(source, followlinks=followlinks):
        directory = Path(directory)
        subdirs[:] = [name for name in subdirs if (directory / name).resolve() != destination.resolve()]
        for name in files:
            item = directory / name
            rel = item.relative_to(source)
            target = destination / rel
            if skip(rel) or not item.is_file() or os.path.lexists(target):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if previous is not None and _unchanged(item, Path(previous) / rel, settled):
                try:
                    os.link(Path(previous) / rel, target)
                    continue
                except OSError:
                    pass
            shutil.copy2(item, target)


class Recovery:
    def __init__(self):
        self.folder = root() / ("session-" + uuid.uuid4().hex)

    def write(self, project, forms=None, snapshot=None):
        """snapshot: the project's state already taken (the history's
        current one), so a big mod is not pickled twice."""
        if project.source_dir and self.folder.resolve().is_relative_to(Path(project.source_dir).resolve()):
            raise ValueError("The recovery folder is inside this mod; choose a different mod folder.")
        self.folder.mkdir(parents=True, exist_ok=True)
        generation = self.folder / uuid.uuid4().hex
        previous = None
        settled = 0.0
        index = self.folder / "recovery.json"
        if index.exists():
            settled = index.stat().st_mtime
            saved = json.loads(index.read_text(encoding="utf-8"))
            previous = saved.get("generation") if isinstance(saved, dict) else None
            if not isinstance(previous, str) or len(previous) != 32 or any(c not in "0123456789abcdef" for c in previous):
                raise ValueError("The previous recovery index is invalid; its files were left untouched.")
        try:
            clone = (snapshot or Snapshot(project)).restore(project.retail, project.source_dir)
            manifest.save_mod(clone, generation, copy_source=False)
            source = project.source_dir
            if source and Path(source).is_dir():
                # What save_mod would copy first; the files it wrote win.
                # The roster's files it read are its own to write (roster.py):
                # a duelist taken out must not come back with its file.
                fill(source, generation, self.folder / previous if previous else None, settled,
                     skip=lambda rel: rel.name == "mod.json" or roster.owned(project, rel.as_posix()))
            record = {"name": project.info.name, "time": stamp(), "generation": generation.name,
                      "source": str(project.source_dir or ""), "forms": forms or {}}
            temporary = index.with_suffix(".tmp")
            temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(index)
        except Exception:
            shutil.rmtree(generation, ignore_errors=True)
            raise
        if previous:
            shutil.rmtree(self.folder / previous, ignore_errors=True)
        return index

    def clear(self):
        shutil.rmtree(self.folder, ignore_errors=True)


def backup(folder, keep=5):
    """Copy the previous mod and all assets before any existing file is replaced."""
    folder = Path(folder).resolve()
    if not (folder / "mod.json").is_file():
        return None
    if manifest.is_game_folder(folder):
        raise ValueError(f"{folder} holds game files; the editor writes mod folders only")
    group = root() / "backups" / hashlib.sha256(str(folder).encode()).hexdigest()[:16]
    # A recovery store placed inside a mod must never copy itself recursively.
    if group.resolve().is_relative_to(folder):
        raise ValueError("The recovery folder is inside this mod; choose a different save folder.")
    destination = group / uuid.uuid4().hex
    last = max(group.glob("*/recovery.json"), key=lambda p: p.stat().st_mtime_ns, default=None)
    try:
        (destination / "mod").mkdir(parents=True)
        fill(folder, destination / "mod", last.parent / "mod" if last else None,
             last.stat().st_mtime if last else 0.0, followlinks=True)
        (destination / "recovery.json").write_text(json.dumps({
            "name": folder.name, "time": stamp(), "source": str(folder), "generation": "mod",
            "backup": True}), encoding="utf-8")
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    old = sorted(group.glob("*/recovery.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for index in old[keep:]:
        shutil.rmtree(index.parent, ignore_errors=True)
    return destination


def records(exclude=None):
    found = []
    indexes = itertools.chain(root().glob("session-*/recovery.json"), root().glob("backups/*/*/recovery.json"))
    for index in indexes:
        if exclude is not None and index.parent == exclude:
            continue
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("time", ""), str):
                continue
            generation = data["generation"]
            if not isinstance(generation, str) or Path(generation).name != generation or generation in (".", ".."):
                continue
            folder = index.parent / generation
            if (folder / "mod.json").is_file():
                found.append((index, folder, data))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(found, key=lambda row: row[2].get("time", ""), reverse=True)
