import os
from functools import partial

import pytest

import extract_soulknight as E
import parallel

CALLS = []


def size_of(path, suffix=''):
    """Top-level so worker processes can unpickle it."""
    CALLS.append(path)
    return f'{os.path.basename(path)}:{os.path.getsize(path)}{suffix}'


@pytest.fixture
def bundles(tmp_path, monkeypatch):
    monkeypatch.setattr(parallel, 'CACHE_ROOT', str(tmp_path / 'cache'))
    monkeypatch.setattr(parallel, 'CACHE_ENABLED', True)
    CALLS.clear()
    paths = []
    for i, n in enumerate(['c.bundle', 'a.bundle', 'b.bundle', 'd.bundle']):
        p = tmp_path / n
        p.write_bytes(b'x' * (i + 1))
        paths.append(str(p))
    return paths


def test_results_keep_input_order_in_parallel(bundles):
    got = parallel.map_bundles(size_of, bundles, workers=3)
    assert got == ['c.bundle:1', 'a.bundle:2', 'b.bundle:3', 'd.bundle:4']


def test_inline_and_parallel_agree(bundles):
    fn = partial(size_of, suffix='!')
    assert parallel.map_bundles(fn, bundles, workers=1) == parallel.map_bundles(
        fn, bundles, workers=4
    )


def test_cache_hit_skips_work_and_size_change_misses(bundles):
    first = parallel.map_bundles(size_of, bundles, workers=1, tag='t')
    assert len(CALLS) == 4
    CALLS.clear()
    assert parallel.map_bundles(size_of, bundles, workers=1, tag='t') == first
    assert CALLS == []
    with open(bundles[1], 'ab') as fh:  # new content -> new size -> new cache file
        fh.write(b'more')
    got = parallel.map_bundles(size_of, bundles, workers=1, tag='t')
    assert [bundles[1]] == CALLS
    assert got[1] == 'a.bundle:6'


def test_cache_can_be_disabled(bundles):
    parallel.map_bundles(size_of, bundles, workers=1, tag='t')
    parallel.CACHE_ENABLED = False
    CALLS.clear()
    parallel.map_bundles(size_of, bundles, workers=1, tag='t')
    assert len(CALLS) == 4


def test_cache_is_keyed_on_code(bundles):
    a = parallel.code_tag('t', size_of)
    b = parallel.code_tag('t', partial(size_of, suffix='x'))
    assert a == b  # partial unwraps to the same function and source
    assert parallel.code_tag('t', E.scan_bundle) != a  # different source file


def test_cache_tag_changes_with_inputs():
    assert parallel.cache_tag('p', 'm1') == parallel.cache_tag('p', 'm1')
    assert parallel.cache_tag('p', 'm1') != parallel.cache_tag('p', 'm2')


def test_consume_runs_in_bundle_order_and_replaces_results(bundles, monkeypatch):
    seen = []

    def consume(value):
        seen.append(value)
        return value.split(':')[0]

    got = parallel.map_bundles(size_of, bundles, workers=4, consume=consume)
    assert seen == ['c.bundle:1', 'a.bundle:2', 'b.bundle:3', 'd.bundle:4']
    assert got == ['c.bundle', 'a.bundle', 'b.bundle', 'd.bundle']


def test_consume_orders_a_mix_of_cache_hits_and_fresh_results(bundles):
    parallel.map_bundles(size_of, bundles[1:3], workers=1, tag='t')  # warm the middle two
    seen = []
    parallel.map_bundles(size_of, bundles, workers=1, tag='t', consume=seen.append)
    assert [v.split(':')[0] for v in seen] == ['c.bundle', 'a.bundle', 'b.bundle', 'd.bundle']


def test_cacheable_veto_means_recompute(bundles):
    no_a = lambda v: not v.startswith('a.')
    parallel.map_bundles(size_of, bundles, workers=1, tag='t', cacheable=no_a)
    CALLS.clear()
    parallel.map_bundles(size_of, bundles, workers=1, tag='t', cacheable=no_a)
    assert bundles[1] == CALLS[0] and len(CALLS) == 1


def test_progress_reports_every_bundle(bundles):
    seen = []
    parallel.map_bundles(size_of, bundles, workers=2, progress=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (4, 4) and len(seen) == 4


# --------------------------------------------------------------------------- sprite merge


def read(tmp_path, rel):
    return (tmp_path / 'icons' / rel).read_bytes()


def test_write_sprites_first_bundle_wins_and_failures_resolve(tmp_path):
    scans = [
        (['A_x', 'B_y'], [('A_x', b'first', None), ('B_y', None, 'not packed')]),
        (['A_x', 'B_y'], [('A_x', b'second', None), ('B_y', b'late', None)]),
        (['C_z'], [('C_z', None, 'err1')]),
        (['C_z'], [('C_z', None, 'err2')]),
    ]
    done, failed = E.write_sprites(scans, str(tmp_path))
    assert done == {'A_x', 'B_y'}
    assert read(tmp_path, 'A_x/A_x.png') == b'first'
    assert read(tmp_path, 'B_y/B_y.png') == b'late'  # failed in bundle 1, found in 2
    assert failed == {'C_z': 'err2'}  # last error wins, as the sequential loop did


def test_write_sprites_forced_folder(tmp_path):
    E.write_sprites([(['EBF_SCATTERING'], [('EBF_SCATTERING', b'p', None)])], str(tmp_path), 'EBF')
    assert read(tmp_path, 'EBF/EBF_SCATTERING.png') == b'p'


# --------------------------------------------------------------------------- atlas sharing


class Ptr:
    def __init__(self, path_id, atlas=None):
        self.m_FileID, self.m_PathID, self.atlas, self.parses = 0, path_id, atlas, 0

    def __bool__(self):
        return self.m_PathID != 0

    def deref_parse_as_object(self):
        self.parses += 1
        return self.atlas


class Obj:
    def __init__(self, type_, name, atlas):
        from UnityPy.enums import ClassIDType

        self.type = getattr(ClassIDType, type_)
        self.name, self.atlas, self.parses = name, atlas, 0

    def peek_name(self):
        return self.name

    def parse_as_object(self):
        self.parses += 1
        return self.atlas


class File:
    def __init__(self, objs):
        self.objects = dict(enumerate(objs))


class Sprite:
    def __init__(self, ptr, tags, file):
        self.m_SpriteAtlas, self.m_AtlasTags, self.assets_file = ptr, tags, file


def test_share_atlas_parses_pointer_once():
    ptr, f, cache = Ptr(7, atlas='ATLAS'), File([]), {}
    sprites = [Sprite(ptr, [], f) for _ in range(3)]
    for s in sprites:
        E._share_atlas(s, cache)
    assert ptr.parses == 1
    assert all(s.m_SpriteAtlas.deref_parse_as_object() == 'ATLAS' for s in sprites)


def test_share_atlas_by_tag_matches_first_named_atlas_once():
    wrong, right, twin = (
        Obj('SpriteAtlas', 'other', 'A0'),
        Obj('SpriteAtlas', 'ui', 'A1'),
        Obj('SpriteAtlas', 'ui', 'A2'),
    )
    f, cache = File([Obj('Sprite', 'ui', 'S'), wrong, right, twin]), {}
    sprites = [Sprite(Ptr(0), ['ui'], f) for _ in range(3)]
    for s in sprites:
        E._share_atlas(s, cache)
    assert right.parses == 1 and wrong.parses == 0 and twin.parses == 0
    assert all(s.m_SpriteAtlas.deref_parse_as_object() == 'A1' for s in sprites)


def test_share_atlas_leaves_unatlased_sprites_alone():
    for ptr, tags in ((Ptr(0), []), (Ptr(0), ['missing'])):
        s = Sprite(ptr, tags, File([Obj('SpriteAtlas', 'ui', 'A')]))
        E._share_atlas(s, {})
        assert s.m_SpriteAtlas is ptr  # UnityPy falls back to m_RD, exactly as before
