#!/usr/bin/env python3
"""Bring an already built Forbidden Memories HD mod up to the current anime frame layout.

For trying the anime frame's styles and rules without rebuilding the whole mod
(which needs the redrawn art folder): edits the mod's mod.json in place, the same
card_layout keys hd_assets_pack.py writes.

    python tools/pc/anime_frame_patch.py <mod folder>

- card_layout.frame_styles / frame_for / default_style (anime_frame_layout.py): an older
  "frame" per kind (and "kinds") becomes frame styles and the rules that pick them. A
  ritual frame that is magic's file is no frame of its own and is dropped; one that
  differs becomes the sub-option "Ritual spells: own frame" (off).
The original mod.json is kept as mod.json.bak (the first one, never overwritten).
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anime_frame_layout  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mod")
    args = parser.parse_args()
    path = os.path.join(args.mod, "mod.json")
    with open(path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    layout = manifest.get("card_layout")
    if not layout or not ("frame" in layout or "frame_styles" in layout):
        sys.exit(f"{path}: no card_layout frames -- this mod has no anime frame to patch")
    if not os.path.exists(path + ".bak"):   # the first original stays
        shutil.copyfile(path, path + ".bak")
    if "frame_styles" not in layout:
        old = layout.pop("frame")
        layout.pop("kinds", None)
        magic = old.get("magic", {}).get("image")
        frames = {kind: entry for kind, entry in old.items()
                  if kind in anime_frame_layout.STYLE_OF_KIND and not (kind == "ritual" and entry.get("image") == magic)}
        styles, extra = anime_frame_layout.build(frames)
        layout.update(styles)
        have = {setting["key"] for setting in manifest.get("settings", [])}
        manifest.setdefault("settings", []).extend(s for s in extra if s["key"] not in have)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=4, ensure_ascii=False)
    print(f"{path}: styles {sorted(layout['frame_styles'])}, {len(layout['frame_for'])} rules")


if __name__ == "__main__":
    main()
