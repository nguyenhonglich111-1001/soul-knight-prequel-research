"""range-guide.html -> a set of PNGs sized for posting to Discord.

One full-page screenshot of the guide is ~10,000 px tall, and Discord shrinks and
re-compresses anything that size until the text is unreadable -- even the "original" you
download back from the message. So the page is cut into pieces no taller than `--max`
CSS px each, rendered at 2x, and the cuts fall only *between* elements: a section is
split into its blocks, a block that is still too tall into its children (gear rows, cards),
and those are packed back together top to bottom. A heading is never left at the bottom
of a piece without the thing it heads.

Uses the Edge that ships with Windows through Playwright (`pip install playwright`, no
browser download needed). Writes both layouts by default:

    python tools/export_guide_png.py                    # desktop + phone
    python tools/export_guide_png.py --layout phone
"""

import argparse
import os
import shutil

from playwright.sync_api import sync_playwright

LAYOUTS = {'desktop': 1100, 'phone': 430}

# Runs in the page. Returns [{group, top, bottom, heading}] -- vertical bands that may be
# cut between, in document order.
UNITS_JS = r"""
(limit) => {
  document.querySelector('nav')?.remove();
  const groups = [
    ['intro', ['header', '.tldr', '.readnote']],
    ...[...document.querySelectorAll('section')].map(s => [s.id, [s]]),
    ['notes', ['footer']],
  ];
  const isHead = el => /^H[1-4]$/.test(el.tagName) || el.classList.contains('sec-head');
  const out = [];
  const walk = (el, group) => {
    const r = el.getBoundingClientRect();
    const kids = [...el.children].filter(k => k.getBoundingClientRect().height > 0);
    if (r.height > limit && kids.length > 1) { kids.forEach(k => walk(k, group)); return; }
    out.push({group, top: r.top + scrollY, bottom: r.bottom + scrollY, heading: isHead(el)});
  };
  for (const [name, sels] of groups)
    for (const s of sels) {
      const el = typeof s === 'string' ? document.querySelector(s) : s;
      if (el) walk(el, name);
    }
  return out;
}
"""


def bands(units):
    """Merge units that overlap vertically (cards side by side in one grid row)."""
    merged = []
    for u in sorted(units, key=lambda u: u['top']):
        if merged and u['top'] < merged[-1]['bottom'] - 1:
            m = merged[-1]
            m['bottom'] = max(m['bottom'], u['bottom'])
            m['heading'] = m['heading'] and u['heading']
        else:
            merged.append(dict(u))
    return merged


def pack(units, limit):
    """Consecutive bands -> pieces no taller than `limit`, never ending on a heading."""
    pieces, cur = [], []
    for b in units:
        if cur and b['bottom'] - cur[0]['top'] > limit:
            carry = []
            while cur and cur[-1]['heading']:
                carry.insert(0, cur.pop())
            if cur:
                pieces.append(cur)
            cur = carry
        cur.append(b)
    if cur:
        pieces.append(cur)
    return pieces


def export(page, html_path, layout, width, limit, out_dir):
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto('file:///' + os.path.abspath(html_path).replace(os.sep, '/'))
    page.wait_for_load_state('networkidle')
    page.evaluate('document.fonts.ready')
    units = page.evaluate(UNITS_JS, limit)
    folder = os.path.join(out_dir, layout)
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    n, pad = 0, 20
    edges = sorted(e for u in units for e in (u['top'], u['bottom']))
    for group in dict.fromkeys(u['group'] for u in units):
        pieces = pack(bands([u for u in units if u['group'] == group]), limit)
        for i, p in enumerate(pieces):
            n += 1
            # Pad into the gap around the piece, but never past a neighbouring element --
            # otherwise the next card's border shows as a sliver along the edge.
            above = max([e for e in edges if e < p[0]['top'] - 0.5] or [0])
            below = min([e for e in edges if e > p[-1]['bottom'] + 0.5] or [float('inf')])
            top = max(0, p[0]['top'] - pad, above + 3)
            bottom = min(p[-1]['bottom'] + pad, below - 3)
            suffix = f'_{chr(97 + i)}' if len(pieces) > 1 else ''
            path = os.path.join(folder, f'{n:02d}_{group}{suffix}.png')
            page.screenshot(
                path=path,
                full_page=True,
                clip={'x': 0, 'y': top, 'width': width, 'height': bottom - top},
            )
            print(f'  {path}  {width * 2}x{round((bottom - top) * 2)}')
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--html', default='range-guide.html')
    ap.add_argument('--out', default=os.path.join('extracted', '_sheets', 'guide_png'))
    ap.add_argument('--layout', choices=[*LAYOUTS, 'both'], default='both')
    ap.add_argument('--max', type=int, default=1400, help='max piece height, CSS px')
    a = ap.parse_args()
    layouts = LAYOUTS if a.layout == 'both' else {a.layout: LAYOUTS[a.layout]}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge')
        for name, width in layouts.items():
            page = browser.new_page(device_scale_factor=2)
            print(f'{name} ({width}px wide, 2x):')
            print(f'  {export(page, a.html, name, width, a.max, a.out)} images')
            page.close()
        browser.close()


if __name__ == '__main__':
    main()
