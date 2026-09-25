# Data model: output files, keys, IDs, prefabs

What `extracted/<version>/` holds and how its keys and IDs are structured. Read this when
querying the output or when touching `build_equipment.py`, `build_item_details.py`,
`build_indexes.py` or `build_guide.py`.

## Output files (1.13.0 counts)

| File / folder | What it is |
|---|---|
| `localization_all.json` | Every string, 28,703 keys × 13 languages: `{key: {"English": …, "Chinese": …}}` |
| `items.json` | 1,490 `ITEM_*` items: `id`, `prefix`, `key`, `name`, `description`, `names`/`descriptions` (all languages), `icon` |
| `items_numeric.json` | 16,908 numeric-key entries: the same fields plus `description_id` |
| `equipment.json` | 806 rows: `slot`, `icon` + `icon_source`, `skill_ids`, `effect` + `effect_key` + `effect_source`, `effect_values_lv1` (767 with an icon, 201 with effect text) |
| `item_details.json` | 806 rows: `category`, `weapon_type` (+ `_source`), `weapon_class`, `armor_class`, `family`, `tier`, `class`, `effect` |
| `skill_links.json` | 64 legendary items → the skill prefab that implements them |
| `prefabs/*.json` | 18,182 prefabs with every MonoBehaviour field (`skill` 7,808, `stage` 5,966, `buff` 1,894, `ui` 728, and the rest) |
| `named_prefabs.json` | 2,368 prefabs whose name is a loc key (1,186 also have a description) |
| `buffs.json` / `characters.json` | 2,412 buffs (279 named) / 1,169 characters (125 named; `is_boss`, `camp`, `race`) |
| `glossary.json` | 128 `$token$`s → term key, name and rules text in 13 languages, `match` (`exact` / `near` / `guide`), `uses` |
| `loc_refs.json` | 1,854 prefabs → the loc keys they reference, and through which field |
| `numeric_ranges.json` | Numeric keys grouped into blocks, with a sample of each |
| `icons/` | ~5,660 PNGs, one subfolder per name prefix; `icon` fields are relative to it |
| `asset_catalog.json` / `sprite_index.json` | Addressables address → asset path / sprite name → its bundle(s) (65,194 sprites) |

## Looking something up

Items live in two tables, split by key shape, and neither covers the other:

- **`10SNNN` numeric IDs** are in `equipment.json` (effect, icon), `item_details.json`
  (category, class) and `items_numeric.json`.
- **`ITEM_*` keys** (`ITEM_CL_S1_010`) are only in `items.json`, keyed `key`, with `id` minus
  the `ITEM_` prefix. Their `descriptions` are usually empty.

Every key, numeric or `ITEM_*`, is also a key in `localization_all.json`. Never answer with a raw
key; resolve it there to its name first.

**For a keyword** ("what does Bladeheart do"):

1. Look up `glossary.json` by token (`renxin`) or by `name`. That gives the rules text.
2. Grep `$<token>$` in `localization_all.json`. That finds every affix and effect line that
   mentions it (stack cap, `: Ascension`, …).
3. Grep `$<token>$` in `equipment.json` `effect`. That finds the items that grant or use it.
4. Check `guide/*.json` notes. Items without effect text (most `ITEM_*` ones) may only be
   described there. Resolve every `key` in those notes through the two tables above.

**For `{0}` values:** they come from the encrypted config and are usually absent
(`effect_values_lv1` is often `null`). Say so, and ask the user for the in-game number (see
[effects.md](effects.md)).

## Equipment IDs: `10S NNN`

`S` is the slot:

| `S` | Slot |
|---|---|
| 1 | weapon |
| 2 | armor |
| 3 | helm |
| 4 | boots |
| 5 | ring |
| 6 | necklace |
| 7 | mech gear |
| 8 | Cubis core |

There is no slot 9. Two things confirm the scheme:

- the legendary skill prefabs live in `Assets/RGPrefab/Skill/LegendEquipSkill/<slot>/<skill id>/`
  and reuse the same leading digit;
- the 7xxx/8xxx name blocks say so themselves (Rusty / Arcane / Vitality **Gear**; Leaf of
  Yggdrasil and the other **cores**).

Sprite numbers do *not* follow this scheme (see [icons.md](icons.md)).

Numeric key blocks (`numeric_ranges.json` lists them all):

- **Names for slots 1-6:**
  - `101000`-`101709` weapons
  - `102000`-`102465` armor
  - `103000`-`103467` helms
  - `104000`-`104716` boots
  - `105000`-`105737` rings
  - `106000`-`106748` necklaces
- **Effect text:** `110001`-`112171` (mostly stepping by 10), `120001`-`120420` (set bonuses,
  specialization upgrades) and `130xxx`. See [effects.md](effects.md).
- **Affixia:** `95001`-`95229` is `"<item name> Affixia"`, and `96001`-`96229` holds the
  matching fragment descriptions.
- **Skills:** `200xxx`.

Textual keys follow `ITEM_<code>` (name), `ITEM_<code>_D` (description) and
`ItemIcon_<code>` (icon). Example: `ITEM_Potion_01` → `icons/ItemIcon_Potion/ItemIcon_Potion_01.png`.
- About 120 IDs have icons but no localized name, for example weapons `101649`-`101655` and
  rings `105446`-`105474`. This is unreleased content whose art shipped early.

## The `ITEM_*` alias encodes type, armor class and content tier

The key has the shape `ITEM_<W|C><tier?>_<code><digit?>_<id>`. `build_item_details.py`
decodes every part of it:

- **Type:** `W` weapon, `C` everything worn.
- **Content tier (second letter):**
  - none: starting/shop gear;
  - `L`: the named sets;
  - `B`: boss drops (`ITEM_WB_GS_EQB` Grimhowl Battleaxe);
  - `S`: the newest block, whose icons the game downloads rather than ships.
- **On weapons, the code is the weapon type.** All twelve exist:

  | Code | Type | Code | Type | Code | Type |
  |---|---|---|---|---|---|
  | `SS` | Sword & Shield | `GS` | Greatsword | `DS` | Dual Blades |
  | `LS` | Spear & Shield | `SP` | Spear | `CB` | Crossbow |
  | `BW` | Bow | `SQ` | Dual Pistols | `ST` | Staff |
  | `BK` | Focus | `MR` | Bangle | `QT` | Fist Weapon |

  `206501`-`206503` group them into Melee / Ranged / Casting.
- **On armor, helms and boots,** the code is `A`/`H`/`S` plus an armor class 1-3. Rings are `R`
  and necklaces `L`, with no digit.

550 of 806 rows carry an alias. The 256 that do not are the legendary block and the
`1xx7xx` newest items.

- **Where their weapon type comes from.** It comes from the in-game codex tabs instead.
  [guide/weapon_types.json](../guide/weapon_types.json) holds 43 weapons typed by pixel-matching
  the user's per-tab codex screenshots (see the `codex-screenshots` skill).
- **The tabs are reliable.** Every alias-typed weapon seen in those grids sat in its own tab
  (about 95 checks, 0 misses).
- **Names mislead.** A legendary's type is often not what its name suggests: Grandfather
  Paradox is **Dual Pistols**.
- **What's left.** Only 9 weapons remain `weapon_type_source: "name-guess"`, and
  `build_item_details.py` reports any clash between codex and alias.

## A legendary's class comes from its effect text

Specialization trees are keyed `SX_P1_<line><modifier>_<node>`, and those two digits *are* the
two halves of `Info_CLASS_<LINE>_<MODIFIER>`:

| Digit | Line (first digit) | Modifier (second digit) |
|---|---|---|
| 1 | WARRIOR | GUARD |
| 2 | ARCHER | ROBBER |
| 3 | PSYCHIC | NATURAL |
| 4 | STORM | FLAME |
| 5 | LIGHT | DARK |

So branch 22 is ARCHER_ROBBER = Ranger, and 55 is LIGHT_DARK = Riftvoker.

A legendary's effect text almost always names a skill, so matching the text against the tree
gives the class. Grandfather Paradox names Scattershot, so it is Ranger.

`S_P1_<line>0_<node>` is the shared tree above the five specializations and only pins the line
("Warrior line"). So a specialization match must outrank a line match, regardless of name
length.

## Rarity is not in the APK

- **Only the labels exist.** The six labels are `ITEM_RATE_0`-`_5`: Common, Charmed, Rare,
  Epic, Legendary, Insane. There is no per-item rarity field anywhere.
- **`tier` is a proxy.** In `item_details.json` it is built from the alias family code.
- **`legendary` is the exception.** It marks the 46 items that have a `LegendEquipSkill` prefab,
  and that one is not a guess: the folder name says so.

## Prefabs

- **`<key>` / `<key>_D`.** A display name at `<key>` and its description at `<key>_D` is the
  convention for `ITEM_*` keys *and* for prefab names. For example, prefab `S_P1_04_100` is
  "Pyroclad" and `S_P1_04_100_D` is its description. 2,368 prefabs resolve this way.
- **Fields that hold loc keys.** Several prefab *fields* also hold loc keys rather than text:
  - `RGBuff.buff_id` (`EBF_CHARGE` → "Concentration")
  - `RGCharacter.specificName` (`E07_S09` → "Scorchsand Hrunnir")
  - `I2.Loc|Localize.mTerm`

  1,664 distinct keys are reachable this way.
- **The C# class is under `$type`, not `type`.** Several MonoBehaviours have their own field
  literally named `type`. It once silently overwrote the class name, so do not reintroduce that
  collision.
- **Compactions:**
  - object references become `{"$ref": <path id>, "$name": "…"}`;
  - the per-level parameter struct becomes `{"lv": [v0, v1, v2, v3]}` (plus `cfg` / `unified`
    / `increment`);
  - empty fields are dropped.
- **`lv` vs `cfg`.**
  - `lv` is the real value at skill level 0-3 (`"atk_rate": {"lv": [60, 80, 100, 120]}`).
  - A component carrying `"cfg": [type, id]` is filled from the encrypted config at runtime,
    and its `lv` values are all zero.

  That is why most legendary-equipment parameters and all character stats
  (`RGCharacter._charAttributeTemplate`) read as `0.0`.

## Cross-check the Chinese column before trusting an English string

**The English columns are inconsistent; the CJK columns are not.** When two keys look like
different things in English, compare their `Chinese` before concluding anything. This has
caused one wrong call and solved three problems:

- **`200102` vs `SX_P1_22_200`.** `200102` is "Rain of Arrows: Leonar" and `SX_P1_22_200` is
  "Rain of Arrows: Maahes".
  - Their Chinese is `箭雨·狮` and `箭雨 狮`: the same lion (狮), apart from the separator.
  - So these are two transliterations of one skill. The tree key's English is stale, and the
    game shows the `200xxx` one.
  - All four Rain of Arrows variants pair this way (`山` Ourea, `狮` Leonar, `林` Syl, `炎`
    Geddon), and only branch 22 disagrees in English.
- **The `$token$` glossary** was first recovered from German and Russian (now automatic, see
  `docs/effects.md`).
- **`Data.skill_tree_icon()`** joins numeric skill ids to their tree icons on Chinese.

So normalise and compare `Chinese` (strip ` ·・:：`) whenever an English mismatch is about to
become a conclusion. Prefer Chinese as a join key generally: it is the source language, and the
translators were not consistent with proper nouns.

The caution also runs in reverse: Chinese alone over-matches on short generic words.

- **Example.** Joining *any* sprite-named key on Chinese maps "Fission" onto the Multishot
  fatebound, because both are 分裂.
- **Fix.** Constrain the source set (tree keys only) and the target block.
