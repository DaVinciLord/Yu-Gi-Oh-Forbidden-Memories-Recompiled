# Card packs

A mod may sell booster packs: a pack costs starchips (and, if it says, cards
from the chest), deals a handful of cards from pools the mod writes down, and
turns them over one by one on the Password screen, in the game's own card, box,
letters and sounds. Nothing about the memory card's save changes.

The data is `src/pc/cards/packs.c` (`packs.h`); the screen is
`src/pc/cards/pack_shop.c` (`pack_shop.h`), reached from a few lines in the
Password screen's own code (`src/overlays/password/shop.c`,
`src/game/main_run_password_menu.c`). With no pack declared none of it acts:
the Password screen is the console's, byte for byte and pixel for pixel.

## The smallest pack

```json
"packs": [
    {"name": "Dragons", "price": 50, "cards": ["Blue-eyes White Dragon", "Baby Dragon", "Koumori Dragon"]}
]
```

That is a pack of five cards, each card as likely as the next, repeats
allowed, as many as the player can pay for, from the start. It is sold on the
Password screen behind △, shows its first card's art on the big card, turns its
cards over one by one, and uses the Password screen's own sounds.

`"packs"` may instead name a file of the mod, `"packs": "packs.json"`, holding
the list, or `{"packs": [...], "pack_shop": {...}}`. The file and the pack
images are part of the mods' signature, so a save state made with other packs
is not taken for this run's (`Mods_Signature`).

The packs of every applied mod add up, in load order. They are read once, when
the game starts, like the other tables: changing them needs a restart.

## Everything a pack may say

| Key | Default | What it does |
|---|---|---|
| `id` | the name, lower case, hyphens for the rest (`"Legend of B.E.W.D."` is `legend-of-b-e-w-d`) | the pack's key: 1-63 letters, digits, `_` or `-`. With the mod's id it is the pack's identity, `mod-id:id`, which the save's progress, `unlock` `opened` and other packs use |
| `name` | the `id` | up to 16 letters, the room between the list's ◄ and ► arrows; longer is cut, with a note. UTF-8: letters the game lacks come from the mods' fonts, as card names do |
| `description` | none | the first two lines (20 letters each) show under the name; □ shows it all |
| `image` | none | a PNG inside the mod: the big card's picture (below) |
| `cover` | the first card of the rarest tier that has cards | the card whose art stands in when there is no `image` |
| `shop` | every shop | a shop's id or a list of them (`pack_shop` `shops`); `"*"` for all |
| `order` | the place it is declared in, across all mods | the list is sorted by it, ties by declaration |
| `price` | 100 | starchips, 0 to 999999; 0 is free |
| `cost` | `{"starchips": price}` | `"starchips"` (the price again; `cost` wins over `price`) and `"cards": {card: copies}` (up to 8 cards, 1-250 copies each): copies taken out of the chest as part of the price. The deck's copies are not taken |
| `count` | 5, or as many as `slots` | cards a pack deals, 1 to 40 |
| `cards` | | the pack's one pool: a list (a weight of 1 each) or `{card: weight}` |
| `tiers` | one tier, `"cards"` | pools with names, `{"common": {"odds": 800, "cards": ...}, "rare": {...}}`. **The order they are written in is their rarity**, commonest first |
| `slots` | every slot by the tiers' odds | a rule per slot: `"tier"`, `{"tiers": {tier: weight}}`, `{"cards": pool}` (a pool of the slot's own) or `{"card": X}` (always that card) |
| `guarantee` | none | `{tier: n}`: at least n cards of that tier or rarer in every pack |
| `pity` | none | `{tier: n}`: the n-th pack in a row without that tier (or rarer) has one. Counted per save |
| `duplicates` | `"allow"` | `"unique_in_pack"`: no card twice in one pack |
| `max_copies` | none | a card the player already holds this many of (chest and deck, and what this pack dealt) is not dealt |
| `include_added_cards` | `true` | `false`: a card a mod added, in any pool, is left out with a note (for packs of the disc's cards only) |
| `stock` | no limit | purchases one save may make, 1 to 999999. Sold out shows SOLD OUT |
| `unlock` | open | conditions the save must meet, all of them (below) |
| `locked` | `"hidden"` | `"shown"`: a locked pack is in the list face down, as ??????, with what opens it |
| `password` | none | up to eight digits: typed on the Password screen they sell this pack (with the same confirmation). A card's password comes first. A pack with a password is not in the list unless `"listed": true` |
| `once` | `false` | a password pack a save may buy once |
| `listed` | `true`, `false` with a `password` | whether the list shows it |
| `reveal` | `"flip"` | `"flip"`: each card turned over, one at a time, ✕ for the next and □ to skip; `"quick"`: turned over at twice the speed, one after the other; `"list"`: straight to the list of what came |
| `sounds` | the Password screen's | sound effect ids of the game's bank: `move` (47), `buy` (48), `refuse` (9), `reveal` (12), `back` (8). [Finding the ids](modding.md#finding-the-ids); an `audio` mod can make any of them a WAV or Ogg |

A tier:

| Key | Default | What it does |
|---|---|---|
| `odds` | 1 | its weight when a slot deals by the tiers' odds; 0 for a tier only `slots`, `guarantee` or `pity` reach |
| `cards` | | its pool, as above |
| `label` | none | what the card's line says when one of this tier turns over (`"ULTRA RARE!"`) |
| `color` | white | the label's colour, the game's text colours `{f8 0A n}`: 0 white, 1 yellow, 2 blue, and so on to 15 |
| `sound` | the pack's `reveal` | the sound a card of this tier turns over with |
| `reveal` | the pack's | `flip`, `quick` or `list` for the pack once it holds a card of this tier |

Cards are named as `decks` and `drops` name them: a name, an id, or the
`mod-id:key` identity of a card a mod added.

### Unlock

The duelists' conditions ([more duelists](more-duelists.md)) and three of the
packs' own. All that are given must hold; nothing is stored of them, they are
read from the save and its progress each time the list opens.

| Key | Holds when |
|---|---|
| `beat` | the save has beaten this duelist (`wins` times, 1 by default) |
| `wins` | without `beat`: this many wins in all |
| `story` | the campaign's story flag is set |
| `card`, `copies` | the chest and deck hold this many copies (1 by default) |
| `starchips_spent` | the save has spent this many starchips on packs |
| `packs_opened` | the save has opened this many packs in all |
| `opened` | `{pack: n}`: the save has opened that pack n times (up to 8 packs, by identity or id) |

A condition that names something not here this run (a duelist of a mod turned
off, a pack no mod has) or is written wrong leaves the pack locked, so nothing
opens by mistake.

### The shop's rules: `pack_shop`

| Key | Default | What it does |
|---|---|---|
| `password` | `"both"` | `"both"`: the Password screen sells cards by password and packs behind △; `"packs_only"`: the screen opens on the packs, and ○ there leaves it; `"password_only"`: no △ (packs with a `password` are still sold by it) |
| `shops` | one, `main`, CARD SHOP | `[{"id", "name", "unlock"}]`: ↑/↓ on the list moves between them; a shop that is locked is skipped. Shops add up by id across mods |
| `rng` | `"game"` | `"save"`: a pack is dealt from numbers of its own, seeded by the save's duelist code, the pack and how often the save opened it, so reloading a save to buy again deals the same cards. The game's random numbers are not touched |
| `music` | 29520 | the song while the screen sells packs |

`pack_shop` is one mod's: the last in the load order, with a note beside it
when another mod gave one too. Its `shops` add up by id.

Not built yet, and said so when a mod asks: `campaign_shop` (a PACKS entry in
the campaign's card shop), `main_menu`, `autosave` (saving after each
purchase), `sell_added_cards` (the password shop selling mod cards by their
own passwords), a currency of the mod's own earned in duels (`cost`
`currency`), and a stock that comes back (`restock`). The design and what each
costs are in the booster-packs design notes; the keys are kept free for them.

### What the reader says

A mistake that leaves a pack unable to be dealt leaves the pack out and says
why in the Mods window: no card of it here; `count` outside 1-40; `slots` not
`count` long, or naming a tier the pack has not; a negative weight, or a
pool's weights (or the tiers' odds) adding up past 1,000,000; a price past
999999; an `id` that is not 1-63 of `[A-Za-z0-9_-]` or is another pack's of the
same mod; a `guarantee` or `pity` naming no tier of the pack, or less than 1;
`unique_in_pack` with fewer different cards than `count`; both `cards` and
`tiers`; every tier at odds 0 with a slot dealt by the odds.

Anything else is a note and the pack stays: an unknown card is left out of its
pool; an unreadable `image` shows the cover; a name past 16 letters is cut; an
unknown key gets the likeliest meant ("did you mean"); an `unlock` naming
something absent stays locked; two packs with one password sell the first.

At most 255 packs in all, 16 tiers a pack and 16 shops.

## How a pack is dealt

Always with **four random numbers a slot**, whatever the slot turns out to
be: two make a 30-bit roll for the tier, two a 30-bit roll for the card. A
fixed card, a pool of one card, an empty tier: still four. So a replay of the
same input (`MEMORIES_INPUT`, the headless tests) deals the same pack and
leaves the game's numbers where they would have been.

1. All the numbers are drawn first: for slot s, `a b c d`, then
   `tier_roll = a << 15 | b` and `card_roll = c << 15 | d` (each number 0-0x7FFF).
2. Each slot in turn: a fixed card is that card; a slot's own pool picks with
   `card_roll`; otherwise the tier is the slot's (`"tier"`), picked by
   `tier_roll` among the slot's weights (`{"tiers"}`) or among the tiers'
   `odds`, and the card is picked in that tier's pool with `card_roll`. A tier
   whose pool has nothing left falls to the one before it (commoner), and so
   on; with none left the slot deals nothing.
3. A pick in a pool: every card's weight as it stands (0 once
   `unique_in_pack` dealt it, 0 once the player holds `max_copies` counting
   what this pack dealt), `roll % total`, then down the pool in the order it
   was written.
4. The guarantee and the pity, rarest tier first: while the pack has fewer
   than asked of that tier or rarer, the last slot dealt by tier that has not
   got it (and was not dealt again already) is dealt again from that tier with
   its own `card_roll` — or from a rarer one when that tier has nothing left.
   A fixed card or a slot's own pool is never dealt again. The pity asks for
   one when the save's count of packs in a row without the tier reaches n - 1.

`tests/pc/packs_fixture.json` and `packs_golden.txt` hold packs dealt this way;
the FM Editor's Simulate deals them the same (`tools/pc/fm_editor/packs.py`),
and both are tested against the file.

The Password screen draws no random numbers of its own each frame, and
nothing is drawn until a pack is bought.

## The save

The memory card's save is not changed. The cards go into the chest by
`Duel_AwardCard`, as a password's card does (the disc's cards in the save, a
mod's cards beside it; `chest_overflow` applies, and the chest shows them as
new), before the first one turns over: a state saved mid-reveal, or the game
closed, never loses or doubles a card. The starchips come off the save's own
count, with the Password screen's counting down (and *Free spending*).

What a save holds of the packs — purchases for `stock`, how often each was
opened, the pity counts, a `once` pack's password used, the starchips spent
on packs and packs opened in all — is kept beside it, in `packs/<token>.txt` in
the user directory, where the token is the save slot's (`save_slots.h`), drawn
anew each time the slot is saved:

```text
# The card packs this save bought (notes/card-packs.md).
spent 1250
opened 12
pack legend-mod:legend bought 11 opened 11 used 0 pity ultra=3
```

It is read when a slot is loaded and written when the game saves to one; the
file of the token the slot held before goes once no slot holds it. A save
without a file starts from nothing. A line for a pack no mod has this run is
kept and written back, so turning a mod off and on again loses nothing. NEW
GAME starts from nothing too.

A save state carries all of it, and where the screen was, in a chunk of its
own (`pack-shop`); a state without the chunk loads with the packs closed.
