#!/usr/bin/env python3
"""Render `guide/<name>.json` into a single self-contained HTML page.

The guide file holds the prose plus, for everything it mentions, a `key` into the
extracted data -- `101644`, `EBF_SCATTERING`, `SX_P1_22_100`. This resolves each key to
its real in-game name, description and icon, inlines the icons as base64 so the page is
one portable file, and prints what it could not resolve instead of quietly dropping it.

    PYTHONIOENCODING=utf-8 python tools/build_guide.py
    PYTHONIOENCODING=utf-8 python tools/build_guide.py --guide guide/ranger.json -o out.html
"""
import argparse
import base64
import collections
import html
import json
import os
import re
import sys

# The game's own rarity palette, from the `ITEM_RATE_*` strings.
RARITY = {0: ('Common', '#F5F5F5'), 1: ('Charmed', '#61E382'), 2: ('Rare', '#3FBBEC'),
          3: ('Epic', '#8E2AC1'), 4: ('Legendary', '#FAAA3F'), 5: ('Insane', '#E85048')}

ORDINALS = ['best', '2nd', '3rd', '4th', '5th']

SLOT_ICON = {'Weapon': 'icn_equip_weapon', 'Helmet': 'icn_equip_helmet',
             'Armor': 'icn_equip_armor', 'Boots': 'icn_equip_shoes',
             'Ring': 'icn_equip_ring', 'Necklace': 'icn_equip_necklace',
             # The game's own labels: Const_ItemType_CHARMS1 is "Mech Core" (机核) and
             # CHARMS2 is "Cubis Core" (魔核). These were the wrong way round.
             'Cubis core': 'icn_equip_charms2', 'Mech gear': 'icn_equip_charms1'}

# Unity rich text, matched *after* html.escape has turned its angle brackets into entities.
COLOR_TAG = re.compile(r'&lt;color=#([0-9A-Fa-f]{6})[0-9A-Fa-f]{0,2}&gt;(.*?)&lt;/color&gt;', re.S)
TERM_TAG = re.compile(r'\$([A-Za-z0-9_]+)\$')
SLOT_TAG = re.compile(r'\{(\d+)\}')
BOLD_TAG = re.compile(r'\*\*(.+?)\*\*')
CODE_TAG = re.compile(r'`([^`]+)`')

# A skill referenced by its numeric id has no sprite of its own -- icons are named after
# the skill-*tree* key. The two are joined by their Chinese, which is identical apart
# from the separator. See `Data.icon_path`.
TREE_KEY = re.compile(r'^SX?_P\d_\d+_\d+$')
CN_SEP = re.compile(r'[\s·・:：]+')


# --------------------------------------------------------------------------- data


class Data:
    """Everything the resolver needs, loaded once."""

    def __init__(self, out):
        self.loc = json.load(open(os.path.join(out, 'localization_all.json'), encoding='utf8'))
        self.numeric = {str(r['id']): r for r in
                        json.load(open(os.path.join(out, 'items_numeric.json'), encoding='utf8'))}
        # Legendary effect text, keyed by item id. `build_equipment.effect_key()` derives
        # it from the item's skill prefab; it is the only description equipment has.
        eq = os.path.join(out, 'equipment.json')
        self.effects = {str(r['id']): r['effect'] for r in
                        json.load(open(eq, encoding='utf8'))} if os.path.exists(eq) else {}
        self.by_en = collections.defaultdict(list)
        for key, row in self.loc.items():
            en = row.get('English')
            if en:
                self.by_en[en].append(key)
        root = os.path.join(out, 'icons')
        self.icons = {f[:-4]: os.path.join(root, d, f)
                      for d in os.listdir(root)
                      for f in os.listdir(os.path.join(root, d)) if f.endswith('.png')}
        # normalised Chinese -> skill-tree key that owns a sprite
        self.by_cn = {}
        for key, row in self.loc.items():
            cn = row.get('Chinese')
            if cn and key in self.icons and TREE_KEY.match(key):
                self.by_cn.setdefault(CN_SEP.sub('', cn.strip()), key)
        self._b64 = {}

    def text(self, key):
        row = self.loc.get(key)
        return (row.get('English') or '').strip() if row else None

    def skill_tree_icon(self, key):
        """Icon for a skill referenced by its numeric id, via the Chinese column.

        Skill sprites are named after the skill-*tree* key (`SX_P1_22_200`), never after
        the `200xxx` id the rest of the data uses, so a numeric reference finds nothing.
        The two keys are the same skill and their Chinese proves it -- `箭雨·狮` against
        `箭雨 狮`, identical but for the separator.

        Worth knowing *why* this is done on the Chinese: the English columns disagree.
        `200102` is "Rain of Arrows: Leonar" and `SX_P1_22_200` is "Rain of Arrows:
        Maahes" -- two transliterations of the same lion (狮), and the tree one is stale.
        Joining on English would have missed it, and reading only English led to the
        wrong conclusion that they were different skills.

        Restricted to the `200xxx` block and to tree keys as sources on purpose: that is
        175 skills matched with no ambiguity, whereas widening it to any sprite-named key
        starts mapping "Fission" onto the Multishot fatebound because both are 分裂.
        """
        if not (key.isdigit() and 200000 <= int(key) < 201000):
            return None
        cn = (self.loc.get(key, {}).get('Chinese') or '').strip()
        tree = self.by_cn.get(CN_SEP.sub('', cn)) if cn else None
        return self.icons.get(tree) if tree else None

    def icon_path(self, key, name):
        """Sprite named after the key -> item-id icon -> `ITEM_*` alias icon.

        The middle step is **known wrong** -- there is no arithmetic link between an item ID
        and its sprite number, so the 115 rows that reach it get someone else's icon. See
        icon-mapping-plan.md. It is still here because removing it would leave those rows
        blank without fixing anything; the plan replaces it with a frozen, eye-checked map.
        The order is harmless in practice: no item resolves under both rules (checked, 0 of
        806), so the reliable alias rule never loses to the broken one."""
        if key in self.icons:
            return self.icons[key]
        if key.isdigit() and 100000 <= int(key) < 110000:
            direct = f'ItemIcon_{(int(key) - 100000) * 1000}'
            if direct in self.icons:
                return self.icons[direct]
        for alias in self.by_en.get(name or '', ()):
            if alias.startswith('ITEM_'):
                path = self.icons.get('ItemIcon_' + alias[len('ITEM_'):])
                if path:
                    return path
        return self.skill_tree_icon(key)

    def data_uri(self, path):
        if path not in self._b64:
            with open(path, 'rb') as fh:
                self._b64[path] = 'data:image/png;base64,' + base64.b64encode(fh.read()).decode()
        return self._b64[path]

    def resolve(self, entry):
        """One `{key, desc_key, ...}` entry -> name, description and icon data-URI."""
        key = entry.get('key')
        if not key:
            return {'name': None, 'desc': None, 'icon': None}
        name = self.text(key)
        desc = None
        for candidate in (entry.get('desc_key'), key + '_D'):
            if candidate:
                desc = self.text(candidate)
                if desc:
                    break
        if not desc:
            desc = (self.numeric.get(key) or {}).get('description') or None
        if not desc:
            desc = self.effects.get(key) or None
        path = self.icon_path(key, name)
        return {'name': name, 'desc': desc,
                'icon': self.data_uri(path) if path else None,
                'icon_name': os.path.basename(path) if path else None}


# --------------------------------------------------------------------------- text


def rich(text, glossary):
    """Game markup and guide markup -> HTML.

    `<color=#RRGGBBAA>` is Unity's rich text. `{0}` is a value the game fills in from the
    encrypted config tables, so it can only be shown as an unknown. `$token$` is a
    glossary reference whose term table is also encrypted -- `glossary` in the guide file
    supplies the ones that could be recovered from context."""
    if not text:
        return ''
    out = html.escape(text)
    out = COLOR_TAG.sub(r'<span style="color:#\1">\2</span>', out)
    out = SLOT_TAG.sub('<span class="unk" title="value lives in the encrypted config">?</span>', out)
    out = TERM_TAG.sub(
        lambda m: (f'<span class="term">{html.escape(glossary[m.group(1)])}</span>'
                   if m.group(1) in glossary
                   else f'<span class="term term-unknown" title="glossary term not recovered">'
                        f'{html.escape(m.group(1))}</span>'), out)
    out = BOLD_TAG.sub(r'<strong>\1</strong>', out)
    out = CODE_TAG.sub(r'<code>\1</code>', out)
    return out.replace('\n', '<br>')


# --------------------------------------------------------------------------- render


class Renderer:
    def __init__(self, data, guide):
        self.d = data
        self.g = guide
        self.glossary = guide.get('glossary', {})
        self.unresolved = []
        self.no_icon = []

    def rt(self, text):
        return rich(text, self.glossary)

    def card(self, entry, kind, rank=None):
        r = self.d.resolve(entry)
        shown = entry.get('as_written')
        if entry.get('key') and not r['name']:
            self.unresolved.append(f"{entry['key']} (key not in localization)")
        if not entry.get('key'):
            self.unresolved.append(f"{shown or '?'} (no key in guide file)")
        elif not r['icon']:
            self.no_icon.append(f"{r['name'] or entry['key']}")

        name = r['name'] or shown or 'Unknown'
        icon = (f'<img class="ic" src="{r["icon"]}" alt="">' if r['icon']
                else '<span class="ic-missing" title="icon not shipped in this APK"></span>')
        slot = entry.get('slot')
        slot_uri = None
        if slot and SLOT_ICON.get(slot) in self.d.icons:
            slot_uri = self.d.data_uri(self.d.icons[SLOT_ICON[slot]])

        bits = [f'<div class="card {kind}{" featured" if entry.get("featured") else ""}">']
        bits.append('<div class="card-head">')
        bits.append(f'<div class="ic-wrap">{icon}</div>')
        bits.append('<div class="card-title">')
        bits.append(f'<h4>{html.escape(name)}</h4>')
        meta = []
        if slot:
            pip = f'<img class="pip" src="{slot_uri}" alt="">' if slot_uri else ''
            meta.append(f'<span class="slot">{pip}{html.escape(slot)}</span>')
        if rank:
            meta.append(f'<span class="rank">{rank}</span>')
        if entry.get('calamity'):
            meta.append('<span class="cal">Calamity</span>')
        if shown and r['name'] and shown.lower() != r['name'].lower():
            meta.append(f'<span class="aka">guide calls it &ldquo;{html.escape(shown)}&rdquo;</span>')
        if meta:
            bits.append(f'<div class="meta">{"".join(meta)}</div>')
        bits.append('</div></div>')
        if r['desc']:
            bits.append(f'<p class="desc">{self.rt(r["desc"])}</p>')
        if entry.get('note'):
            bits.append(f'<p class="note">{self.rt(entry["note"])}</p>')
        bits.append('</div>')
        return ''.join(bits)

    def block(self, b):
        kind = b['type']
        head = f'<h3>{html.escape(b["title"])}</h3>' if b.get('title') else ''
        if kind == 'prose':
            return f'{head}<p class="prose">{self.rt(b["text"])}</p>'
        if kind == 'callout':
            return (f'<div class="callout {b.get("tone", "tip")}">'
                    f'<p>{self.rt(b["text"])}</p></div>')
        if kind == 'steps':
            rows = []
            for i, step in enumerate(b['items'], 1):
                extra = ''
                if step.get('key'):
                    name = self.d.text(step['key'])
                    if not name:
                        self.unresolved.append(f"{step['key']} (step reference)")
                    elif name.lower() not in step['text'].lower():
                        # The prose usually names the place already; only add the chip when
                        # the in-game name differs from what the guide wrote.
                        extra = f'<span class="chip">{html.escape(name)}</span>'
                rows.append(f'<li><span class="n">{i}</span>'
                            f'<span class="t">{self.rt(step["text"])}{extra}</span></li>')
            return f'{head}<ol class="steps">{"".join(rows)}</ol>'
        if kind == 'cards':
            # Kuma's lists are ranked best-first within a slot, which is invisible once the
            # entries are laid out as a grid -- so number them where a slot repeats.
            counts = collections.Counter(e.get('slot') for e in b['items'] if e.get('slot'))
            seen = collections.Counter()
            cards = []
            for e in b['items']:
                slot, rank = e.get('slot'), None
                if slot and counts[slot] > 1:
                    seen[slot] += 1
                    rank = ORDINALS[min(seen[slot], len(ORDINALS)) - 1]
                cards.append(self.card(e, b['kind'], rank))
            cards = ''.join(cards)
            foot = (f'<p class="foot">{self.rt(b["footnote"])}</p>' if b.get('footnote') else '')
            return f'{head}<div class="grid">{cards}</div>{foot}'
        raise ValueError(f'unknown block type {kind!r}')

    def render(self):
        g = self.g
        cls = self.d.text(g['class_key']) or 'Ranger'
        nav = ''.join(f'<a href="#{s["id"]}">{html.escape(s["title"].split("—")[0].strip())}</a>'
                      for s in g['sections'])
        secs = []
        for s in g['sections']:
            body = ''.join(self.block(b) for b in s['blocks'])
            secs.append(
                f'<section id="{s["id"]}"><div class="sec-head">'
                f'<h2>{html.escape(s["title"])}</h2>'
                f'<span class="tag">{html.escape(s.get("tag", ""))}</span></div>{body}</section>')
        tldr = ''.join(f'<li>{self.rt(x)}</li>' for x in g.get('tldr', []))
        src = g['source']
        return PAGE.format(
            page_title=html.escape(g.get('page_title', g['title'])),
            title=html.escape(g['title']),
            cls=html.escape(cls),
            subtitle=html.escape(g['subtitle']),
            nav=nav,
            tldr=tldr,
            reading_note=self.rt(g.get('reading_note', '')),
            sections=''.join(secs),
            limits=self.rt(g['limits']),
            author=html.escape(src['author']),
            posted=html.escape(src['posted']),
            src_note=self.rt(src['note']),
            legendary=RARITY[4][1], insane=RARITY[5][1], epic=RARITY[3][1],
            rare=RARITY[2][1], charmed=RARITY[1][1])


# The page is emitted as a fragment -- `<title>`, `<style>`, then content -- because that
# is what the artifact host wants; `STANDALONE` wraps it into a real document for the copy
# that lives in the repo and opens by double-click.

PAGE = """<title>{page_title}</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?\
family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&\
family=IBM+Plex+Mono:wght@500;600&\
family=IBM+Plex+Sans:ital,wght@0,400;0,600;1,400&display=swap">
<style>
/* Committed to one dark world on purpose: these are the game's own UI colours, and the
   icons are pixel sprites drawn to sit on a dark ground. Every colour is painted
   explicitly so the page holds whatever theme the host is in. */
:root {{
  --bg:#14151c; --panel:#1c1e28; --panel2:#242734; --line:#31364a;
  --fg:#e8eaf2; --dim:#99a0b8; --faint:#6b7288;
  --legendary:{legendary}; --insane:{insane}; --epic:{epic};
  --rare:{rare}; --charmed:{charmed};
  --display:"Bricolage Grotesque","Trebuchet MS",system-ui,sans-serif;
  --body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Consolas,monospace;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--bg); color:var(--fg);
  font:400 16px/1.65 var(--body); -webkit-font-smoothing:antialiased;
}}
img {{ image-rendering:pixelated; max-width:100%; }}
h1,h2,h3,h4 {{ font-family:var(--display); text-wrap:balance; }}
a:focus-visible, [tabindex]:focus-visible {{
  outline:2px solid var(--legendary); outline-offset:3px; border-radius:4px;
}}
.wrap {{ max-width:1060px; margin:0 auto; padding-inline:16px; padding-block:0 96px; }}

header {{ padding-block:56px 30px; border-bottom:1px solid var(--line); }}
.kicker {{
  font-family:var(--mono); color:var(--legendary); font-size:12px; font-weight:600;
  letter-spacing:.18em; text-transform:uppercase;
}}
h1 {{ margin:10px 0 6px; font-size:clamp(32px,6vw,54px); font-weight:800; line-height:1.03;
     letter-spacing:-.02em; }}
.sub {{ color:var(--dim); margin:0 0 22px; font-size:18px; }}
.byline {{ color:var(--faint); font-size:14px; max-width:68ch; }}
.byline b {{ color:var(--dim); font-weight:600; }}

nav {{
  position:sticky; top:env(safe-area-inset-top, 0px); z-index:10;
  display:flex; gap:4px; flex-wrap:wrap; padding-block:10px;
  background:rgba(20,21,28,.93); backdrop-filter:blur(10px);
  border-bottom:1px solid var(--line); margin-bottom:38px;
}}
nav a {{
  font-family:var(--mono); color:var(--dim); text-decoration:none; font-size:13px;
  font-weight:600; padding:6px 13px; border-radius:99px; white-space:nowrap;
}}
nav a:hover {{ color:var(--bg); background:var(--legendary); }}

section {{ margin-bottom:60px; scroll-margin-top:72px; }}
.sec-head {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:16px; }}
h2 {{ font-size:clamp(22px,3.4vw,30px); font-weight:800; margin:0; letter-spacing:-.015em; }}
h3 {{
  font-family:var(--mono); font-size:12px; font-weight:600; text-transform:uppercase;
  letter-spacing:.14em; color:var(--faint); margin:36px 0 14px;
}}
.tag {{
  font-family:var(--mono); font-size:11px; font-weight:600; color:var(--bg);
  background:var(--legendary); padding:3px 10px; border-radius:99px;
  letter-spacing:.04em; white-space:nowrap;
}}
.prose {{ color:#cbd0e0; max-width:68ch; }}

.tldr {{
  background:var(--panel); border:1px solid var(--line); border-left:3px solid var(--legendary);
  border-radius:12px; padding:20px 24px; margin:28px 0 14px;
}}
.tldr h3 {{ margin:0 0 10px; color:var(--legendary); }}
.tldr ul {{ margin:0; padding-left:20px; }}
.tldr li {{ margin:6px 0; color:#cbd0e0; }}
.readnote {{
  color:var(--dim); font-size:15px; background:var(--panel2); border-radius:12px;
  padding:15px 20px; margin:0 0 10px; max-width:78ch;
}}
code {{ font-family:var(--mono); font-size:.87em; color:var(--charmed);
       background:var(--panel2); padding:1px 5px; border-radius:4px; }}

.steps {{ list-style:none; padding:0; margin:0 0 10px; max-width:76ch;
         display:flex; flex-direction:column; }}
.steps li {{ display:flex; gap:15px; padding-block:10px; border-bottom:1px solid var(--line); }}
.steps li:last-child {{ border-bottom:0; }}
.steps .n {{
  flex:0 0 26px; height:26px; border-radius:50%; background:var(--panel2);
  color:var(--legendary); font-family:var(--mono); font-size:12px; font-weight:600;
  display:flex; align-items:center; justify-content:center;
}}
.chip {{
  display:inline-block; margin-left:8px; padding:1px 9px; border-radius:99px;
  background:var(--panel2); color:var(--rare); font-size:13px; font-weight:600;
}}

.grid {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fill,minmax(296px,1fr)); }}
.card {{
  background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:15px;
  display:flex; flex-direction:column; gap:10px;
}}
/* Border, not a badge: the left rail says which system the thing belongs to. */
.card.equipment {{ border-left:3px solid var(--legendary); }}
.card.fatebound {{ border-left:3px solid var(--rare); }}
.card.skill {{ border-left:3px solid var(--epic); }}
.card.incarnate {{ border-left:3px solid var(--insane); }}
.card.featured {{ background:var(--panel2); border-color:var(--legendary); }}
.card-head {{ display:flex; gap:13px; align-items:flex-start; }}
.ic-wrap {{
  flex:0 0 54px; width:54px; height:54px; border-radius:10px; background:var(--bg);
  display:flex; align-items:center; justify-content:center; overflow:hidden;
}}
.ic {{ width:46px; height:46px; object-fit:contain; }}
.ic-missing {{ width:28px; height:28px; border:2px dashed var(--line); border-radius:6px; }}
.card-title {{ flex:1; min-width:0; }}
.card h4 {{ margin:0; font-size:17px; font-weight:600; line-height:1.25; }}
.meta {{ display:flex; gap:6px; flex-wrap:wrap; margin-top:6px; align-items:center; }}
.meta span {{ font-size:12px; color:var(--faint); }}
.slot {{ display:inline-flex; align-items:center; gap:5px; background:var(--panel2);
        padding:2px 9px; border-radius:99px; }}
.pip {{ width:13px; height:13px; }}
.cal, .rank {{
  font-family:var(--mono); font-size:11px!important; font-weight:600;
  padding:2px 9px; border-radius:99px; letter-spacing:.06em; text-transform:uppercase;
}}
.cal {{ background:rgba(232,80,72,.16); color:var(--insane)!important; }}
.rank {{ background:rgba(250,170,63,.15); color:var(--legendary)!important; }}
.aka {{ font-style:italic; }}
.desc {{ margin:0; font-size:14.5px; color:#bfc5d6; }}
.note {{
  margin:0; font-size:14px; color:var(--dim);
  border-top:1px dashed var(--line); padding-top:10px;
}}
.foot {{ color:var(--faint); font-size:13px; margin-top:12px; max-width:68ch; }}
.unk {{
  display:inline-block; min-width:17px; text-align:center; background:var(--panel2);
  color:var(--faint); border-radius:4px; font-family:var(--mono); font-size:12px;
  padding:0 4px; cursor:help;
}}
.term {{ color:var(--charmed); font-weight:600; }}
.term-unknown {{ color:var(--faint); font-style:italic; cursor:help; }}

.callout {{
  border-radius:12px; padding:14px 18px; margin:20px 0; font-size:15px;
  border:1px solid var(--line); background:var(--panel); max-width:78ch;
}}
.callout p {{ margin:0; }}
.callout.tip {{ border-left:3px solid var(--rare); }}
.callout.warn {{ border-left:3px solid var(--legendary); }}
.callout.ok {{ border-left:3px solid var(--charmed); }}

footer {{ border-top:1px solid var(--line); padding-top:26px; color:var(--faint);
         font-size:14px; max-width:72ch; }}
footer h3 {{ margin-top:0; }}
footer code {{ font-family:var(--mono); font-size:13px; color:var(--dim); }}

@media (max-width:560px) {{
  .grid {{ grid-template-columns:1fr; }}
  header {{ padding-block:34px 24px; }}
}}
@media (prefers-reduced-motion:reduce) {{
  * {{ animation:none!important; transition:none!important; }}
}}
</style>

<div class="wrap">
<header>
  <div class="kicker">{cls} &middot; Soul Knight Prequel</div>
  <h1>{title}</h1>
  <p class="sub">{subtitle}</p>
  <p class="byline">Written by <b>{author}</b>, {posted}. {src_note}</p>
</header>
<nav>{nav}</nav>

<div class="tldr"><h3>The short version</h3><ul>{tldr}</ul></div>
<p class="readnote">{reading_note}</p>

{sections}

<footer>
  <h3>About the numbers</h3>
  <p>{limits}</p>
</footer>
</div>
"""

STANDALONE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
{fragment}</body>
</html>
"""


# --------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--guide', default='guide/ranger.json')
    ap.add_argument('--out', default='extracted', help='directory holding the extracted JSON')
    ap.add_argument('-o', '--output', default='range-guide.html')
    ap.add_argument('--fragment',
                    help='also write the bare title+style+content form, for publishing')
    args = ap.parse_args()

    if not os.path.isdir(args.out):
        sys.exit(f'missing {args.out} -- run the extraction pipeline first')
    data = Data(args.out)
    guide = json.load(open(args.guide, encoding='utf8'))
    renderer = Renderer(data, guide)
    fragment = renderer.render()
    head, _, rest = fragment.partition('</style>\n')
    page = STANDALONE.format(fragment=f'{head}</style>\n</head>\n<body>\n{rest}')

    written = [(args.output, page)]
    if args.fragment:
        written.append((args.fragment, fragment))
    for path, text in written:
        with open(path, 'w', encoding='utf8') as fh:
            fh.write(text)
        print(f'{path}: {len(text) / 1024:.0f} KB')

    print(f'{page.count("data:image/png;base64,")} inlined icons '
          f'({len(data._b64)} distinct)')
    for label, rows in (('with no icon shipped', renderer.no_icon),
                        ('unresolved', renderer.unresolved)):
        if rows:
            names = sorted(set(rows))
            print(f'  {len(names)} {label}: {", ".join(names)}')
    if 'src=""' in page:
        sys.exit('ERROR: empty img src in output')


if __name__ == '__main__':
    main()
