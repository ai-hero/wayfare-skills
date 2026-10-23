#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for the Kindle edition's EPUB markup (publishing/kindle.py),
# the author's-note parser every edition shares (publishing/inline.py), and the
# print path's URL fetcher and font pin (publishing/book.py).
#
# Usage: bash scripts/publishing.test.sh

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PUBLISH_PYTHON:-$ROOT/.analysis/publish-env/bin/python3}"
[ -x "$PY" ] || { echo "SKIP: no publish venv at $PY"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# A fixture map: the real one is in the gitignored manuscript, and importing
# the pipeline without one stops it.
printf '{"repos": [{"old": "real-repo", "new": "plain-repo"}]}\n' >"$TMP/repo-names.json"

MANUSCRIPT_DIR="$TMP" PUBLISH_OUT="$TMP/out" "$PY" - "$ROOT/publishing" "$TMP" <<'EOF'
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, sys.argv[1])
tmp = sys.argv[2]
import book
import kindle
import web
from inline import note_end, sub_notes

failed = 0


def check(name, expected, actual):
    global failed
    if expected != actual:
        failed += 1
        print(f"FAIL  {name}\n      expected: [{expected}]\n      actual:   [{actual}]")


def well_formed(fragment):
    try:
        ET.fromstring(f'<div xmlns:epub="http://www.idpf.org/2007/ops">{fragment}</div>')
        return True
    except ET.ParseError:
        return False


def cell(t):
    return {"md": t, "html": t}


def table(*rows):
    return {"kind": "table", "rows": [[cell(c) for c in r] for r in rows]}


note = 'a<span class="fn" data-key="note-x">one <span class="repo">r</span> two</span> b'
check("a note holding a span is read whole", "a[one <span class=\"repo\">r</span> two] b",
      sub_notes(note, lambda inner: f"[{inner}]"))
check("note_end skips past the inner span", len(note) - 2, note_end(note, 1))
check("note_end is None where no note opens", None, note_end(note, 0))

calls = kindle.footnotes("ch-1", f"<p>{note}</p>")
check("a footnote with a nested span stays well-formed", True, well_formed(calls))

t = kindle.table_html(table(["H", "V"], ["x", "y"])["rows"], "t1", "h", "prose-table")
merged = book.example({"example": True, "example_start": True}, t)
check("a table in an example card has one class attribute", 1, merged.split("<table", 1)[1].split(">", 1)[0].count("class="))
check("a table in an example card is well-formed", True, well_formed(merged))

chapter = {"n": 1, "title": "One", "further": [], "sections": [
    {"title": "A", "slug": "a", "html": "A", "blocks": [table(["H", "V"], ["x", "y"])]},
    {"title": "", "slug": "", "html": "", "blocks": [table(["H", "V"], ["x", "y"])]},
]}
html_text = kindle.chapter(chapter, kindle.Images())
ids = re.findall(r'\sid="([^"]+)"', html_text)
check("an untitled section's table repeats no id", [], sorted({i for i in ids if ids.count(i) > 1}))

group = kindle.table_html(table(["H", "V"], ["Group", ""], ["x", "y"])["rows"], "t2", "h")
check("a group row opens its own tbody", 1, group.count("<tbody>"))
check("a data cell names its column, row and group", True, 'headers="t2-c1 t2-r2 t2-g1"' in group)

for name, given, expected in [
    ("a trailing full stop stays outside", "see https://a.org/x.", 'see <a href="https://a.org/x">https://a.org/x</a>.'),
    ("a DOI's balanced parentheses stay in", "https://doi.org/10.1/a(b)c",
     '<a href="https://doi.org/10.1/a(b)c">https://doi.org/10.1/a(b)c</a>'),
    ("an unopened parenthesis stays outside", "(https://a.org/x).", '(<a href="https://a.org/x">https://a.org/x</a>).'),
    ("an escaped quote ends the URL", "&quot;https://q.com/x&quot;", '&quot;<a href="https://q.com/x">https://q.com/x</a>&quot;'),
    ("&amp; inside a query stays in", "https://q.com/?a=1&amp;b=2", '<a href="https://q.com/?a=1&amp;b=2">https://q.com/?a=1&amp;b=2</a>'),
    ("a URL already linked is left alone", '<a href="https://a.org">https://a.org</a>', '<a href="https://a.org">https://a.org</a>'),
]:
    out = kindle.link_urls(given)
    check(name, expected, out)
    check(f"{name}: well-formed", True, well_formed(out))

from PIL import Image
for d in ("a", "b"):
    os.makedirs(os.path.join(tmp, d), exist_ok=True)
    Image.new("RGB", (4, 4), "white").save(os.path.join(tmp, d, "fig.png"))
images = kindle.Images()
hrefs = {images.add(os.path.join(tmp, d, "fig.png")) for d in ("a", "b")}
check("two figures with one file name get two files", 2, len(hrefs))

tree = kindle.contents_tree([chapter], None, False)
nav = kindle.nav(tree, "ch-1.xhtml")
ncx = kindle.ncx({"title": "T"}, "u", tree)
files = {"OEBPS/kindle.css": "", "OEBPS/nav.xhtml": nav, "OEBPS/toc.ncx": ncx,
         "OEBPS/ch-1.xhtml": kindle.page("One", "<section id=\"ch-1\"></section>")}
problems = kindle.check(files)
check("a contents entry to a missing heading is a problem", True,
      any("ch-1.xhtml#ch-1-a names no element" in p for p in problems))
files["OEBPS/ch-1.xhtml"] = kindle.page("One", '<section id="ch-1"><h2 id="ch-1-a">A</h2><p id="x"></p><p id="x"></p></section>')
problems = kindle.check(files)
check("a repeated id is a problem", ["OEBPS/ch-1.xhtml: id x is used twice"], problems)

import hashlib
import pathlib
import urllib.error
import urllib.request

import paths
import weasyprint.urls
from PIL import Image

os.makedirs(paths.ASSETS, exist_ok=True)
local_png = os.path.join(paths.ASSETS, "fig.png")
Image.new("RGB", (4, 4), "white").save(local_png)


def refused(url):
    try:
        book.local_fetcher(url)
    except ValueError:
        return True
    return False


fetched = []
real_fetcher = weasyprint.urls.default_url_fetcher
weasyprint.urls.default_url_fetcher = lambda url, *a, **k: fetched.append(url) or real_fetcher(url, *a, **k)
try:
    hostile = ('<p><img src="http://127.0.0.1:9/x.png"><img src="file:///etc/hosts">'
               '<img src="../../../etc/hosts"><img src="fig.png">'
               '<a rel="attachment" href="file:///etc/hosts">x</a></p>')
    book.weasy_html()(string=hostile, base_url=paths.ASSETS + "/").render()
finally:
    weasyprint.urls.default_url_fetcher = real_fetcher
check("a render fetches only the asset it names", [pathlib.Path(local_png).as_uri()], fetched)
check("a remote image is refused", True, refused("http://127.0.0.1:9/x.png"))
check("an out-of-tree file is refused", True, refused("file:///etc/hosts"))
check("a dot-dot path out of the assets is refused", True,
      refused(pathlib.Path(paths.ASSETS, "..", "..", "x").as_uri()))
check("a file on another host is refused", True, refused("file://example.com/etc/hosts"))
check("a data URI still loads", False, refused("data:image/png;base64,iVBORw0KGgo="))
font = os.path.join(tmp, "italic.woff2")
open(font, "wb").close()
book.GEIST_ITALIC = font
check("a font file the book names is allowed", False, refused(pathlib.Path(font).as_uri()))
roots_ok = {}
for name, path in [("Manrope", book.FONTS["Manrope"]), ("turned table", os.path.join(paths.BUILD, "book", "t.svg")),
                   ("author photo", os.path.join(paths.EDITIONS, "author.jpg"))]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").close()
    roots_ok[name] = not refused(pathlib.Path(path).as_uri())
check("every root the book reads from is allowed", {k: True for k in roots_ok}, roots_ok)
check("a sibling folder sharing the assets prefix is refused", True,
      refused(pathlib.Path(paths.ASSETS + "-x", "f.png").as_uri()))
book.REFUSED.clear()
refused("http://127.0.0.1:9/x.png")
check("a refusal is recorded for the build to fail on", {"http://127.0.0.1:9/x.png"}, book.REFUSED)
book.REFUSED.clear()

kept = {h: web.clean(f'<a href="{h}">x</a>') for h in ("/book/x", "#a", "https://x.example", "mailto:a@b.example")}
check("a site, anchor, https or mailto href is kept", {h: f'<a href="{h}">x</a>' for h in kept}, kept)
dropped = {h: web.clean(f'<a href="{h}">x</a>') for h in
           ("//evil.example", "/\\evil.example", "/&#9;/evil.example", "/&#10;/evil.example", " //evil.example",
            "javascript:alert(1)")}
check("a protocol-relative or script href loses its href", {h: "<a>x</a>" for h in dropped}, dropped)

import source
check("an escaped pipe keeps a table cell whole", ["a | b", "c"], source.unescape_pipes(["a \\", " b", "c"]))


def fake_urlopen(body):
    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return body
    return lambda url, timeout=None: R()


real_urlopen = urllib.request.urlopen
dest = os.path.join(tmp, "fonts", "m.ttf")
urllib.request.urlopen = fake_urlopen(b"not the font")
try:
    book.fetch_manrope(dest)
    outcome = "no error"
except SystemExit as e:
    outcome = str(e)
finally:
    urllib.request.urlopen = real_urlopen
check("a wrong digest is a hard error naming both hashes", True,
      book.MANROPE_SHA256 in outcome and hashlib.sha256(b"not the font").hexdigest() in outcome)
check("a wrong digest leaves nothing in place", [], os.listdir(os.path.dirname(dest)))
urllib.request.urlopen = fake_urlopen(b"font")
try:
    book.fetch_manrope(dest, sha256=hashlib.sha256(b"font").hexdigest())
finally:
    urllib.request.urlopen = real_urlopen
check("a matching digest moves the file into place", ["m.ttf"], os.listdir(os.path.dirname(dest)))
check("a matching digest writes the downloaded bytes", b"font", open(dest, "rb").read())
check("MANROPE_URL names a commit, not a branch", True,
      re.search(r"/raw/[0-9a-f]{40}/", book.MANROPE_URL) is not None)


def failing_urlopen(url, timeout=None):
    raise urllib.error.URLError("no route")


urllib.request.urlopen = failing_urlopen
try:
    book.fetch_manrope(dest + "2")
    outcome = "no error"
except SystemExit as e:
    outcome = str(e)
finally:
    urllib.request.urlopen = real_urlopen
check("a failed download names the URL and where to put the font", True,
      book.MANROPE_URL in outcome and dest + "2" in outcome)

with open(book.FONTS["Manrope"], "wb") as f:
    f.write(b"an old unpinned font")
calls = []
real_fetch = book.fetch_manrope
book.fetch_manrope = calls.append
try:
    try:
        book.font_faces()
    except SystemExit:
        pass
finally:
    book.fetch_manrope = real_fetch
check("a Manrope file with the wrong digest is fetched again", [book.FONTS["Manrope"]], calls)

sys.exit(1 if failed else 0)
EOF
status=$?
[ "$status" -eq 0 ] && echo "publishing: all cases pass"
exit "$status"
