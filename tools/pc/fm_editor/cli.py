"""The editor's command line.

    python tools/pc/fm_editor [--game <folder or .bin>] [--mod <mod folder>]
        the editor's window (the game is found where the port looks for it)

    python tools/pc/fm_editor check <mod folder> [--game <folder or .bin>]
        open the mod over the retail tables, list what the loader would
        complain about, and print the mod.json the editor would save

    python tools/pc/fm_editor import <modified .bin, folder or SLUS_014.11> -o <mod folder>
                             [--wa <modified WA_MRG.MRG>] [--game <retail>] [--id <mod id>]
        turn a community mod's modified game files into a port mod (what
        differs from retail); what cannot be carried over is reported
"""
from __future__ import annotations

import argparse
import sys

from . import disc, gamedata, importer, manifest, validate


def load_retail(game):
    files = disc.load(game) if game else disc.find_game()
    if files is None:
        raise SystemExit("the game files were not found; name them with --game <folder or .bin>")
    return gamedata.load_game(files), files


def command_check(arguments) -> int:
    retail, files = load_retail(arguments.game)
    project, messages = manifest.open_mod(retail, arguments.mod)
    for message in messages:
        print(f"read: {message}")
    issues = validate.validate(project)
    for issue in issues:
        print(issue)
    if arguments.print:
        sys.stdout.write(manifest.dumps(manifest.build(project)))
    print(f"{len(validate.errors(issues))} errors, {len(issues) - len(validate.errors(issues))} warnings "
          f"(game files: {files.source})", file=sys.stderr)
    return 1 if validate.errors(issues) else 0


def command_import(arguments) -> int:
    _, retail_files = load_retail(arguments.game)
    if arguments.wa:
        modded = disc.load_pair(arguments.modded, arguments.wa)
    else:
        modded = disc.load(arguments.modded)
    from pathlib import Path
    from .importers import slug
    source = Path(arguments.modded).resolve()
    if source.is_file() and source.suffix.lower() in (".bin", ".iso", ".img"):
        name = source.stem
    else:
        name = source.parent.name if source.is_file() else source.name
    result = importer.import_modded(retail_files, modded, arguments.id or slug(name), name)
    importer.save(result, arguments.output)
    for line in result.report:
        print(line)
    print(f"wrote {Path(arguments.output) / 'mod.json'}", file=sys.stderr)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="fm_editor", description="FM Editor: mods for the Forbidden Memories port")
    parser.add_argument("--game", help="the game: a folder with SLUS_014.11 and DATA/WA_MRG.MRG, or the .bin")
    parser.add_argument("--mod", help="a mod folder to open")
    commands = parser.add_subparsers(dest="command")
    check = commands.add_parser("check", help="validate a mod folder against the retail tables")
    check.add_argument("mod")
    check.add_argument("--game", default=argparse.SUPPRESS,     # so a --game before "check" counts too
                       help="the game: a folder with SLUS_014.11 and DATA/WA_MRG.MRG, or the .bin")
    check.add_argument("--print", action="store_true", help="print the mod.json the editor would write")
    imp = commands.add_parser("import", help="turn a modified game into a port mod")
    imp.add_argument("modded", help="the modified game: a .bin, a folder, or its SLUS_014.11")
    imp.add_argument("-o", "--output", required=True, help="the mod folder to write")
    imp.add_argument("--wa", help="the modified WA_MRG.MRG, when the first argument is SLUS_014.11 alone")
    imp.add_argument("--game", help="the retail game (default: found where the port looks)")
    imp.add_argument("--id", help="the mod id (default: from the file name)")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "check":
        return command_check(arguments)
    if arguments.command == "import":
        return command_import(arguments)
    from .app import main as window
    return window(arguments.game, arguments.mod)
