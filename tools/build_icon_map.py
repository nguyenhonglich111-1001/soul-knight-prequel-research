#!/usr/bin/env python3
"""Fill in `guide/icon_map.json` -- the item -> icon table for equipment the alias rule misses.

There is no arithmetic link between an equipment ID and its sprite number, and the real
table is in the encrypted Luban config. What *is* known is a set of hand-checked pairs,
kept under `confirmed`. This script never edits those. It only derives the items that sit
**between** two confirmed pairs of the same slot, and only when the gap is unambiguous:

    102454 -> 2459  and  102462 -> 2467        (same offset, +5)
    => 102455..102461 -> 2460..2466            (7 items, 7 sprites, all present)

That assumes the art numbers do not run backwards *inside* the gap. They can: the
2026-09-22 codex video showed `102465` -> `2470` but `102466` -> `2469`. Such pairs are
reported as notes (never derived across), and every derived entry that video later
covered -- dozens -- matched, so the assumption holds almost everywhere. When the two
ends disagree on the offset, a sprite is missing somewhere in between and there is no
telling where, so nothing is derived: `106728 -> 6454` and `106733 -> 6458` leave four
items for three sprites.

Why not align whole slots by rank, as icon-mapping-plan.md first proposed: it was tested
against 10 in-game observations and got 2 right. Armor lands one sprite short on all four
checked items, and the cores are not even in the `8xxx` series -- they are `94xx`.

    python tools/build_icon_map.py           # rewrite `derived`
    python tools/build_icon_map.py --check   # compare against the frozen file; exit 1 on drift
"""

import argparse
import datetime
import itertools
import json
import os
import re
import sys

import versions

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_equipment import icon_by_alias, icon_table, slot_of

NUMERIC = re.compile(r'^ItemIcon_(\d+)000$')


def derive(confirmed, equipment, sprites):
    """`derived` entries and the problems found, from the confirmed pairs alone."""
    derived, problems, gaps = {}, [], []
    # Group by slot *and* the sprite series' leading digit: a few `1087xx` items are Mech
    # Cores drawn from the `84xx` gear series, not the `94xx` Cubis Core one.
    by_slot = {}
    for key, entry in confirmed.items():
        m = NUMERIC.match(entry['icon'])
        if key.isdigit() and m:
            series = f'{slot_of(int(key))}/{m.group(1)[0]}xxx'
            by_slot.setdefault(series, []).append((int(key), int(m.group(1))))
    for slot, pairs in sorted(by_slot.items()):
        pairs.sort()
        for (a, sa), (b, sb) in itertools.pairwise(pairs):
            if sb <= sa:
                gaps.append(
                    f'{slot}: {a}->{sa} and {b}->{sb} run backwards (confirmed both; not derived across)'
                )
                continue
            if b - a == 1:
                continue
            ids = range(a + 1, b)
            nums = range(sa + 1, sb)
            if b - a != sb - sa:
                gaps.append(
                    f'{slot}: {a}->{sa} .. {b}->{sb}: {len(ids)} items, '
                    f'{len(nums)} sprite numbers -- ambiguous, left out'
                )
                continue
            missing = [i for i in ids if i not in equipment] + [
                f'ItemIcon_{n}000' for n in nums if f'ItemIcon_{n}000' not in sprites
            ]
            if missing:
                gaps.append(f'{slot}: {a}..{b}: not contiguous ({", ".join(map(str, missing))})')
                continue
            for i, n in zip(ids, nums):
                derived[str(i)] = {
                    'icon': f'ItemIcon_{n}000',
                    'name': equipment[i],
                    'between': [str(a), str(b)],
                }
    return derived, problems, gaps


def write_map(path, data):
    """One entry per line, sorted, so a change shows up as a one-line diff."""

    def block(entries):
        rows = [
            f'  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}'
            for k, v in sorted(entries.items())
        ]
        return '{\n' + ',\n'.join(rows) + '\n }' if rows else '{}'

    head = {k: v for k, v in data.items() if k not in ('confirmed', 'derived')}
    lines = [f' {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}' for k, v in head.items()]
    lines += [f' "confirmed": {block(data["confirmed"])}', f' "derived": {block(data["derived"])}']
    with open(path, 'w', encoding='utf8') as fh:
        fh.write('{\n' + ',\n'.join(lines) + '\n}\n')


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('--out', help='extracted version folder (default: newest extracted/<version>/)')
    ap.add_argument('--map', default=os.path.join('guide', 'icon_map.json'))
    ap.add_argument(
        '--check',
        action='store_true',
        help='re-derive and compare against the frozen file instead of writing it',
    )
    args = ap.parse_args()
    versions.resolve_out_arg(args)

    frozen = json.load(open(args.map, encoding='utf8'))
    confirmed = frozen['confirmed']
    numeric = json.load(open(os.path.join(args.out, 'items_numeric.json'), encoding='utf8'))
    equipment = {r['id']: r['name'] for r in numeric if slot_of(r['id'])}
    strings = json.load(open(os.path.join(args.out, 'localization_all.json'), encoding='utf8'))
    byen = {}
    for key, row in strings.items():
        if row.get('English'):
            byen.setdefault(row['English'], []).append(key)
    icons = icon_table(args.out)

    problems = []
    for key, entry in confirmed.items():
        if entry['icon'] not in icons:
            problems.append(f'confirmed {key}: sprite {entry["icon"]} was not extracted')
        # Where the alias rule also has an answer, the two must agree -- this is the
        # only test the alias rule has against the game.
        name = equipment.get(int(key)) if key.isdigit() else strings.get(key, {}).get('English')
        alias = icon_by_alias(name, byen, icons) if name else None
        if alias and os.path.basename(alias)[:-4] != entry['icon']:
            problems.append(f'confirmed {key}: game says {entry["icon"]}, alias rule says {alias}')

    derived, backwards, gaps = derive(confirmed, equipment, icons)
    problems += backwards
    for g in gaps:
        print('  gap:', g)

    if args.check:
        old = frozen.get('derived', {})
        for key in sorted(set(old) | set(derived), key=str):
            a, b = old.get(key, {}).get('icon'), derived.get(key, {}).get('icon')
            if a != b:
                problems.append(f'derived {key}: frozen {a}, re-derived {b}')
    else:
        if frozen.get('derived') != derived:  # re-running unchanged leaves the file alone
            frozen['generated'] = datetime.date.today().isoformat()
        frozen['derived'] = derived
        write_map(args.map, frozen)

    print(
        f'{len(confirmed)} confirmed, {len(derived)} derived'
        + ('' if args.check else f' -> {args.map}')
    )
    for p in problems:
        print('  PROBLEM:', p)
    if problems:
        sys.exit(1)
    if args.check:
        print('  check OK')


if __name__ == '__main__':
    main()
