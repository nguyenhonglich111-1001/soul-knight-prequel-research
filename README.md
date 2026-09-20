# Soul Knight Prequel 1.13.0 - extracted data guide

Everything here was read out of the unpacked APK (`soul-knight-prequel-1-13-0/`). The game is
Unity 2022.3 (Addressables). Its content sits in ~465 `.bundle` files in
`soul-knight-prequel-1-13-0/assets/Asset/`.

## What is in `extracted/`

| File / folder | What it is |
|---|---|
| `localization_all.json` | Every string the game shows, 28,703 keys, 13 languages. `{ "<key>": { "English": "...", "Chinese": "...", ... } }` |
| `items.json` | 1,490 `ITEM_*` items: `id`, `prefix`, `key`, `name`, `description`, `names` / `descriptions` (all languages), `icon` |
| `items_numeric.json` | 16,908 numeric-key entries (most weapons, armor, consumables, UI text). Same fields as above, plus `description_id` |
| `equipment.json` | 806 equipment rows: `id`, `slot`, `name`, `names`, `icon`, `skill_ids`, `rarity_hint`, `effect`, `effect_key` (665 have an icon, 46 have effect text) |
| `item_details.json` | 806 rows with everything derivable per item: `category`, `weapon_type`, `weapon_class`, `armor_class`, `family`, `tier`, `class`, `effect` |
| `skill_links.json` | 64 legendary items joined to the skill prefab that implements them (`item_id`, `skill_id`, `bundle`) |
| `prefabs/*.json` | 18,182 prefabs with every `MonoBehaviour` field: skills, buffs, bullets, characters, stages, UI |
| `named_prefabs.json` | 2,368 prefabs whose name is a loc key: name + description in 13 languages (1,186 have a description) |
| `buffs.json` | 2,412 buffs: `buff_id`, localized `name`, effect component list (279 are named) |
| `characters.json` | 1,169 characters: prefab, localized `name`, `is_boss`, `camp`, `race` (125 are named) |
| `loc_refs.json` | 1,854 prefabs -> the localization keys they reference, and via which field |
| `numeric_ranges.json` | The numeric keys grouped into blocks (`from`, `to`, `count`, `sample`) so you can see what each block holds |
| `icons/` | 5,544 PNG icons, one subfolder per name prefix (`ItemIcon_C/`, `ItemIcon_W/`, `EBF/`, `ICON_SP/`, ...) |
| `asset_catalog.json` | Addressables catalog: address -> asset path in the original Unity project (prefabs, anims, sprites) |
| `sprite_index.json` | Sprite name -> the bundle(s) it lives in (65,194 sprites across 209 bundles; only the variants the game ships are indexed) |

`icon` in the item files is a path relative to `extracted/icons/`, or `null` if no icon was found.

## How to look things up

**Search text (VS Code):** search `extracted/localization_all.json` for a word. The line above
the match is the key.

**Search from a terminal:**
```powershell
# find every key whose English text contains a word
python -c "import json;s=json.load(open('extracted/localization_all.json',encoding='utf8'));[print(k,'|',v['English'][:100]) for k,v in s.items() if 'paradox' in v['English'].lower()]"
```

**Look up one item:**
```python
import json
items = json.load(open('extracted/items_numeric.json', encoding='utf8'))
print([i for i in items if 'Paradox' in i['name']])
```

**Key naming (observed, not from official docs):**
- `ITEM_<code>` is an item name, `ITEM_<code>_D` its description, and `ItemIcon_<code>` its icon.
  Example: `ITEM_Potion_01` / `ITEM_Potion_01_D` / `icons/ItemIcon_Potion/ItemIcon_Potion_01.png`.
- Plain numbers (`101643`) are a newer ID scheme. Blocks seen in `numeric_ranges.json`:
  `101000-101709` weapon names, `102000-102465` armor, `103000-103467` helms, `104000-104716` boots,
  `105000-105737` rings, `106000-106748` necklaces, `110001-112171` and `120001+` skill/effect text
  with placeholders like `{0}%` and `$tag$` (see "Equipment effects" below).
- For some blocks the description is at `id + offset`: ids 1-416 use `+1000`, ids 7301-7437 use `+100`
  (this is applied automatically in `items_numeric.json`).
- **Equipment IDs are `10S NNN`, where `S` is the slot:** 1 weapon, 2 armor, 3 helm, 4 boots,
  5 ring, 6 necklace, 7 mech gear, 8 Cubis core. There is no slot 9. That is not a guess -- the
  legendary skill prefabs sit in `Assets/RGPrefab/Skill/LegendEquipSkill/<slot>/<skill id>/` and
  their IDs use the *same* leading digit (`1......` weapon, `2......` armor, ...), and the 7xxx /
  8xxx name blocks say so themselves (Rusty / Arcane / Vitality **Gear**; Leaf of Yggdrasil and
  the other **cores**). `equipment.json` labels every row from this.
- **Finding an equipment icon: one rule that works, one that is broken.**
  - *Works.* Look the English name up again in the localization -- most items *also* exist under
    a textual `ITEM_<suffix>` key, and the icon is then `ItemIcon_<suffix>`. "Orion's Galoshes"
    is both `104400` and `ITEM_CL_S1_000`, giving `ItemIcon_CL_S1_000.png`. This covers 550 of
    the 806 rows and is self-verifying, because the English name has to match in both
    directions. `build_equipment.icon_by_alias()` does this.
  - *Also works.* A few sprites are simply named after their key, which is how every Fatebound
    icon resolves (`EBF_SCATTERING`).
  - **Broken -- do not trust.** For the 115 rows the alias misses, the tools still fall back to
    "drop the leading `100` and append three zeroes" (`101643` -> `ItemIcon_1643000`). There is
    no arithmetic link between an item ID and its sprite number. Checked against the game,
    `103467` Tophat of Six Splendors is `ItemIcon_3470000`, not `3467000`. The two number series
    align by **rank**, not by value, with an arbitrary per-slot offset, so no formula can fix
    it. See [icon-mapping-plan.md](icon-mapping-plan.md).
  - Items with IDs below `10000` use the ID verbatim under one of `ItemIcon_`, `ItemIcon_spt_`,
    `ICON_SP_`, `UI_SkillIcon_` or `UI_BF_`; `icon_candidates()` tries all of those.
  - *Skills are different again.* A skill's icon is named after its skill-**tree** key
    (`SX_P1_22_200`), not the `200xxx` id used everywhere else, so a numeric reference finds
    nothing. The two keys are bridged by their **Chinese**, which is identical apart from the
    separator -- their English is not: `200102` is "Rain of Arrows: Leonar" while
    `SX_P1_22_200` is "Rain of Arrows: Maahes", two transliterations of the same lion (狮).
    `build_guide.Data.skill_tree_icon()` does this for 175 skills.
  - The remaining ~140 equipment icons are not in the APK at all -- the game downloads them.

## Equipment effects: where the text actually is

Legendary equipment has no `<id>_D` description key, which is why `items_numeric.json` shows a
name and nothing else. The effect text is not missing from the game data, though -- it lives in
its own blocks of `localization_all.json`:

| Key block | What it holds |
|---|---|
| `110001`-`112171` | Legendary / forged-affix effect text, e.g. `111961`, `112111`. IDs mostly step by 10 |
| `120001`-`120420` | A second effect block (set bonuses, specialization upgrades) |
| `95001`-`95229` | `"<item name> Affixia"` -- one entry per item whose legendary effect can be forged |
| `96001`-`96229` | The matching fragment descriptions |

Within these blocks the convention is **description at `N`, name at `N+1`** --
`111561` is `"$diaoling$'s effects changed to: ..."` and `111562` is its name `"Bone-Deep Torment"`.
Placeholders `{0}`, `{1}` are the numbers the config fills in, and `$tag$` is a game term
(`$kuangnu$`, `$jiankang$`, ...) the UI expands.

**The item -> effect link is solved for legendaries.** It was thought to be locked in the Luban
config; it is not. The `1500xxx` skill prefabs step by 10 and the `130xxx` effect-text block is
numbered densely from 1, so they line up by index:

```
effect key = 130001 + (skill_id - 1500001) // 10

101643  Grandfather Paradox / 祖父悖论  ->  skill prefab 1500441  ->  effect text 130045
                                                             ->  buff BF_1500441
```

Three items were checked against the game and all three land exactly -- `1500441` -> `130045`,
`1500451` Firmament's Caprice -> `130046`, `1500431` Iron Maidenfan -> `130044` -- and the
semantics corroborate the rest of the table (`130003` names a Fire Colossus and belongs to
Spatha of the Fire Colossus). `build_equipment.effect_key()` applies it, and `equipment.json`
now carries `effect` and `effect_key`.

This fills **46 of 806** equipment rows, which between them previously had *zero* descriptions.
11 of the 57 `130xxx` texts remain unassigned: their prefabs exist but carry an effect name
rather than an item name in `Desc`, and 27 legendary-range weapons have no skill link, so there
is no bijection to fall back on.

`tools/extract_skill_links.py` builds that mapping by reading the prefabs' Unity type trees: the
root `RGSkill` component keeps the designers' own Chinese label in its `Desc` field, and that label
is the item's Chinese name, so it joins straight onto the `Chinese` column of the localization
table. `--dump <skill id>` prints one prefab's whole component tree, values included.

## `extracted/prefabs/` -- the game logic itself

Every bundle still ships its Unity **type trees**, so `UnityPy`'s `read_typetree()` returns each
`MonoBehaviour` field by name. `tools/dump_prefabs.py` walks all of them and writes the
MonoBehaviour side of 18,182 prefabs (Transforms, renderers and particles are dropped):

| File | Prefabs | What's in it |
|---|---|---|
| `skill.json` | 7,808 | every skill: conditions, bullets, damage components, buff links |
| `stage.json` | 5,966 | dungeon objects, spawners, enemies |
| `buff.json` | 1,894 | `RGBuff` + its effect components (`BFC_*`, `BF_*`, `BC_*`) |
| `ui.json` | 728 | UI panels and their bound components |
| `obj.json`, `char.json`, `skin.json`, `home.json`, `scene.json` | 1,773 | props, pets/NPCs, skins, furniture, scene roots |

Values come through as the type tree gives them, with three compactions: object references become
`{"$ref": <path id>, "$name": "..."}`, the engine's per-level parameter struct collapses to
`{"lv": [v0, v1, v2, v3]}` (plus `cfg` / `unified` / `increment`), and empty fields are dropped.
The component's C# class is in `$type`.

Several prefab fields hold a *localization key* rather than free text, which is how prefabs join
back to readable names -- `RGBuff.buff_id` (`EBF_CHARGE` -> "Concentration"),
`RGCharacter.specificName` (`E07_S09` -> "Scorchsand Hrunnir") and `I2.Loc|Localize.mTerm`.
1,664 distinct localization keys are reachable this way.

**A prefab's own name is often a localization key as well**, and it follows the same
`<key>` / `<key>_D` convention as `ITEM_*`: prefab `S_P1_04_100` is "Pyroclad" and
`S_P1_04_100_D` is "Upon taking damage, you conjure a defensive shield that increases your Fire
Damage." That is 2,368 prefabs, 1,186 of them with a full description -- effectively a skill and
buff codex. `tools/build_indexes.py` resolves all of the above into `named_prefabs.json`,
`buffs.json`, `characters.json` and `loc_refs.json`.

Read `lv` as the value at skill level 0/1/2/3 -- e.g. `"atk_rate": {"lv": [60, 80, 100, 120]}`.
A component carrying `"cfg": [type, id]` instead is filled from the config tables at runtime and
its `lv` values are all zero; that is the case for most legendary-equipment parameters and for
character stats (`RGCharacter._charAttributeTemplate`).

## Known gaps (please read)

Several of these are gaps only because nothing in the APK can settle them. If you play the
game, you can: a few spot checks against what is actually on screen are worth more than any
amount of further digging, and that is how the icon-mapping bug below was found. Contact sheets
for pointing at are generated into `extracted/_sheets/`.

- **The numeric item -> icon mapping is wrong for 115 of 806 equipment rows.** The rule the
  tools use is an arithmetic guess that does not hold; the real table is in the encrypted Luban
  config and is not recoverable (zero `ItemIcon_` strings in `global-metadata.dat`, zero
  `ItemIcon` paths in the Addressables catalog, zero references across all 18,182 prefab dumps).
  The 550 rows that resolve through the `ITEM_*` name alias are fine. Fix plan and the evidence:
  [icon-mapping-plan.md](icon-mapping-plan.md).
- **Only 46 of 806 equipment rows have machine-derivable description text.** Those 46 come from
  the `130xxx` rule above. Ruled out as sources: `ITEM_<suffix>_D` (0 of 550), the
  `148xxx`/`149xxx` name block, and `95xxx`/`96xxx` (a per-item index for 156 items, but it only
  reaches fragment boilerplate).
- **`110001`-`112171` does hold more effect text, but the item link is unsolved.** Nothing in it
  joins to an item by name, yet it demonstrably describes items: `110421` is the effect of *both*
  `101591` Sangrilok Twinblades and `101593` Sangrilok Longbow, and `111061` is `101628`
  Valkyrian Scepter (all three confirmed in-game). So one text can serve several items, and the
  two known pairs share no offset. More confirmed pairs are needed before a rule is worth trying.
- **Rarity is not in the APK at all.** Only the six labels exist (`ITEM_RATE_0`-`_5`); no
  per-item rarity field appears anywhere. `item_details.json` carries a `tier` proxy instead,
  derived from the alias family code, with `legendary` asserted only for the 46 items that have
  a `LegendEquipSkill` prefab.
- **every config-driven number, and which affix an item rolls.** Both live in the
  [Luban](https://github.com/focus-creative-games/luban) config tables (`Luban.Runtime.dll` is
  referenced in `global-metadata.dat`). Those `.bytes` tables are not in Addressables, not in
  `Resources`, and not in any of the 468 bundles -- the only place left is `code_dll.bundle`, or
  the server. So drop rates, prices, enemy HP/ATK and the legendary effect lookup all stay out of
  reach for now. What IS available is every prefab-side number: see `extracted/prefabs/`.
- **`code_dll.bundle` / `code_aot.bundle` are encrypted and I did not crack them.** What is known:
  - They are *not* in the Addressables catalog, and only the two stock providers are registered,
    so they are loaded by the game's own bootstrap, not by a custom Addressables provider.
  - The plaintext is a normal AssetBundle holding `SoulKnight-Prequel.dll.bytes` -- the log strings
    `加载 SoulKnight-Prequel.dll.bytes成功` and `加载code_aot.bundle成功` are in `global-metadata.dat`.
    So the first 32 plaintext bytes are the fixed `UnityFS ... 5.x.x ... 2022.3.62f3` header.
  - It is a **block cipher in ECB mode**, not a stream cipher: the two files share exactly their
    first 32 bytes and diverge at byte 32, where the bundle's size field starts. A keystream cipher
    is ruled out because `file1 ^ file2` past byte 32 is uniformly random rather than the XOR of
    two nearly identical headers. Block size is 8, 16 or 32.
  - The key is **not a contiguous byte sequence** in `global-metadata.dat`, the four `classes*.dex`,
    `libnative-lib.so`, `libanogs.so`, `libanort.so` or `libil2cpp.so`. Every offset in those files
    was tested as a key against the known header for AES-128/192/256 (ECB and CBC), DES/3DES and
    SM4, plus MD5/SHA-256 of every printable string. Nothing matched.
  - Most likely it is materialised in ARM64 code as `MOV`/`MOVK` immediates, which no byte scan can
    find. The next step is a real disassembler on `libil2cpp.so`, starting from the
    `code_aot.bundle` string literal's xref.
- **The `assets/*.bytes` configs** (`distroConfig`, `cmjax`, `rnjax`) are base64 of an
  **8-byte-block ECB** ciphertext -- `distroConfig.bytes` and `iOS_CNdistroConfig.bytes` share
  exactly 56 decoded bytes (7 blocks), `rnjax`/`cmjax` exactly 8. `CoreKit.Util|CryptUtil.DecryptDES`
  exists in the metadata, so this is almost certainly DES, but that key was not found either.
  These are channel/SDK config, not game content.
- **`skp_loc_s13_bin` adds items that have no names yet.** Icons exist for ~120 IDs that have no
  localized name (e.g. weapons `101649`-`101655`, rings `105446`-`105474`) -- unreleased content
  whose art shipped early.

Four things the earlier version of this file listed as gaps are now fixed:

- **`skp_loc_s13_bin` is readable.** It is an ordinary table XORed with a repeating 120-byte key.
  Every table begins with the same `"Key"<TAB>"Type"<TAB>"English"<TAB>...` header row, so
  `ciphertext ^ header` *is* the key stream and the key falls out of it. That added 1,777 strings
  (26,926 -> 28,703), including 159 new effect descriptions in `111563`-`112171`, the `95xxx`/`96xxx`
  affix blocks, and 32 more equipment names. `deobfuscate()` in the extractor does this automatically.
- **`global-metadata.dat` is not encrypted.** Only its 0x108-byte header is scrambled; everything
  after it, including the whole string-literal table, is plaintext and greppable as-is.
- **Numeric equipment does have icons** -- 328 item rows are now linked, up from 23. See the icon
  naming rule under "Key naming" above.
- **Category labels are solved.** The slot is the third digit of the ID; `equipment.json` carries it.

## How to run it again

1. Unzip the APK folder so that `soul-knight-prequel-1-13-0/assets/Asset/*.bundle` exists.
   (The `.zip` is the same file as the `.apk`; it is a normal zip.)
2. Install Python 3.10+ and the one dependency: `pip install UnityPy`
3. From the project root:
   ```powershell
   python tools/extract_soulknight.py               # everything (icons take a long time)
   python tools/extract_soulknight.py --skip-icons  # text + catalog + item tables only
   python tools/extract_skill_links.py              # skill_links.json      (~5 min)
   python tools/dump_prefabs.py                     # prefabs/*.json        (~20 min)
   python tools/build_equipment.py                  # equipment.json        (instant)
   python tools/build_indexes.py                    # buffs/characters/loc_refs (instant)
   python tools/build_item_details.py               # item_details.json     (instant)
   python tools/build_guide.py                      # range-guide.html      (instant)
   ```
   The last three read the output of the first three, so run them last.
   `python tools/extract_named_sprites.py --prefix EBF_ --folder EBF` exports sprites the icon
   name filter never matched, without re-running the full pass.
   Options: `--apk-dir <folder>` and `--out <folder>` (defaults: `soul-knight-prequel-1-13-0`, `extracted`).

## What the script does, and why

1. **Localization.** The strings are `TextAsset`s inside the `localization_*.bundle` files, stored as a
   tab-separated table (`Key, Type, English, Chinese, ...`). Python's `csv` module breaks on it (unescaped
   quotes and newlines inside cells), so records are split at lines that start with `"key"<TAB>"type"<TAB>`.
   Bundles come in duplicate variants that are *not* interchangeable, so only the variant named by
   the Addressables catalog is read (see "Bundle variants" below). One table (`skp_loc_s13_bin`)
   is XOR-obfuscated; the header row of any plain table is the known plaintext that recovers its key.
2. **Asset catalog.** `assets/aa/catalog.json` is an Addressables catalog whose keys, buckets and entries are
   base64 blobs. The script decodes them to map each address to its asset path.
3. **Sprite index.** Every bundle is opened once and each `Sprite` name is recorded.
4. **Icons.** Bundles are opened **one at a time** and the sprites whose names match the icon patterns
   (`ItemIcon_`, `ICON_`, `UI_SkillIcon`, ...) are saved. One bundle per environment is a correctness
   requirement, not a memory trick -- see "Bundle variants" below. A sprite packed into a SpriteAtlas
   is only exportable from the atlas bundle it was packed into, so nothing is gained by co-loading.
   `--all-sprites` drops the name filter and exports all ~112k sprites instead (hours, several GB).
5. **Item tables.** Names, descriptions and icons are joined by key as described above.

## Bundle variants

44 logical bundles ship two or three files that differ only by a content hash in the filename,
and **none of those 44 groups are byte-identical**. Picking one by filename order lands on a
bundle the game does not load in 21 of them -- `buff_all`, `skill_class_all`, every
`skill_directclass_*` and three `skp_loc_*` tables among them.

`assets/aa/catalog.json` settles it: its `m_InternalIds` name exactly one variant per group,
44 out of 44. `extract_soulknight.shipped_bundles()` reads that list and every tool filters
through it.

Reading the wrong variant caused two distinct failures, both silent:

- **Stale text.** The orphan `skp_loc_s3`/`s5`/`s7` carry straight quotes where the shipped
  tables have curly ones. (`skp_loc_s13_bin` already sorted first, so it was unaffected. Two of
  its strings do read like earlier drafts -- `82115` has a malformed `#FA3914...</color>` where
  the orphan has `<color=#25bbbcff>` -- but that is the game's own shipped data, so it stays.)
- **Garbage icons.** Variants reuse the CAB name of their `.resS` stream file. Load two of them
  into one UnityPy environment and both atlas textures resolve that shared name to the *same*
  8 MB pixel blob -- and because the variants pack at different shapes (2048x4096 against
  4096x2048), every sprite crop lands on unrelated pixels. Nothing raises. This scrambled all
  ~500 `ItemIcon_*` PNGs and the `EBF_*` Fatebound icons in earlier versions of this repo, which
  is why the icon stage now opens one bundle at a time.

`tools/extract_skill_links.py`, `tools/dump_prefabs.py` and `tools/build_equipment.py` are
separate. The first two rest on the same fact: every bundle still ships its Unity type trees, so
`UnityPy`'s `read_typetree()` returns each `MonoBehaviour` field by name. That is what makes the
prefab side of the game readable at all, and it is worth calling directly for anything not covered
by the JSON files here.

Everything here was last regenerated after the bundle-variant fix: 28,703 strings, 1,490 `ITEM_*`
items, 16,908 numeric items, 65,194 indexed sprites and 5,544 icons (5,392 from the icon stage
plus 152 pulled by `extract_named_sprites.py`).
