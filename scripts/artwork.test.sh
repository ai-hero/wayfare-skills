#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "$ROOT/publishing" <<'PY'
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, sys.argv[1])
import artwork


def ratio(color):
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    y = sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))
    return 1.05 / (y + 0.05)


for fill, _ in artwork.DATA.values():
    assert ratio(fill) >= 3, fill
for fill in artwork.TEXT.values():
    assert ratio(fill) >= 7, fill

svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="200pt" height="100pt">
<defs><pattern id="old"><rect fill="#e93a61" width="6" height="6"/></pattern></defs>
<g id="figure_1"><path id="bar" d="M0 0H20V20H0Z" style="fill: #f1839a"/>
<path id="legend" d="M30 0H50V20H30Z" style="fill: #f1839a"/>
<path id="retry" d="M60 0H80V20H60Z" style="fill: url(#old)"/>
<text id="label" style="fill: #666d7b; font-weight: 200">Count</text></g></svg>'''
out = artwork.recolor(svg)
root = ET.fromstring(out)
by_id = {el.get('id'): el for el in root.iter() if el.get('id')}
bar = artwork.properties(by_id['bar'])
legend = artwork.properties(by_id['legend'])
assert bar['fill'] == legend['fill'] and bar['fill'].startswith('url(#book-fill-')
assert by_id['bar'].get('stroke') == '#0B0D14'
assert artwork.properties(by_id['label']) == {'fill': '#383D49', 'font-weight': '400'}
assert 'url(#old)' not in artwork.properties(by_id['retry'])['fill']
assert artwork.recolor(out) == out
assert artwork.dimensions(svg) == [200, 100]
assert artwork.dimensions('<svg width="96px" height="1in"/>') == [72, 72]

native = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
<rect fill="#0B0D14" width="100" height="100"/>
<text id="reverse" fill="#C6C9D0">Delivery</text>
<path id="edge" stroke="#C6C9D0" fill="none"/>
<text id="quiet" fill="#666D7B" font-weight="300">Proposed</text></svg>'''
root = ET.fromstring(artwork.recolor(native))
by_id = {el.get('id'): el for el in root.iter() if el.get('id')}
assert by_id['reverse'].get('fill') == '#C6C9D0'
assert by_id['edge'].get('stroke') == '#666D7B'
assert by_id['quiet'].get('fill') == '#383D49'
assert by_id['quiet'].get('font-weight') == '400'
blank = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"/>'
assert artwork.recolor(blank) == blank
assert artwork.prepare({}, '/unused') == {}
annotated = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40">
<g id="figure_1"><path d="M0 0 L100 0 L100 30 L0 30 Z" fill="#c6c9d0"/>
<text x="50" y="18" style="fill: #0b0d14; font-size: 8px; text-anchor: middle">22.7%</text></g></svg>'''
root = ET.fromstring(artwork.recolor(annotated))
group = next(el for el in root.iter() if el.get('id') == 'figure_1')
label = next(el for el in group if el.tag.endswith('}text'))
chip = list(group)[list(group).index(label) - 1]
assert chip.tag.endswith('}rect') and chip.get('fill') == '#FFFFFF'
assert label.text == '22.7%'
assert root.get('data-book-labels') == '1'
print('PASS: artwork contrast, matching legend patterns, reverse text, units and repeat preparation')
PY

PYTHON="$ROOT/.analysis/publish-env/bin/python3"
if [ -x "$PYTHON" ]; then
  "$PYTHON" - "$ROOT/publishing" <<'PY'
import pathlib
import sys
import tempfile

sys.path.insert(0, sys.argv[1])
import artwork
import book
import fitz
from PIL import Image

with tempfile.TemporaryDirectory() as tmp:
    path = pathlib.Path(tmp)
    (path / 'figure.svg').write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="120pt" height="60pt">
    <g id="figure_1"><rect x="0" y="0" width="20" height="20" fill="#e93a61"/>
    <rect x="30" y="0" width="20" height="20" fill="#c6c9d0"/></g></svg>''')
    Image.new('RGB', (2, 2), '#FF00FF').save(path / 'figure.png')
    book.font_faces = lambda: ''
    files = artwork.prepare({'svg': 'figure.svg', 'png': 'figure.png'}, tmp)
    assert set(files) == {'svg', 'png', 'pdf'}
    with Image.open(path / files['png']) as im:
        assert all(abs(a - b) <= 1 for a, b in zip(im.getpixel((150, 150)), (186, 27, 69)))
    with fitz.open(path / files['pdf']) as pdf:
        assert tuple(pdf[0].rect)[2:] == (120, 60)
    assert not book.REFUSED
print('PASS: the EPUB PNG and vector PDF are regenerated from the accessible SVG')
PY
fi
