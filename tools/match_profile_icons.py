#!/usr/bin/env python3
"""Identify all 8 items a player wears from a leaderboard profile screenshot.

The profile ("Character Traits") shows the gear in two columns of four framed slots:

    Mech gear   | Cubis core
    Necklace    | Helm
    Ring        | Armor
    Boots       | Weapon

Each slot is compared against the 20x20 sprites of that slot's items only (a helm slot
never matches a ring). This differs from a codex page (match_screenshot_icons.py) in three
ways:

- **The label.** The `+NN` enhancement label covers the lower half of every icon, so only
  sprite rows 0-10 are compared.
- **The glow.** The profile draws icons under a rarity glow that brightens and tints them.
  Plain colour distance then prefers dark sprites (Ciphertag, Elementalist's Sorcery Hat)
  that blend into the dark slot. So the score is normalised cross-correlation over the
  sprite's opaque pixels, `100 * (1 - r)`, which ignores a uniform brightness and contrast
  shift.
- **The scale.** It varies per row, from 5.7 to 6.8 screen pixels per art pixel, and the
  weapon is the largest. A coarse pass at three scales ranks every candidate, and a fine
  scale/offset search re-scores the best few.

**Calibration.** Done 2026-09-25 on four 2868x1320 profiles (IMG_6312-6315), whose 32 items
were read off the codex recordings.

- **Accuracy:** 32/32 correct.
- **Scores:** 5-32 for the winner.
- **Smallest gap:** 9, between Evanescent and Forester's Halfboots, which are sibling
  sprites.

Other resolutions are scaled from the width. Check an `UNSURE` slot by eye. An item whose
icon the game downloads (not in the APK) cannot win, and loses to its nearest lookalike.

    python tools/match_profile_icons.py "Soul knight prequel"/IMG_6312.PNG
"""

import argparse
import json
import math
import os
import re

import versions
from PIL import Image

from match_screenshot_icons import load_sprites

REF_W = 2868
# (slot, sprite kind, icon centre x, icon centre y) on a REF_W-wide shot
SLOTS = [
    ('Mech gear', 'gear/core', 690, 264),
    ('Necklace', 'necklace', 696, 425),
    ('Ring', 'ring', 696, 592),
    ('Boots', 'boots', 696, 758),
    ('Cubis core', 'gear/core', 1428, 264),
    ('Helm', 'helm', 1424, 425),
    ('Armor', 'armor', 1424, 592),
    ('Weapon', 'weapon', 1425, 758),
]
LABEL_FREE_ROWS = 11  # sprite rows above the +NN label
COARSE = [(s, dx, dy) for s in (5.8, 6.2, 6.6) for dx in (-4, 0, 4) for dy in (-4, 0, 4)]
FINE = [
    (s / 10, dx, dy) for s in range(56, 70, 2) for dx in range(-8, 9, 4) for dy in range(-8, 9, 4)
]
REFINE_TOP = 12
# `10S NNN`: S is the slot (docs/data-model.md). Gear (7) and core (8) share a kind,
# because the profile's gear slot also holds `108xxx` Clockgears and Octagram Matrix.
ID_KIND = {'1': 'weapon', '2': 'armor', '3': 'helm', '4': 'boots', '5': 'ring', '6': 'necklace'}
ALIAS_KIND = {'A': 'armor', 'H': 'helm', 'S': 'boots', 'R': 'ring', 'L': 'necklace'}


def kind_of(key):
    """Equipment key -> the profile slot kind its sprite can appear in, or None."""
    if key.isdigit():
        return ID_KIND.get(key[2], 'gear/core' if key[2] in '78' else None)
    m = re.match(r'ITEM_([WC])[A-Z]*_([A-Z])', key)
    if not m:
        return None
    return 'weapon' if m.group(1) == 'W' else ALIAS_KIND.get(m.group(2))


def owners(out):
    """sprite name -> (key, name) of the equipment it belongs to."""
    claimed = {}
    for r in json.load(open(os.path.join(out, 'equipment.json'), encoding='utf8')):
        if r['icon']:
            claimed.setdefault(os.path.basename(r['icon'])[:-4], (str(r['id']), r['name']))
    # `ITEM_*`-only equipment (Evanescent Halfboots) has no numeric row.
    for r in json.load(open(os.path.join(out, 'items.json'), encoding='utf8')):
        if r.get('icon') and r['key'].startswith(('ITEM_W', 'ITEM_C')):
            claimed.setdefault(os.path.basename(r['icon'])[:-4], (r['key'], r['name']))
    return claimed


def grid(px, cx, cy, s):
    """The 20x20 art-pixel grid centred on (cx, cy) at `s` screen px per art px."""
    ox, oy = cx - 10 * s, cy - 10 * s
    xs = [int(ox + (i + 0.5) * s) for i in range(20)]
    ys = [int(oy + (i + 0.5) * s) for i in range(20)]
    return [[px[x, y] for x in xs] for y in ys]


def ncc(g, opaque):
    """100 * (1 - Pearson r) between a sprite's opaque RGB values and the screen grid."""
    a = [v for _, _, c in opaque for v in c]
    b = [v for x, y, _ in opaque for v in g[y][x][:3]]
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sab = saa = sbb = 0.0
    for u, v in zip(a, b):
        u -= ma
        v -= mb
        sab += u * v
        saa += u * u
        sbb += v * v
    return 100 * (1 - sab / (math.sqrt(saa * sbb) + 1e-6))


def match_slot(px, candidates, cx, cy, k):
    """[(score, sprite)] best first."""

    def fit(names, steps):
        grids = [grid(px, cx + dx * k, cy + dy * k, s * k) for s, dx, dy in steps]
        return sorted((min(ncc(g, candidates[n]) for g in grids), n) for n in names)

    coarse = fit(candidates, COARSE)
    return fit([n for _, n in coarse[:REFINE_TOP]], FINE)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('screenshots', nargs='+')
    ap.add_argument('--out', help='extracted version folder (default: newest extracted/<version>/)')
    ap.add_argument('--top', type=int, default=2)
    args = ap.parse_args()
    versions.resolve_out_arg(args)

    claimed = owners(args.out)
    by_kind = {}
    for n, op in load_sprites(os.path.join(args.out, 'icons')).items():
        kind = kind_of(claimed[n][0]) if n in claimed else None
        top = [p for p in op if p[1] < LABEL_FREE_ROWS]
        if kind and len(top) >= 20:
            by_kind.setdefault(kind, {})[n] = top
    print(', '.join(f'{len(v)} {k}' for k, v in sorted(by_kind.items())) + ' sprites')

    for path in args.screenshots:
        shot = Image.open(path).convert('RGB')
        k = shot.size[0] / REF_W
        px = shot.load()
        print(f'== {os.path.basename(path)}')
        for slot, kind, cx, cy in SLOTS:
            ranked = match_slot(px, by_kind[kind], cx * k, cy * k, k)
            best, name = ranked[0]
            gap = ranked[1][0] - best
            verdict = '' if best < 40 and gap > 5 else '  UNSURE -- look at it'
            key, item = claimed[name]
            print(
                f'  {slot:<10} {key} {item}  ({name}, score {best:.0f}, next +{gap:.0f}){verdict}'
            )
            for e, n in ranked[1 : args.top]:
                print(f'      {" ".join(claimed[n])} ({n}) {e:.0f}')


if __name__ == '__main__':
    main()
