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

import versions

# The game's own rarity palette, from the `ITEM_RATE_*` strings.
RARITY = {
    0: ('Common', '#F5F5F5'),
    1: ('Charmed', '#61E382'),
    2: ('Rare', '#3FBBEC'),
    3: ('Epic', '#8E2AC1'),
    4: ('Legendary', '#FAAA3F'),
    5: ('Insane', '#E85048'),
}

ORDINALS = ['best', '2nd', '3rd', '4th', '5th']

SLOT_ICON = {
    'Weapon': 'icn_equip_weapon',
    'Helmet': 'icn_equip_helmet',
    'Armor': 'icn_equip_armor',
    'Boots': 'icn_equip_shoes',
    'Ring': 'icn_equip_ring',
    'Necklace': 'icn_equip_necklace',
    # The game's own labels: Const_ItemType_CHARMS1 is "Mech Core" (机核) and
    # CHARMS2 is "Cubis Core" (魔核). These were the wrong way round.
    'Cubis core': 'icn_equip_charms2',
    'Mech gear': 'icn_equip_charms1',
}

# Unity rich text, matched *after* html.escape has turned its angle brackets into entities.
COLOR_TAG = re.compile(
    r'&lt;color=#([0-9A-Fa-f]{6})[0-9A-Fa-f]{0,2}&gt;(.*?)&lt;/color&gt;', re.DOTALL
)
TERM_TAG = re.compile(r'\$([A-Za-z0-9_]+)\$')
SLOT_TAG = re.compile(r'\{(\d+)\}')
BOLD_TAG = re.compile(r'\*\*(.+?)\*\*')
CODE_TAG = re.compile(r'`([^`]+)`')
EMPH_TAG = re.compile(r'\*([^*]+)\*')  # the game's own emphasis: *Deadlock*

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
        self.numeric = {
            str(r['id']): r
            for r in json.load(open(os.path.join(out, 'items_numeric.json'), encoding='utf8'))
        }
        # Legendary effect text, keyed by item id. `build_equipment.effect_key()` derives
        # it from the item's skill prefab; it is the only description equipment has.
        eq = os.path.join(out, 'equipment.json')
        eq = json.load(open(eq, encoding='utf8')) if os.path.exists(eq) else []
        self.effects = {str(r['id']): r['effect'] for r in eq}
        # Lv.1 `{n}` values read off the codex, positional: [v0, v1, ...] fills {0}, {1}, ...
        self.effect_values = {
            str(r['id']): r['effect_values_lv1'] for r in eq if r.get('effect_values_lv1')
        }
        # effect_map.json also holds items only known by their `ITEM_*` key (Bishop's
        # Biretta), which have no numeric equipment row for build_equipment.py to fill.
        emap = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'guide', 'effect_map.json'
        )
        if os.path.exists(emap):
            for k, v in json.load(open(emap, encoding='utf8'))['confirmed'].items():
                text = (self.loc.get(v['key']) or {}).get('English')
                if text and k not in self.effects:
                    self.effects[k] = text
                if v.get('lv1') and k not in self.effect_values:
                    self.effect_values[k] = v['lv1']
        # Equipment icons as build_equipment.py settled them: guide/icon_map.json (checked
        # in game, or derived from checked pairs) before the `ITEM_*` alias rule.
        self.equip_icons = {
            str(r['id']): os.path.join(out, 'icons', r['icon']) for r in eq if r['icon']
        }
        self.by_en = collections.defaultdict(list)
        for key, row in self.loc.items():
            en = row.get('English')
            if en:
                self.by_en[en].append(key)
        root = os.path.join(out, 'icons')
        self.icons = {
            f[:-4]: os.path.join(root, d, f)
            for d in os.listdir(root)
            for f in os.listdir(os.path.join(root, d))
            if f.endswith('.png')
        }
        # normalised Chinese -> skill-tree key that owns a sprite
        self.by_cn = {}
        for key, row in self.loc.items():
            cn = row.get('Chinese')
            if cn and key in self.icons and TREE_KEY.match(key):
                self.by_cn.setdefault(CN_SEP.sub('', cn.strip()), key)
        # Hand-checked key -> sprite pairs for things whose sprite is not named after
        # their key (Axial Incarnate pieces are `Incarnation_NN`). See docs/icons.md.
        imap = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'guide', 'icon_map.json'
        )
        imap = json.load(open(imap, encoding='utf8')) if os.path.exists(imap) else {}
        self.mapped_icons = {
            k: self.icons[v['icon']]
            for part in ('confirmed', 'derived')
            for k, v in imap.get(part, {}).items()
            if v['icon'] in self.icons
        }
        # `$token$` -> the keyword's in-game name and rules text (tools/build_glossary.py).
        gl = os.path.join(out, 'glossary.json')
        gl = json.load(open(gl, encoding='utf8'))['glossary'] if os.path.exists(gl) else {}
        self.terms = {
            t: {'name': g['name'], 'description': g['description']} for t, g in gl.items()
        }
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
        """Sprite named after the key -> equipment.json's icon -> `ITEM_*` alias icon.

        Never computes a sprite name from an item ID: there is no arithmetic link between
        the two (`103467` is `ItemIcon_3470000`). An item with no checked icon gets the
        placeholder, which is the point -- a wrong icon is worse than none. See
        docs/icons.md."""
        if key in self.icons:
            return self.icons[key]
        if key in self.equip_icons:
            return self.equip_icons[key]
        if key in self.mapped_icons:
            return self.mapped_icons[key]
        for alias in self.by_en.get(name or '', ()):
            if alias.startswith('ITEM_'):
                path = self.icons.get('ItemIcon_' + alias[len('ITEM_') :])
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
        values = None
        if not desc:
            desc = self.effects.get(key) or None
            if desc and self.effect_values.get(key):
                values = {
                    str(i): (f'{v:g}' if isinstance(v, (int, float)) else v)
                    for i, v in enumerate(self.effect_values[key])
                }
        path = self.icon_path(key, name)
        return {
            'name': name,
            'desc': desc,
            'values': values,
            'icon': self.data_uri(path) if path else None,
            'icon_name': os.path.basename(path) if path else None,
        }


# --------------------------------------------------------------------------- text


def term_html(token, glossary):
    """A `$token$` as its keyword, with the keyword's rules text as a hover/tap tooltip.

    `glossary[token]` is `{name, description}` (from glossary.json) or a bare name."""
    entry = glossary.get(token)
    if entry is None:
        return (
            f'<span class="term term-unknown" title="glossary term not recovered">'
            f'{html.escape(token)}</span>'
        )
    if isinstance(entry, str):
        return f'<span class="term">{html.escape(entry)}</span>'
    name = html.escape(entry['name'])
    if not entry.get('description'):
        return f'<span class="term">{name}</span>'
    desc = html.escape(entry['description'])
    desc = SLOT_TAG.sub('<span class="unk">?</span>', desc)
    desc = EMPH_TAG.sub(r'<em>\1</em>', desc).replace('\n', '<br>')
    return (
        f'<span class="term has-tip" tabindex="0">{name}'
        f'<span class="tip" role="tooltip"><b>{name}</b>{desc}</span></span>'
    )


def rich(text, glossary, values=None):
    """Game markup and guide markup -> HTML.

    `<color=#RRGGBBAA>` is Unity's rich text. `{0}` is a value the game fills in from the
    encrypted config tables, so it can only be shown as an unknown. `$token$` is a
    glossary keyword, shown by `term_html()` with its rules text as a tooltip. `values`
    fills `{n}` with what an in-game screenshot showed, where the guide file records it."""
    if not text:
        return ''
    out = html.escape(text)
    out = COLOR_TAG.sub(r'<span style="color:#\1">\2</span>', out)
    values = values or {}
    out = SLOT_TAG.sub(
        lambda m: (
            f'<span class="val" title="read off an in-game screenshot">'
            f'{html.escape(str(values[m.group(1)]))}</span>'
            if m.group(1) in values
            else '<span class="unk" title="value lives in the encrypted config">?</span>'
        ),
        out,
    )
    out = TERM_TAG.sub(lambda m: term_html(m.group(1), glossary), out)
    out = BOLD_TAG.sub(r'<strong>\1</strong>', out)
    out = CODE_TAG.sub(r'<code>\1</code>', out)
    return out.replace('\n', '<br>')


# --------------------------------------------------------------------------- render


class Renderer:
    def __init__(self, data, guide):
        self.d = data
        self.g = guide
        # The game's keyword names and rules text; the guide's hand-made glossary only fills
        # tokens the game data does not resolve.
        self.glossary = {**guide.get('glossary', {}), **data.terms}
        self.unresolved = []
        self.no_icon = []

    def rt(self, text, values=None):
        return rich(text, self.glossary, values)

    def pieces(self, entries):
        """A row of small icon + name tiles, e.g. an Axial Incarnate's three slots."""
        tiles = []
        for e in entries:
            r = self.d.resolve(e)
            if not r['icon']:
                self.no_icon.append(r['name'] or e['key'])
            name = r['name'] or e['key']
            # "Lamian: Ghastly Malocchio" -> "Ghastly Malocchio"; the card already names Lamian.
            short = name.split(':', 1)[1].strip() if ':' in name else name
            icon = (
                f'<img class="ic" src="{r["icon"]}" alt="">'
                if r['icon']
                else '<span class="ic-missing" title="icon not shipped in this APK"></span>'
            )
            slot = (
                f'<span class="piece-slot">{html.escape(e["slot"])}</span>' if e.get('slot') else ''
            )
            tiles.append(
                f'<div class="piece">{icon}<span class="piece-name">'
                f'{html.escape(short)}</span>{slot}</div>'
            )
        return f'<div class="pieces">{"".join(tiles)}</div>'

    def card(self, entry, kind, rank=None, show_slot=True):
        r = self.d.resolve(entry)
        shown = entry.get('as_written')
        if entry.get('key') and not r['name']:
            self.unresolved.append(f'{entry["key"]} (key not in localization)')
        if not entry.get('key'):
            self.unresolved.append(f'{shown or "?"} (no key in guide file)')
        elif not r['icon']:
            self.no_icon.append(f'{r["name"] or entry["key"]}')

        name = r['name'] or shown or 'Unknown'
        icon = (
            f'<img class="ic" src="{r["icon"]}" alt="">'
            if r['icon']
            else '<span class="ic-missing" title="icon not shipped in this APK"></span>'
        )
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
        if slot and show_slot:
            pip = f'<img class="pip" src="{slot_uri}" alt="">' if slot_uri else ''
            meta.append(f'<span class="slot">{pip}{html.escape(slot)}</span>')
        if rank:
            meta.append(f'<span class="rank">{rank}</span>')
        if entry.get('calamity'):
            meta.append('<span class="cal">Calamity</span>')
        if meta:
            bits.append(f'<div class="meta">{"".join(meta)}</div>')
        bits.append('</div></div>')
        if r['desc']:
            bits.append(
                f'<p class="desc">{self.rt(r["desc"], entry.get("values") or r["values"])}</p>'
            )
        if entry.get('pieces'):
            bits.append(self.pieces(entry['pieces']))
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
            return f'<div class="callout {b.get("tone", "tip")}"><p>{self.rt(b["text"])}</p></div>'
        if kind == 'steps':
            rows = []
            for i, step in enumerate(b['items'], 1):
                extra = ''
                if step.get('key'):
                    name = self.d.text(step['key'])
                    if not name:
                        self.unresolved.append(f'{step["key"]} (step reference)')
                    elif name.lower() not in step['text'].lower():
                        # The prose usually names the place already; only add the chip when
                        # the in-game name differs from what the guide wrote.
                        extra = f'<span class="chip">{html.escape(name)}</span>'
                rows.append(
                    f'<li><span class="n">{i}</span>'
                    f'<span class="t">{self.rt(step["text"])}{extra}</span></li>'
                )
            return f'{head}<ol class="steps">{"".join(rows)}</ol>'
        if kind == 'cards':
            # Kuma's lists are ranked best-first within a slot, which is invisible once the
            # entries are laid out as a grid -- so number them where a slot repeats.
            counts = collections.Counter(e.get('slot') for e in b['items'] if e.get('slot'))
            seen = collections.Counter()
            cards = []
            rows = {}  # slot -> [card html], in first-seen order
            for e in b['items']:
                slot, rank = e.get('slot'), None
                if slot and counts[slot] > 1 and b.get('ranked', True):
                    seen[slot] += 1
                    rank = ORDINALS[min(seen[slot], len(ORDINALS)) - 1]
                if b.get('by_slot') and slot:
                    rows.setdefault(slot, []).append(self.card(e, b['kind'], rank, show_slot=False))
                else:
                    cards.append(self.card(e, b['kind'], rank))
            foot = f'<p class="foot">{self.rt(b["footnote"])}</p>' if b.get('footnote') else ''
            if rows:
                # One line per slot, best pick leftmost, so the ranking reads left to right.
                lines = []
                for slot, row in rows.items():
                    pip = (
                        f'<img class="pip" src="{self.d.data_uri(self.d.icons[SLOT_ICON[slot]])}" alt="">'
                        if SLOT_ICON.get(slot) in self.d.icons
                        else ''
                    )
                    lines.append(
                        f'<div class="slotrow"><div class="slotlabel">{pip}'
                        f'{html.escape(slot)}</div><div class="rowcards">{"".join(row)}</div></div>'
                    )
                return f'{head}<div class="slotrows">{"".join(lines)}</div>{foot}'
            return f'{head}<div class="grid">{"".join(cards)}</div>{foot}'
        raise ValueError(f'unknown block type {kind!r}')

    def render(self):
        g = self.g
        cls = g.get('kicker') or self.d.text(g.get('class_key', '')) or 'Ranger'
        nav = ''.join(
            f'<a href="#{s["id"]}">{html.escape(s["title"].split("—")[0].strip())}</a>'
            for s in g['sections']
        )
        secs = []
        for s in g['sections']:
            body = ''.join(self.block(b) for b in s['blocks'])
            secs.append(
                f'<section id="{s["id"]}"><div class="sec-head">'
                f'<h2>{html.escape(s["title"])}</h2>'
                f'<span class="tag">{html.escape(s.get("tag", ""))}</span></div>{body}</section>'
            )
        tldr = ''.join(f'<li>{self.rt(x)}</li>' for x in g.get('tldr', []))
        src = g.get('source')
        byline = (
            f'Written by <b>{html.escape(src["author"])}</b>, {html.escape(src["posted"])}. '
            f'{self.rt(src["note"])}'
            if src
            else self.rt(g.get('byline', ''))
        )
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
            byline=byline,
            legendary=RARITY[4][1],
            insane=RARITY[5][1],
            epic=RARITY[3][1],
            rare=RARITY[2][1],
            charmed=RARITY[1][1],
        )


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
  color-scheme:dark;
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
.slotrows {{ display:flex; flex-direction:column; gap:14px; }}
.slotrow {{ display:grid; grid-template-columns:104px 1fr; gap:12px; align-items:start; }}
.slotlabel {{
  display:flex; align-items:center; gap:7px; padding-top:18px;
  font-family:var(--mono); font-size:12px; font-weight:600; color:var(--dim);
  text-transform:uppercase; letter-spacing:.08em;
}}
.slotlabel .pip {{ width:16px; height:16px; }}
.rowcards {{ display:grid; gap:12px; grid-template-columns:repeat(3,minmax(0,1fr)); }}
@media (max-width:900px) {{
  .slotrow {{ grid-template-columns:1fr; gap:6px; }}
  .slotlabel {{ padding-top:0; }}
  .rowcards {{ grid-template-columns:1fr; }}
}}
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
.val {{ color:var(--legendary); font-weight:600; cursor:help; }}
.pieces {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }}
.piece {{
  background:var(--bg); border-radius:10px; padding:10px 6px 8px;
  display:flex; flex-direction:column; align-items:center; gap:6px; text-align:center;
}}
.piece .ic {{ width:52px; height:52px; }}
.piece-name {{ font-size:12.5px; line-height:1.25; color:#cbd0e0; }}
.piece-slot {{ font-size:11px; color:var(--faint); }}
.term {{ color:var(--charmed); font-weight:600; }}
.term-unknown {{ color:var(--faint); font-style:italic; cursor:help; }}
.has-tip {{ position:relative; cursor:help; text-decoration:underline dotted; text-underline-offset:3px; }}
.has-tip:focus {{ outline:none; }}
.tip {{
  display:none; position:absolute; left:50%; bottom:calc(100% + 8px);
  transform:translateX(calc(-50% + var(--dx, 0px)));
  width:max-content; max-width:min(300px, 78vw); z-index:20;
  background:var(--panel2); border:1px solid var(--line); border-radius:8px;
  padding:9px 11px; box-shadow:0 6px 20px rgba(0,0,0,.45);
  color:#cbd0e0; font-size:13px; font-weight:400; line-height:1.45; text-align:left;
  font-style:normal; white-space:normal;
}}
.tip b {{ display:block; color:var(--charmed); margin-bottom:3px; }}
.has-tip:hover .tip, .has-tip:focus .tip {{ display:block; }}
.tip.below {{ bottom:auto; top:calc(100% + 8px); }}

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
  <p class="byline">{byline}</p>
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
<script>
// Keep a keyword tooltip on screen: shift it sideways, or drop it below the keyword.
function placeTip(e) {{
  const term = e.target.closest && e.target.closest('.has-tip');
  if (!term) return;
  const tip = term.querySelector('.tip'), pad = 8;
  tip.style.setProperty('--dx', '0px');
  tip.classList.remove('below');
  let r = tip.getBoundingClientRect();
  if (r.top < pad) {{ tip.classList.add('below'); r = tip.getBoundingClientRect(); }}
  const dx = r.left < pad ? pad - r.left
    : r.right > innerWidth - pad ? innerWidth - pad - r.right : 0;
  tip.style.setProperty('--dx', dx + 'px');
}}
document.addEventListener('mouseover', placeTip);
document.addEventListener('focusin', placeTip);
</script>
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
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('--guide', default='guide/ranger.json')
    ap.add_argument('--out', help='extracted version folder (default: newest extracted/<version>/)')
    ap.add_argument('-o', '--output', default='range-guide.html')
    ap.add_argument(
        '--fragment', help='also write the bare title+style+content form, for publishing'
    )
    args = ap.parse_args()
    versions.resolve_out_arg(args)

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

    print(f'{page.count("data:image/png;base64,")} inlined icons ({len(data._b64)} distinct)')
    for label, rows in (
        ('with no icon shipped', renderer.no_icon),
        ('unresolved', renderer.unresolved),
    ):
        if rows:
            names = sorted(set(rows))
            print(f'  {len(names)} {label}: {", ".join(names)}')
    if 'src=""' in page:
        sys.exit('ERROR: empty img src in output')


if __name__ == '__main__':
    main()
