import copy
import io
import json
import os
import zipfile

import pytest
import unpack_apk as U
import version_diff as VD
import versions as V
from conftest import ROOT
from PIL import Image

APK_1_13 = os.path.join(ROOT, 'soul-knight-prequel-1-13-0')
OUT_1_13 = os.path.join(ROOT, 'extracted', '1.13.0')

# --------------------------------------------------------------------------- versions


def test_version_key_sorts_numerically():
    assert sorted(['1.13.0', '1.9.2', '1.13.10', '2.0'], key=V.version_key) == [
        '1.9.2',
        '1.13.0',
        '1.13.10',
        '2.0',
    ]
    assert V.dir_name('1.14.0') == 'soul-knight-prequel-1-14-0'


def test_version_from_files_prefers_bundle_version_data():
    files = {'assets/bundleVersionData.txt': b'\xef\xbb\xbf{"version": "1.14.2"}'}
    assert V.version_from_files(files.get) == '1.14.2'
    assert V.version_from_files({}.get) is None
    assert V.version_from_files({'assets/bundleVersionData.txt': b'not json'}.get) is None


@pytest.mark.skipif(not os.path.isdir(APK_1_13), reason='unpacked 1.13.0 APK not present')
def test_manifest_version_reads_real_axml():
    with open(os.path.join(APK_1_13, 'AndroidManifest.xml'), 'rb') as fh:
        assert V.manifest_version(fh.read()) == '1.13.0'
    assert V.manifest_version(b'not axml at all') is None


def make_apk_tree(root, version, with_assets=True):
    d = root / V.dir_name(version)
    (d / 'assets' / 'Asset').mkdir(parents=True)
    (d / 'assets' / 'bundleVersionData.txt').write_text(json.dumps({'version': version}))
    if not with_assets:
        (d / 'assets' / 'Asset').rmdir()
    return d


def test_apk_dirs_and_default_pick_the_newest(tmp_path):
    make_apk_tree(tmp_path, '1.9.0')
    make_apk_tree(tmp_path, '1.13.0')
    make_apk_tree(tmp_path, '1.20.0', with_assets=False)  # not a usable unpack
    assert [v for v, _ in V.apk_dirs(str(tmp_path))] == ['1.9.0', '1.13.0']
    assert V.default_apk_dir(str(tmp_path)).endswith('soul-knight-prequel-1-13-0')


def test_out_versions_needs_localization(tmp_path):
    for v in ('1.13.0', '1.9.0', '1.14.0'):
        (tmp_path / v).mkdir()
    for v in ('1.13.0', '1.9.0'):
        (tmp_path / v / 'localization_all.json').write_text('{}')
    assert V.out_versions(str(tmp_path)) == ['1.9.0', '1.13.0']
    assert V.default_out(str(tmp_path)).endswith('1.13.0')
    with pytest.raises(SystemExit):
        V.default_out(str(tmp_path / 'nothing'))


# --------------------------------------------------------------------------- unpack_apk


def zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def apk_files(version, extra=None):
    files = {
        'AndroidManifest.xml': b'base-manifest',
        'assets/bundleVersionData.txt': json.dumps({'version': version}).encode(),
        'assets/Asset/a.bundle': b'A',
    }
    files.update(extra or {})
    return files


def test_unpack_plain_apk(tmp_path):
    src = tmp_path / 'game.apk'
    src.write_bytes(zip_bytes(apk_files('1.14.0')))
    v, _dest, n = U.unpack(str(src), root=str(tmp_path))
    assert v == '1.14.0' and n == 3
    assert (tmp_path / 'soul-knight-prequel-1-14-0' / 'assets' / 'Asset' / 'a.bundle').exists()


def test_unpack_wrapped_folder_zip(tmp_path):
    files = {f'soul-knight-prequel-1-13-0/{k}': v for k, v in apk_files('1.13.0').items()}
    src = tmp_path / 'wrapped.zip'
    src.write_bytes(zip_bytes(files))
    v, _dest, _ = U.unpack(str(src), root=str(tmp_path))
    assert v == '1.13.0'
    assert (tmp_path / 'soul-knight-prequel-1-13-0' / 'AndroidManifest.xml').exists()


def test_unpack_xapk_merges_splits_without_overwriting_base(tmp_path):
    base = zip_bytes(apk_files('1.15.0'))
    split = zip_bytes({'AndroidManifest.xml': b'split-manifest', 'assets/Asset/b.bundle': b'B'})
    src = tmp_path / 'game.xapk'
    src.write_bytes(
        zip_bytes({'config.arm64.apk': split, 'base.apk': base, 'manifest.json': b'{}'})
    )
    v, _dest, _ = U.unpack(str(src), root=str(tmp_path))
    d = tmp_path / 'soul-knight-prequel-1-15-0'
    assert v == '1.15.0'
    assert (d / 'AndroidManifest.xml').read_bytes() == b'base-manifest'
    assert (d / 'assets' / 'Asset' / 'b.bundle').read_bytes() == b'B'


def test_unpack_version_from_xapk_manifest_and_override(tmp_path):
    inner = zip_bytes({'AndroidManifest.xml': b'x', 'assets/Asset/a.bundle': b'A'})
    src = tmp_path / 'game.xapk'
    src.write_bytes(zip_bytes({'base.apk': inner, 'manifest.json': b'{"version_name": "2.0.1"}'}))
    assert U.unpack(str(src), root=str(tmp_path))[0] == '2.0.1'
    assert U.unpack(str(src), root=str(tmp_path), version='2.0.2')[0] == '2.0.2'


def test_unpack_refuses_existing_and_unsafe(tmp_path):
    src = tmp_path / 'game.apk'
    src.write_bytes(zip_bytes(apk_files('1.14.0')))
    U.unpack(str(src), root=str(tmp_path))
    with pytest.raises(FileExistsError):
        U.unpack(str(src), root=str(tmp_path))
    U.unpack(str(src), root=str(tmp_path), force=True)  # --force replaces

    evil = tmp_path / 'evil.apk'
    evil.write_bytes(zip_bytes(apk_files('1.16.0', {'../../escape.txt': b'x'})))
    with pytest.raises(ValueError, match='unsafe'):
        U.unpack(str(evil), root=str(tmp_path))
    assert not (tmp_path.parent / 'escape.txt').exists()


def test_unpack_rejects_non_apk(tmp_path):
    src = tmp_path / 'photos.zip'
    src.write_bytes(zip_bytes({'a.jpg': b'x', 'b/c.jpg': b'y'}))
    with pytest.raises(ValueError, match='not an APK'):
        U.unpack(str(src), root=str(tmp_path))


def test_newest_archive_skips_versions_already_unpacked(tmp_path):
    old = tmp_path / 'old.apk'
    old.write_bytes(zip_bytes(apk_files('1.13.0')))
    make_apk_tree(tmp_path, '1.13.0')
    assert U.newest_archive(str(tmp_path)) is None
    new = tmp_path / 'new.apk'
    new.write_bytes(zip_bytes(apk_files('1.14.0')))
    assert U.newest_archive(str(tmp_path)) == str(new)


# --------------------------------------------------------------------------- version_diff


def png(path, color):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGBA', (4, 4), color).save(path)
    return str(path)


def fake_version(tmp_path, tag, items, loc, icons):
    return {
        'equipment': [
            {'id': i, 'name': n, 'slot': 'helm', 'icon': ic, 'effect_key': ek}
            for i, n, ic, ek in items
        ],
        'loc': {k: {'English': v} for k, v in loc.items()},
        'icons': {name: png(tmp_path / tag / f'{name}.png', c) for name, c in icons.items()},
    }


HAND = {
    'icon_map': {'confirmed': {'103467': {'icon': 'ItemIcon_3470000', 'name': "Tophat's Six"}}},
    'effect_map': {'confirmed': {'103467': {'key': '110549', 'name': "Tophat's Six"}}},
    'weapon_types': {},
    'guides': [{'sections': [{'items': ['SX_P1_22_200']}]}],
}


def test_diff_identical_versions_is_empty(tmp_path):
    items = [(103467, 'Tophat’s Six', 'x.png', None)]  # curly quote vs straight in HAND
    loc = {'103467': 'Tophat’s Six', '110549': 'Effect {0}', 'SX_P1_22_200': 'Scattershot'}
    old = fake_version(tmp_path, 'a', items, loc, {'ItemIcon_3470000': 'red'})
    new = fake_version(tmp_path, 'b', items, loc, {'ItemIcon_3470000': 'red'})
    r = VD.diff(old, new, HAND)
    assert not any(r.values()), r
    assert 'Nothing to capture' in VD.report(r, '1', '2')


def test_diff_catches_every_kind_of_change(tmp_path):
    old = fake_version(
        tmp_path,
        'a',
        [(103467, "Tophat's Six", 'x.png', None), (103468, 'Old Hat', 'y.png', None)],
        {'103467': "Tophat's Six", '110549': 'Effect {0}', 'SX_P1_22_200': 'Scattershot'},
        {'ItemIcon_3470000': 'red'},
    )
    new = fake_version(
        tmp_path,
        'b',
        [(103467, 'Totally Different Hat', 'x.png', None), (103469, 'New Hat', None, None)],
        {'103467': 'Totally Different Hat', '110549': 'Effect {0} and {1}'},
        {'ItemIcon_3470000': 'blue', 'ItemIcon_3471000': 'green'},
    )
    r = VD.diff(old, new, HAND)
    assert [x['id'] for x in r['new_items']] == [103469]
    assert [x['id'] for x in r['removed_items']] == [103468]
    assert [x['id'] for x in r['renamed_items']] == [103467]
    assert {x['file'] for x in r['hand_name_drift']} == {'icon_map', 'effect_map'}
    assert [x['sprite'] for x in r['sprite_changed']] == ['ItemIcon_3470000']
    assert [x['key'] for x in r['text_changed']] == ['110549']
    assert [x['key'] for x in r['text_gone']] == ['SX_P1_22_200']
    assert r['new_sprites'] == ['ItemIcon_3471000']
    assert VD.needs_review(r)
    text = VD.report(r, '1.13.0', '1.14.0')
    assert 'New Hat' in text and '**no icon**' in text and 'Your action' in text


def test_diff_flags_missing_sprite_and_gone_item(tmp_path):
    old = fake_version(
        tmp_path,
        'a',
        [(103467, "Tophat's Six", 'x', None)],
        {'103467': "Tophat's Six"},
        {'ItemIcon_3470000': 'red'},
    )
    new = fake_version(tmp_path, 'b', [], {}, {})
    r = VD.diff(old, new, HAND)
    assert [x['sprite'] for x in r['sprite_gone']] == ['ItemIcon_3470000']
    assert {x['key'] for x in r['hand_item_gone']} == {'103467'}


def test_contact_sheet(tmp_path):
    icons = {n: png(tmp_path / f'{n}.png', 'red') for n in ('ItemIcon_1', 'ItemIcon_2')}
    out = VD.contact_sheet(sorted(icons), icons, str(tmp_path / 'sheet.png'))
    assert Image.open(out).size[0] > 0


@pytest.mark.slow
@pytest.mark.skipif(not os.path.isdir(OUT_1_13), reason='extracted/1.13.0 not present')
def test_diff_on_real_data_self_and_altered_copy():
    """The real 1.13.0 data against itself is clean; a copy with one change of each
    kind reports exactly those."""
    real, hand = VD.load_version(OUT_1_13), VD.load_hand()
    assert not any(VD.diff(real, real, hand).values())

    new = copy.deepcopy(real)
    confirmed = hand['icon_map']['confirmed']
    key, entry = next(iter(confirmed.items()))
    new['loc'][key] = {'English': 'Some Other Item'}  # id reused
    other = next(s for s in real['icons'] if s != entry['icon'] and s.startswith('ItemIcon_'))
    new['icons'][entry['icon']] = real['icons'][other]  # same name, other pixels
    dropped = new['equipment'].pop()  # an item removed
    effect_key = next(e['key'] for e in hand['effect_map']['confirmed'].values())
    new['loc'][effect_key] = {'English': 'Reworded {0}'}

    r = VD.diff(real, new, hand)
    assert key in {x['key'] for x in r['hand_name_drift']}
    assert [x['sprite'] for x in r['sprite_changed']] == [entry['icon']]
    assert [x['id'] for x in r['removed_items']] == [dropped['id']]
    assert effect_key in {x['key'] for x in r['text_changed']}
