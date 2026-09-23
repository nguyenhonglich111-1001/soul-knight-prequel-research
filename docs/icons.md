# Item and skill icons

How every icon in `extracted/<version>/icons/` is tied to a key, and why most equipment
needs a hand-checked table. Read this before touching `icon_candidates()`,
`build_equipment.icon_by_alias()`, `build_icon_map.py`, `guide/icon_map.json` or
`build_guide.Data.icon_path()`.

## The rules, in the order the tools apply them

1. **IDs below `10000`** use the ID verbatim under one of `ItemIcon_`, `ItemIcon_spt_`,
   `ICON_SP_`, `UI_SkillIcon_` or `UI_BF_` (`icon_candidates()` tries all five).
2. **The `ITEM_*` alias.** Look the English name up again in the localization. Most items
   *also* exist under a textual `ITEM_<suffix>` key, and their icon is then
   `ItemIcon_<suffix>`. For example, "Orion's Galoshes" is both `104400` and
   `ITEM_CL_S1_000`, so its icon is `ItemIcon_CL_S1_000.png`. The rule is self-verifying,
   because the English name has to match in both directions. It covers 550 rows, and two
   screenshots agree with it (`104400`, `ITEM_CL_H3_006`). The alias also encodes the
   weapon type and armour class; see [data-model.md](data-model.md).
3. **Named after the key.** Every Fatebound icon is the sprite named after its buff id
   (`EBF_SCATTERING`).
4. **[guide/icon_map.json](../guide/icon_map.json)** covers everything the alias misses. Anything
   not in it gets **no icon**, because a wrong icon is worse than none.
   - `confirmed`: checked against the game (a screenshot plus `match_screenshot_icons.py`, or
     the user picking the sprite off a contact sheet). No tool rewrites these entries.
   - `derived`: `build_icon_map.py` fills items that sit between two confirmed pairs of the
     same slot. It does so **only** when both ends have the same offset and every item and
     sprite in between exists. Then the gap has as many items as sprites, and there is only
     one way to fill it. Unequal offsets mean a sprite was skipped somewhere inside, and the
     tool does not guess where. Derivation groups by sprite series, not by ID slot.
   - `build_icon_map.py --check` re-derives the table. It fails on drift, on a confirmed
     sprite that has not been extracted, on pairs that run backwards, and on a confirmed
     entry that the alias rule contradicts.
   - `equipment.json` records `icon_source` (`alias` / `confirmed` / `derived`).
5. **Skills referenced by numeric id have no sprite of their own.** A skill's icon is named
   after its skill-*tree* key (`SX_P1_22_200`), never after the `200xxx` id, so looking up the
   numeric id finds nothing. `build_guide.Data.skill_tree_icon()` joins the two on the Chinese
   column. This covers 175 skills with no ambiguity (see "Cross-check the Chinese column" in
   [data-model.md](data-model.md)).

Coverage: 767 of 806 equipment rows have an icon (549 alias, 154 confirmed, 64 derived). The
map also holds the 32 Axial Incarnate pieces and 2 Axial Urges. About 140 equipment icons
are **not in the APK at all**: they are neither in `sprite_index.json` nor in the catalog,
because the game downloads them. Do not go looking for them.

## There is no ID → sprite-number rule. Do not write one.

- **Offset formula:** "drop the leading `100`, append `000`" (`103467` → `ItemIcon_3467000`).
  - It filled 115 rows until 2026-09-22.
  - Of the 18 of those since checked in game, it was right **once** (`106441` Censurer's
    Necklace → `6441`).
  - It survived so long because the two series run close together (`3448` vs `103448`). A
    wrong guess still lands on *a helmet*, just the wrong one, three places along.
- **Rank alignment per slot** was the next hypothesis. It matched the first four helmets by
  coincidence, then got 2 of 10 checks right:

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

- **The offset drifts inside a block.** Helm is `+3` at `103464`/`103467` and `+4` at
  `103468`/`103469`. Armor is `+5` from `102452` to `102462`. The Tophat of Six Splendors
  `103467` is `3470000`, not `3467000`.
- **The real table is in the encrypted Luban config and cannot be recovered.** Every other
  source has been searched and turned up nothing:
  - `global-metadata.dat`: zero hits for `ItemIcon_`, `iconId` or `GetItemIcon`.
  - The Addressables catalog: zero asset paths containing `ItemIcon`.
  - The 18,182 prefab dumps: zero `ItemIcon_*` references.

  The only route is a Codex of Equipment screenshot. One screenshot settles one item, and two
  with equal offsets settle everything between them.

## Sprite series, per slot

Sprite numbers do **not** follow the slot digit everywhere.

- **Weapons** have offset 0 wherever they were checked: `101591`, `101615`, `101619`,
  `101621`, `101643`, `101644`, `101655`.
  - Runs where items and sprites are both contiguous: `101591`-`101615` (filled),
    `101619`-`101641`, and `101643`-`101655` (filled up to `101635`). `101617`/`101618` have
    no item.
  - **The offset breaks at `101636`.** Tome of True Martial has no sprite, so from there the
    art runs one behind the ID. All of these came from screenshots:
    - `101637` Branding Twinlash → `1636`
    - `101638` Sheol's Gavel → `1637`
    - `101639` Searing Gyves → `1638`
    - `101640` Moiraic Wheel → `1639`
    - `101641` Lethean Knell → `1640`

    `101642` Iron Maidenfan → `1641` was user-confirmed from the Spear & Shield tab. A contact
    sheet labelled by ID put the wrong names on exactly these items, which is how the break was
    caught. Never trust a derived label past a known gap.
  - Sprites `1617`/`1618` are unclaimed. Anumbral Blade `101616` probably owns one of them,
    but it is not in the user's codex and neither sprite could be confirmed (2026-09-22).
    **Closed; do not ask again.**
  - Weapons without an icon: Anumbral Blade, Tome of True Martial, Vinebranch Saber, Silent
    Shadow Shortsword and the four Krisclaw weapons.
  - The gourd at `1646000` and the moon at `1647000` hint that Panthalassic Gourd `101646` and
    Argent Lunarium `101647` are also offset 0.
- **Mech gear is the `84xx` series.** The rule is `1077nn` → `84(nn-1)`. Three screenshots
  confirm it: Vitality Gear `107702` → `8401`, Clockwork Gear `107704` → `8403` and
  Soulforce Clockwork `107709` → `8408`. `107703`-`107708` are derived from those.
  - The user confirmed Warpdrive Gear `107701` → `8400` and Arcane Gear `107501` → `8300`.
    Rusty Gear `107401` → `8200` is the one gear still unchecked.
  - `ItemIcon_7501000`-`7508000` are **not** gear. They are the Voidlock materials of loc
    keys `7501`-`7508` (Lesser Voidlock … Voidal Armor Hephaestite).
- **Cubis cores are `94xx`, not `87xx`**: `108701` Hellhound Claw → `9400`, `108708` Leaf of
  Yggdrasil → `9407`. Gear sprites are `8xxx` and core sprites `9xxx`, one digit above the
  slot, and the two runs look parallel (`8200`/`8300`/`8400`-`8418` against
  `9200`/`9300`/`9400`-`9420`).
- **The codex tab, not the ID, decides Mech vs Cubis Core.** These `108xxx` ids are shown in
  the Mech Core tab with `84xx` sprites:
  - the five Clockgears and both Pandora's Arks (`108717` Darkness → `8409` … `108724`
    Nigmahex → `8416`);
  - `108719` Clockgear of the Aegis, `108725` Pandora's Ark - Trinathema, `108728` Octagram
    Matrix.
- **Necklaces:**
  - `106728` Fettered Fury → `6454` and `106733` Heart Pendant → `6458` leave four necklaces
    for three sprites, so the gap stays blank.
  - `106729`-`106732` are the four Axial Keystones, which the user does not see in the game;
    they are probably unreleased.
  - Codex neighbours: Helheim Tether `106725` → `6452`, Einheri Icon `106735` → `6460`.
  - The codex order is **not** ID order.
- **Where one screenshot would extend a derived run:**
  - Helm `103445`-`103463` and armor `102446`-`102451`, one shot near the low end of each.
  - Currently derived: `103465`-`103466`, `102455`-`102461`, `107703`, `107705`-`107708`
    and `108702`-`108707`.

## Axial Incarnate pieces

- **Sprites.** The pieces are `Incarnation_NN`; export them with
  `extract_named_sprites.py --prefix Incarnation_ UI_Incarnation_ --folder Incarnation`.
- **Keys.** Loc keys come in fours per incarnate: `<Name>: Axial Heart`, then three pieces.
  Examples: `68834`-`68837` Lamian, `68846`-`68849` Tartarean Pantocrator.
- **Key → sprite.** Sprite = key − 68817 (`68835` → `Incarnation_18` … `68849` →
  `Incarnation_32`).
  - Nine screenshots matched this rule, and the user confirmed the whole sheet
    (`_sheets/incarnate_pieces.png`).
  - So all 32 pieces are `confirmed` in `icon_map.json`, which `build_guide.py` reads for any
    key.
  - Sprites `33`/`34` are missing. Do not extend the formula past `32` without a check.
- **Slots.** Axial Heart is the centre slot; the first/second/third piece is the
  top/left/right slot.
- **Names.** Talk about pieces as "<boss> – <slot>" (Medusa – Top), not by number. All
  user-confirmed 2026-09-22:

  | Incarnate | Boss |
  |---|---|
  | Bouldarch | Boar King |
  | Terrachnid | Crystal Snapclaw |
  | Demiurgicon | Zulan the Colossus |
  | Ordained Praetorian | Valadrion |
  | Lamian | Medusa |
  | Auryon | Ember Wyrm |
  | Sir Peleus | Archknight |
  | Tartarean Pantocrator | Hades |
- **Axial Urge** unlock items are `Incarnation_icon_NN` (20×20), numbered like the heart:
  `344` → `icon_17`, `356` → `icon_29` (matched as the heart's 3rd unlock material).
- **Matching screenshots.** The in-game medallion has a rarity-coloured rim that the sprite
  lacks, so match on the inner disc only.
- **Set effect texts:** `120401` Bouldarch, `120407` Lamian, `120415` Tartarean Pantocrator.

## Known limits, stated rather than hidden

- `derived` assumes the art never runs backwards inside a gap. It does once:
  - `102465` Pandora's Gossamer Silks → `2470`;
  - `102466` Overcoat of the Vagrant Wyrm → `2469` (codex video, 2026-09-22).

  The same video re-covered dozens of derived entries and contradicted none. `--check`
  reports pairs like these.
- If a patch adds or removes art, sprite numbers shift. On a new version:
  1. Run `version_diff.py`. It flags confirmed sprites whose pixels changed.
  2. Run `build_icon_map.py --check`.
  3. Spot-check a couple of confirmed items.
