#!/usr/bin/env python3
"""What changed between two game versions, and what that means for the hand-made data.

    python tools/version_diff.py                 # the two newest extracted versions
    python tools/version_diff.py 1.13.0 1.14.0

The hand-collected files in `guide/` are keyed on item ids, loc keys and sprite names,
and a patch normally keeps all three -- so nothing has to be re-captured by default.
This tool finds the exceptions and the new work, and writes them to
`extracted/<new>/changes_from_<old>.md`:

  * new and removed equipment, and items whose name changed (an id reused for a
    different item would silently carry the old item's hand-mapped icon and effect);
  * hand-mapped entries whose item or sprite no longer matches (name drift, sprite gone);
  * confirmed sprites whose **pixels** changed -- the one way an icon mapping can go
    wrong without any name changing;
  * changed text on loc keys the guide or `effect_map.json` uses;
  * new `ItemIcon_*` sprites, drawn on a contact sheet (`extracted/_sheets/`) so a new
    item's icon can be pointed at instead of looked up.

It ends with a "Your action" list: the in-game screenshots that would settle the rest.
Exit code 1 means something already hand-mapped needs a second look.
"""

import argparse
import hashlib
import json
import os
import sys

import versions

GUIDE = os.path.join(versions.ROOT, 'guide')
SHEETS = os.path.join(versions.EXTRACTED, '_sheets')


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf8') as fh:
        return json.load(fh)


def icon_files(out):
    """`sprite name -> absolute png path` for one version's icons/."""
    root = os.path.join(out, 'icons')
    found = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            if f.endswith('.png'):
                found.setdefault(f[:-4], os.path.join(d, f))
    return found


def digest(path):
    with open(path, 'rb') as fh:
        return hashlib.sha1(fh.read()).hexdigest()


def english(loc, key):
    return (loc.get(key) or {}).get('English')


_QUOTES = str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"'})


def same_name(a, b):
    """Names as a human would compare them: the hand-written maps type `'` where the
    game has `’` (Sheol's Gavel), and that is not a different item."""

    def norm(s):
        return ' '.join(s.translate(_QUOTES).casefold().split())

    return norm(a) == norm(b)


def guide_keys(guide_files, loc):
    """Every string in the guide files that is also a loc key."""
    keys = set()

    def walk(v):
        if isinstance(v, str):
            if v in loc:
                keys.add(v)
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(k)
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    for data in guide_files:
        walk(data)
    return keys


# --------------------------------------------------------------------------- diff


def diff(old, new, hand):
    """Compare two loaded versions. `old`/`new`: {'equipment', 'loc', 'icons'};
    `hand`: {'icon_map', 'effect_map', 'weapon_types', 'guides'}. Returns a dict of
    lists, each item a short dict -- see `report()` for how they are shown."""
    eq_a = {e['id']: e for e in old['equipment']}
    eq_b = {e['id']: e for e in new['equipment']}
    r = {
        k: []
        for k in (
            'new_items',
            'removed_items',
            'renamed_items',
            'hand_name_drift',
            'hand_item_gone',
            'sprite_gone',
            'sprite_changed',
            'text_changed',
            'text_gone',
            'new_sprites',
        )
    }

    for i in sorted(eq_b.keys() - eq_a.keys()):
        e = eq_b[i]
        r['new_items'].append(
            {
                'id': i,
                'name': e['name'],
                'slot': e['slot'],
                'icon': e.get('icon'),
                'effect': e.get('effect_key'),
            }
        )
    for i in sorted(eq_a.keys() - eq_b.keys()):
        r['removed_items'].append({'id': i, 'name': eq_a[i]['name']})
    for i in sorted(eq_a.keys() & eq_b.keys()):
        if not same_name(eq_a[i]['name'], eq_b[i]['name']):
            r['renamed_items'].append({'id': i, 'old': eq_a[i]['name'], 'new': eq_b[i]['name']})

    # Hand-mapped entries: the item must still exist under the name it was checked as.
    sprites_used = set()
    for file, data in (
        ('icon_map', hand['icon_map']),
        ('effect_map', hand['effect_map']),
        ('weapon_types', hand['weapon_types']),
    ):
        for section in ('confirmed', 'derived'):
            for key, entry in ((data or {}).get(section) or {}).items():
                if file == 'icon_map':
                    sprites_used.add(entry['icon'])
                current = english(new['loc'], key)
                if current is None:
                    r['hand_item_gone'].append(
                        {'file': file, 'key': key, 'name': entry.get('name')}
                    )
                elif entry.get('name') and not same_name(entry['name'], current):
                    r['hand_name_drift'].append(
                        {'file': file, 'key': key, 'was': entry['name'], 'now': current}
                    )

    # The sprites those mappings point at must still exist and still look the same.
    for sprite in sorted(sprites_used):
        a, b = old['icons'].get(sprite), new['icons'].get(sprite)
        if a and not b:
            r['sprite_gone'].append({'sprite': sprite})
        elif a and b and digest(a) != digest(b):
            r['sprite_changed'].append({'sprite': sprite, 'old': a, 'new': b})

    # Text the hand data depends on.
    used = guide_keys(hand['guides'], old['loc'])
    used |= {e['key'] for e in ((hand['effect_map'] or {}).get('confirmed') or {}).values()}
    used |= {e['effect_key'] for e in old['equipment'] if e.get('effect_key')}
    for key in sorted(used):
        a, b = english(old['loc'], key), english(new['loc'], key)
        if a is not None and b is None:
            r['text_gone'].append({'key': key, 'old': a})
        elif a is not None and a != b:
            r['text_changed'].append({'key': key, 'old': a, 'new': b})

    r['new_sprites'] = sorted(
        s for s in new['icons'].keys() - old['icons'].keys() if s.startswith('ItemIcon_')
    )
    return r


NEEDS_REVIEW = (
    'renamed_items',
    'hand_name_drift',
    'hand_item_gone',
    'sprite_gone',
    'sprite_changed',
    'text_changed',
    'text_gone',
)


def needs_review(r):
    return any(r[k] for k in NEEDS_REVIEW)


# --------------------------------------------------------------------------- output


def report(r, old_v, new_v, sheet=None):
    """The markdown report."""
    L = [f'# Changes from {old_v} to {new_v}', '']
    counts = ', '.join(f'{len(v)} {k.replace("_", " ")}' for k, v in r.items() if v)
    L += [counts or 'No differences that affect the extracted data or the hand-made maps.', '']

    def section(title, rows, fmt, note=None):
        if not rows:
            return
        L.extend([f'## {title} ({len(rows)})', ''])
        if note:
            L.extend([note, ''])
        L.extend(f'- {fmt(x)}' for x in rows)
        L.append('')

    section(
        'Hand-mapped item renamed or reused',
        r['hand_name_drift'],
        lambda x: (
            f'`{x["key"]}` in {x["file"]}.json: checked as **{x["was"]}**, now **{x["now"]}**'
        ),
        'The id may now be a different item. Re-check these before trusting their icon/effect.',
    )
    section(
        'Hand-mapped item gone',
        r['hand_item_gone'],
        lambda x: f'`{x["key"]}` {x.get("name") or ""} ({x["file"]}.json)',
    )
    section(
        'Confirmed sprite changed pixels',
        r['sprite_changed'],
        lambda x: f'`{x["sprite"]}`',
        'Same name, new picture: the item it was matched to may have moved.',
    )
    section('Confirmed sprite gone', r['sprite_gone'], lambda x: f'`{x["sprite"]}`')
    section(
        'Text used by the guide changed',
        r['text_changed'],
        lambda x: f'`{x["key"]}`: {x["old"][:90]!r} -> {x["new"][:90]!r}',
        'If a `{n}` placeholder moved, the Lv.1 values in effect_map.json may need a recheck.',
    )
    section(
        'Text used by the guide gone', r['text_gone'], lambda x: f'`{x["key"]}`: {x["old"][:90]!r}'
    )
    section(
        'Renamed equipment', r['renamed_items'], lambda x: f'`{x["id"]}` {x["old"]} -> {x["new"]}'
    )
    section(
        'New equipment',
        r['new_items'],
        lambda x: (
            f'`{x["id"]}` {x["name"]} ({x["slot"]})'
            + ('' if x['icon'] else ' -- **no icon**')
            + (f', effect `{x["effect"]}`' if x['effect'] else '')
        ),
    )
    section('Removed equipment', r['removed_items'], lambda x: f'`{x["id"]}` {x["name"]}')
    if r['new_sprites']:
        L.extend([f'## New ItemIcon sprites ({len(r["new_sprites"])})', ''])
        if sheet:
            L.extend([f'Contact sheet: `{os.path.relpath(sheet, versions.ROOT)}`', ''])
        L.extend([', '.join(f'`{s}`' for s in r['new_sprites']), ''])

    L.extend(['## Your action', ''])
    actions = []
    no_icon = [x for x in r['new_items'] if not x['icon']]
    if no_icon:
        names = ', '.join(x['name'] for x in no_icon[:8]) + (' ...' if len(no_icon) > 8 else '')
        actions.append(
            f'Screenshot the Codex of Equipment page of the {len(no_icon)} new item(s) without '
            f'an icon ({names}). One page settles icon, effect text and Lv.1 values.'
        )
    if r['hand_name_drift'] or r['sprite_changed']:
        actions.append(
            'Open the codex page of each re-check item above and say whether it still matches.'
        )
    L.extend(f'{i}. {a}' for i, a in enumerate(actions, 1))
    if not actions:
        L.append('Nothing to capture.')
    return '\n'.join(L) + '\n'


def contact_sheet(sprites, icons, path, scale=4, cols=8):
    """Upscaled new sprites with their names underneath, for pointing at."""
    from PIL import Image, ImageDraw

    cell_w, pad, label = 32 * scale, 8, 14
    rows = (len(sprites) + cols - 1) // cols
    sheet = Image.new('RGBA', (cols * (cell_w + pad), rows * (cell_w + pad + label)), 'white')
    draw = ImageDraw.Draw(sheet)
    for n, name in enumerate(sprites):
        x, y = (n % cols) * (cell_w + pad), (n // cols) * (cell_w + pad + label)
        im = Image.open(icons[name]).convert('RGBA')
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        im.thumbnail((cell_w, cell_w), Image.NEAREST)
        sheet.alpha_composite(im, (x, y))
        draw.text((x, y + cell_w + 1), name.replace('ItemIcon_', ''), fill='black')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path)
    return path


def load_version(out):
    return {
        'equipment': load_json(os.path.join(out, 'equipment.json'), []),
        'loc': load_json(os.path.join(out, 'localization_all.json'), {}),
        'icons': icon_files(out),
    }


def load_hand(guide_dir=GUIDE):
    guides = [
        load_json(os.path.join(guide_dir, f))
        for f in sorted(os.listdir(guide_dir))
        if f.endswith('.json')
        and f not in ('icon_map.json', 'effect_map.json', 'weapon_types.json')
    ]
    return {
        'icon_map': load_json(os.path.join(guide_dir, 'icon_map.json'), {}),
        'effect_map': load_json(os.path.join(guide_dir, 'effect_map.json'), {}),
        'weapon_types': load_json(os.path.join(guide_dir, 'weapon_types.json'), {}),
        'guides': guides,
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('old', nargs='?', help='old version (default: second newest)')
    ap.add_argument('new', nargs='?', help='new version (default: newest)')
    args = ap.parse_args()

    have = versions.out_versions()
    old_v = args.old or (have[-2] if len(have) >= 2 else None)
    new_v = args.new or (have[-1] if have else None)
    if not old_v or not new_v:
        sys.exit(f'need two extracted versions to compare; have {have}')
    old_out, new_out = versions.out_dir(old_v), versions.out_dir(new_v)
    for d in (old_out, new_out):
        if not os.path.isfile(os.path.join(d, 'equipment.json')):
            sys.exit(f'{d} has no equipment.json -- run tools/pipeline.py for that version')

    new = load_version(new_out)
    r = diff(load_version(old_out), new, load_hand())
    sheet = None
    if r['new_sprites']:
        sheet = contact_sheet(
            r['new_sprites'], new['icons'], os.path.join(SHEETS, f'new_icons_{new_v}.png')
        )
    text = report(r, old_v, new_v, sheet)
    path = os.path.join(new_out, f'changes_from_{old_v}.md')
    with open(path, 'w', encoding='utf8') as fh:
        fh.write(text)
    print(text)
    print(f'-> {os.path.relpath(path, versions.ROOT)}')
    sys.exit(1 if needs_review(r) else 0)


if __name__ == '__main__':
    main()
