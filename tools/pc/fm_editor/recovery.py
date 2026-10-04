"""Separate JSON recovery copies and rotating backups of saved mod folders."""
from __future__ import annotations

import hashlib
import itertools
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import manifest, settings
from .history import Snapshot


def root():
    return settings.path().parent / "recovery"


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Recovery:
    def __init__(self):
        self.folder = root() / ("session-" + uuid.uuid4().hex)

    def write(self, project, forms=None):
        if project.source_dir and self.folder.resolve().is_relative_to(Path(project.source_dir).resolve()):
            raise ValueError("The recovery folder is inside this mod; choose a different mod folder.")
        self.folder.mkdir(parents=True, exist_ok=True)
        generation = self.folder / uuid.uuid4().hex
        previous = None
        index = self.folder / "recovery.json"
        if index.exists():
            saved = json.loads(index.read_text(encoding="utf-8"))
            previous = saved.get("generation") if isinstance(saved, dict) else None
            if not isinstance(previous, str) or len(previous) != 32 or any(c not in "0123456789abcdef" for c in previous):
                raise ValueError("The previous recovery index is invalid; its files were left untouched.")
        try:
            clone = Snapshot(project).restore(project.retail, project.source_dir)
            manifest.save_mod(clone, generation)
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
    try:
        shutil.copytree(folder, destination / "mod")
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
