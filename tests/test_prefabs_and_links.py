import dump_prefabs as D
import extract_skill_links as L

# --------------------------------------------------------------------------- dump_prefabs


def test_logical_strips_content_hash():
    assert D.logical('x/skill_all_0123456789abcdef0123456789abcdef.bundle') == 'skill_all'
    assert D.logical('plain.bundle') == 'plain.bundle'


def test_compact_references():
    names = {5: 'Child'}
    assert D.compact({'m_FileID': 0, 'm_PathID': 0}, names) is None
    assert D.compact({'m_FileID': 0, 'm_PathID': 5}, names) == {'$ref': 5, '$name': 'Child'}
    # A reference into another file never gets a local name, even if the id collides.
    assert D.compact({'m_FileID': 2, 'm_PathID': 5}, names) == {'$ref': 5}


def test_compact_level_parameter():
    p = {'v0': 1, 'v1': 2, 'v2': 3, 'v3': 4, 'parameterType': 0, 'configureId': 0}
    assert D.compact(p, {}) == {'lv': [1, 2, 3, 4]}
    p.update(configureId=77, configureType=3, unified=True, levelId=9)
    assert D.compact(p, {}) == {'lv': [1, 2, 3, 4], 'cfg': [3, 77], 'unified': True, 'levelId': 9}


def test_compact_drops_boilerplate_and_empties():
    value = {'m_Name': 'x', 'm_Enabled': 1, 'a': '', 'b': [], 'c': [{'m_Script': 1}], 'd': 0}
    assert D.compact(value, {}) == {'d': 0}
    assert D.compact({'m_Name': 'only'}, {}) is None


def test_pick_bundles_prefers_catalog_variant(tmp_path, monkeypatch):
    for n in [
        'buff_all_' + 'a' * 32 + '.bundle',
        'buff_all_' + 'b' * 32 + '.bundle',
        'skill_x_' + 'c' * 32 + '.bundle',
        'ui_y_' + 'd' * 32 + '.bundle',
    ]:
        (tmp_path / n).write_bytes(b'')
    monkeypatch.setattr(D, 'shipped_bundles', lambda _: {'buff_all_' + 'b' * 32 + '.bundle'})
    got = sorted(
        p.replace('\\', '/').rsplit('/', 1)[-1]
        for p in D.pick_bundles(str(tmp_path), ('buff_all', 'skill_'))
    )
    assert got == ['buff_all_' + 'b' * 32 + '.bundle', 'skill_x_' + 'c' * 32 + '.bundle']


# --------------------------------------------------------------------------- skill links


def test_link_joins_on_chinese_and_prefers_lowest_item():
    found = {
        '1500441': {'desc': '祖父悖论', 'class': 'RGSkill', 'bundle': 'b1'},
        'BF_1500441': {'desc': '祖父悖论', 'class': 'RGBuff', 'bundle': 'b1'},  # not numeric
        '1500999': {'desc': '没有物品', 'class': 'RGSkill', 'bundle': 'b2'},
    }
    strings = {
        '101643': {'English': 'Grandfather Paradox', 'Chinese': '祖父悖论'},
        '101700': {'English': 'Dup', 'Chinese': '祖父悖论'},
        '7': {'English': 'Not an item id', 'Chinese': '祖父悖论'},
    }
    assert L.link(found, strings) == [
        {
            'item_id': 101643,
            'item_name': 'Grandfather Paradox',
            'item_name_cn': '祖父悖论',
            'skill_id': '1500441',
            'skill_class': 'RGSkill',
            'bundle': 'b1',
        }
    ]
