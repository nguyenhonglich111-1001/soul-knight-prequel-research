#!/usr/bin/env python3
"""Extract readable game data from an unpacked Soul Knight Prequel APK.

Usage (from the project root):
    pip install UnityPy
    python tools/extract_soulknight.py                       # everything
    python tools/extract_soulknight.py --skip-icons          # text/catalog only (fast)
    python tools/extract_soulknight.py --apk-dir <dir> --out <dir>

Stages (each writes into --out):
    1. localization_all.json   every string, all languages, keyed by the game's own key
    2. asset_catalog.json      Addressables catalog: address -> asset path in the Unity project
    3. sprite_index.json       sprite name -> bundle(s) it lives in
    4. icons/                  PNG export of icon-like sprites (slow: ~15-30 min;
                               --all-sprites exports all ~112k sprites instead)
    5. items.json              'ITEM_*' style items joined with names/descriptions/icon
       items_numeric.json      numeric-ID items joined with names/descriptions/icon
       numeric_ranges.json     summary of numeric key ranges (what each block looks like)

`skp_loc_s13_bin` is XOR-obfuscated rather than encrypted and is unpacked here (see
`deobfuscate`). What is still NOT extractable: numeric stats (drop rates, prices) and the
item -> effect-ID mapping, which live in the Luban config tables inside the encrypted
code_dll/code_aot bundles or on the game server. For the item -> skill-prefab link, and for
the per-level numbers that prefabs do carry, see tools/extract_skill_links.py.
"""
import argparse
import base64
import collections
import glob
import gzip
import json
import os
import re
import struct
import sys

# --------------------------------------------------------------------------- helpers

ICON_PATTERN = re.compile(
    r'^(ItemIcon_|ICON_|UI_SkillIcon|UI_Pet|UI_Spirit|UI_BF|UI_ES|icn_com|'
    r'SX_P\d|S_P\d|S_C_|S_\d|SKIN_WEAPON_)')

# Bundles that never contain sprites/text we need (skipped to save time).
SKIP_BUNDLES = ('videos_', 'audio_', 'localization', 'spine_', 'stage_')

# name id -> description id is `id + offset` in these numeric blocks. Verified by
# sampling (1->1001, 2->1002, 10->1010, 400->1400, 7301->7401, 7330->7430).
NUMERIC_DESC_RULES = [(1, 416, 1000), (7301, 7437, 100)]

_RECORD_START = re.compile(r'\r?\n(?="[^"\t\r\n]*"\t"[^"\t\r\n]*"\t)')


def unity(*paths):
    import UnityPy
    return UnityPy.load(*paths)


def textasset_bytes(obj):
    """Raw bytes of a TextAsset (UnityPy's decoded m_Script can mangle non-UTF8)."""
    raw = obj.get_raw_data()
    name_len = struct.unpack('<I', raw[:4])[0]
    pos = (4 + name_len + 3) & ~3
    size = struct.unpack('<I', raw[pos:pos + 4])[0]
    return raw[4:4 + name_len].decode('utf8', 'replace'), raw[pos + 4:pos + 4 + size]


def deobfuscate(data, header):
    """`skp_loc_s13_bin` is a normal table XORed with a short repeating key.

    Every table starts with the same `"Key" TAB "Type" TAB "English" ...` header row, so
    `cipher ^ header` *is* the key stream; it repeats with a period of 120 bytes."""
    ks = bytes(a ^ b for a, b in zip(data, header))
    key = next((ks[:p] for p in range(1, len(ks))
                if all(ks[i] == ks[i + p] for i in range(len(ks) - p))), None)
    if key is None:
        return None
    plain = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return plain if plain.startswith(b'"Key"') else None


def parse_tsv(text):
    """The game's TSV has unescaped quotes/newlines in cells, so csv.reader breaks.
    Split on record starts (`"key"<TAB>"type"<TAB>`) instead."""
    recs = _RECORD_START.split(text)

    def cell(c):
        if len(c) >= 2 and c[0] == '"' and c[-1] == '"':
            c = c[1:-1].replace('""', '"')
        return c

    header = [cell(c) for c in recs[0].split('\t')]
    rows = []
    for r in recs[1:]:
        cells = [cell(c) for c in r.split('\t')]
        if len(cells) == len(header):
            rows.append(cells)
    return header, rows


# --------------------------------------------------------------------------- stage 1

def stage_localization(asset_dir, out):
    # Pass 1: read the raw TextAssets. Plain tables are used to learn the header row,
    # which is then the known plaintext that unlocks the obfuscated ones.
    tables, header_bytes = [], None
    for f in bundle_files(asset_dir, 'localization_*.bundle', skip=False):
        env = unity(f)
        for o in env.objects:
            if o.type.name != 'TextAsset':
                continue
            name, data = textasset_bytes(o)
            tables.append((name, data))
            if header_bytes is None and data.startswith(b'"Key"'):
                header_bytes = data[:data.index(b'\n') + 1]

    strings, langs, skipped, decoded = {}, None, [], []
    for name, data in tables:
        if not data.startswith(b'"Key"'):
            plain = deobfuscate(data, header_bytes) if header_bytes else None
            if plain is None:
                skipped.append(name)
                continue
            decoded.append(name)
            data = plain
        header, rows = parse_tsv(data.decode('utf8'))
        langs = header[2:]
        for r in rows:
            # Same key can appear in several bundle variants; first one wins.
            if r[0] and r[0] not in strings:
                strings[r[0]] = dict(zip(langs, r[2:]))
    with open(os.path.join(out, 'localization_all.json'), 'w', encoding='utf8') as fh:
        json.dump(strings, fh, ensure_ascii=False, indent=1)
    print(f'[1] {len(strings)} strings, languages: {langs}')
    if decoded:
        print(f'    de-obfuscated: {sorted(set(decoded))}')
    if skipped:
        print(f'    not readable: {sorted(set(skipped))}')
    return strings


# --------------------------------------------------------------------------- stage 2

def stage_catalog(apk_dir, out):
    """aa/catalog.json is an Addressables ContentCatalogData; decode key -> asset path."""
    j = json.load(open(os.path.join(apk_dir, 'assets', 'aa', 'catalog.json'), encoding='utf8'))
    kd = base64.b64decode(j['m_KeyDataString'])
    bd = base64.b64decode(j['m_BucketDataString'])
    ed = base64.b64decode(j['m_EntryDataString'])
    ids = j['m_InternalIds']
    nk, = struct.unpack_from('<i', bd, 0)
    pos, buckets = 4, []
    for _ in range(nk):
        kpos, n = struct.unpack_from('<ii', bd, pos)
        pos += 8
        entries = struct.unpack_from('<%di' % n, bd, pos)
        pos += 4 * n
        t = kd[kpos]
        if t in (0, 1):                                   # ascii / utf16 string
            ln, = struct.unpack_from('<i', kd, kpos + 1)
            key = kd[kpos + 5:kpos + 5 + ln].decode('utf8' if t == 0 else 'utf16')
        elif t in (4, 5):                                 # int key
            key = str(struct.unpack_from('<i', kd, kpos + 1)[0])
        else:
            continue
        buckets.append((key, entries))
    ne, = struct.unpack_from('<i', ed, 0)
    entry = [struct.unpack_from('<7i', ed, 4 + 28 * i) for i in range(ne)]
    catalog = {}
    for key, ents in buckets:
        for e in ents:
            target = ids[entry[e][0]]
            if target.startswith('Assets/'):
                catalog[key] = target
    with open(os.path.join(out, 'asset_catalog.json'), 'w', encoding='utf8') as fh:
        json.dump(catalog, fh, indent=1)
    print(f'[2] {len(catalog)} catalog addresses with an Assets/ path')


# --------------------------------------------------------------------------- stage 3

def shipped_bundles(asset_dir):
    """Basenames of the bundles the Addressables catalog actually points at, or `None`
    if the catalog cannot be read.

    44 logical bundles ship two or three variants that differ only by content hash, and
    the catalog names exactly one of each -- all 44, no exceptions. That is the only
    reliable signal of which copy the game loads; the others are leftovers from earlier
    builds. Reading the wrong one gives stale text (an older `skp_loc_s13_bin` is missing
    a colour-tag fix, and four tables still have straight quotes), and reading two at once
    gives garbage pixels, because variants share the CAB name of their `.resS` stream --
    see `export_sprites`.

    Filtering to this set costs three sprites, `S13_SKIN_H_icon_4`/`_5`/`_6`, which live
    only in an orphaned variant and are not icons we export."""
    path = os.path.join(asset_dir, os.pardir, 'aa', 'catalog.json')
    if not os.path.exists(path):
        return None
    ids = json.load(open(path, encoding='utf8'))['m_InternalIds']
    return {os.path.basename(i) for i in ids if i.endswith('.bundle')}


def bundle_files(asset_dir, pattern='*.bundle', skip=True):
    """Every bundle worth opening: one variant per logical bundle, minus the families
    that never hold anything we read. `skip` is off when the caller asked for one of
    those families by name -- `localization_*` is both in SKIP_BUNDLES and stage 1's
    whole input."""
    shipped = shipped_bundles(asset_dir)
    return [f for f in sorted(glob.glob(os.path.join(asset_dir, pattern)))
            if not (skip and any(s in os.path.basename(f) for s in SKIP_BUNDLES))
            and (shipped is None or os.path.basename(f) in shipped)]


def stage_sprite_index(asset_dir, out):
    index = {}
    for f in bundle_files(asset_dir):
        env = unity(f)
        names = []
        for o in env.objects:
            if o.type.name == 'Sprite':
                try:
                    names.append(o.read().m_Name)
                except Exception:
                    pass
        if names:
            index[os.path.basename(f)] = names
    with open(os.path.join(out, 'sprite_index.json'), 'w') as fh:
        json.dump(index, fh)
    print(f'[3] {sum(len(v) for v in index.values())} sprites in {len(index)} bundles')
    return index


# --------------------------------------------------------------------------- stage 4

def sprite_folder(name, forced=None):
    """`icons/<family>/<name>.png`, where the family is the name's leading alpha run(s).

    That rule assumes a `Family_Item` shape and scatters longer names -- `EBF_SCATTERING`
    and `EBF_LEAD_BULLET` would land in two different folders -- so callers that know
    better pass `forced`."""
    if forced:
        return forced
    m = re.match(r'^([A-Za-z]+(?:_[A-Za-z]+)?)', name)
    return m.group(1) if m else 'misc'


def export_sprites(paths, want, out, folder=None, progress=None):
    """Write every sprite whose name satisfies `want`, **one bundle per environment**.

    Loading one bundle at a time is not a memory optimisation, it is the correctness
    requirement. Many logical bundles ship two or three variants that differ only by
    content hash, and the variants reuse the CAB name of their `.resS` stream file. Put
    two of them in one UnityPy environment and both atlas textures resolve that shared
    name to the *same* 8 MB pixel blob -- but the variants pack at different shapes
    (2048x4096 vs 4096x2048), so every crop lands on unrelated pixels. No exception is
    raised; the PNGs just come out as garbage, which is what happened to all ~500
    `ItemIcon_*` files in an earlier version of this repo.

    Nothing is lost by not co-loading the atlases. UnityPy looks for a packed sprite's
    SpriteAtlas only in the sprite's *own* assets file (`SpriteHelper.get_image_from_
    sprite`), so a packed sprite was only ever exportable from the atlas bundle it was
    packed into; its copies in other bundles carry `m_RD.texture` == PathID 0 and fail
    either way.
    """
    done, failed = set(), {}
    for i, path in enumerate(paths, 1):
        for o in unity(path).objects:
            if o.type.name != 'Sprite':
                continue
            try:
                sprite = o.read()
                name = sprite.m_Name
            except Exception:
                continue
            if name in done or not want(name):
                continue
            try:
                image = sprite.image
            except Exception as e:  # not packed here -> another bundle may have it
                failed[name] = str(e)[:60]
                continue
            d = os.path.join(out, 'icons', sprite_folder(name, folder))
            os.makedirs(d, exist_ok=True)
            image.save(os.path.join(d, name + '.png'))
            done.add(name)
        if progress:
            progress(i, len(paths), len(done))
    return done, {k: v for k, v in failed.items() if k not in done}


def stage_icons(asset_dir, out, index, all_sprites=False):
    """`all_sprites` drops the icon name filter and exports every sprite in the game
    (~112k files, several GB, hours) instead of the ~5.4k icon-like ones."""
    want = (lambda n: True) if all_sprites else ICON_PATTERN.match
    files = [b for b, names in index.items() if any(want(n) for n in names)]
    print(f'[4] scanning {len(files)} bundles one at a time (slow)...', flush=True)

    def tick(i, total, n):
        if i % 10 == 0 or i == total:
            print(f'    {i}/{total} bundles, {n} icons', flush=True)

    done, failed = export_sprites([os.path.join(asset_dir, b) for b in files],
                                  want, out, progress=tick)
    unresolved = sorted(failed)
    with open(os.path.join(out, 'icons_unresolved.json'), 'w') as fh:
        json.dump(unresolved, fh, indent=1)
    print(f'[4] {len(done)} icons written, {len(unresolved)} could not be decoded')
    return done


# --------------------------------------------------------------------------- stage 5

def icon_folder(name):
    m = re.match(r'^([A-Za-z]+(?:_[A-Za-z]+)?)', name)
    return (m.group(1) if m else 'misc') + '/' + name + '.png'


def icon_candidates(nid):
    """Sprite names that may hold item `nid`'s icon, best guess first.

    The ID is used verbatim, under several prefixes depending on which UI first showed
    the item. There is deliberately **no** equipment branch: an earlier one mapped
    `10SNNNN` to `ItemIcon_<NNNNN>000` (`101643` -> `ItemIcon_1643000`), and no such
    arithmetic link exists -- `103467` Tophat of Six Splendors is `ItemIcon_3470000`.
    Equipment icons come from `guide/icon_map.json` (hand-checked) and the `ITEM_*`
    alias rule, both applied in build_equipment.py. See icon-mapping-plan.md."""
    yield f'ItemIcon_{nid}'
    yield f'ItemIcon_spt_{nid}'
    yield f'ICON_SP_{nid}'
    yield f'UI_SkillIcon_{nid}'
    yield f'UI_BF_{nid}'


def stage_items(strings, sprite_names, out):
    have_icons = os.path.isdir(os.path.join(out, 'icons'))

    def icon_for(name):
        # Prefer the file that was really written; fall back to the sprite index.
        if have_icons:
            rel = icon_folder(name)
            return rel if os.path.exists(os.path.join(out, 'icons', rel)) else None
        return icon_folder(name) if name in sprite_names else None

    def first_icon(names):
        return next((r for r in (icon_for(n) for n in names) if r), None)

    # ---- 'ITEM_<code>' items: name = ITEM_x, description = ITEM_x_D
    items = []
    for key, names in strings.items():
        m = re.match(r'^ITEM_([A-Za-z]+)_(.+)$', key)
        if not m or key.endswith(('_D', '_Info')):
            continue
        icon = first_icon(('ItemIcon_' + key[5:], 'ICON_SP_' + key[5:]))
        items.append({
            'id': key[5:], 'prefix': m.group(1), 'key': key,
            'name': names['English'],
            'description': strings.get(key + '_D', {}).get('English', ''),
            'names': names, 'descriptions': strings.get(key + '_D', {}),
            'icon': icon,
        })
    with open(os.path.join(out, 'items.json'), 'w', encoding='utf8') as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)

    # ---- numeric-ID items (weapons, armor, consumables, ...)
    numeric = {int(k): v for k, v in strings.items() if k.isdigit()}
    rows = []
    for nid, names in sorted(numeric.items()):
        desc_id = next((nid + off for lo, hi, off in NUMERIC_DESC_RULES if lo <= nid <= hi), None)
        desc = strings.get(str(desc_id), {}) if desc_id else {}
        rows.append({
            'id': nid, 'name': names['English'], 'names': names,
            'description': desc.get('English', ''), 'descriptions': desc,
            'description_id': desc_id if desc else None,
            'icon': first_icon(icon_candidates(nid)),
        })
    with open(os.path.join(out, 'items_numeric.json'), 'w', encoding='utf8') as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)

    # ---- blocks of numeric keys, so you can see what each range holds
    ranges, start, prev = [], None, None
    for nid in sorted(numeric):
        if prev is None or nid - prev > 50:
            if start is not None:
                ranges.append((start, prev))
            start = nid
        prev = nid
    ranges.append((start, prev))
    summary = [{'from': a, 'to': b, 'count': sum(1 for n in numeric if a <= n <= b),
                'sample': numeric[a]['English'][:80]} for a, b in ranges]
    with open(os.path.join(out, 'numeric_ranges.json'), 'w', encoding='utf8') as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print(f"[5] items.json={len(items)}  items_numeric.json={len(rows)} "
          f"(with icon: {sum(1 for r in rows if r['icon'])}, "
          f"with description: {sum(1 for r in rows if r['description'])})")


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apk-dir', default='soul-knight-prequel-1-13-0')
    ap.add_argument('--out', default='extracted')
    ap.add_argument('--skip-icons', action='store_true')
    ap.add_argument('--all-sprites', action='store_true',
                    help='export every sprite, not just icons (~112k files, hours)')
    args = ap.parse_args()

    asset_dir = os.path.join(args.apk_dir, 'assets', 'Asset')
    if not os.path.isdir(asset_dir):
        sys.exit(f'not found: {asset_dir} (unzip the APK first, see README)')
    os.makedirs(args.out, exist_ok=True)

    strings = stage_localization(asset_dir, args.out)
    stage_catalog(args.apk_dir, args.out)
    index = stage_sprite_index(asset_dir, args.out)
    if not args.skip_icons:
        stage_icons(asset_dir, args.out, index, args.all_sprites)
    sprite_names = {n for v in index.values() for n in v}
    stage_items(strings, sprite_names, args.out)


if __name__ == '__main__':
    main()
