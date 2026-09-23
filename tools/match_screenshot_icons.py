#!/usr/bin/env python3
"""Identify the item icon in Codex-of-Equipment screenshots by pixel-matching extracted sprites.

This is how `confirmed` entries in guide/icon_map.json are made: the user screenshots an
item's codex page, this finds the sprite, and the item name is read off the screenshot.
Item icons are 20x20 pixel art drawn at an integer-ish scale, so sampling the centre of
each art pixel and comparing it against every extracted 20x20 `ItemIcon*` sprite gives a
near-exact score -- 0 for an identical sprite, and a correct match stays under ~35 while
the runner-up sits above ~70. Only the sprite's opaque pixels are compared, which skips
the rarity frame behind it.

The icon position was calibrated on a 2868x1320 screenshot against a known item (Orion's
Galoshes = `ItemIcon_CL_S1_000`): 5.2 screen pixels per art pixel, top-left at (448, 158).
Other resolutions are scaled from the width; a small jitter search absorbs rounding.

    python tools/match_screenshot_icons.py "Soul knight prequel"/*.PNG
"""

import argparse
import glob
import json
import os

import versions
from PIL import Image

REF_W, SCALE, OX, OY = 2868, 5.2, 448, 158


def load_sprites(root):
    sprites = {}
    for d in os.listdir(root):
        if not d.startswith('ItemIcon'):
            continue
        for f in glob.glob(os.path.join(root, d, '*.png')):
            im = Image.open(f).convert('RGBA')
            if im.size != (20, 20):
                continue
            p = im.load()
            opaque = [(x, y, p[x, y][:3]) for y in range(20) for x in range(20) if p[x, y][3] > 200]
            if len(opaque) > 40:
                sprites[os.path.basename(f)[:-4]] = opaque
    return sprites


def score(px, opaque, s, ox, oy):
    err = 0
    for x, y, c in opaque:
        q = px[int(ox + (x + 0.5) * s), int(oy + (y + 0.5) * s)]
        err += abs(q[0] - c[0]) + abs(q[1] - c[1]) + abs(q[2] - c[2])
    return err / len(opaque)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('screenshots', nargs='+')
    ap.add_argument('--out', help='extracted version folder (default: newest extracted/<version>/)')
    ap.add_argument('--top', type=int, default=3)
    args = ap.parse_args()
    versions.resolve_out_arg(args)

    sprites = load_sprites(os.path.join(args.out, 'icons'))
    claimed = {}
    eq = os.path.join(args.out, 'equipment.json')
    if os.path.exists(eq):
        for r in json.load(open(eq, encoding='utf8')):
            if r['icon']:
                claimed.setdefault(os.path.basename(r['icon'])[:-4], []).append(
                    f'{r["id"]} {r["name"]}'
                )
    print(f'{len(sprites)} sprites')

    for path in args.screenshots:
        shot = Image.open(path).convert('RGB')
        k = shot.size[0] / REF_W
        s, ox, oy = SCALE * k, OX * k, OY * k
        px = shot.load()
        ranked = sorted(
            (
                min(score(px, op, s, ox + dx, oy + dy) for dx in (-2, 0, 2) for dy in (-2, 0, 2)),
                name,
            )
            for name, op in sprites.items()
        )
        best, name = ranked[0]
        gap = ranked[1][0] - best
        verdict = 'OK' if best < 40 and gap > 30 else 'UNSURE -- look at it'
        owner = '; '.join(claimed.get(name, ['unclaimed']))
        print(
            f'{os.path.basename(path)}: {name} (score {best:.0f}, next +{gap:.0f}) {verdict}'
            f'  [currently: {owner}]'
        )
        for e, n in ranked[1 : args.top]:
            print(f'    {n} {e:.0f}')


if __name__ == '__main__':
    main()
