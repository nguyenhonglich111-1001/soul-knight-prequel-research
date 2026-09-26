import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from match_panel_icons import PANELS, load, ncc
from PIL import Image


def test_panels_are_well_formed():
    for _pattern, size, targets, scales, keep in PANELS.values():
        assert size in (20, 72)
        assert 0 < keep <= 1
        assert targets and scales


def test_load_keeps_only_the_rows_above_the_label(tmp_path):
    os.makedirs(tmp_path / 'ClassSkill')
    im = Image.new('RGBA', (72, 72), (200, 100, 50, 255))
    im.save(tmp_path / 'ClassSkill' / 'soul_bonus_x.png')
    opaque = load(str(tmp_path), 'ClassSkill/soul_bonus_*.png', 72, 0.75)['soul_bonus_x']
    assert max(y for _, y, _ in opaque) < 54


def test_ncc_ignores_a_brightness_shift():
    sprite = Image.new('RGB', (20, 20))
    sp = sprite.load()
    for y in range(20):
        for x in range(20):
            sp[x, y] = (x * 10, y * 10, 80)
    opaque = [(x, y, sp[x, y]) for y in range(20) for x in range(20)]
    screen = Image.new('RGB', (200, 200))
    px = screen.load()
    for y in range(200):
        for x in range(200):
            r, g, b = sp[min(x // 10, 19), min(y // 10, 19)]
            px[x, y] = (r + 40, g + 40, b + 40)
    assert ncc(px, opaque, 20, 100, 100, 10) < 1
