#!/usr/bin/env python3
"""Run every stage for one game version, in order.

    python tools/pipeline.py                  # newest unpacked APK -> extracted/<version>/
    python tools/pipeline.py --version 1.13.0
    python tools/pipeline.py --from build_equipment   # resume at a stage
    python tools/pipeline.py --list

After the build stages it runs `version_diff.py` against the previous extracted version,
if there is one, which lists what a new version needs from the game (screenshots).
Stops at the first stage that fails, except `build_icon_map` -- see STAGES.
"""

import argparse
import os
import subprocess
import sys
import time

import versions

TOOLS = os.path.dirname(os.path.abspath(__file__))

# (name, script, extra args, takes --apk-dir, fatal). Order matters: see "Commands" in CLAUDE.md.
# build_icon_map exits 1 when a confirmed sprite is missing or disagrees with the alias
# rule. On a new version that is a finding for version_diff to explain, not a reason to
# stop before the report is written.
STAGES = [
    ('extract', 'extract_soulknight.py', [], True, True),
    (
        'fatebound_icons',
        'extract_named_sprites.py',
        ['--prefix', 'EBF_', '--folder', 'EBF'],
        True,
        True,
    ),
    (
        'incarnate_icons',
        'extract_named_sprites.py',
        ['--prefix', 'Incarnation_', 'UI_Incarnation_', '--folder', 'Incarnation'],
        True,
        True,
    ),
    (
        'slot_icons',
        'extract_named_sprites.py',
        ['--prefix', 'icn_equip_', 'item_rate_frame_s_', 'icn_resonance_'],
        True,
        True,
    ),
    (
        'class_skill_icons',
        'extract_named_sprites.py',
        ['--prefix', 'SD_', 'soul_bonus_', '97', '--folder', 'ClassSkill'],
        True,
        True,
    ),
    ('skill_links', 'extract_skill_links.py', [], True, True),
    ('prefabs', 'dump_prefabs.py', [], True, True),
    ('build_icon_map', 'build_icon_map.py', [], False, False),
    ('build_equipment', 'build_equipment.py', [], False, True),
    ('build_indexes', 'build_indexes.py', [], False, True),
    ('build_glossary', 'build_glossary.py', [], False, True),
    ('build_item_details', 'build_item_details.py', [], False, True),
    ('build_guide', 'build_guide.py', ['--all'], False, True),
]


def run(cmd):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run(cmd, env=env, cwd=versions.ROOT, check=False).returncode


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('--version', help='game version to build (default: newest unpacked)')
    ap.add_argument(
        '--from',
        dest='start',
        choices=[s[0] for s in STAGES],
        help='skip the stages before this one',
    )
    ap.add_argument('--list', action='store_true', help='print the stages and exit')
    ap.add_argument('--no-diff', action='store_true', help='skip the version_diff step')
    args = ap.parse_args()

    if args.list:
        for name, script, extra, _, _ in STAGES:
            print(f'{name:20} {script} {" ".join(extra)}')
        return

    if args.version:
        apk_dir = os.path.join(versions.ROOT, versions.dir_name(args.version))
        if not os.path.isdir(apk_dir):
            sys.exit(f'{apk_dir} not found -- run tools/unpack_apk.py first')
        version = args.version
    else:
        apk_dir = versions.default_apk_dir()
        version = versions.version_of(apk_dir)
    out = versions.out_dir(version)
    print(
        f'== {version}: {os.path.relpath(apk_dir, versions.ROOT)} -> '
        f'{os.path.relpath(out, versions.ROOT)}',
        flush=True,
    )

    names = [s[0] for s in STAGES]
    todo = STAGES[names.index(args.start) :] if args.start else STAGES
    t_all, warnings = time.time(), []
    for name, script, extra, takes_apk, fatal in todo:
        cmd = [sys.executable, os.path.join(TOOLS, script), *extra, '--out', out]
        if takes_apk:
            cmd += ['--apk-dir', apk_dir]
        print(f'\n== {name}', flush=True)
        t = time.time()
        if run(cmd) != 0:
            if fatal:
                sys.exit(
                    f'stage {name} failed -- fix it, then: python tools/pipeline.py --from {name}'
                )
            warnings.append(name)
        print(f'   ({time.time() - t:.0f} s)', flush=True)
    print(f'\n== all stages done in {time.time() - t_all:.0f} s', flush=True)
    for name in warnings:
        print(f'   warning: {name} reported problems (see above)', flush=True)

    key = versions.version_key(version)
    older = [v for v in versions.out_versions() if versions.version_key(v) < key]
    if older and not args.no_diff:
        print(f'\n== version_diff {older[-1]} -> {version}', flush=True)
        run([sys.executable, os.path.join(TOOLS, 'version_diff.py'), older[-1], version])


if __name__ == '__main__':
    main()
