import build_glossary as BGL

import build_equipment as BE
import build_guide as BG
import build_icon_map as BI
import build_item_details as BD

# --------------------------------------------------------------------------- build_equipment


def test_effect_key_matches_in_game_checks():
    # All three were confirmed against the game.
    assert BE.effect_key(['1500441']) == '130045'  # Grandfather Paradox
    assert BE.effect_key(['1500451']) == '130046'  # Firmament's Caprice
    assert BE.effect_key(['1500431']) == '130044'  # Iron Maidenfan


def test_effect_key_ignores_other_families_and_takes_lowest():
    assert BE.effect_key(['1550441', '1405291']) is None
    assert BE.effect_key(['1500451', '1550001', '1500441']) == '130045'
    assert BE.effect_key(None) is None


def test_slot_of():
    assert BE.slot_of(101643) == 'weapon'
    assert BE.slot_of(104400) == 'boots'
    assert BE.slot_of(108701) == 'core'
    assert BE.slot_of(109000) is None  # there is no slot 9
    assert BE.slot_of(7501) is None


def test_icon_by_alias():
    byen = {"Orion's Galoshes": ['104400', 'ITEM_CL_S1_000']}
    icons = {'ItemIcon_CL_S1_000': 'ItemIcon_CL/ItemIcon_CL_S1_000.png'}
    assert BE.icon_by_alias("Orion's Galoshes", byen, icons) == 'ItemIcon_CL/ItemIcon_CL_S1_000.png'
    assert BE.icon_by_alias("Orion's Galoshes", byen, {}) is None
    assert BE.icon_by_alias('Unknown', byen, icons) is None


# --------------------------------------------------------------------------- build_icon_map


def confirmed(*pairs):
    return {str(k): {'icon': f'ItemIcon_{n}000'} for k, n in pairs}


def test_derive_fills_between_equal_offsets():
    eq = {i: f'helm {i}' for i in range(103464, 103468)}
    sprites = {f'ItemIcon_{n}000' for n in range(3467, 3471)}
    derived, _, gaps = BI.derive(confirmed((103464, 3467), (103467, 3470)), eq, sprites)
    assert gaps == []
    assert {k: v['icon'] for k, v in derived.items()} == {
        '103465': 'ItemIcon_3468000',
        '103466': 'ItemIcon_3469000',
    }
    assert derived['103465']['between'] == ['103464', '103467']


def test_derive_refuses_unequal_offsets():
    eq = dict.fromkeys(range(103467, 103470), 'x')
    sprites = {f'ItemIcon_{n}000' for n in range(3470, 3475)}
    derived, _, gaps = BI.derive(confirmed((103467, 3470), (103469, 3473)), eq, sprites)
    assert derived == {}
    assert 'ambiguous' in gaps[0]


def test_derive_refuses_missing_sprite_and_backwards_pairs():
    eq = dict.fromkeys(range(102452, 102456), 'x')
    sprites = {'ItemIcon_2457000', 'ItemIcon_2460000'}  # 2458/2459 missing
    derived, _, gaps = BI.derive(confirmed((102452, 2457), (102455, 2460)), eq, sprites)
    assert derived == {} and 'not contiguous' in gaps[0]
    _, _, gaps = BI.derive(confirmed((102452, 2460), (102455, 2457)), eq, sprites)
    assert 'backwards' in gaps[0]


def test_derive_keeps_gear_and_core_series_apart():
    # 1087xx items can be Mech Cores (84xx sprites) or Cubis Cores (94xx): never bridged.
    eq = dict.fromkeys(range(108717, 108722), 'x')
    derived, _, gaps = BI.derive(confirmed((108717, 8409), (108721, 9413)), eq, set())
    assert derived == {} and gaps == []


# --------------------------------------------------------------------------- item details


def test_class_of_prefers_specialization_over_line():
    index = {'Scattershot': 'Ranger', 'Piercing Arrows of Doom': 'Archer line'}
    text = 'Scattershot and Piercing Arrows of Doom deal more damage'
    assert BD.class_of(text, index) == 'Ranger'
    assert BD.class_of('nothing here', index) is None


def test_class_index_decodes_tree_keys():
    loc = {
        'SX_P1_22_200': {'English': 'Scattershot'},
        'Info_CLASS_ARCHER_ROBBER': {'English': 'Ranger'},
        'S_P1_20_100': {'English': 'Piercing Arrows'},
        'SX_P1_11_100': {'English': 'Hit'},  # too short, skipped
    }
    assert BD.class_index(loc) == {'Scattershot': 'Ranger', 'Piercing Arrows': 'Archer line'}


def test_type_from_name():
    assert BD.type_from_name('Ancient Lance') == 'Spear'
    assert BD.type_from_name('Something') is None


# --------------------------------------------------------------------------- guide text


def test_rich_escapes_then_applies_markup():
    out = BG.rich('<b>x</b> <color=#ff0000ff>red</color>', {})
    assert out.startswith('&lt;b&gt;x&lt;/b&gt;')
    assert '<span style="color:#ff0000">red</span>' in out


def test_rich_values_and_glossary():
    out = BG.rich('Deal {0}% and {1}% as $kuangnu$ or $nope$', {'kuangnu': 'Berserk'}, {'0': 25})
    assert '>25</span>' in out
    assert 'class="unk"' in out  # {1} unknown
    assert '<span class="term">Berserk</span>' in out
    assert 'term-unknown' in out and 'nope' in out


def test_rich_glossary_term_gets_rules_text_tooltip():
    swift = {'name': 'Swift', 'description': 'Movement speed is increased by {0}% for *{1}*s.'}
    out = BG.rich('Grants $jisu$.', {'jisu': swift})
    assert '<span class="term has-tip" tabindex="0">Swift<span class="tip"' in out
    assert '<b>Swift</b>Movement speed is increased by <span class="unk">?</span>%' in out
    assert '<em><span class="unk">?</span></em>s.' in out
    # no description -> plain term, no tooltip
    assert BG.rich('$x$', {'x': {'name': 'X', 'description': ''}}) == '<span class="term">X</span>'


def test_rich_empty_and_newlines():
    assert BG.rich('', {}) == ''
    assert BG.rich('a\nb **c** `d`', {}) == 'a<br>b <strong>c</strong> <code>d</code>'


# --------------------------------------------------------------------------- build_glossary

TERMS = {
    '206013': '易伤',
    '206022': '流血',
    '206032': '急速',
    '206054': '健康',
    '206055': '濒危',
    '206098': '鹰眼',
    '206108': '虚·辐光',
    '206112': '凛风',
}


def test_glossary_matches_screenshot_confirmed_tokens():
    # All five were read off the in-game codex (docs/effects.md).
    found = BGL.match(['jiankang', 'binwei', 'jisu', 'yingyan', 'yishang'], TERMS)
    assert {t: k for t, (k, _) in found.items()} == {
        'jiankang': '206054',
        'binwei': '206055',
        'jisu': '206032',
        'yingyan': '206098',
        'yishang': '206013',
    }
    assert {how for _, how in found.values()} == {'exact'}


def test_glossary_handles_separators_polyphones_and_typos():
    found = BGL.match(['xu_fuguang', 'liuxue', 'lingfeng'], TERMS)
    assert found['xu_fuguang'] == ('206108', 'exact')  # 虚·辐光, `_` for `·`
    assert found['liuxue'][0] == '206022'  # 血 is read xue or xie
    assert found['lingfeng'] == ('206112', 'near')  # the game's typo for 凛风 linfeng


def test_glossary_leaves_ambiguous_and_distant_tokens_unmatched():
    assert BGL.match(['jisu'], {'1': '急速', '2': '疾速'}) == {}
    assert BGL.match(['daxue'], {'206023': '大出血'}) == {}  # a whole syllable is missing


def test_one_edit_apart():
    assert BGL.one_edit_apart('lingfeng', 'linfeng')
    assert BGL.one_edit_apart('abc', 'abd')
    assert not BGL.one_edit_apart('abc', 'abc')
    assert not BGL.one_edit_apart('daxue', 'dachuxue')
