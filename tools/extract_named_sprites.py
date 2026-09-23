#!/usr/bin/env python3
"""Export sprites by exact name, for icons `extract_soulknight.py` never looked at.

`ICON_PATTERN` in the main extractor only matches names like `ItemIcon_*` or `UI_BF_*`,
so whole families of icons were skipped. The Fatebound icons are the important one: each
is a sprite named after its buff id, e.g. the sprite `EBF_SCATTERING` is the icon for the
buff `EBF_SCATTERING` ("Multishot"). Those never matched, so they were never written.

Rather than re-running the ~30 minute full sprite pass, this reads `sprite_index.json` to
find which bundles actually hold the wanted names and opens only those -- one at a time,
which is what `extract_soulknight.export_sprites` requires to decode them correctly.

    python tools/extract_named_sprites.py EBF_SCATTERING icn_equip_weapon
    python tools/extract_named_sprites.py --prefix EBF_ --folder EBF
    python tools/extract_named_sprites.py --names-file wanted.txt
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_soulknight as E


def folder_for(name, forced=None):
    """Delegates to the main extractor so both tools file icons the same way."""
    return E.sprite_folder(name, forced)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('names', nargs='*', help='exact sprite names')
    ap.add_argument(
        '--prefix',
        nargs='*',
        default=[],
        help='every indexed sprite whose name starts with one of these',
    )
    ap.add_argument('--names-file', help='file with one sprite name per line')
    ap.add_argument('--asset-dir', default='soul-knight-prequel-1-13-0/assets/Asset')
    ap.add_argument('--out', default='extracted')
    ap.add_argument('--folder', help='write everything into extracted/icons/<folder>')
    ap.add_argument('--force', action='store_true', help='re-export already-written PNGs')
    args = ap.parse_args()

    index = json.load(open(os.path.join(args.out, 'sprite_index.json'), encoding='utf8'))
    known = {n for names in index.values() for n in names}

    want = set(args.names)
    if args.names_file:
        want |= {l.strip() for l in open(args.names_file, encoding='utf8') if l.strip()}
    for p in args.prefix:
        want |= {n for n in known if n.startswith(p)}
    if not want:
        sys.exit('nothing requested -- pass names, --prefix or --names-file')

    missing = sorted(want - known)
    want &= known
    if not args.force:
        skip = {
            n
            for n in want
            if os.path.exists(
                os.path.join(args.out, 'icons', folder_for(n, args.folder), n + '.png')
            )
        }
        want -= skip
        if skip:
            print(f'{len(skip)} already exported, skipping (use --force to redo)')
    if not want:
        print('nothing left to do')
        return

    # One bundle at a time -- see `export_sprites`. Co-loading the atlases is not just
    # unnecessary, it actively corrupts the output.
    sources = sorted(b for b, names in index.items() if want & set(names))
    print(f'{len(want)} sprites wanted, in {len(sources)} bundles; loading...', flush=True)
    done, _failed = E.export_sprites(
        [os.path.join(args.asset_dir, b) for b in sources],
        want.__contains__,
        args.out,
        folder=args.folder,
    )

    print(f'exported {len(done)} sprites')
    unresolved = sorted(want - done)
    if unresolved:
        print(f'  {len(unresolved)} indexed but not exported: {unresolved[:10]}')
    if missing:
        print(f'  {len(missing)} not in the sprite index at all: {missing[:10]}')


if __name__ == '__main__':
    main()
