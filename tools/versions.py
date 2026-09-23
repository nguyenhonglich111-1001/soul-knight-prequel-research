"""Which game version a tool works on, and where its files live.

Each unpacked APK sits in `soul-knight-prequel-<a-b-c>/` and each version's output in
`extracted/<a.b.c>/`; `extracted/_sheets/` (hand-made contact sheets, guide PNGs) is
shared. Every tool defaults to the newest of each, so a new APK needs no flags:

    python tools/unpack_apk.py                  # drop the .apk/.xapk/.zip in the root first
    python tools/pipeline.py                    # extract + build it
    python tools/version_diff.py 1.13.0 1.14.0  # what changed, what to screenshot

A version is read from the game's own `assets/bundleVersionData.txt` (`"version":
"1.13.0"`), falling back to `versionName` in the binary `AndroidManifest.xml`.
"""

import glob
import json
import os
import re
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACTED = os.path.join(ROOT, 'extracted')
APK_PREFIX = 'soul-knight-prequel-'


def version_key(v):
    """'1.13.0' -> (1, 13, 0), so '1.9' sorts before '1.13'."""
    return tuple(int(n) for n in re.findall(r'\d+', v))


def dir_name(version):
    """'1.13.0' -> 'soul-knight-prequel-1-13-0'."""
    return APK_PREFIX + version.replace('.', '-')


# --------------------------------------------------------------------------- manifest


def manifest_version(data):
    """`versionName` from a binary (AXML) AndroidManifest.xml, or None.

    AXML is a chunked format: a string pool, then XML nodes whose attributes point into
    it. `versionName` sits on the root `<manifest>` element, so the first start-element
    chunk is enough."""
    try:
        if struct.unpack_from('<H', data, 0)[0] != 0x0003:
            return None
        pos, strings = 8, []
        while pos + 8 <= len(data):
            ctype, header, size = struct.unpack_from('<HHI', data, pos)
            if ctype == 0x0001:  # string pool
                count, _styles, flags, str_start = struct.unpack_from('<IIII', data, pos + 8)
                utf8 = bool(flags & 0x100)
                offsets = struct.unpack_from(f'<{count}I', data, pos + header)
                strings = [_pool_string(data, pos + str_start + o, utf8) for o in offsets]
            elif ctype == 0x0102:  # start element
                attr_start, attr_size, attr_count = struct.unpack_from('<HHH', data, pos + 24)
                base = pos + 16 + attr_start
                for i in range(attr_count):
                    _ns, name, raw, _vsize, _res, _vtype, _vdata = struct.unpack_from(
                        '<IIIHBBI', data, base + i * attr_size
                    )
                    if strings[name] == 'versionName' and raw != 0xFFFFFFFF:
                        return strings[raw]
                return None
            if size <= 0:
                return None
            pos += size
    except (struct.error, IndexError):
        return None
    return None


def _pool_string(data, pos, utf8):
    if utf8:
        pos += 2 if data[pos] & 0x80 else 1  # utf-16 length, skipped
        n = data[pos]
        if n & 0x80:
            n = ((n & 0x7F) << 8) | data[pos + 1]
            pos += 1
        return data[pos + 1 : pos + 1 + n].decode('utf8', 'replace')
    (n,) = struct.unpack_from('<H', data, pos)
    if n & 0x8000:
        n = ((n & 0x7FFF) << 16) | struct.unpack_from('<H', data, pos + 2)[0]
        pos += 2
    return data[pos + 2 : pos + 2 + 2 * n].decode('utf-16-le', 'replace')


def version_from_files(read):
    """The game version from an unpacked or zipped APK. `read(relpath)` returns the
    file's bytes or None."""
    raw = read('assets/bundleVersionData.txt')
    if raw:
        try:
            return json.loads(raw.decode('utf-8-sig'))['version']
        except (ValueError, KeyError):
            pass
    raw = read('AndroidManifest.xml')
    return manifest_version(raw) if raw else None


# --------------------------------------------------------------------------- lookup


def version_of(apk_dir):
    """Version of an unpacked APK folder: its own files first, then the folder name."""

    def read(rel):
        p = os.path.join(apk_dir, *rel.split('/'))
        if os.path.isfile(p):
            with open(p, 'rb') as fh:
                return fh.read()
        return None

    v = version_from_files(read)
    if v:
        return v
    m = re.fullmatch(re.escape(APK_PREFIX) + r'(\d+(?:-\d+)*)', os.path.basename(apk_dir))
    return m.group(1).replace('-', '.') if m else None


def apk_dirs(root=ROOT):
    """`[(version, dir)]` for every unpacked APK under `root`, oldest first."""
    found = []
    for d in glob.glob(os.path.join(root, APK_PREFIX + '*')):
        if os.path.isdir(os.path.join(d, 'assets', 'Asset')):
            v = version_of(d)
            if v:
                found.append((v, d))
    return sorted(found, key=lambda x: version_key(x[0]))


def out_versions(extracted=EXTRACTED):
    """Versions that have extracted output (a `localization_all.json`), oldest first."""
    vs = [
        os.path.basename(os.path.dirname(p))
        for p in glob.glob(os.path.join(extracted, '*', 'localization_all.json'))
    ]
    return sorted(vs, key=version_key)


def out_dir(version, extracted=EXTRACTED):
    return os.path.join(extracted, version)


def default_apk_dir(root=ROOT):
    dirs = apk_dirs(root)
    if not dirs:
        raise SystemExit(f'no unpacked APK ({APK_PREFIX}*/) -- run tools/unpack_apk.py first')
    return dirs[-1][1]


def default_out(extracted=EXTRACTED):
    """Newest version with extracted output -- what the build_* tools read by default."""
    vs = out_versions(extracted)
    if not vs:
        raise SystemExit(f'no extracted version under {extracted}/ -- run tools/pipeline.py')
    return out_dir(vs[-1], extracted)


def resolve_extract_args(args):
    """Fill `args.apk_dir` / `args.out` for an extractor: newest APK, and that APK's own
    output folder. Either can still be given explicitly."""
    if args.apk_dir is None:
        args.apk_dir = default_apk_dir()
    if args.out is None:
        v = version_of(args.apk_dir)
        if not v:
            raise SystemExit(f'cannot tell the version of {args.apk_dir}; pass --out')
        args.out = out_dir(v)
    return args


def resolve_out_arg(args):
    """Fill `args.out` for a build_* tool: the newest extracted version."""
    if args.out is None:
        args.out = default_out()
    return args
