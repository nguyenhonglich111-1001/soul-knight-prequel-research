# Fixing the numeric item → icon mapping

**Status:** the broken formula is gone (2026-09-22). Equipment icons now come from the `ITEM_*`
alias rule, or from a hand-checked table ([guide/icon_map.json](guide/icon_map.json)), or not at
all. What's still open is **coverage**: 215 of 806 rows have no icon, and more screenshots are
the only way to close that.

## The bug

`icon_candidates()` in [extract_soulknight.py](tools/extract_soulknight.py) and
`Data.icon_path()` in [build_guide.py](tools/build_guide.py) both assumed an arithmetic link
between an item's numeric ID and its sprite's number:

```
103467  ->  (103467 - 100000) * 1000  ->  ItemIcon_3467000
```

**No such link exists.** It was inferred because the two numbers look alike, and nobody checked
it against the game. It filled 115 equipment rows. Of the 18 of those since checked in game, it
was right **once** (`106441` Censurer's Necklace really is `6441000`).

The real table is in the encrypted Luban config. `global-metadata.dat`, the Addressables catalog
and all 18,182 prefab dumps have zero references to it, so it can't be derived. It can only be
observed.

## The second hypothesis, also wrong: rank alignment

The first draft of this plan proposed aligning each slot's alias-less items against its sprites
**by rank**. It reproduced the four helmet observations, but that was a coincidence of which
items had been checked. Against the 10 numeric items from the 2026-09-22 screenshots it got
**2 right**:

| Item | ID | Game | Formula | Rank |
|---|---|---|---|---|
| Crown of the Martial Saint | `103468` | `3472` | 3468 | 3472 ✓ |
| Plumesilk Vestments | `102452` | `2457` | 2452 | 2456 |
| Garment of Immortality | `102453` | `2458` | 2453 | 2457 |
| Starforged Battlegarb | `102454` | `2459` | 2454 | 2458 |
| Bloodoath Overcoat | `102462` | `2467` | 2462 | 2466 |
| Huntsman's Boots | `104709` | `4457` | — | 4457 ✓ |
| Welkin-Jade Thimble | `105712` | `5452` | — | 5445 |
| Censurer's Necklace | `106441` | `6441` | 6441 ✓ | — |
| Fettered Fury | `106728` | `6454` | — | 6441 |
| Heart Pendant | `106733` | `6458` | — | 6451 |
| Hellhound Claw | `108701` | **`9400`** | — | — |
| Leaf of Yggdrasil | `108708` | **`9407`** | — | — |

Cores aren't even in the `8xxx` sprite series the plan assumed. They are `94xx`, which the
survey never looked at, and it wrongly rejected the whole slot. `8xxx` turned out to be mech
gear (`107702` Vitality Gear → `8401`), and the `75xx` sprites the survey called gear are
Voidlock materials.

## What replaced it

1. **`guide/icon_map.json`, `confirmed`**: pairs checked against the game. 23 entries: the four
   helmets from 2026-09-21, 17 codex screenshots from 2026-09-22 (Crown of the Martial Saint
   is in both), and three the user picked off contact sheets (Firmament's Caprice, Arcane
   Gear, Warpdrive Gear). No tool rewrites them.
2. **`derived`**: `tools/build_icon_map.py` fills items that sit between two confirmed pairs of
   the same slot. It only does this when both ends have **the same offset** and every item and
   sprite in between exists. Then the gap has exactly as many items as sprites, and (assuming
   the art never runs backwards against the IDs, which every check so far bears out) there is
   only one way to fill it. That gives 20 items: `103465`-`103466`, `102455`-`102461`,
   `107703`, `107705`-`107708` and `108702`-`108707`. When the offsets differ, a sprite was skipped somewhere inside and the
   script leaves the whole gap blank: `106728` → `6454` and `106733` → `6458` leave four
   necklaces for three sprites.
3. **`--check`** re-derives and fails on any drift, on a confirmed sprite that isn't extracted,
   on pairs that run backwards, and on a confirmed entry the alias rule contradicts. Both
   screenshots that the alias rule also covers (`104400`, `ITEM_CL_H3_006`) agree with it.
4. **Everything else gets no icon.** `build_equipment.py` and `build_guide.py` read the map;
   neither computes a sprite name from an ID. `equipment.json` records `icon_source`
   (`alias` / `confirmed` / `derived`).

Counts: 591 of 806 rows have an icon (549 alias, 22 confirmed, 20 derived). Before the fix it was
665, but 115 of those came from the formula.

## Getting more

**Screenshot the Codex of Equipment page**, one item per shot, at any resolution. Then run:

```bash
python tools/match_screenshot_icons.py "Soul knight prequel"/*.PNG
```

It pixel-matches the icon against every extracted 20×20 item sprite. A correct match scores
0–31 and the runner-up 55+. The tool prints the winning sprite, the item that currently claims
it, and `UNSURE` when the gap is too small. Read the item name off the screenshot, add a
`confirmed` entry, and run `build_icon_map.py`, then `build_equipment.py` and `build_guide.py`.

The same screenshot also shows the item's legendary effect with every `$token$` expanded and
every `{n}` filled in. Record that in [guide/effect_map.json](guide/effect_map.json).

**Which items to ask for.** Pick the ones that bracket the most unknowns. The best picks sit just
inside a run of consecutive IDs, so that two screenshots with equal offsets settle everything
between them:

- **Weapons** have one confirmed item, `101644` Firmament's Caprice → `1644000` (offset 0). One
  more weapon with offset 0 fills everything between the two; ones near both ends of
  `101591`-`101655` settle up to 60 items. The gourd at `1646000` and the moon at `1647000` hint
  that Panthalassic Gourd (`101646`) and Argent Lunarium (`101647`) are offset 0 as well.
- **Mech gear is the `84xx` series**, not `75xx`. The 8 sprites `ItemIcon_7501000`-`7508000`
  are the Voidlock materials (localization keys `7501`-`7508`, Lesser Voidlock … Voidal Armor
  Hephaestite). Three screenshots confirm `1077nn` → `84(nn-1)`: Vitality Gear `107702` →
  `8401`, Clockwork Gear `107704` → `8403`, Soulforce Clockwork `107709` → `8408`, so
  `107703`-`107708` are derived. The user confirmed `107701` Warpdrive Gear → `8400` and
  `107501` Arcane Gear → `8300` from the contact sheet, so gear mirrors the core layout
  (`9300` / `9400`+). Only `107401` Rusty Gear is open; `8200` is the candidate.
- **Helm** `103445`-`103463` and **armor** `102446`-`102451`: one screenshot near the low end of
  each would extend the derived runs.
- **Necklace** `106729`-`106732`: one screenshot in the middle resolves the ambiguous gap.

## Known limits, stated rather than hidden

- `derived` rests on the art never being numbered backwards against the IDs. No check has
  contradicted that, and `--check` fails if one ever does.
- ~140 equipment icons aren't in the APK at all (the game downloads them). No mapping will
  produce those.
- If Chillyroom adds or removes art in a patch, sprite numbers shift. Re-run `--check` after
  re-extracting a new APK, and spot-check a couple of confirmed items.
