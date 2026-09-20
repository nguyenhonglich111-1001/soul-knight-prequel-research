#!/usr/bin/env python3
"""Derive browsable indexes from `extracted/prefabs/*.json`.

Several prefab fields hold localization keys rather than free text, which is what lets
prefabs be joined back to readable names:

    RGBuff.buff_id        'EBF_CHARGE'  -> "Concentration"
    RGCharacter.specificName 'E07_S09'  -> "Scorchsand Hrunnir"
    I2.Loc|Localize.mTerm '65384'       -> "Aeon Hunter"

A prefab's own *name* is frequently a localization key too, and those keys follow the
`ITEM_*` convention: `<key>` is the display name and `<key>_D` the description. So
`S_P1_04_100` is "Pyroclad" and `S_P1_04_100_D` is "Upon taking damage, you conjure a
defensive shield ...". That covers 2,368 skill, buff and dungeon-object prefabs.

Writes:
    named_prefabs.json  prefabs whose name is a loc key: name + description, 13 languages
    buffs.json      every RGBuff: id, localized name/description, effect component types
    characters.json every RGCharacter: prefab, localized name, boss flag, camp, template ids
    loc_refs.json   prefab -> every localization key it references, and via which field

    python tools/build_indexes.py
"""
import argparse
import collections
import json
import os
import sys

BUFF_TYPES = ('RGBuff',)


def iter_components(node, root=None):
    """(root prefab name, node name, component) for every MonoBehaviour in a prefab."""
    root = root or node.get('name', '')
    for c in node.get('components', []):
        yield root, node.get('name', ''), c
    for child in node.get('children', []):
        yield from iter_components(child, root)


def walk_strings(value, field, out):
    """Collect (field name, string) for every string in a component."""
    if isinstance(value, dict):
        for k, v in value.items():
            walk_strings(v, k, out)
    elif isinstance(value, list):
        for v in value:
            walk_strings(v, field, out)
    elif isinstance(value, str):
        out.append((field, value))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='extracted')
    args = ap.parse_args()

    loc_path = os.path.join(args.out, 'localization_all.json')
    prefab_dir = os.path.join(args.out, 'prefabs')
    if not os.path.isdir(prefab_dir):
        sys.exit(f'missing {prefab_dir} -- run tools/dump_prefabs.py first')
    loc = json.load(open(loc_path, encoding='utf8'))

    def text(key):
        row = loc.get(key)
        return row.get('English', '') if row else None

    buffs, chars, refs, named = [], [], [], []
    for fname in sorted(os.listdir(prefab_dir)):
        group = fname[:-5]
        for prefab in json.load(open(os.path.join(prefab_dir, fname), encoding='utf8')):
            key = prefab.get('name')
            if key in loc:
                desc = loc.get(key + '_D', {})
                named.append({
                    'prefab': key, 'group': group,
                    'name': loc[key].get('English', ''),
                    'names': loc[key],
                    'description': desc.get('English', ''),
                    'descriptions': desc or None,
                    'components': sorted({c.get('$type') for _, _, c
                                          in iter_components(prefab)}),
                })
            seen = collections.defaultdict(set)
            for root, node, comp in iter_components(prefab):
                kind = comp.get('$type', '')
                if kind in BUFF_TYPES or kind.startswith('RGBuff_'):
                    bid = comp.get('buff_id')
                    if bid:
                        buffs.append({
                            'buff_id': bid,
                            'name': text(bid),
                            'prefab': root, 'group': group,
                            'buff_type': comp.get('buff_type'),
                            'priority': comp.get('_priority'),
                            'show_icon': comp.get('show_icon'),
                            'components': sorted({c.get('$type') for _, _, c in
                                                  iter_components(prefab)} - {kind}),
                        })
                if kind == 'RGCharacter' or kind.startswith('RGCharacter'):
                    spec = comp.get('specificName')
                    chars.append({
                        'prefab': root, 'node': node, 'group': group,
                        'specific_name': spec,
                        'name': text(spec) if spec else None,
                        'is_boss': comp.get('isBoss'),
                        'camp': comp.get('camp'),
                        'race': comp.get('_race'),
                        'char_type': comp.get('char_type'),
                        'attribute_template': comp.get('_charAttributeTemplate'),
                    })
                found = []
                walk_strings(comp, '', found)
                for field, value in found:
                    if field not in ('$type', '$name') and value in loc:
                        seen[value].add(field)
            if seen:
                refs.append({
                    'prefab': prefab.get('name'), 'group': group,
                    'keys': {k: sorted(v) for k, v in sorted(seen.items())},
                })

    for name, rows in (('named_prefabs.json', named), ('buffs.json', buffs),
                       ('characters.json', chars), ('loc_refs.json', refs)):
        path = os.path.join(args.out, name)
        with open(path, 'w', encoding='utf8') as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
        print(f'{len(rows):6} rows -> {path}')
    print(f'       named prefabs with a description: {sum(1 for n in named if n["description"])}')
    print(f'       buffs with a localized name: {sum(1 for b in buffs if b["name"])}')
    print(f'       characters with a localized name: {sum(1 for c in chars if c["name"])}')


if __name__ == '__main__':
    main()
