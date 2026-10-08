"""Bounded, in-memory project history. Snapshots never deserialize disk data."""
from __future__ import annotations

import copy
import hashlib
import io
import pickle
import zlib
from pathlib import Path, PurePath

from . import art, board_art, guardian_stars, map_art, pngio
from .model import Project, RetailNames


def _values(value):
    """Canonical values for comparison, independent of dict order and aliases."""
    if isinstance(value, dict):
        pairs = [(_values(k), _values(v)) for k, v in value.items()]
        return ("dict", tuple(sorted(pairs, key=lambda pair: repr(pair[0]))))
    if isinstance(value, (set, frozenset)):
        return ("set", tuple(sorted((_values(v) for v in value), key=repr)))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(_values(v) for v in value))
    if isinstance(value, pngio.Image):
        return ("image", value.width, value.height, value.rgba)
    if isinstance(value, PurePath):
        return ("path", str(value))
    if hasattr(value, "__dict__"):
        return (type(value).__module__, type(value).__qualname__, _values(vars(value)))
    return value


class Snapshot:
    def __init__(self, project):
        # Freeze lazy images before a later Save can overwrite their files.
        st = art.state(project)
        for cid, part in list(st.images):
            try:
                art.replacement_image(project, cid, part)
            except (OSError, pngio.PngError):
                pass  # Preserve broken references so the validation tab can explain them.
        maps = map_art.state(project)
        for pic in list(maps.strips.values()) + list(maps.textures.values()):
            map_art.picture(project, pic)
        board_art.freeze(project)
        memo = {id(project.retail): project.retail, id(project.names): project.names}
        map_data = getattr(project.retail, "campaign_map", None)
        if map_data is not None:
            memo[id(map_data)] = map_data
        data = copy.deepcopy(project.__dict__, memo)
        # These tabs write files directly, rather than using ArtState. Keep
        # their original bytes too, including images opened lazily from disk.
        asset_names = {star.icon for star in guardian_stars.read(project.other.get("guardian_stars")).stars.values()
                       if star.icon}
        asset_names.update(entry.get("image") for entry in project.packs
                           if isinstance(entry, dict) and isinstance(entry.get("image"), str))
        if project.source_dir:
            for name in asset_names:
                if art.contained(name) and name not in data["files"]:
                    try:
                        data["files"][name] = (Path(project.source_dir) / name).read_bytes()
                    except OSError:
                        data["files"].pop(name, None)
        # The roster's files in the mod folder (roster.py) are what is on
        # disk, not an edit: an undo must not bring back an older idea of
        # them, or a save after it would leave a file it wrote behind.
        for key in ("retail", "names", "source_dir", "_recipes", "_own_pairs", "roster_owned"):
            data.pop(key, None)
        cloned_art = data["art_state"]
        # Ownership uses object IDs: store entry positions instead.
        cloned_art.owned = {i: st.owned[id(entry)] for i, entry in enumerate(st.entries or [])
                            if id(entry) in st.owned}
        cloned_art.folder = None
        cloned_art.changed = False
        for rep in cloned_art.images.values():
            rep.pending = False
        if "map_state" in data:
            data["map_state"].retail = None
        data["map_art"].version = 0
        for pic in list(data["map_art"].strips.values()) + list(data["map_art"].textures.values()):
            pic.pending = False
        if "board_art" in data:
            data["board_art"].version = 0
            for pic in data["board_art"].pictures.values():
                pic.pending = False
        comparison = io.BytesIO()
        encoder = pickle.Pickler(comparison, protocol=5)
        encoder.fast = True  # compare values, not incidental shared-object identities
        encoder.dump(_values(data))
        self.key = hashlib.sha256(comparison.getvalue()).digest()
        self.data = zlib.compress(pickle.dumps(data, protocol=5), 1)

    def restore(self, retail, source_dir=None, roster_owned=()):
        # Only bytes produced by Snapshot above enter pickle.loads. Recovery
        # files use the ordinary JSON mod reader, never this representation.
        project = Project.__new__(Project)
        project.__dict__.update(pickle.loads(zlib.decompress(self.data)))
        project.retail = retail
        project.names = RetailNames(retail.cards)
        project.source_dir = source_dir
        project.roster_owned = set(roster_owned)
        project._recipes = project._own_pairs = None
        st = project.art_state
        st.owned = {id(st.entries[i]): owner for i, owner in st.owned.items()}
        st.folder = source_dir
        boards = board_art.state(project)
        st.changed = bool(st.entries or st.images or project.map_art.strips or project.map_art.textures or
                          boards.pictures)
        for rep in st.images.values():
            rep.pending = rep.image is not None
        if hasattr(project, "map_state"):
            project.map_state.retail = getattr(retail, "campaign_map", None)
        for pic in list(project.map_art.strips.values()) + list(project.map_art.textures.values()):
            pic.pending = pic.image is not None
        for pic in boards.pictures.values():
            pic.pending = pic.image is not None
        return project


class History:
    def __init__(self, project, limit=50, max_bytes=64 * 1024 * 1024):
        self.limit, self.max_bytes = limit, max_bytes
        self.items = [Snapshot(project)]
        self.position = 0
        self.saved = self.items[0].key

    @property
    def dirty(self):
        return self.items[self.position].key != self.saved

    def record(self, project):
        item = Snapshot(project)
        if item.key == self.items[self.position].key:
            return False
        del self.items[self.position + 1:]
        self.items.append(item)
        while len(self.items) > 2 and (len(self.items) > self.limit + 1 or
                                      sum(len(s.data) for s in self.items) > self.max_bytes):
            self.items.pop(0)
        self.position = len(self.items) - 1
        return True

    def mark_saved(self, project):
        # Saving may normalize artwork paths. It is still the same user action.
        self.items[self.position] = Snapshot(project)
        self.saved = self.items[self.position].key

    def move(self, delta, project):
        target = self.position + delta
        if not 0 <= target < len(self.items):
            return None
        self.position = target
        return self.items[target].restore(project.retail, project.source_dir, getattr(project, "roster_owned", ()))
