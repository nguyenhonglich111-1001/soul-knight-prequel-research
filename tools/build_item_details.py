#!/usr/bin/env python3
"""Everything derivable about each piece of equipment: `extracted/item_details.json`.

`equipment.json` answers "what is this item called and which slot is it". This answers
the rest -- weapon type, weapon class, armor class, content tier, effect text -- by
decoding the `ITEM_<family>_<code>_<id>` alias key, which turns out to carry most of it.

    ITEM_WL_BK_000   ->  family WL (named weapon)  type BK (Focus)
    ITEM_CB_A1_EQB   ->  family CB (boss armor)    armor class 1

What is NOT here, because it is not in the APK: the actual **rarity** (Common / Charmed /
Rare / Epic / Legendary / Insane). Only the six labels exist, at `ITEM_RATE_0`-`_5`; no
per-item rarity field appears anywhere. `tier` below is the closest honest proxy.

    PYTHONIOENCODING=utf-8 python tools/build_item_details.py
    PYTHONIOENCODING=utf-8 python tools/build_item_details.py --slot weapon --tier legendary
"""

import argparse
import collections
import json
import os
import re
import sys

import versions

# The game's own names, from `Const_ItemType_*`.
CATEGORY = {
    'weapon': 'Weapon',
    'armor': 'Armor',
    'helm': 'Helm',
    'boots': 'Boots',
    'ring': 'Ring',
    'necklace': 'Necklace',
    'gear': 'Mech Core',
    'core': 'Cubis Core',
}

# Alias code -> `Const_ItemType_*` label. All twelve weapon types are covered.
WEAPON_TYPE = {
    'SS': 'Sword & Shield',
    'GS': 'Greatsword',
    'DS': 'Dual Blades',
    'LS': 'Spear & Shield',
    'SP': 'Spear',
    'CB': 'Crossbow',
    'BW': 'Bow',
    'SQ': 'Dual Pistols',
    'ST': 'Staff',
    'BK': 'Focus',
    'MR': 'Bangle',
    'QT': 'Fist Weapon',
}

# `206501`-`206503` group the twelve types into three classes.
WEAPON_CLASS = {
    t: c
    for c, ts in (
        ('Melee', ('Sword & Shield', 'Spear & Shield', 'Greatsword', 'Dual Blades', 'Spear')),
        ('Ranged', ('Bow', 'Crossbow', 'Dual Pistols')),
        ('Casting', ('Staff', 'Focus', 'Bangle')),
    )
    for t in ts
}

# Second letter of the family code, read off the ID blocks and the item names:
#   (none) the starting/shop gear      B  boss drops (Grimhowl*, *of the Boar King)
#   L      the named sets              S  the newest block, whose icons the game downloads
FAMILY = {'': 'base', 'L': 'named', 'B': 'boss', 'S': 'latest'}

ALIAS = re.compile(r'^ITEM_([WC])([BLS]?)_([A-Z]+)(\d*)_(.+)$')

# Specialization trees are keyed `SX_P1_<line><modifier>_<node>`, and the two digits are
# exactly the two halves of the `Info_CLASS_<LINE>_<MODIFIER>` key -- branch 22 is
# ARCHER_ROBBER (Ranger), 55 is LIGHT_DARK (Riftvoker, whose tree holds Reality Throw,
# the skill Pollux Castor's effect text names). That gives a legendary its class: its
# effect text almost always names a skill, and the skill names its tree.
LINE = {'1': 'WARRIOR', '2': 'ARCHER', '3': 'PSYCHIC', '4': 'STORM', '5': 'LIGHT'}
MODIFIER = {'1': 'GUARD', '2': 'ROBBER', '3': 'NATURAL', '4': 'FLAME', '5': 'DARK'}
SPEC = re.compile(r'^SX_P1_(\d)(\d)_\d+$')
# `S_P1_<line>0_<node>` is the shared line tree above the five specializations.
BASE = re.compile(r'^S_P1_(\d)0_\d+$')
LINE_LABEL = {'1': 'Warrior', '2': 'Archer', '3': 'Psychic', '4': 'Storm', '5': 'Light'}

# Only used when there is no alias -- which is exactly the legendary block. Guesses from
# the English name, so it is reported separately from the alias-derived answer.
NAME_HINTS = [
    ('Sword & Shield', 'Sword & Shield'),
    ('Spear & Shield', 'Spear & Shield'),
    ('Crossbow', 'Crossbow'),
    ('Longbow', 'Bow'),
    ('Bow', 'Bow'),
    ('Greatsword', 'Greatsword'),
    ('Twinblades', 'Dual Blades'),
    ('Dual Blades', 'Dual Blades'),
    ('Knuckles', 'Fist Weapon'),
    ('Pistols', 'Dual Pistols'),
    ('Scepter', 'Staff'),
    ('Staff', 'Staff'),
    ('Tome', 'Focus'),
    ('Grimoire', 'Focus'),
    ('Bangle', 'Bangle'),
    ('Spear', 'Spear'),
    ('Lance', 'Spear'),
]


def type_from_name(name):
    for needle, label in NAME_HINTS:
        if needle.lower() in name.lower():
            return label
    return None


def class_index(loc):
    """`skill display name -> class`, for every skill-tree node.

    A specialization node pins the exact class. A node from the shared line tree only
    pins the line, so it answers "Warrior line" -- still the useful half of the answer,
    and it is what an item like Iron Maidenfan (Whirlwind Slash) can support."""
    out = {}
    for key, row in loc.items():
        name = (row.get('English') or '').strip()
        if len(name) <= 3:  # short names match far too loosely
            continue
        m = SPEC.match(key)
        if m:
            ck = f'Info_CLASS_{LINE[m.group(1)]}_{MODIFIER[m.group(2)]}'
            label = (loc.get(ck, {}).get('English') or '').strip()
            if label:
                out[name] = label  # specialization wins over a line match
            continue
        b = BASE.match(key)
        if b:
            out.setdefault(name, LINE_LABEL[b.group(1)] + ' line')
    return out


def class_of(effect, index):
    """Best skill name mentioned in the effect text wins.

    A specialization beats a line, however long the names are -- Grandfather Paradox
    names both "Scattershot" (Ranger) and "Piercing Arrows" (Archer line), and Ranger is
    the real answer. Within a rank the longest name wins, so "Rain of Arrows: Syl" beats
    a bare "Rain of Arrows"."""
    hits = [(not c.endswith(' line'), len(n), c) for n, c in index.items() if n in effect]
    return max(hits)[2] if hits else None


def build(out):
    eq = json.load(open(os.path.join(out, 'equipment.json'), encoding='utf8'))
    loc = json.load(open(os.path.join(out, 'localization_all.json'), encoding='utf8'))
    byen = collections.defaultdict(list)
    for key, row in loc.items():
        if row.get('English'):
            byen[row['English']].append(key)
    cidx = class_index(loc)
    # Weapon types read off the in-game codex tabs (guide/weapon_types.json). They beat a
    # name guess; an alias type is from the item's own key, so a disagreement is reported.
    wt = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', 'guide', 'weapon_types.json'
    )
    codex = json.load(open(wt, encoding='utf8'))['confirmed'] if os.path.exists(wt) else {}

    rows = []
    for r in eq:
        alias = next((k for k in byen.get(r['name'], ()) if ALIAS.match(k)), None)
        fam = code = digit = None
        if alias:
            kind, sub, code, digit, _ = ALIAS.match(alias).groups()
            fam = kind + sub
        wtype = WEAPON_TYPE.get(code) if r['slot'] == 'weapon' else None
        source = 'alias' if wtype else None
        seen = codex.get(str(r['id']), {}).get('type')
        if seen and wtype and seen != wtype:
            print(f'  CODEX DISAGREES: {r["id"]} {r["name"]}: alias {wtype}, codex tab {seen}')
        if seen and not wtype:
            wtype, source = seen, 'codex'
        if r['slot'] == 'weapon' and not wtype:
            wtype = type_from_name(r['name'])
            source = 'name-guess' if wtype else None
        rows.append(
            {
                'id': r['id'],
                'name': r['name'],
                'name_cn': r['names'].get('Chinese'),
                'category': CATEGORY[r['slot']],
                'weapon_type': wtype,
                'weapon_type_source': source,
                'weapon_class': WEAPON_CLASS.get(wtype),
                'armor_class': int(digit) if digit else None,
                'family': fam,
                # A LegendEquipSkill prefab is proof of the tier; the family code is a proxy.
                'tier': 'legendary' if r['skill_ids'] else (FAMILY.get(fam[1:]) if fam else None),
                'class': class_of(r.get('effect') or '', cidx),
                'alias': alias,
                'icon': r['icon'],
                'skill_ids': r['skill_ids'],
                'effect_key': r.get('effect_key'),
                'effect': r.get('effect'),
            }
        )
    return rows


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('--out', help='extracted version folder (default: newest extracted/<version>/)')
    ap.add_argument('--slot', help='print only this category, e.g. weapon')
    ap.add_argument('--tier', help='print only this tier: legendary/latest/boss/named/base')
    args = ap.parse_args()
    versions.resolve_out_arg(args)
    if not os.path.isdir(args.out):
        sys.exit(f'missing {args.out} -- run the extraction pipeline first')

    rows = build(args.out)
    path = os.path.join(args.out, 'item_details.json')
    with open(path, 'w', encoding='utf8') as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    print(f'{len(rows)} rows -> {path}')
    for field in (
        'weapon_type',
        'weapon_class',
        'armor_class',
        'family',
        'tier',
        'class',
        'effect',
    ):
        print(f'  with {field:18}: {sum(1 for r in rows if r[field])}')
    print('  tiers:', dict(collections.Counter(r['tier'] for r in rows).most_common()))
    print(
        '  weapon types:',
        dict(collections.Counter(r['weapon_type'] for r in rows if r['weapon_type'])),
    )

    sel = [
        r
        for r in rows
        if (not args.slot or r['category'].lower() == args.slot.lower())
        and (not args.tier or r['tier'] == args.tier)
    ]
    if args.slot or args.tier:
        print(f'\n{len(sel)} matching rows\n')
        print(f'{"id":>7}  {"name":32} {"type":14} {"class":14} {"tier":10} effect')
        for r in sel:
            eff = (r['effect'] or '')[:40]
            src = '?' if r['weapon_type_source'] == 'name-guess' else ' '
            print(
                f'{r["id"]:>7}  {r["name"][:30]:32} {str(r["weapon_type"] or "-")[:13]:13}{src} '
                f'{str(r["class"] or "-")[:14]:14} {r["tier"] or "-"!s:10} {eff}'
            )


if __name__ == '__main__':
    main()
