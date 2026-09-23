#!/usr/bin/env python3
"""Dump the game-logic side of every prefab to JSON.

The bundles still carry their Unity type trees, so every `MonoBehaviour` can be read
field by field. This walks each prefab's GameObject hierarchy and writes out the
MonoBehaviour components only -- skills, buffs, bullets, conditions, character stats --
dropping Transforms, renderers and particle systems, which are presentation noise.

    python tools/dump_prefabs.py                     # every group (~25 s, cached after)
    python tools/dump_prefabs.py --groups buff skill
    python tools/dump_prefabs.py --list              # show the groups and their bundles

Output: `extracted/prefabs/<group>.json`

    [{"name": "BF_1500441", "bundle": "...", "components": [{"$type": "RGBuff", ...}],
      "children": [...]}, ...]

Field values are passed through as the type tree gives them, with three compactions:

  * object references become `{"$ref": <path id>}`, or `{"$ref": id, "$name": "..."}`
    when the target is in the same bundle, and are dropped entirely when null;
  * the engine's per-level parameter struct collapses to
    `{"lv": [v0, v1, v2, v3]}` plus `cfg` / `unified` / `increment` when those are set
    (`cfg` means the real value comes from the encrypted config tables at runtime, and
    the `lv` values will be zero);
  * empty strings, empty lists and Unity boilerplate fields are omitted.
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from functools import partial

import parallel
from extract_soulknight import shipped_bundles
from parallel import cache_tag, every, map_bundles

BUNDLE_HASH = re.compile(r'_[0-9a-f]{32}\.bundle$')
BOILERPLATE = {
    'm_GameObject',
    'm_Enabled',
    'm_Script',
    'm_Name',
    'm_EditorHideFlags',
    'm_EditorClassIdentifier',
    'm_ObjectHideFlags',
    'm_PrefabInstance',
    'm_PrefabAsset',
    'm_CorrespondingSourceObject',
}
PARAM_KEYS = {'v0', 'v1', 'v2', 'v3', 'parameterType', 'configureId'}

GROUPS = {
    'buff': ('buff_all',),
    'skill': ('skill_',),
    'obj': ('obj_misc', 'misc_'),
    'stage': ('stage_',),
    'char': ('anim_',),
    'ui': ('ui_',),
    'home': ('homedecorate_',),
    'skin': ('skin_', 'skincoloroverrides'),
    'scene': ('scenes_',),
}


def unity(*paths):
    import UnityPy

    return UnityPy.load(*paths)


def logical(path):
    """Bundle name without the content hash, so duplicate variants collapse to one."""
    return BUNDLE_HASH.sub('', os.path.basename(path))


def pick_bundles(asset_dir, prefixes):
    """One file per logical bundle -- the one the Addressables catalog points at.

    Variants are *not* interchangeable. All 44 multi-variant groups in this APK differ
    byte for byte, and taking the first by filename (the old rule here) picks a bundle
    the game does not load in 21 of them, `buff_all`, `skill_class_all` and every
    `skill_directclass_*` among them. `shipped_bundles()` reads the catalog, which names
    exactly one variant per group. Bundles the catalog does not mention at all fall back
    to first-by-name."""
    shipped = shipped_bundles(asset_dir)
    seen = {}
    for f in sorted(glob.glob(os.path.join(asset_dir, '*.bundle'))):
        name = logical(f)
        if not name.startswith(prefixes):
            continue
        if shipped and os.path.basename(f) in shipped:
            seen[name] = f  # catalog pick always wins
        elif name not in seen:
            seen[name] = f
    return list(seen.values())


def script_names(env):
    out = {}
    for o in env.objects:
        if o.type.name == 'MonoScript':
            try:
                d = o.read_typetree()
            except Exception:
                continue
            ns, cn = d.get('m_Namespace') or '', d.get('m_ClassName') or ''
            out[o.path_id] = f'{ns}|{cn}' if ns else cn
    return out


def compact(value, names):
    """Shrink a type-tree value; return None for 'nothing worth keeping'."""
    if isinstance(value, dict):
        keys = set(value)
        if keys == {'m_FileID', 'm_PathID'}:
            pid = value['m_PathID']
            if not pid:
                return None
            ref = {'$ref': pid}
            if value['m_FileID'] == 0 and pid in names:
                ref['$name'] = names[pid]
            return ref
        if keys >= PARAM_KEYS:
            out = {'lv': [value['v0'], value['v1'], value['v2'], value['v3']]}
            if value.get('configureId'):
                out['cfg'] = [value.get('configureType'), value['configureId']]
            for k in ('unified', 'increment'):
                if value.get(k):
                    out[k] = value[k]
            if value.get('levelId'):
                out['levelId'] = value['levelId']
            return out
        out = {}
        for k, v in value.items():
            if k in BOILERPLATE:
                continue
            c = compact(v, names)
            if c is not None:
                out[k] = c
        return out or None
    if isinstance(value, list):
        out = [c for c in (compact(v, names) for v in value) if c is not None]
        return out or None
    if isinstance(value, str):
        return value or None
    return value


def mono_scripts(mono):
    """MonoScript path_id -> class name, read once from the monoscripts bundle(s).

    MonoBehaviours reference their script across files by path_id alone, and the three
    monoscripts variants agree on every one they share, so this table is global. It used
    to be rebuilt by loading the monoscripts bundle next to every single bundle."""
    return script_names(unity(*mono))


def dump_bundle(path, mono_names, out_rows):
    env = unity(path)
    # Same precedence as loading both files into one environment: the monoscripts
    # bundle's entries win over any the bundle carries itself.
    scripts = {**script_names(env), **mono_names}
    objs = {o.path_id: o for o in env.objects}
    trees = {}
    for o in env.objects:
        if o.type.name in ('Transform', 'RectTransform', 'GameObject'):
            try:
                trees[o.path_id] = o.read_typetree()
            except Exception:
                pass
    # path_id -> readable label, used to resolve $ref targets
    names = {}
    for pid, t in trees.items():
        if 'm_Name' in t:
            names[pid] = t['m_Name']

    def node(go_pid):
        g = trees.get(go_pid)
        if g is None:
            return None
        comps, transform = [], None
        for c in g.get('m_Component', []):
            o = objs.get(c['component']['m_PathID'])
            if o is None:
                continue
            if o.type.name in ('Transform', 'RectTransform'):
                transform = o.path_id
            if o.type.name != 'MonoBehaviour':
                continue
            try:
                t = o.read_typetree()
            except Exception:
                continue
            # '$type' rather than 'type': several components have their own `type` field.
            body = {'$type': scripts.get(t.get('m_Script', {}).get('m_PathID'), '?')}
            body.update(compact(t, names) or {})
            comps.append(body)
        children = []
        if transform is not None:
            for ch in trees.get(transform, {}).get('m_Children', []):
                ct = trees.get(ch['m_PathID'])
                if ct is None:
                    continue
                sub = node(ct['m_GameObject']['m_PathID'])
                if sub is not None:
                    children.append(sub)
        if not comps and not children:
            return None  # pure presentation branch
        row = {'name': g.get('m_Name', '')}
        if comps:
            row['components'] = comps
        if children:
            row['children'] = children
        return row

    base = logical(path)
    for t in trees.values():
        if 'm_Children' not in t or t.get('m_Father', {}).get('m_PathID'):
            continue  # only prefab roots
        row = node(t['m_GameObject']['m_PathID'])
        if row is not None:
            row['bundle'] = base
            out_rows.append(row)


def dump_one(path, mono_names):
    """Worker: `(rows, error)` for one bundle. Rows found before an error are kept, as
    the sequential loop kept them."""
    rows = []
    try:
        dump_bundle(path, mono_names, rows)
    except Exception as e:
        return rows, str(e)
    return rows, None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('--apk-dir', default='soul-knight-prequel-1-13-0')
    ap.add_argument('--out', default='extracted')
    ap.add_argument('--groups', nargs='*', default=None, choices=sorted(GROUPS))
    ap.add_argument('--list', action='store_true')
    parallel.add_arguments(ap)
    args = ap.parse_args()
    parallel.configure(args)

    asset_dir = os.path.join(args.apk_dir, 'assets', 'Asset')
    if not os.path.isdir(asset_dir):
        sys.exit(f'not found: {asset_dir} (unzip the APK first, see README)')

    if args.list:
        for g, pre in sorted(GROUPS.items()):
            files = pick_bundles(asset_dir, pre)
            print(f'{g:8} {len(files):3} bundles  {pre}')
        return

    mono = pick_bundles(asset_dir, ('2df21d6c37629e395273171aa169d769_monoscripts',))
    mono_names = mono_scripts(mono)
    dest = os.path.join(args.out, 'prefabs')
    os.makedirs(dest, exist_ok=True)

    # All groups' bundles go through one pool, so a group of 3 big bundles does not
    # leave 5 workers idle. The cache tag carries the monoscripts file names: a new
    # script table must not be joined with rows cached under the old one.
    groups = args.groups or sorted(GROUPS)
    files = {g: pick_bundles(asset_dir, GROUPS[g]) for g in groups}
    flat = [f for g in groups for f in files[g]]
    tag = cache_tag('prefabs', *map(os.path.basename, mono))
    print(f'reading {len(flat)} bundles in parallel...', flush=True)
    results = dict(
        zip(
            flat,
            map_bundles(
                partial(dump_one, mono_names=mono_names),
                flat,
                tag=tag,
                progress=every(25),
                cacheable=lambda r: r[1] is None,  # a bundle that raised is retried next run
            ),
        )
    )

    for group in groups:
        rows = []
        for f in files[group]:
            got, err = results[f]
            rows.extend(got)
            if err:
                print(f'    {logical(f)}: {err}', file=sys.stderr)
        path = os.path.join(dest, group + '.json')
        with open(path, 'w', encoding='utf8') as fh:
            json.dump(rows, fh, ensure_ascii=False, separators=(',', ':'))
        print(
            f'{group}: {len(rows)} prefabs -> {path} ({os.path.getsize(path) / 1e6:.1f} MB)',
            flush=True,
        )


if __name__ == '__main__':
    main()
