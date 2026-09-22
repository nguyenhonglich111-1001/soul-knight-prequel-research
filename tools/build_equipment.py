#!/usr/bin/env python3
"""Join the equipment tables into one file: `extracted/equipment.json`.

Combines, per item:
  * `id`, `slot`, `name` and `names` (13 languages)  -- from localization_all.json
  * `icon` / `icon_source`                           -- guide/icon_map.json first (hand-checked
                                                        or derived from checked pairs), then
                                                        the `ITEM_*` alias rule
  * `skill_id`                                       -- from skill_links.json
  * `rarity_hint`                                    -- "legendary" when a skill prefab
                                                        implements the item
  * `effect` / `effect_key` / `effect_source`       -- guide/effect_map.json first (checked
                                                        in game), then `effect_key()` below

The slot comes from the ID's third digit. That mapping is not guesswork: the legendary
skill prefabs are filed as `Assets/RGPrefab/Skill/LegendEquipSkill/<slot>/<skill id>/`,
and the skill IDs use the *same* leading digit -- weapon skills are `1......`, armor
`2......`, and so on, matching the `101xxx` / `102xxx` / ... name blocks.

    python tools/build_equipment.py
"""
import argparse
import json
import os
import sys

SLOTS = {1: 'weapon', 2: 'armor', 3: 'helm', 4: 'boots', 5: 'ring', 6: 'necklace',
         7: 'gear', 8: 'core'}

# `1500xxx` skill prefabs step by 10; the `130xxx` effect-text block is numbered densely
# from 1. So the two line up by index, not by value.
EFFECT_BASE, SKILL_BASE = 130001, 1500001


def effect_key(skill_ids):
    """A legendary's effect-text key, from the id of the skill prefab that implements it.

        130001 + (skill_id - 1500001) // 10

    This is the item -> effect link that the Luban config was thought to be hiding. It is
    not a guess: three items were checked against the game and all three land exactly --
    `1500441` Grandfather Paradox -> `130045`, `1500451` Firmament's Caprice -> `130046`,
    `1500431` Iron Maidenfan -> `130044`. The semantics corroborate the rest of the table
    (`130003` talks about a Fire Colossus and belongs to Spatha of the Fire Colossus;
    `130012` rerolls dice and belongs to Pollux Castor).

    Only the `1500xxx` family is numbered this way. `1550xxx` ids are secondary skills on
    the same items and `1405291` is something else entirely; both are ignored, which is
    why the lowest `1500xxx` id wins when an item has several.
    """
    ids = sorted(s for s in (skill_ids or ()) if s.startswith('1500'))
    if not ids:
        return None
    return str(EFFECT_BASE + (int(ids[0]) - SKILL_BASE) // 10)


def slot_of(nid):
    """101643 -> 'weapon'. Only IDs shaped `10S____` carry a slot."""
    if not 100000 <= nid < 110000:
        return None
    return SLOTS.get(nid // 1000 % 10)


def icon_by_alias(name, byen, icons):
    """Resolve an icon through the item's English name -- the rule that actually works.

    The same English name also exists under a textual `ITEM_<suffix>` key, and the icon is
    then `ItemIcon_<suffix>`: "Orion's Galoshes" is both `104400` and `ITEM_CL_S1_000`, and
    its icon is `ItemIcon_CL_S1_000.png`. This is self-verifying, because the name has to
    match in both directions, and it covers 550 of 806 rows.

    Items it cannot reach take their icon from `guide/icon_map.json` or get none. There
    is no arithmetic link from an item ID to a sprite number -- see icon-mapping-plan.md."""
    for key in byen.get(name, ()):
        if key.startswith('ITEM_'):
            path = icons.get('ItemIcon_' + key[len('ITEM_'):])
            if path:
                return path
    return None


def icon_table(out):
    """`sprite name -> 'folder/file.png'` for every exported icon."""
    root = os.path.join(out, 'icons')
    return {f[:-4]: f'{d}/{f}' for d in os.listdir(root)
            for f in os.listdir(os.path.join(root, d)) if f.endswith('.png')}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='extracted')
    ap.add_argument('--guide-dir', default='guide',
                    help='where icon_map.json and effect_map.json live')
    args = ap.parse_args()

    def load(name, default=None):
        path = os.path.join(args.out, name)
        if not os.path.exists(path):
            if default is None:
                sys.exit(f'missing {path} -- run the other tools first')
            return default
        return json.load(open(path, encoding='utf8'))

    strings = load('localization_all.json')
    numeric = {r['id']: r for r in load('items_numeric.json')}
    links = load('skill_links.json', [])
    by_item = {}
    for r in links:
        by_item.setdefault(r['item_id'], []).append(r['skill_id'])

    byen = {}
    for key, row in strings.items():
        en = row.get('English')
        if en:
            byen.setdefault(en, []).append(key)
    icons = icon_table(args.out)
    sprite_path = {os.path.basename(p)[:-4]: p for p in icons.values()}

    def guide_map(name):
        path = os.path.join(args.guide_dir, name)
        return json.load(open(path, encoding='utf8')) if os.path.exists(path) else {}
    icon_map = guide_map('icon_map.json')
    effect_map = guide_map('effect_map.json').get('confirmed', {})

    def mapped_icon(nid):
        for source in ('confirmed', 'derived'):
            entry = icon_map.get(source, {}).get(str(nid))
            if entry:
                return sprite_path.get(entry['icon']), source
        return None, None

    rows, disagree = [], []
    for nid, row in sorted(numeric.items()):
        slot = slot_of(nid)
        if slot is None:
            continue
        skills = by_item.get(nid)
        icon, icon_source = mapped_icon(nid)
        if not icon:
            icon, icon_source = row['icon'], 'key'
            if not icon:
                icon = icon_by_alias(row['name'], byen, icons)
                icon_source = 'alias' if icon else None
        ekey, effect_source = effect_key(skills), 'skill-link'
        checked = effect_map.get(str(nid))
        if checked:
            if ekey and ekey != checked['key']:
                disagree.append(f'{nid}: game says {checked["key"]}, effect_key() says {ekey}')
            ekey, effect_source = checked['key'], 'confirmed'
        effect = (strings.get(ekey, {}).get('English') or '').strip() or None if ekey else None
        rows.append({
            'id': nid,
            'slot': slot,
            'name': row['name'],
            'names': row['names'],
            'icon': icon,
            'icon_source': icon_source,
            'skill_ids': skills,
            'rarity_hint': 'legendary' if skills else None,
            'effect_key': ekey if effect else None,
            'effect': effect,
            'effect_source': effect_source if effect else None,
            'effect_values_lv1': (checked or {}).get('lv1'),
        })

    path = os.path.join(args.out, 'equipment.json')
    with open(path, 'w', encoding='utf8') as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)

    from collections import Counter
    per_slot = Counter(r['slot'] for r in rows)
    print(f'{len(rows)} equipment rows -> {path}')
    print('  by slot:   ', dict(per_slot))
    print('  with icon: ', sum(1 for r in rows if r['icon']),
          dict(Counter(r['icon_source'] for r in rows if r['icon'])))
    print('  with skill:', sum(1 for r in rows if r['skill_ids']))
    print('  with effect:', sum(1 for r in rows if r['effect']),
          dict(Counter(r['effect_source'] for r in rows if r['effect'])))
    for d in disagree:
        print('  EFFECT DISAGREES:', d)
    if disagree:
        sys.exit(1)


if __name__ == '__main__':
    main()
