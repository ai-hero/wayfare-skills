#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "$ROOT/publishing" <<'PY'
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, sys.argv[1])
import artwork

WHITE = "#FFFFFF"
for fill, _ in artwork.DATA.values():
    assert artwork.ratio(fill, WHITE) >= 3, fill
for fill in artwork.TEXT.values():
    assert artwork.ratio(fill, WHITE) >= 7, fill


def ids(svg):
    return {el.get('id'): el for el in ET.fromstring(svg).iter() if el.get('id')}


svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="200pt" height="100pt">
<defs><pattern id="old"><rect fill="#e93a61" width="6" height="6"/></pattern></defs>
<g id="figure_1"><path id="bar" d="M0 0H20V20H0Z" style="fill: #f1839a"/>
<path id="legend" d="M30 0H50V20H30Z" style="fill: #f1839a"/>
<path id="retry" d="M60 0H80V20H60Z" style="fill: url(#old)"/>
<path id="grid" d="M0 50 L200 50" style="fill: none; stroke: #c6c9d0"/>
<path id="axis" d="M0 60 L200 60" style="fill: none; stroke: #7b8290"/>
<text id="label" style="fill: #666d7b; font-weight: 200">Count</text></g></svg>'''
out = artwork.recolor(svg)
by_id = ids(out)
bar = artwork.properties(by_id['bar'])
legend = artwork.properties(by_id['legend'])
assert bar['fill'] == legend['fill'] and bar['fill'].startswith('url(#book-fill-')
assert by_id['bar'].get('stroke') == '#0B0D14'
assert artwork.properties(by_id['label']) == {'fill': '#383D49', 'font-weight': '400'}
assert artwork.properties(by_id['retry'])['fill'] == '#BA1B45'
assert artwork.properties(by_id['grid'])['stroke'] == '#858B96'
assert artwork.properties(by_id['axis'])['stroke'] == '#5A6070'
assert artwork.recolor(out) == out
assert ET.fromstring(out).get(artwork.MARKER) == artwork.VERSION
try:
    artwork.recolor(out.replace(f'{artwork.MARKER}="{artwork.VERSION}"', f'{artwork.MARKER}="1"'))
    raise AssertionError('an SVG from an older palette was mapped again')
except ValueError:
    pass
assert artwork.dimensions(svg) == [200, 100]
assert artwork.dimensions('<svg width="96px" height="1in"/>') == [72, 72]

native = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
<rect fill="#0B0D14" width="100" height="100"/>
<text id="reverse" fill="#C6C9D0">Delivery</text>
<path id="edge" stroke="#C6C9D0" fill="none"/>
<text id="quiet" fill="#666D7B" font-weight="300">Proposed</text></svg>'''
by_id = ids(artwork.recolor(native))
assert by_id['reverse'].get('fill') == '#C6C9D0'
assert by_id['edge'].get('stroke') == '#666D7B'
assert by_id['quiet'].get('fill') == '#383D49'
assert by_id['quiet'].get('font-weight') == '400'
blank = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"/>'
assert artwork.recolor(blank) == blank
assert artwork.prepare({}, '/unused') == {}


def chip_before(svg, text_id):
    root = ET.fromstring(artwork.recolor(svg))
    for parent in root.iter():
        kids = list(parent)
        for i, el in enumerate(kids):
            if el.get('id') == text_id:
                return kids[i - 1] if i and kids[i - 1].tag.endswith('}rect') and not kids[i - 1].get('id') else None
    raise AssertionError(text_id)


annotated = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40">
<g id="figure_1"><path d="M 0 0 L 100 0 L 100 30 L 0 30 z" fill="#c6c9d0"/>
<text id="t" x="50" y="18" style="fill: #0b0d14; font-size: 8px; text-anchor: middle">22.7%</text></g></svg>'''
chip = chip_before(annotated, 't')
assert chip is not None and chip.get('fill') == '#FFFFFF'

solid = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40">
<g id="figure_1"><rect x="0" y="0" width="100" height="30" fill="#e93a61"/>
<text id="dark" x="10" y="18" style="fill: #383d49; font-size: 8px">12</text>
<text id="white" x="60" y="18" style="fill: #ffffff; font-size: 8px">34</text></g></svg>'''
assert chip_before(solid, 'dark').get('fill') == '#FFFFFF'
assert chip_before(solid, 'white') is None

rotated = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40">
<g id="figure_1"><rect x="0" y="0" width="100" height="30" fill="#7b8290"/>
<text id="end" x="80" y="18" transform="rotate(-0 80 18)" style="fill: #ffffff; font-size: 8px; text-anchor: end">5.0</text></g></svg>'''
chip = chip_before(rotated, 'end')
assert chip.get('fill') == '#0B0D14' and chip.get('transform') == 'rotate(-0 80 18)'
assert abs(float(chip.get('x')) + float(chip.get('width')) - 82) < 1e-6

unmapped = set()
artwork.recolor('''<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><g id="figure_1">
<rect width="4" height="4" fill="#1f77b4"/><rect width="4" height="4" fill="#ffffff"/></g></svg>''', unmapped)
assert unmapped == {'#1f77b4'}


def css_color(path, name):
    return re.search(rf'{name}:\s*(#[0-9A-Fa-f]{{6}})', open(path).read())[1]


book_css = sys.argv[1] + '/book/book.css'
for token in ('--ink-500', '--rose'):
    assert artwork.ratio(css_color(book_css, token), WHITE) >= 4.5, token
kindle = open(sys.argv[1] + '/kindle/kindle.css').read()
assert not re.search(r'(?<![-\w])color:\s*#', kindle), 'kindle text colors must inherit'
print('PASS: artwork contrast, distinct patterns, label chips, unmapped fills, palette version, CSS tokens')
PY

PYTHON="${PUBLISH_PYTHON:-$ROOT/.analysis/publish-env/bin/python3}"
if [ ! -x "$PYTHON" ]; then
  echo "SKIP: no publish venv at $PYTHON, so PNG and PDF regeneration is untested"
  exit 0
fi
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
touch "$TMP/FLEET.md"
WAYFARE_FLEET_ROOT="$TMP" "$PYTHON" - "$ROOT/publishing" "$ROOT/analysis/report" "$TMP" <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, sys.argv[1])
sys.path.insert(1, sys.argv[2])
import artwork
import book
import fitz
from PIL import Image

book.font_faces = lambda: ''
path = pathlib.Path(sys.argv[3])
(path / 'figure.svg').write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="120pt" height="60pt">
<g id="figure_1"><rect x="0" y="0" width="20" height="20" fill="#e93a61"/>
<rect x="30" y="0" width="20" height="20" fill="#c6c9d0"/></g></svg>''')
Image.new('RGB', (2, 2), '#FF00FF').save(path / 'figure.png')
files = artwork.prepare({'svg': 'figure.svg', 'png': 'figure.png'}, str(path))
assert set(files) == {'svg', 'png', 'pdf'}
with Image.open(path / files['png']) as im:
    assert all(abs(a - b) <= 1 for a, b in zip(im.getpixel((150, 150)), (186, 27, 69)))
with fitz.open(path / files['pdf']) as pdf:
    assert tuple(pdf[0].rect)[2:] == (120, 60)
assert not book.REFUSED

(path / 'card.svg').write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="40pt" height="20pt">
<text fill="#666d7b" x="2" y="10">Card</text></svg>''')
assert artwork.prepare({'svg': 'card.svg'}, str(path), raster=False) == {'svg': 'card.svg', 'pdf': 'card.pdf'}

original = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4"><text fill="#666d7b">x</text></svg>'''
(path / 'broken.svg').write_text(original)
try:
    artwork.prepare({'svg': 'broken.svg'}, str(path))
    raise AssertionError('an SVG without a size was prepared')
except ValueError:
    pass
assert (path / 'broken.svg').read_text() == original, 'a failed render left a marked SVG'

import charts
drawn = charts.draw([{"kind": "bar", "cats": ["a", "b"], "labels": True, "series": [
    {"name": "Owner", "values": [3, 5], "color": "A5153E"},
    {"name": "Codex", "values": [2, 4], "color": "7B8290"}]}], str(path / 'chart'))
warnings = []
artwork.prepare(drawn, str(path), warn=warnings.append)
root = ET.fromstring((path / 'chart.svg').read_text())
texts = [el for el in root.iter() if el.tag.endswith('}text')]
assert any(''.join(t.itertext()) == '5' for t in texts), 'chart labels must stay <text>'
fills = {artwork.properties(el).get('fill') for el in root.iter() if el.tag.endswith('}path')}
assert {'url(#book-fill-a5153e)', 'url(#book-fill-7b8290)'} <= fills
chips = [el for el in root.iter() if el.tag.endswith('}rect') and el.get('rx') == '1']
assert chips, 'value labels on hatched bars need chips'
assert not warnings, warnings
print('PASS: PNG and PDF regenerate from the accessible SVG, written last; charts keep text and get chips')
PY
