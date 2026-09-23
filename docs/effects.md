# Descriptions and legendary effect text

Where item and skill descriptions live, how legendary effects join to their items, and which
places have already been checked and found empty. Read this before touching `effect_key()`,
`NUMERIC_DESC_RULES`, [guide/effect_map.json](../guide/effect_map.json) or anything that
fills `effect` in `equipment.json`.

## Fixed description offsets

Numeric keys keep the description at a fixed offset from the name, and the offset differs per
block:

- `+1000` for the `1`-`447` item block and for the `200xxx` skill block (`200102` Rain of
  Arrows: Leonar → `201102`);
- `+100` for `7301`-`7437`.

`NUMERIC_DESC_RULES` in `extract_soulknight.py` holds the item offsets, and they are applied
automatically in `items_numeric.json`.

Inside the `110xxx`/`120xxx` effect blocks the convention is reversed: the **description is at
`N` and the name at `N+1`**. For example, `111561` is "`$diaoling$`'s effects changed to: …"
and `111562` is "Bone-Deep Torment".

## Weapon legendaries: `1500xxx` → `130xxx`, solved

Equipment has no `<id>_D` key. The item → effect link is **not** locked in the Luban config,
at least for weapon legendaries:

```
effect key = 130001 + (skill_id - 1500001) // 10          # build_equipment.effect_key()
101643 Grandfather Paradox / 祖父悖论 → skill 1500441 → 130045   (buff BF_1500441)
```

The `1500xxx` skill prefabs step by 10, and the `130xxx` text block is numbered densely from 1,
so the two line up by index.

- **Checked in game:** all three items checked land exactly: `1500441` → `130045`, `1500451`
  Firmament's Caprice → `130046`, `1500431` Iron Maidenfan → `130044`.
- **Semantics agree:** `130003` names a Fire Colossus and belongs to Spatha of the Fire
  Colossus; `130012` rerolls dice and belongs to Pollux Castor.
- **Only `1500xxx` counts.** `1550xxx` are secondary skills of the same items, and `1405291`
  is unrelated, so the lowest `1500xxx` id wins.
- **Where the link comes from.** `extract_skill_links.py` reads the root `RGSkill` component's
  `Desc` field. It holds the designers' Chinese label, which is the item's Chinese name, so it
  joins straight onto the localization's `Chinese` column.

This rule fills 46 of 806 rows.

- **One orphan has an owner.** `130056` Scorching Breath belongs to `101653` Prairie Fire and
  Rending Earth, which has no skill prefab (confirmed by screenshot). So the other orphans can
  have owners too.
- **10 of the 57 `130xxx` texts stay unassigned.** Their prefabs' `Desc` holds an effect name,
  not an item name (`1500531` is `火焰吐息焦土`). 27 legendary-range weapons have no skill link,
  so there is no bijection to fall back on. **Do not rank-align these; ask instead.**
- **One lead worth checking:** `130024` says "your weapon become Immaterial and
  **Anumbral**", and `101616` Anumbral Blade has no link.

Legendary weapons pair one-to-one with a class skill, so they do not need codex recordings.

## Everything else: collected, not derived

**[guide/effect_map.json](../guide/effect_map.json) holds every confirmed item → text-key pair**,
together with its Lv.1 `{n}` values.

- **Precedence.** `build_equipment.py` prefers it over `effect_key()` and fails if the two ever
  disagree. They agree on all twelve legendaries checked.
- **Where the keys are.** They sit in `110001`-`112171` (414 keys, stepping by 10) and
  `120001`-`120420`.
- **This block was called a dead end here for a while.** It reads like a generic affix pool, and
  nothing in it joins to an item by name (0 matches). But it holds real per-item text for the
  legendaries that have no skill prefab.
- **Confirmed in game:**
  - `110421` ("You become `$kuangnu$` whenever you've taken damage equal to {0}% of your max
    life") is the effect of **both** `101591` Sangrilok Twinblades and `101593` Sangrilok
    Longbow.
  - `111061` ("…gain Final Verdict…") is `101628` Valkyrian Scepter.
- **So the mapping is not one-to-one, and not derivable from either id.** Pairs read off
  screenshots show no pattern: `102452` → `110549`, `102453` → `111161`, `108701` →
  `110567`, `108708` → `111081`, and neighbouring items land thousands of keys apart.

**Why only weapons link automatically** (researched 2026-09-22):

- **Every slot has legendary skill prefabs**, under
  `LegendEquipSkill/<armor|head|shoes|ring|lace|other>/…`:
  - 24 armor (`24xxxxx`), 26 helm (`34xxxxx`), 20 boots (`44xxxxx`), 35 ring (`54xxxxx`)
    and 31 necklace (`64000x1`);
  - plus the `71`, `72` and `90` families.
- **Unlike `1500xxx`, there is nothing to join on.** Their `RGSkill` has **no `Desc`**, their
  buffs carry no loc key, and every number is `cfg: [0, <prefab id>]`, i.e. it comes from the
  encrypted config.
- **The `"<name> Affixia"` list (`95xxx`) is the legendary roster.** 156 of its items match
  equipment: 26 necklaces, 30 rings, 31 cores, and so on. But its order does not predict the
  text key.
- **Text keys in `110xxx`-`112xxx` were handed out roughly chronologically.**
  - Necklaces `106441` < `106725` < `106728` < `106733` < `106735` get increasing keys.
  - The dense `11054x`-`11057x` block is one patch: `110560` names Warp Drive (`107701`),
    `110561` is Vitality, `110563` Clockwork and `110567` Hellhound Claw (`108701`).
  - There are exceptions: `102453` → `111161` jumps far ahead of `102452` → `110549`.

  This is good enough to *propose* candidates, never to assert them.
- **Gear texts in that block use the old "Chip" wording.** Several gear effects have a `Chip`
  twin a few keys away (`110561`/`111261`, `110563`/`111281`). The codex shows the "talent
  skill" one.
- **Many effect texts have 2-4 near-duplicate keys:** older wording, a Chip twin, or an
  alternate version. Pick the one whose wording matches the screenshot, never the first
  regex hit.
- **`111561`-`111679` are Forged Affixes (熔铸词缀), not item effects.** They step by 2
  (description at `N`, name at `N+1`), sit between legendary blocks that step by 10, and no
  item owns them. Proof: `95229` "Frostshock Thunder Affixia" / `96229` "Fragments obtained by
  dismantling the Frostshock Thunder Forged Affix" (2026-09-24). Families by wording:
  - `$keyword$`'s effects changed to …: Bone-Deep Torment, Polar Extremes, Frostshock Thunder.
  - Possessing a keyword or hitting an ailing enemy (one per damage type): Pyrekindled,
    Snowburied, Thundertrailed, Marroweaten, Worldbright, Shadowvouring, Mountcleaving.
  - "If you also possess …" sets, Han vs Yellow Turbans: Mandate of the Han, Motley Mob, ….
  - `<keyword>: Ascension` (effect +{0}%): Lambent, Voltcharged, Gelid, Bladeheart.

  Which slot or forge category each rolls on is not in the text; ask the user.

## Dead ends: do not search these again

- **`ITEM_<suffix>_D`.** The alias that reliably gives an icon gives **no** description
  (0 of 550).
- **`148xxx`/`149xxx`** (1,312 keys) is a pure *name* block for the textual items. For example,
  `148114 + 1000` is "Fallen Starwalkers", not a description of "Wayfarer's Tophat".
- **`95xxx`/`96xxx`** (`"<name> Affixia"` + fragment descriptions). Parsing it yields a
  per-item index for 156 items, including the `108726`-`108730` cores. But the text it reaches
  is fragment boilerplate, not the item's effect.
- **Ordinary non-legendary equipment** has no per-item description anywhere in the APK, and
  would not have one. In game those items show *rolled* affixes, which the config draws from
  the `11xxxx` pool. The `130xxx` block exists precisely because legendary effects are fixed.

## `$token$` and `{0}`

- **`{0}`** is a value the game fills in from the encrypted config, so it cannot be recovered.
- **`$token$`** is a glossary reference (`$kuangnu$`). The token table is encrypted, but it is
  not needed (found 2026-09-24; `tools/build_glossary.py` -> `glossary.json`):
  - **The token is the pinyin of the term's Chinese**, and the terms are keys `206001`-`206136`
    (`$jisu$` = `206032` 急速 Swift). 122 of 128 tokens match exactly one term.
  - The rest: `_` separators (`xu_fuguang` = 虚·辐光), polyphones (流血 read *liuxue*), one
    game typo (`lingfeng` = 凛风 *lin*feng) and `daxue` = 大出血 Exsanguinate (a syllable
    dropped; taken from the hand-checked `guide/ranger.json` glossary, which German
    "Verbluten" and Russian "обескровливание" agree with).
  - **Each term's rules text is its key + 500** (`206532`: "Movement speed is increased by
    {0}% for {1}s."). All 136 pairs were read side by side and every one fits, and the user
    confirmed in game (2026-09-24) that the tooltip text matches. `206699`-`206701`
    are extra variants with no term.
  - The screenshot-confirmed tokens below all come out right.
- **Screenshots settle both.** The codex shows effect text with every token expanded and every
  `{n}` filled in. That is how these tokens were recovered:
  - `jiankang` Healthy
  - `binwei` Critically Injured
  - `jisu` Swift
  - `yingyan` Eagle Eye
  - `yishang` Vulnerable

  It is also where the `lv1` values in `effect_map.json` come from (effect Lv.1 = equipment
  level 60, Normal tier).
