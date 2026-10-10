#!/usr/bin/env python3
"""Disc-backed regression for replacement attack traps and monster combat effects.

The first duel gives the CPU a replacement House of Adhesive Tape which heals
its owner.  The player's attacking monster deals 100 damage on ``combat``;
the final LP delta proves the trap's heal, one (not two) combat trigger, and
ordinary battle damage all completed.  The second duel instead destroys that
attacker, proving combat (and its damage trigger) is cancelled.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
from fm_editor import disc, gamedata, manifest
from fm_editor.model import Project
from trap_effects_runtime import attack_direct
from yfm_control import Game


def run(executable, out):
    retail = gamedata.load_game(disc.find_game([ROOT / "game"]))
    project = Project(retail)
    project.info.id = "replacement-trap-combat-test"
    # Card 5 is the small direct attacker used by trap_effects_runtime.
    project.set_monster_effects(5, [{"when": "combat", "do": "damage", "amount": 100}])
    decks, traps = {}, []
    for opponent, action in ((1, "heal"), (2, "destroy")):
        cid = project.add_card(3, f"replacement-{action}")
        project.cards[cid] = project.cards[cid].copy(type=21, attack=0, defense=0, level=0,
                                                      star1=0, star2=0, attribute=7)
        extra = project.added[cid].extra
        extra.update({"effect": 681, "trap_threshold": 1000,
                      "card_effects_mode": "replace",
                      "card_effects": [{"do": action, "amount": 200} if action == "heal"
                                       else {"do": action}]})
        decks[gamedata.DUELIST_NAMES[opponent]] = {"fixed": True, project.identity(cid): 40}
        traps.append(cid)
    built = manifest.build(project)
    built["decks"] = decks
    # The healing case deliberately distinguishes one combat trigger from
    # none or two. Keep the retail 8,000 start, but leave room for its +200.
    built["limits"] = {"life_points": {"max": 9999}}
    mod = out / "mods/replacement-trap-combat-test"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "mod.json").write_text(json.dumps(built), encoding="utf-8")

    with Game(executable=executable, out=out / "game", mods_dir=out / "mods",
              settings={"mod.replacement-trap-combat-test": 1, "mod.3d-monsters": 0,
                        "mod.hand-camera": 0}) as game:
        for opponent, action in ((1, "heal"), (2, "destroy")):
            game.goto("duel", opponent=opponent, deck=[5, 4, 6, 7, 8, 9, 10])
            game.duel_ready(before_deal=lambda g: g.arrange_deck(0, [5, 4, 6, 7]))
            game.play_card(0, face_up=True)
            game.end_turn()
            assert any(c and c["id"] == traps[opponent - 1] for c in game.duel()[1]["spells"]), game.duel()
            before = game.duel()
            attack_direct(game)
            game.step(180)
            after = game.duel()
            assert not any(after[1]["spells"]), after
            if action == "heal":
                # +200 from the trap, -50 ordinary direct damage, -100 from
                # exactly one combat trigger.
                assert after[1]["lp"] == before[1]["lp"] + 50, (before, after)
                assert after[0]["monsters"][0], after
            else:
                assert not after[0]["monsters"][0], after
                assert after[1]["lp"] == before[1]["lp"], (before, after)
            print(f"replacement {action} trap combat path: passed", flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / "tmp/pc/game32/memories-pc")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        raise SystemExit(run(args.executable, args.out))
    with tempfile.TemporaryDirectory(prefix="fm-replacement-traps-") as folder:
        raise SystemExit(run(args.executable, Path(folder)))
