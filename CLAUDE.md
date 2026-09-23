# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Not an application. It is a **data-extraction project**: a set of Python scripts that read an
unpacked Soul Knight Prequel 1.13.0 Android APK and write readable JSON into `extracted/`.
There is no build, no lint config and no test suite — "running the code" means running a
pipeline stage and checking its printed counts and its JSON output.

- `soul-knight-prequel-<a-b-c>/` — one unpacked APK per game version (git-ignored). Made by
  `tools/unpack_apk.py`; do not re-unzip by hand.
- `tools/` — the pipeline scripts. Every tool defaults to the newest version (`tools/versions.py`).
- `extracted/<a.b.c>/` — one version's output: ~132 MB of JSON plus ~5,660 PNG icons, all
  regenerable. `extracted/_sheets/` (contact sheets, guide PNGs) is shared across versions.
- `guide/` — hand-written guide content (prose + keys into `extracted/`), rendered to HTML by
  `tools/build_guide.py`. The only hand-authored data in the repo; everything else is derived.
- `README.md` — the user-facing guide. Keep it in sync when the pipeline's counts change.
- `icon-mapping-plan.md` — how equipment icons outside the alias rule are settled (see below).

## Commands

Only dependency: `pip install UnityPy` (everything else is stdlib). Python 3.10+.

```bash
python tools/unpack_apk.py                       # new .apk/.xapk/.zip in root -> soul-knight-prequel-<v>/
python tools/pipeline.py                         # every stage below, in order (~90 s cold)
python tools/version_diff.py [old new]           # changes + what to screenshot -> extracted/<new>/changes_from_<old>.md
```

The stages one by one (each takes `--out extracted/<version>`, extractors also `--apk-dir`):

```bash
python tools/extract_soulknight.py               # stages 1-5          (~35 s cold)
python tools/extract_soulknight.py --skip-icons  # text + catalog + item tables only
python tools/extract_skill_links.py              # skill_links.json      (~15 s)
python tools/dump_prefabs.py                     # prefabs/*.json        (~25 s)
python tools/build_icon_map.py                   # guide/icon_map.json   (instant; --check)
python tools/build_equipment.py                  # equipment.json        (instant)
python tools/build_indexes.py                    # named_prefabs/buffs/… (instant)
python tools/build_item_details.py               # item_details.json     (instant)
python tools/build_guide.py                      # range-guide.html      (instant)
python tools/export_guide_png.py                 # guide -> Discord PNGs (pip install playwright)
```

The three extractors read bundles in parallel (`tools/parallel.py`, CPUs - 1 workers) and
cache each bundle's result in `.cache/`, keyed by the bundle's hashed file name plus the
extractor's own source, so a warm re-run takes ~35 s for all three and a new APK only
re-reads changed bundles. `--no-cache` / `--workers N` on each. Results are merged in
bundle order, so output is byte-identical to a sequential run (checked on all 5,409 files).
Cold time was 642 s before this; 364 s of it was one bundle, because UnityPy re-parses a
sprite's whole SpriteAtlas for every sprite it crops -- `_share_atlas()` parses it once.

Dev loop: `pip install ruff pre-commit pytest && pre-commit install` once. Every commit then
runs `ruff check --fix`, `ruff format` and the fast tests. `python -m pytest -m ""` also runs
the slow test, which rebuilds the instant stages and fails if any committed output changes.

`export_guide_png.py` writes `extracted/_sheets/guide_png/{desktop,phone}/`: the guide cut
between elements into pieces ≤1400 CSS px tall at 2x, because Discord blurs one full-page
screenshot (~10,000 px) beyond reading. It drives the system Edge (`channel='msedge'`), so
Playwright needs no browser download.

Order matters: `build_equipment.py` reads `localization_all.json`, `items_numeric.json`,
`skill_links.json`, `guide/icon_map.json` and `guide/effect_map.json`; `build_indexes.py` reads `localization_all.json` and `prefabs/`;
`build_guide.py` reads `guide/*.json`, `localization_all.json`, `items_numeric.json`,
`equipment.json` (for legendary effect text) and `extracted/icons/`, so it runs after
`build_equipment.py`.

`extract_named_sprites.py` exports sprites the main extractor's `ICON_PATTERN` never matched,
without re-running its 30-minute pass — it consults `sprite_index.json` and opens only the
bundles that actually hold the names asked for:

New in-game screenshots of the Codex of Equipment are turned into `confirmed` entries with
`match_screenshot_icons.py`, which pixel-matches the icon against every extracted sprite and
prints the winner, its score and which item currently claims it:

```bash
python tools/match_screenshot_icons.py "Soul knight prequel"/*.PNG
```

A **screen recording** of the user tapping › through a codex category is the cheapest way to
collect a whole slot (non-weapon legendary descriptions can only be linked this way). Frames
come out already landscape at 2868x1320, so the matcher works on them unchanged; the text has
to be read by eye from name + effect-panel crops, then found in the localization by phrase:

```bash
FF=$(python -c "import imageio_ffmpeg as f; print(f.get_ffmpeg_exe())")   # pip install imageio-ffmpeg
"$FF" -i "Soul knight prequel/<video>.mp4" -vf fps=4 frames/f_%03d.png
python tools/match_screenshot_icons.py frames/*.png --top 1
```

The first one (2026-09-22) covered all 26 legendary necklaces in 17 s; the second (75 s,
sampled at 10 fps and split into stable pages by frame differencing) covered 113 legendaries
across Helm, Armor, Boots, Ring, Mech Core and Cubis Core; 19 screenshots (IMG_6280-6298)
then filled every roster name the video skipped, so all legendary armor, helm, boots, ring,
gear and core pieces in the `Affixia` roster now have their text. The five Clockgears and both
Pandora's Arks are `108xxx` ids shown in the **Mech Core** tab with `84xx` sprites
(`108717` Darkness → `8409` … `108724` Nigmahex → `8416`), like `108719`/`108725`/`108728`
before them. Several effect texts have 2-4
near-duplicate keys (older wording, a "Chip" twin, an alternate version); pick the one whose
wording matches the frame, never the first regex hit.

```bash
python tools/extract_named_sprites.py --prefix EBF_ --folder EBF   # Fatebound icons
python tools/extract_named_sprites.py --prefix icn_equip_ item_rate_frame_s_
```

Useful while iterating:

```bash
python tools/dump_prefabs.py --groups buff skill     # one group instead of all nine
python tools/dump_prefabs.py --list                  # groups and their bundle counts
python tools/extract_skill_links.py --dump 1500441   # one prefab's whole component tree
python tools/extract_soulknight.py --all-sprites     # all ~112k sprites (hours, GBs)
```

To re-run a single stage without the rest, import the module rather than adding a flag:

```python
import sys, json; sys.path.insert(0, 'tools')
import extract_soulknight as E
s = E.stage_localization('soul-knight-prequel-1-13-0/assets/Asset', 'extracted/1.13.0')
sprites = {n for v in json.load(open('extracted/1.13.0/sprite_index.json')).values() for n in v}
E.stage_items(s, sprites, 'extracted/1.13.0')
```

**On Windows, always run with `PYTHONIOENCODING=utf-8`.** Printing any Chinese string crashes
with a `cp1252` `UnicodeEncodeError` otherwise, and most of this data is bilingual.

## Architecture

Two independent extraction paths converge on `extracted/`.

**Path 1 — localization and items** (`extract_soulknight.py`). The game's strings are
`TextAsset`s inside `localization_*.bundle`, stored as a hand-rolled TSV. Python's `csv` module
breaks on it (unescaped quotes and newlines inside cells), so `parse_tsv` splits on record
starts (`"key"<TAB>"type"<TAB>`) instead. Stages: localization → Addressables catalog →
sprite index → icon PNGs → item tables. Stage 5 joins names, descriptions and icons by key.

**Path 2 — prefabs** (`dump_prefabs.py`, `extract_skill_links.py`). Every bundle still ships its
Unity **type trees**, so `UnityPy`'s `read_typetree()` returns each `MonoBehaviour` field by
name. This is the single fact the whole prefab side rests on. `dump_prefabs.py` walks each
prefab's GameObject hierarchy and keeps MonoBehaviours only, dropping Transforms, renderers and
particles.

`build_equipment.py` and `build_indexes.py` are pure joins over the JSON the other three wrote —
they never touch the APK.

## Domain knowledge that is expensive to rediscover

**ID schemes.** Equipment IDs are `10S NNN` where `S` is the slot: 1 weapon, 2 armor, 3 helm,
4 boots, 5 ring, 6 necklace, 7 mech gear, 8 Cubis core. There is no slot 9. Confirmed by the
legendary skill prefabs, which live in `Assets/RGPrefab/Skill/LegendEquipSkill/<slot>/<skill
id>/` and reuse the same leading digit, and by the 7xxx/8xxx name blocks themselves (Rusty /
Arcane / Vitality **Gear**; Leaf of Yggdrasil and the other **cores**). IDs below `10000` use
the ID verbatim under one of five prefixes — see `icon_candidates()`. Careful: the *sprite*
numbers do not follow the slot digit everywhere — core icons are `ItemIcon_94xx000`
(`108701` Hellhound Claw is `9400000`), not `87xx`. And `ItemIcon_7501000`-`7508000`
are **not** mech gear: they are the Voidlock materials of loc keys `7501`-`7508`. Mech gear
is the `84xx` series: `1077nn` → `84(nn-1)`, confirmed by three exact screenshot matches
(`107702` → `8401`, `107704` → `8403`, `107709` → `8408`). So gear sprites are `8xxx` and core
sprites `9xxx`, one digit above the slot, and the two runs look parallel (`8200`/`8300`/
`8400`-`8418` against `9200`/`9300`/`9400`-`9420`). Arcane Gear → `8300` and Warpdrive Gear →
`8400` are user-confirmed; Rusty Gear → `8200` is the one gear still unchecked. Several gear effects have a `Chip` twin a few keys
away (`110561`/`111261`, `110563`/`111281`); the codex shows the `talent skill` one.

**Finding an item's icon.** See [icon-mapping-plan.md](icon-mapping-plan.md) for the history.

1. **There is no ID → sprite-number rule. Do not write one.** The old fallback, "drop the
   leading `100`, append three zeroes" (`101643` → `ItemIcon_1643000`), was removed on
   2026-09-22; of the 18 items since checked in game it was right once. Nor do the two series
   align by rank per slot — that was the next hypothesis, and it got 2 of 10 checks right
   (armor lands one short on every checked item). The offset drifts inside a block: helm is
   `+3` at `103464`/`103467` and `+4` at `103468`/`103469`; armor is `+5` from `102452` to
   `102462`. Equipment the alias rule misses gets its icon from
   [guide/icon_map.json](guide/icon_map.json) or gets **none**:
   - `confirmed` — hand-checked against the game (screenshot + `match_screenshot_icons.py`).
     Never rewritten by a tool.
   - `derived` — `build_icon_map.py` fills items between two confirmed pairs of the same slot,
     **only** when both ends have the same offset and every item and sprite in between exists.
     Unequal offsets mean a skipped sprite somewhere inside, and it does not guess where.
   - `build_icon_map.py --check` re-derives and fails on drift, on a confirmed sprite that is
     not extracted, on pairs that run backwards, and on a confirmed entry the alias rule
     contradicts.
2. Look the English name up again in the localization: most items *also* exist under a textual
   `ITEM_<suffix>` key, and the icon is then `ItemIcon_<suffix>`. "Orion's Galoshes" is both
   `104400` and `ITEM_CL_S1_000`, giving `ItemIcon_CL_S1_000.png`. This is the rule that
   works — it is self-verifying, because the English name has to match in both directions, and
   it covers 550 rows. Two screenshots agree with it (`104400`, `ITEM_CL_H3_006`).
3. Some sprites are simply named after their key — every Fatebound icon is the sprite named
   after its buff id, e.g. `EBF_SCATTERING`.
5. **Axial Incarnate pieces are `Incarnation_NN`** (export with
   `extract_named_sprites.py --prefix Incarnation_ UI_Incarnation_ --folder Incarnation`).
   Loc keys come in fours per incarnate — `<Name>: Axial Heart` then three pieces
   (`68834`-`68837` Lamian, `68846`-`68849` Tartarean Pantocrator) — and the sprites do too.
   Sprite = key − 68817 (`68835` → `Incarnation_18` … `68849` → `Incarnation_32`): nine
   screenshots matched it and the user confirmed the whole sheet (`_sheets/incarnate_pieces.png`),
   so all 32 are `confirmed` in `icon_map.json`, which `build_guide.py` reads for any key. Axial
   Heart = centre slot. Talk about these as "<boss> – <slot>" (Medusa – Top), not by number:
   Bouldarch = Boar King, Terrachnid = Crystal Snapclaw, Demiurgicon = Zulan the Colossus,
   Ordained Praetorian = Valadrion, Lamian = Medusa, Auryon = Ember Wyrm, Sir Peleus = Archknight,
   Tartarean Pantocrator = Hades (all user-confirmed 2026-09-22). The **Axial Urge**
   unlock items are `Incarnation_icon_NN` for the heart's number: `344` → `icon_17`, `356` →
   `icon_29` (matched as the heart's 3rd unlock material). The in-game medallion has a rarity-coloured rim
   the sprite lacks, so match on the inner disc only. First/second/third piece = top/left/right
   slot. `Incarnation_icon_NN` (20×20) are the matching unlock materials, same numbering. The set
   effect texts are `120401` Bouldarch, `120407` Lamian, `120415` Tartarean Pantocrator.
   Sprites `33`/`34` are missing, so do not extend the formula past `32` without a check.
4. **Skills referenced by numeric id have no sprite of their own.** Icons are named after
   the skill-*tree* key (`SX_P1_22_200`), never the `200xxx` id, so a numeric reference
   finds nothing. `build_guide.Data.skill_tree_icon()` bridges the two on the Chinese
   column — 175 skills, no ambiguity. See "Cross-check the Chinese column" below.

The real item → icon table is in the encrypted Luban config and **cannot be recovered**. Do not
go looking again: `global-metadata.dat` has zero hits for `ItemIcon_`, `iconId` or
`GetItemIcon`; the Addressables catalog has zero asset paths containing `ItemIcon`; and the
18,182 prefab dumps contain zero `ItemIcon_*` references. The only route left is the user
screenshotting the Codex of Equipment page for the item — one screenshot settles one item
exactly, and two with equal offsets can settle everything between them.

Why this survived so long: the two number series run close together (`3448` against `103448`),
so a wrong assignment still lands on *a helmet* — just the wrong one, three places along.

The remaining ~140 equipment icons are **not in the APK at all** (not in `sprite_index.json`,
not in the catalog); the game downloads them. Do not go looking for those either.

**Skill and item description offsets.** Numeric keys keep the description at a fixed offset
from the name, which differs per block: `+1000` for the `1`-`447` item block and for the
`200xxx` skill block (`200102` Rain of Arrows: Leonar → `201102`), `+100` for `7301`-`7437`.
`NUMERIC_DESC_RULES` in `extract_soulknight.py` holds the item ones.

**Legendary effect text — the item → effect link is solved for the `1500xxx` family.**
Equipment has no `<id>_D`, and older notes here claimed the item → effect mapping was locked in
the Luban config. It is not, for legendaries:

```
effect key = 130001 + (skill_id - 1500001) // 10          # build_equipment.effect_key()
101643 Grandfather Paradox → skill 1500441 → 130045
```

The `1500xxx` skill prefabs step by 10 and the `130xxx` text block is numbered densely from 1,
so the two align **by index**. Three items were checked against the game and all three land
exactly: `1500441` → `130045`, `1500451` Firmament's Caprice → `130046`, `1500431` Iron
Maidenfan → `130044`. The semantics corroborate the rest (`130003` names a Fire Colossus and
belongs to Spatha of the Fire Colossus; `130012` rerolls dice and belongs to Pollux Castor).
Only `1500xxx` is numbered this way — `1550xxx` are secondary skills of the same items and
`1405291` is unrelated, so the lowest `1500xxx` id wins.

This fills 46 of 806 equipment rows, which previously had **zero** descriptions between them.
`130056` (Scorching Breath) belongs to `101653` Prairie Fire and Rending Earth, which has no
skill prefab — confirmed by screenshot, so the other orphans can have owners too. 10 of the 57
`130xxx` texts stay unassigned: their prefabs exist in `prefabs/skill.json` but
their `Desc` field holds an effect name rather than an item name (`1500531` is `火焰吐息焦土`,
not a product), and 27 legendary-range weapons have no skill link, so there is no bijection to
fall back on. Do not rank-align these — ask instead. One lead worth checking: `130024` says
"your weapon become Immaterial and **Anumbral**", and `101616` **Anumbral Blade** has no link.

**Why only weapons link automatically (researched 2026-09-22).** Every slot has legendary
skill prefabs (`LegendEquipSkill/<armor|head|shoes|ring|lace|other>/…`: 24 armor `24xxxxx`,
26 helm `34xxxxx`, 20 boots `44xxxxx`, 35 ring `54xxxxx`, 31 necklace `64000x1`, plus
`71`/`72`/`90` families), but unlike `1500xxx` their `RGSkill` has **no `Desc`**, their buffs
carry no loc key, and every number is `cfg: [0, <prefab id>]`, i.e. from the encrypted config.
So there is nothing to join an item or a text on. The `"<name> Affixia"` list (`95xxx`, 156
items that match equipment) *is* the legendary roster — 26 necklaces, 30 rings, 31 cores, … —
but its order does not predict the text key either. What the confirmed pairs do show: text
keys in `110xxx`-`112xxx` were handed out roughly **chronologically** (necklaces `106441` <
`106725` < `106728` < `106733` < `106735` get increasing keys; the dense `11054x`-`11057x`
block is one patch — `110560` names Warp Drive = `107701`, `110561` Vitality, `110563`
Clockwork, `110567` Hellhound Claw `108701`), with exceptions (`102453` → `111161` jumps far
ahead of `102452` → `110549`). Good enough to *propose* candidates, never to assert them.
Gear texts in that block are the old "Chip" wording; the codex shows the "talent skill" twin.

**Where equipment descriptions are *not*.** All four of these were checked and are dead ends:

- `ITEM_<suffix>_D` — the alias that reliably gives an icon gives **no** description:
  0 of 550.
- `148xxx`/`149xxx` (1,312 keys) — a pure *name* block for the textual items. `148114 + 1000`
  is "Fallen Starwalkers", not a description of "Wayfarer's Tophat".
- `110001`-`112171` (414 keys, stepping by 10) and `120001`-`120420` — **this one was
  called wrong here for a while.** It reads like a generic affix pool and nothing in it
  joins to an item by name (0 matches), but it *does* hold real per-item effect text for
  the legendaries that have no skill prefab. Confirmed in-game: `110421` ("You become
  $kuangnu$ whenever you've taken damage equal to {0}% of your max life") is the effect
  of **both** `101591` Sangrilok Twinblades and `101593` Sangrilok Longbow, and `111061`
  ("…gain Final Verdict…") is `101628` Valkyrian Scepter. Two facts follow: the mapping
  is **not** one-to-one, since one text serves several items, and it is not derivable
  from either id. 21 more pairs were read off screenshots on 2026-09-22 (e.g. `102452`
  → `110549`, `102453` → `111161`, `108701` → `110567`, `108708` → `111081`) and still
  show no pattern: neighbouring items land thousands of keys apart. So these are
  **collected, not derived** — [guide/effect_map.json](guide/effect_map.json) holds every
  confirmed pair with its Lv.1 `{n}` values, and `build_equipment.py` prefers it over
  `effect_key()`, failing if the two ever disagree (they agree on all twelve legendaries
  checked).
- `95xxx`/`96xxx` — parsing `"<name> Affixia"` does yield a per-item index for 156 items
  (a different set from the skill route, including the `108726`-`108730` cores), but the text
  it reaches is fragment boilerplate, not the item's effect.

Ordinary non-legendary equipment has no per-item description anywhere in the APK, and would not:
in game those items show *rolled* affixes drawn from the `11xxxx` pool by the config. The
`130xxx` block exists precisely because legendary effects are fixed.

**`$token$` and `{0}` in description text.** `{0}` is a value the game fills in from the
encrypted config tables — unrecoverable. `$token$` is a glossary reference (`$kuangnu$`) whose
term table is *also* encrypted. The tokens can be partly recovered from the German and Russian
columns, which often expand them inline as `Berserker ($kuangnu$)`; `guide/ranger.json` keeps a
hand-checked glossary of the ones that mattered. In-game screenshots settle both: the codex
shows effect text with every token expanded and every `{n}` filled in. That is how `jiankang`
Healthy, `binwei` Critically Injured, `jisu` Swift, `yingyan` Eagle Eye and `yishang`
Vulnerable were recovered, and where the `lv1` values in `effect_map.json` come from.

**The `ITEM_*` alias key encodes type, armor class and content tier.** The alias that
`icon_by_alias()` uses for icons is `ITEM_<W|C><tier?>_<code><digit?>_<id>`, and every
part of it is meaningful. `build_item_details.py` decodes all of it:

- `W` weapon, `C` everything worn.
- Second letter is the content tier: none = starting/shop gear, `L` = the named sets,
  `B` = boss drops (`ITEM_WB_GS_EQB` Grimhowl Battleaxe), `S` = the newest block, whose
  icons the game downloads rather than ships.
- On weapons the code is the **weapon type**, and all twelve exist: `SS` Sword & Shield,
  `GS` Greatsword, `DS` Dual Blades, `LS` Spear & Shield, `SP` Spear, `CB` Crossbow,
  `BW` Bow, `SQ` Dual Pistols, `ST` Staff, `BK` Focus, `MR` Bangle, `QT` Fist Weapon.
  `206501`-`206503` group them into Melee / Ranged / Casting.
- On armor, helms and boots the code is `A`/`H`/`S` plus an armor class 1-3; rings are
  `R` and necklaces `L`, with no digit.

550 of 806 rows carry an alias. The 256 that do not are the legendary block and the
`1xx7xx` newest items. Their weapon type comes from the **in-game codex tabs** instead:
[guide/weapon_types.json](guide/weapon_types.json) holds 43 weapons typed by pixel-matching
the user's per-tab Codex of Equipment screenshots (IMG_6261-6273; one tab per weapon type) and
mapping each sprite to its item through `icon_map.json`. Grid geometry on a 2868x1320 shot:
8 columns, pitch 229.4 px, rows at y = 325 / 771 / 993, rightmost cell origin x = 2165, 6.48 px
per sprite pixel. Owned cells match in colour; "Unowned" cells are greyscale, so match on
luminance correlation over sprite rows 0-12 (the label covers the rest). Every alias-typed
weapon seen in those grids sat in its own tab (~95 checks, 0 misses), and a legendary's type
is often not what its name suggests (Grandfather Paradox is **Dual Pistols**). Only 9 remain
`weapon_type_source: "name-guess"`; `build_item_details.py` reports any codex/alias clash.

**A legendary's class comes from its effect text.** Specialization trees are keyed
`SX_P1_<line><modifier>_<node>` and those two digits *are* the two halves of
`Info_CLASS_<LINE>_<MODIFIER>`: line `1` WARRIOR, `2` ARCHER, `3` PSYCHIC, `4` STORM,
`5` LIGHT; modifier `1` GUARD, `2` ROBBER, `3` NATURAL, `4` FLAME, `5` DARK. So branch 22
is ARCHER_ROBBER = Ranger and 55 is LIGHT_DARK = Riftvoker. Since a legendary's effect
text almost always names a skill, matching the text against the tree gives the class —
Grandfather Paradox names Scattershot, so it is Ranger. `S_P1_<line>0_<node>` is the
shared tree above the five specializations and only pins the line ("Warrior line"), so a
specialization match must outrank a line match regardless of name length.

**Rarity is not in the APK.** Only the six labels exist, `ITEM_RATE_0`-`_5` (Common,
Charmed, Rare, Epic, Legendary, Insane). There is no per-item rarity field anywhere. The
`tier` field in `item_details.json` is a proxy built from the alias family code, plus
`legendary` for the 46 items that have a `LegendEquipSkill` prefab — that one is not a
guess, the folder name says so.

**`<key>` / `<key>_D`.** A display name at `<key>` and its description at `<key>_D` is the
convention for `ITEM_*` keys *and* for prefab names: prefab `S_P1_04_100` is "Pyroclad" and
`S_P1_04_100_D` is its description. 2,368 prefabs resolve this way. Several prefab *fields* also
hold loc keys rather than text: `RGBuff.buff_id`, `RGCharacter.specificName`, `I2.Loc.mTerm`.

**`lv` vs `cfg` in prefab dumps.** `{"lv": [v0, v1, v2, v3]}` is the real per-level value. A
component carrying `"cfg": [type, id]` instead is filled from the encrypted config tables at
runtime and its `lv` values are all zero — that is why most legendary-equipment parameters and
all character stats read as `0.0`.

**Bundle variants — the catalog decides, and it matters.** 44 logical bundles ship two or
three files differing only by content hash, and **none of the 44 groups are byte-identical**.
Picking by filename order lands on a bundle the game does not load in 21 of them, including
`buff_all`, `skill_class_all`, every `skill_directclass_*` and three `skp_loc_*` tables.
`extract_soulknight.shipped_bundles()` reads `assets/aa/catalog.json`, whose `m_InternalIds`
name exactly one variant per group (44 of 44, no exceptions); every tool filters through it.
Two symptoms this was causing:

- *Stale text.* The orphan `skp_loc_s3`/`s5`/`s7` still carry straight quotes where the shipped
  tables have curly ones. (`skp_loc_s13_bin` happens to sort first, so it was already the
  shipped copy. Note its `77646` and `82115` read like earlier drafts anyway -- `82115` has a
  malformed `#FA3914...</color>` where the orphan has `<color=#25bbbcff>`. That is a bug in the
  game's own shipped data, not in the extraction; the catalog copy is what the game loads, so it
  is what we keep.)
- *Garbage pixels.* Variants reuse the CAB name of their `.resS` stream file. Load two into
  one UnityPy environment and both atlas textures resolve that shared name to the **same**
  8 MB blob — and since the variants pack at different shapes (2048x4096 vs 4096x2048), every
  sprite crop lands on unrelated pixels. No exception is raised. This silently scrambled all
  ~500 `ItemIcon_*` PNGs and the `EBF_*` Fatebound icons. `export_sprites()` therefore loads
  **one bundle per environment**; do not "optimise" that back into a single `UnityPy.load(*all)`.

Nothing is lost by not co-loading the atlases: UnityPy looks for a packed sprite's SpriteAtlas
only in the sprite's *own* assets file (`export/SpriteHelper.py`), so a packed sprite is only
ever exportable from the atlas bundle it was packed into — its copies elsewhere carry
`m_RD.texture` == PathID 0 and raise either way. Filtering to the catalog costs three sprites
(`S13_SKIN_H_icon_4`/`_5`/`_6`), which live only in an orphan variant and are not icons.

Not affected: the three `*monoscripts*` variants agree on every shared MonoScript path_id, and
the only path_id a prefab bundle shares with them is `1`, the AssetBundle manifest — so the
prefab dumps were never mislabelled by this. They were, however, reading stale bundles.

**`$type`, not `type`.** In `prefabs/*.json` the component's C# class is under `$type`. Several
MonoBehaviours have their own field literally named `type`, which silently overwrote the class
name in an earlier version — do not reintroduce that collision.

## Cross-check the Chinese column before trusting an English string

**The English columns are inconsistent; the CJK columns are not.** When two keys look
like different things in English, compare their `Chinese` before concluding anything.
This has now caused one wrong call and solved three problems:

- `200102` is "Rain of Arrows: Leonar" and `SX_P1_22_200` is "Rain of Arrows: Maahes".
  Reading only English, they look like two skills, and this file briefly claimed the
  Ranger's skill was a different one. Their Chinese is `箭雨·狮` and `箭雨 狮` -- the same
  lion (狮), separator aside. Two transliterations of one skill; the tree key's English is
  stale and the game shows the `200xxx` one. All four Rain of Arrows variants pair this
  way (`山` Ourea, `狮` Leonar, `林` Syl, `炎` Geddon) and only branch 22 disagrees in
  English.
- The `$token$` glossary was recovered from German and Russian, which expand tokens
  inline as `Berserker ($kuangnu$)`.
- `Data.skill_tree_icon()` joins numeric skill ids to their tree icons on Chinese.

So: **normalise and compare `Chinese` (strip ` ·・:：`) whenever an English mismatch is
about to become a conclusion.** Prefer it as a join key over English generally -- it is
the source language, and the translators were not consistent with proper nouns.

The same caution in reverse: Chinese alone over-matches on short generic words. Joining
*any* sprite-named key on Chinese maps "Fission" onto the Multishot fatebound because
both are 分裂. Constrain the source set (tree keys only) and the target block.

## When the data cannot settle it, ask for the game

**The user plays this game. They are a source of ground truth that no amount of digging can
replace — ask them.** A lot of what this repo wants to know (which icon belongs to which item,
what a `{0}` actually resolves to, whether a name is the one shown on screen) lives only in the
encrypted config or on the server. Guessing produces output that looks right and is wrong.

This is not hypothetical. The numeric item → icon rule was an unverified inference that sat in
the code, in `CLAUDE.md` and in a published guide for as long as it did precisely because nobody
compared it against the game. One screenshot-level observation — "the Tophat of Six Splendors is
`3470000`, not `3467000`" — collapsed the whole thing in a single message, and three more
observations pinned down the real structure. See [icon-mapping-plan.md](icon-mapping-plan.md).

Ask early, and ask in a form that is cheap to answer:

- **Render a labelled contact sheet and let them point.** `extracted/_sheets/` holds the ones
  built so far; the generator pattern is a grid of upscaled PNGs with the sprite name and the
  claiming item under each cell. "Which of these is the Tophat" is a five-second question.
  "What is the icon ID for the Tophat" is not.
- **Give them the current answer and ask if it matches**, rather than asking open-ended. A wrong
  guess they can correct beats a question they have to research.
- **Ask for a handful of spot checks, not an audit.** Four helmets were enough to determine the
  rule for all 25. Pick items that would disambiguate competing hypotheses.
- **Say what you are unsure about, in the output.** The guide page marks unrecoverable values
  with a `?` chip and missing icons with a placeholder. Never render a guess as though it were
  extracted fact.

When an answer comes back, write it down where it cannot be re-derived away: a `confirmed`
entry in a frozen map, a note in this file, a test. An observation that only exists in a chat
log will be lost.

## What is and is not decrypted

Already solved, and handled automatically by the tools:

- `skp_loc_s13_bin` is XOR-obfuscated, not encrypted. Every table starts with the same
  `"Key"<TAB>"Type"<TAB>"English"…` header row, so `ciphertext ^ header` *is* the key stream; it
  repeats every 120 bytes. `deobfuscate()` recovers it from a sibling table's header.
- `global-metadata.dat` is **not** encrypted. Only its 0x108-byte header is scrambled; the whole
  string-literal table after it is plaintext and greppable with plain `re`.

Still closed — **do not repeat this search, it has been done exhaustively**:

`code_dll.bundle` / `code_aot.bundle` hold the Luban config tables (item→effect-ID, drop rates,
prices, enemy HP/ATK). They are a block cipher in ECB mode; a keystream cipher is ruled out
because `file1 ^ file2` past byte 32 is uniformly random. Plaintext of the first 32 bytes is the
fixed `UnityFS … 2022.3.62f3` header, so known-plaintext attacks are easy to run — and every
byte offset of `global-metadata.dat`, all four `classes*.dex`, `libnative-lib.so`, `libanogs.so`,
`libanort.so` and `libil2cpp.so` has already been tested for AES-128/192/256 (ECB and CBC),
DES/3DES, SM4, SEED and Camellia, plus MD5/SHA-256 of every printable string. Nothing matched.
The key is most likely built in ARM64 code as `MOV`/`MOVK` immediates; the only remaining route
is a real disassembler on `libil2cpp.so`, starting from the xref to the `code_aot.bundle` string
literal. The `assets/*.bytes` SDK configs are a separate, also-uncracked 8-byte-block ECB
(DES) over base64.
