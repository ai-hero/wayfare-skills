#!/usr/bin/env bash
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Regression table for the Kindle edition's EPUB markup (publishing/kindle.py)
# and the author's-note parser every edition shares (publishing/inline.py).
#
# Each case is a bug that once produced an EPUB KDP rejects or a reader
# misreads, while the build still exited 0.
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

tree = kindle.contents_tree([chapter], False, None, None, False)
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

sys.exit(1 if failed else 0)
EOF
status=$?
[ "$status" -eq 0 ] && echo "publishing: all cases pass"
exit "$status"
