#!/usr/bin/env python3
"""Resolve every `$token$` in the game text to its glossary term.

Descriptions reference highlighted keywords by token, e.g. `$jisu$` in "grants $jisu$".
The token table itself is encrypted, but the tokens are the pinyin of the term's Chinese
name, and the terms are the `206xxx` localization block:

    $jisu$     -> 206032 急速 "Swift"
    $yingyan$  -> 206098 鹰眼 "Eagle Eye"
    $yishang$  -> 206013 易伤 "Vulnerable"

So a token is matched to the term whose Chinese reads as the token (all readings of
polyphones such as 血 xue/xie are tried; `_` in a token is ignored). A handful of tokens
are misspelled by the game (`lingfeng` for 凛风 linfeng); a leftover token that is one
letter away from exactly one leftover term is matched too, marked `"match": "near"`.
What is still left is looked up in the hand-checked `glossary` of the guide files
(`daxue` -> "Exsanguinate": 大出血 is dachuxue), marked `"match": "guide"`.

Each term's rules text is the key 500 above it, in the `2065xx` block. Checked by
reading all 136 pairs side by side (1.13.0), every one describes its term:

    206032 Swift  -> 206532 "Movement speed is increased by {0}% for {1}s."

Writes:
    glossary.json   {token: {key, name, names, description, descriptions, match, uses}},
                    plus the unmatched tokens, the terms no token points at and the
                    descriptions with no term 500 below them

    python tools/build_glossary.py      (needs: pip install pypinyin)
"""

import argparse
import collections
import itertools
import json
import os
import re
import sys

import versions

TOKEN = re.compile(r'\$([A-Za-z0-9_]+)\$')
TERM_KEYS = re.compile(r'206[0-4]\d\d$')
DESC_KEYS = re.compile(r'206[5-9]\d\d$')
DESC_OFFSET = 500
GUIDE_DIR = os.path.join(versions.ROOT, 'guide')


def readings(chinese):
    """Every pinyin spelling of a Chinese string, tones and non-Han characters dropped."""
    from pypinyin import Style, pinyin

    per_char = pinyin(chinese, style=Style.NORMAL, heteronym=True, errors='ignore')
    per_char = [[r.replace('ü', 'v') for r in rs] for rs in per_char]
    return {''.join(combo) for combo in itertools.product(*per_char)}


def one_edit_apart(a, b):
    """True when a and b differ by one substitution, insertion or deletion."""
    if abs(len(a) - len(b)) > 1 or a == b:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    return any(a == b[:i] + b[i + 1 :] for i in range(len(b)))


def match(tokens, terms):
    """{token: (term key, 'exact' | 'near')} for every token that resolves unambiguously.

    `terms` is {key: Chinese}. A token matching several terms is left unresolved."""
    spelled = {key: readings(zh) for key, zh in terms.items()}
    found = {}
    for tok in tokens:
        hits = [key for key, rs in spelled.items() if tok.replace('_', '') in rs]
        if len(hits) == 1:
            found[tok] = (hits[0], 'exact')
    used = {key for key, _ in found.values()}
    for tok in tokens:
        if tok in found:
            continue
        flat = tok.replace('_', '')
        hits = [
            key
            for key, rs in spelled.items()
            if key not in used and any(one_edit_apart(flat, r) for r in rs)
        ]
        if len(hits) == 1:
            found[tok] = (hits[0], 'near')
    return found


def guide_glossary():
    """{token: English} from the `glossary` of every guide file (hand-checked)."""
    out = {}
    for name in sorted(os.listdir(GUIDE_DIR)):
        if name.endswith('.json'):
            data = json.load(open(os.path.join(GUIDE_DIR, name), encoding='utf8'))
            if isinstance(data, dict):
                out.update(data.get('glossary', {}))
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('--out', help='extracted version folder (default: newest extracted/<version>/)')
    args = ap.parse_args()
    versions.resolve_out_arg(args)
    try:
        import pypinyin  # noqa: F401
    except ImportError:
        sys.exit('build_glossary needs pypinyin: pip install pypinyin')

    loc = json.load(open(os.path.join(args.out, 'localization_all.json'), encoding='utf8'))
    uses = collections.Counter()
    for row in loc.values():
        uses.update(TOKEN.findall(row.get('English') or ''))
    terms = {k: row.get('Chinese') or '' for k, row in loc.items() if TERM_KEYS.match(k)}

    found = match(sorted(uses), terms)
    by_english = collections.defaultdict(list)
    for key in terms:
        by_english[loc[key].get('English', '').lower()].append(key)
    for tok, english in guide_glossary().items():
        hits = by_english.get(english.lower(), [])
        if tok in uses and tok not in found and len(hits) == 1:
            found[tok] = (hits[0], 'guide')

    def desc(key):
        return loc.get(str(int(key) + DESC_OFFSET)) or {}

    glossary = {
        tok: {
            'key': key,
            'name': loc[key].get('English', ''),
            'names': loc[key],
            'description': desc(key).get('English', ''),
            'descriptions': desc(key) or None,
            'match': how,
            'uses': uses[tok],
        }
        for tok, (key, how) in sorted(found.items())
    }
    pointed = {g['key'] for g in glossary.values()}
    out = {
        'glossary': glossary,
        'unmatched_tokens': sorted(t for t in uses if t not in found),
        'terms_without_token': {
            k: loc[k].get('English', '') for k in sorted(terms) if k not in pointed
        },
        'descriptions_without_term': {
            k: row.get('English', '')
            for k, row in sorted(loc.items())
            if DESC_KEYS.match(k) and str(int(k) - DESC_OFFSET) not in terms
        },
    }
    path = os.path.join(args.out, 'glossary.json')
    with open(path, 'w', encoding='utf8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f'{len(glossary):6} of {len(uses)} tokens resolved -> {path}')
    for how in ('near', 'guide'):
        toks = sorted(t for t, g in glossary.items() if g['match'] == how)
        pairs = ', '.join(f'{t} -> {glossary[t]["name"]}' for t in toks)
        print(f'       {how}: {pairs}')
    print(f'       with a description: {sum(1 for g in glossary.values() if g["description"])}')
    if out['unmatched_tokens']:
        print(f'       unmatched: {", ".join(out["unmatched_tokens"])}')
    print(f'       terms no token uses: {", ".join(out["terms_without_token"].values())}')
    print(f'       descriptions with no term: {len(out["descriptions_without_term"])}')


if __name__ == '__main__':
    main()
