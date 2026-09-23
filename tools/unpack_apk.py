#!/usr/bin/env python3
"""Unpack a new game download into `soul-knight-prequel-<version>/`.

    python tools/unpack_apk.py                     # newest .apk/.xapk/.apks/.zip in the root
    python tools/unpack_apk.py path/to/game.xapk
    python tools/unpack_apk.py game.apk --version 1.14.0   # if it cannot be read

Accepts every shape the game has come in:

  * a plain `.apk` (a zip with `AndroidManifest.xml` at its root);
  * a `.zip` that wraps an already-unpacked APK in one top-level folder -- which is
    what `soul-knight-prequel-1-13-0.zip` is;
  * an `.xapk` / `.apks` bundle holding `base.apk` plus split APKs (asset packs, native
    libraries). Every inner APK is unpacked into the same folder, base first, which is
    how Android itself merges them.

The version comes from the game's own `assets/bundleVersionData.txt`, then from the
binary manifest's `versionName`, then from an XAPK's `manifest.json`; `--version`
overrides all three. An existing folder is never overwritten without `--force`.
"""

import argparse
import glob
import json
import os
import shutil
import sys
import tempfile
import zipfile

import versions

ARCHIVES = ('*.apk', '*.xapk', '*.apks', '*.zip')


def _safe_target(dest, rel):
    """`dest/rel`, refusing names that would escape `dest` (zip-slip)."""
    target = os.path.realpath(os.path.join(dest, rel))
    if os.path.commonpath([target, os.path.realpath(dest)]) != os.path.realpath(dest):
        raise ValueError(f'unsafe path in archive: {rel!r}')
    return target


def _extract(z, dest, strip='', overwrite=True):
    """Extract every member of `z` under `dest`, dropping the `strip` prefix. With
    `overwrite` off, files already there are kept (a split APK only adds files)."""
    n = 0
    for info in z.infolist():
        name = info.filename
        if strip:
            if not name.startswith(strip):
                continue
            name = name[len(strip) :]
        if not name or name.endswith('/'):
            continue
        target = _safe_target(dest, name)
        if not overwrite and os.path.exists(target):
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with z.open(info) as src, open(target, 'wb') as out:
            shutil.copyfileobj(src, out, 1 << 20)
        n += 1
    return n


def classify(z):
    """`('apk', '')`, `('wrapped', '<folder>/')` or `('bundle', [inner apk names])`."""
    names = z.namelist()
    if 'AndroidManifest.xml' in names:
        return 'apk', ''
    inner = sorted(n for n in names if n.lower().endswith('.apk') and '/' not in n)
    if inner:
        # base.apk first. Each split carries its own AndroidManifest.xml and
        # resources.arsc; those must not replace the base's, so splits only add files.
        inner.sort(key=lambda n: (os.path.basename(n).lower() != 'base.apk', n))
        return 'bundle', inner
    tops = {n.split('/', 1)[0] for n in names if '/' in n}
    if len(tops) == 1:
        top = tops.pop() + '/'
        if top + 'AndroidManifest.xml' in names:
            return 'wrapped', top
    raise ValueError(
        'not an APK: no AndroidManifest.xml at the root, in one folder, or in an inner .apk'
    )


def read_version(z, kind, strip):
    """The game version from inside an open archive, or None."""

    def reader(zf, prefix=''):
        def read(rel):
            try:
                return zf.read(prefix + rel)
            except KeyError:
                return None

        return read

    if kind in ('apk', 'wrapped'):
        return versions.version_from_files(reader(z, strip))
    for inner in strip:  # bundle: look inside each inner APK, then the XAPK manifest
        with z.open(inner) as fh, zipfile.ZipFile(_spool(fh)) as iz:
            v = versions.version_from_files(reader(iz))
            if v:
                return v
    try:
        return json.loads(z.read('manifest.json'))['version_name']
    except (KeyError, ValueError):
        return None


def _spool(fh):
    """A seekable copy of an inner archive (ZipFile needs to seek)."""
    tmp = tempfile.SpooledTemporaryFile(max_size=64 << 20)
    shutil.copyfileobj(fh, tmp, 1 << 20)
    tmp.seek(0)
    return tmp


def unpack(path, root=versions.ROOT, version=None, force=False):
    """Unpack `path` under `root`; return `(version, folder, files written)`."""
    with zipfile.ZipFile(path) as z:
        kind, strip = classify(z)
        version = version or read_version(z, kind, strip)
        if not version:
            raise ValueError(f'cannot read the game version from {path}; pass --version')
        dest = os.path.join(root, versions.dir_name(version))
        if os.path.exists(dest):
            if not force:
                raise FileExistsError(f'{dest} already exists (use --force to replace it)')
            shutil.rmtree(dest)
        os.makedirs(dest)
        if kind == 'bundle':
            n = 0
            for i, inner in enumerate(strip):
                with z.open(inner) as fh, zipfile.ZipFile(_spool(fh)) as iz:
                    n += _extract(iz, dest, overwrite=i == 0)
        else:
            n = _extract(z, dest, strip)
    if not os.path.isdir(os.path.join(dest, 'assets', 'Asset')):
        print(f'warning: {dest} has no assets/Asset/ -- the bundles may ship in an asset pack')
    return version, dest, n


def newest_archive(root=versions.ROOT):
    """The most recently modified archive in `root` whose version is not unpacked yet."""
    have = {v for v, _ in versions.apk_dirs(root)}
    found = sorted(
        (p for pat in ARCHIVES for p in glob.glob(os.path.join(root, pat))),
        key=os.path.getmtime,
        reverse=True,
    )
    for p in found:
        try:
            with zipfile.ZipFile(p) as z:
                kind, strip = classify(z)
                v = read_version(z, kind, strip)
        except (zipfile.BadZipFile, ValueError):
            continue
        if v and v not in have:
            return p
    return None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('archive', nargs='?', help='default: newest not-yet-unpacked archive')
    ap.add_argument('--version', help='override the detected game version')
    ap.add_argument('--force', action='store_true', help='replace an existing folder')
    args = ap.parse_args()

    path = args.archive or newest_archive()
    if not path:
        sys.exit('no new .apk/.xapk/.apks/.zip in the project root (all already unpacked)')
    try:
        version, dest, n = unpack(path, version=args.version, force=args.force)
    except (ValueError, FileExistsError, zipfile.BadZipFile) as e:
        sys.exit(str(e))
    print(
        f'{os.path.basename(path)} -> {os.path.relpath(dest, versions.ROOT)}/ '
        f'(version {version}, {n} files)'
    )
    print('next: python tools/pipeline.py')


if __name__ == '__main__':
    main()
