#!/usr/bin/env python3
"""Identify the Sacred Soul portraits and equipped Eidolons in Character-panel screenshots.

Two panels, both reached from Character in game:

- **Sacred Soul.** A ring of six round portraits, one per equipped piece. The set a
  portrait belongs to is read off the Set Effect list on the right. The portraits are the
  72x72 `soul_bonus_*` sprites (`icons/ClassSkill/`), drawn at ~2.9 screen px per art px.
- **Eidolons.** Three slot boxes top right: Support, Weapon, Armor. Each shows the equipped
  Eidolon's 20x20 `ItemIcon_spt_<id>` sprite at ~6 px per art px. The selected slot's
  Eidolon is named under the big portrait, which pins the id (`spt_<id>` in the game text).

Each target is scored like `match_profile_icons.py`: normalised cross-correlation over the
sprite's opaque pixels, `100 * (1 - r)`, searched over a few scales and offsets. It ignores a
uniform brightness shift, such as the selection glow.

**Calibration.** Done 2026-09-26 on 2868x1320 shots.

- **Sacred Soul:** IMG_6322.
- **Eidolons:** IMG_6323-6325.

Other resolutions are scaled from the width.

    python tools/match_panel_icons.py sacred "Soul knight prequel"/IMG_6322.PNG
    python tools/match_panel_icons.py eidolon "Soul knight prequel"/IMG_6323.PNG
"""

import argparse
import glob
import math
import os

import versions
from PIL import Image

REF_W = 2868
PANELS = {
    # name -> (sprite glob under icons/, sprite size, [(label, cx, cy)], scales, rows kept)
    # The Sacred Soul ring prints `Lv.NN` over the lower quarter of each portrait, so only
    # the top 75% of its rows are compared.
    'sacred': (
        'ClassSkill/soul_bonus_*.png',
        72,
        [
            ('top-left', 894, 337),
            ('top-right', 1276, 337),
            ('left', 743, 649),
            ('right', 1436, 649),
            ('bottom-left', 894, 953),
            ('bottom-right', 1276, 953),
        ],
        [2.7, 2.8, 2.9, 3.0, 3.1],
        0.75,
    ),
    'eidolon': (
        'ItemIcon_spt/ItemIcon_spt_*.png',
        20,
        [('Support', 1863, 357), ('Weapon', 2102, 357), ('Armor', 2341, 357)],
        [5.4, 5.7, 6.0, 6.3, 6.6],
        1.0,
    ),
}
OFFSETS = [(dx, dy) for dx in (-8, -4, 0, 4, 8) for dy in (-8, -4, 0, 4, 8)]
STEP = 2  # sample every 2nd art pixel of a 72x72 portrait; plenty for a face


def load(root, pattern, size, keep):
    """sprite name -> [(x, y, rgb)] of its opaque pixels, for sprites of exactly `size`."""
    step = STEP if size > 40 else 1
    out = {}
    for f in sorted(glob.glob(os.path.join(root, pattern))):
        im = Image.open(f).convert('RGBA')
        if im.size != (size, size):
            continue
        p = im.load()
        opaque = [
            (x, y, p[x, y][:3])
            for y in range(0, int(size * keep), step)
            for x in range(0, size, step)
            if p[x, y][3] > 200
        ]
        if len(opaque) >= 20:
            out[os.path.basename(f)[:-4]] = opaque
    return out


def ncc(px, opaque, size, cx, cy, s):
    """100 * (1 - Pearson r) between the sprite and the screen, sprite centred on (cx, cy)."""
    ox, oy = cx - size / 2 * s, cy - size / 2 * s
    a, b = [], []
    for x, y, c in opaque:
        q = px[int(ox + (x + 0.5) * s), int(oy + (y + 0.5) * s)]
        a += c
        b += q[:3]
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


def match(px, sprites, size, cx, cy, scales, k):
    """[(score, sprite)] best first."""
    ranked = []
    for name, opaque in sprites.items():
        best = min(
            ncc(px, opaque, size, cx + dx * k, cy + dy * k, s * k)
            for s in scales
            for dx, dy in OFFSETS
        )
        ranked.append((best, name))
    return sorted(ranked)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('panel', choices=sorted(PANELS))
    ap.add_argument('screenshots', nargs='+')
    ap.add_argument('--out', help='extracted version folder (default: newest extracted/<version>/)')
    ap.add_argument('--top', type=int, default=3)
    args = ap.parse_args()
    versions.resolve_out_arg(args)

    pattern, size, targets, scales, keep = PANELS[args.panel]
    sprites = load(os.path.join(args.out, 'icons'), pattern, size, keep)
    print(f'{len(sprites)} candidate sprites ({pattern})')
    for path in args.screenshots:
        shot = Image.open(path).convert('RGB')
        k = shot.size[0] / REF_W
        px = shot.load()
        print(f'== {os.path.basename(path)}')
        for label, cx, cy in targets:
            ranked = match(px, sprites, size, cx * k, cy * k, scales, k)
            best, name = ranked[0]
            gap = ranked[1][0] - best
            verdict = '' if best < 40 and gap > 5 else '  UNSURE -- look at it'
            print(f'  {label:<12} {name}  (score {best:.0f}, next +{gap:.0f}){verdict}')
            for e, n in ranked[1 : args.top]:
                print(f'      {n} {e:.0f}')


if __name__ == '__main__':
    main()
