import match_profile_icons as MP


def test_kind_of_numeric_ids_use_the_slot_digit():
    assert MP.kind_of('101644') == 'weapon'  # Firmament's Caprice
    assert MP.kind_of('103461') == 'helm'  # Darksteel Helm
    assert MP.kind_of('106733') == 'necklace'  # Heart Pendant
    # The profile's gear slot also holds 108xxx Clockgears, so gear and core share a kind.
    assert MP.kind_of('107702') == MP.kind_of('108721') == 'gear/core'


def test_kind_of_item_aliases():
    assert MP.kind_of('ITEM_CL_S1_010') == 'boots'  # Evanescent Halfboots
    assert MP.kind_of('ITEM_C_L_022') == 'necklace'  # Ciphertag
    assert MP.kind_of('ITEM_CB_A1_HSM') == 'armor'
    assert MP.kind_of('ITEM_W_BW_004') == 'weapon'
    assert MP.kind_of('ITEM_Potion_01') is None


def _grid(f):
    return [[f(x, y) for x in range(20)] for y in range(20)]


def test_ncc_ignores_the_profile_glow():
    opaque = [(x, y, (x * 12, y * 9, (x + y) * 5)) for y in range(11) for x in range(20)]
    same = _grid(lambda x, y: (x * 12, y * 9, (x + y) * 5))
    # The rarity glow brightens and flattens the icon; a uniform shift must still match.
    glow = _grid(lambda x, y: (40 + x * 6, 40 + y * 4.5, 40 + (x + y) * 2.5))
    other = _grid(lambda x, y: (200 - x * 12, y * 9, 100))
    assert MP.ncc(same, opaque) < 1
    assert MP.ncc(glow, opaque) < 5
    assert MP.ncc(other, opaque) > 50
