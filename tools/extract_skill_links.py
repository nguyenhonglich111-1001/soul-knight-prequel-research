#!/usr/bin/env python3
"""Link numeric equipment IDs to the skill/buff prefabs that implement them.

The game's config tables (Luban) are encrypted, so there is no table that says
"item 101643 uses effect X". But the prefabs are not encrypted and they still carry
their Unity type trees, so every MonoBehaviour can be read field by field.

Legendary equipment is implemented as a prefab under
`Assets/RGPrefab/Skill/LegendEquipSkill/<slot>/<skill id>/`, whose root `RGSkill`
component keeps the designers' own Chinese label in its `Desc` field -- and that label
is the item's Chinese name. Matching `Desc` against the `Chinese` column of
localization_all.json therefore recovers the item -> skill link.

    python tools/extract_skill_links.py                  # write extracted/skill_links.json
    python tools/extract_skill_links.py --dump 1500441   # print one skill's component tree

Slot digit of the skill id: 1 weapon, 2 armor, 3 helm, 4 boots, 5 ring, 6 necklace,
7 core, 9 relic -- the same slot order as the 101xxx/102xxx/... name blocks.
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from functools import partial

import versions

import parallel
from extract_soulknight import shipped_bundles
from parallel import cache_tag, every, map_bundles

SKIP_PREFIX = ('audio_', 'videos_', 'spine_', 'texture_', 'fonts_', 'localization', 'code_')
ITEM_ID = re.compile(r'^10[1-9]\d{3}$|^1[0-9]{5}$')


def unity(*paths):
    import UnityPy

    return UnityPy.load(*paths)


def _shipped(asset_dir, paths):
    """Keep only the variant the Addressables catalog points at.

    All 44 multi-variant groups here differ byte for byte, so reading every variant
    means reading stale copies of `buff_all`, `skill_class_all` and the
    `skill_directclass_*` bundles alongside the live ones. See
    `extract_soulknight.shipped_bundles`."""
    shipped = shipped_bundles(asset_dir)
    if not shipped:
        return paths
    return [f for f in paths if os.path.basename(f) in shipped]


def bundles(asset_dir):
    return _shipped(
        asset_dir,
        [
            f
            for f in sorted(glob.glob(os.path.join(asset_dir, '*.bundle')))
            if not os.path.basename(f).startswith(SKIP_PREFIX)
        ],
    )


def monoscript_bundles(asset_dir):
    return _shipped(asset_dir, sorted(glob.glob(os.path.join(asset_dir, '*monoscripts*.bundle'))))


def script_names(env):
    """MonoScript path_id -> C# class name, so MonoBehaviours can be identified."""
    out = {}
    for o in env.objects:
        if o.type.name == 'MonoScript':
            try:
                out[o.path_id] = o.read_typetree().get('m_ClassName')
            except Exception:
                pass
    return out


def labelled_prefabs(path, mono_names):
    """Worker: `[(prefab name, desc, class)]` for one bundle, in object order, or the
    load error as a string."""
    try:
        env = unity(path)
    except Exception as e:
        return str(e)
    # Same precedence as loading both files into one environment: the monoscripts
    # bundle's entries win over any the bundle carries itself.
    scripts = {**script_names(env), **mono_names}
    objs = {o.path_id: o for o in env.objects}
    out = []
    for o in env.objects:
        if o.type.name != 'MonoBehaviour':
            continue
        try:
            t = o.read_typetree()
        except Exception:
            continue
        desc = t.get('Desc')
        if not isinstance(desc, str) or not desc.strip():
            continue
        go = objs.get(t.get('m_GameObject', {}).get('m_PathID'))
        if go is None or go.type.name != 'GameObject':
            continue
        try:
            name = go.read_typetree().get('m_Name', '')
        except Exception:
            continue
        if name:
            out.append((name, desc.strip(), scripts.get(t.get('m_Script', {}).get('m_PathID'))))
    return out


def collect(asset_dir, verbose=True):
    """{prefab name: {desc, class, bundle}} for every prefab whose root has a `Desc`.

    Bundles are read in parallel; the first bundle in filename order still wins."""
    mono = monoscript_bundles(asset_dir)
    mono_names = script_names(unity(*mono))
    files = bundles(asset_dir)
    results = map_bundles(
        partial(labelled_prefabs, mono_names=mono_names),
        files,
        tag=cache_tag('skill-labels', *map(os.path.basename, mono)),
        progress=every(50) if verbose else None,
        cacheable=lambda got: not isinstance(got, str),  # a load error is retried next run
    )
    found = {}
    for f, got in zip(files, results):
        base = os.path.basename(f)
        if isinstance(got, str):
            print(f'    skipped {base}: {got}', file=sys.stderr)
            continue
        for name, desc, cls in got:
            if name not in found:
                found[name] = {'desc': desc, 'class': cls, 'bundle': base}
    return found


def link(found, strings):
    """Join designer labels to localized item names via the Chinese column."""
    by_cn = collections.defaultdict(list)
    for key, row in strings.items():
        cn = (row.get('Chinese') or '').strip()
        if cn and key.isdigit():
            by_cn[cn].append(key)
    links = []
    for skill_id, info in sorted(found.items()):
        if not skill_id.isdigit():
            continue
        items = [k for k in by_cn.get(info['desc'], []) if ITEM_ID.match(k)]
        if not items:
            continue
        item = min(items, key=int)
        links.append(
            {
                'item_id': int(item),
                'item_name': strings[item].get('English', ''),
                'item_name_cn': strings[item].get('Chinese', ''),
                'skill_id': skill_id,
                'skill_class': info['class'],
                'bundle': info['bundle'],
            }
        )
    links.sort(key=lambda r: (r['item_id'], r['skill_id']))
    return links


def dump(asset_dir, skill_id):
    """Print one skill prefab's full component tree, values included."""
    mono = monoscript_bundles(asset_dir)
    for f in bundles(asset_dir):
        env = unity(f, *mono)
        objs = {o.path_id: o for o in env.objects}
        target = None
        for o in env.objects:
            if o.type.name == 'GameObject' and o.read_typetree().get('m_Name') == skill_id:
                target = o
                break
        if target is None:
            continue
        print(f'# {skill_id}  ({os.path.basename(f)})')
        scripts = script_names(env)

        def walk(go_pid, depth=0, objs=objs, scripts=scripts):
            g = objs[go_pid].read_typetree()
            print('  ' * depth + '* ' + g['m_Name'])
            tr = None
            for c in g['m_Component']:
                co = objs.get(c['component']['m_PathID'])
                if co is None:
                    continue
                if co.type.name == 'Transform':
                    tr = co
                if co.type.name != 'MonoBehaviour':
                    continue
                t = co.read_typetree()
                cls = scripts.get(t.get('m_Script', {}).get('m_PathID'), '?')
                body = {
                    k: v
                    for k, v in t.items()
                    if k not in ('m_GameObject', 'm_Enabled', 'm_Script', 'm_Name')
                }
                print('  ' * depth + f'  - {cls}: ' + json.dumps(body, ensure_ascii=False))
            if tr is not None:
                for ch in tr.read_typetree()['m_Children']:
                    walk(
                        objs[ch['m_PathID']].read_typetree()['m_GameObject']['m_PathID'], depth + 1
                    )

        walk(target.path_id)
        return
    print(f'{skill_id}: not found', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        '--apk-dir', help='unpacked APK folder (default: newest soul-knight-prequel-*/)'
    )
    ap.add_argument('--out', help='output folder (default: extracted/<that APK version>/)')
    ap.add_argument('--dump', metavar='SKILL_ID', help='print one prefab instead')
    parallel.add_arguments(ap)
    args = ap.parse_args()
    parallel.configure(args)
    versions.resolve_extract_args(args)

    asset_dir = os.path.join(args.apk_dir, 'assets', 'Asset')
    if not os.path.isdir(asset_dir):
        sys.exit(f'not found: {asset_dir} (unzip the APK first, see README)')

    if args.dump:
        dump(asset_dir, args.dump)
        return

    strings = json.load(open(os.path.join(args.out, 'localization_all.json'), encoding='utf8'))
    found = collect(asset_dir)
    links = link(found, strings)
    path = os.path.join(args.out, 'skill_links.json')
    with open(path, 'w', encoding='utf8') as fh:
        json.dump(links, fh, ensure_ascii=False, indent=1)
    print(f'{len(found)} labelled prefabs, {len(links)} linked to an item -> {path}')


if __name__ == '__main__':
    main()
