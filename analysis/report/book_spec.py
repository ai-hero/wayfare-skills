"""Parse the owner's figures brief into the figure manifest, and check its anchors against the manuscript.

    python report/book_spec.py [--book .analysis/book] [--write]

`_FIGURES_BRIEF.md` in the book folder is the owner's specification: one `### Figure N.M — title`,
`### Diagram N.M — title` or `### Table N.TM — title` entry per figure, each with an updated question, the
Origin cards it regenerates, the form it should take and a placement (chapter, section, and the ending of
the paragraph it follows). This reads every entry into `figures.json` beside it and reports each anchor or
section the manuscript does not contain, so a figure is never placed by a paragraph that has moved.

Anchors are compared after normalising quotes, dashes and whitespace, on the text after the brief's
leading ellipsis, so a retyped quote mark in the brief does not fail a paragraph that is there.
"""
import argparse
import glob
import json
import os
import re
import sys

BOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".analysis", "book")
BRIEF, MANIFEST = "_FIGURES_BRIEF.md", "figures.json"

ENTRY_RE = re.compile(r"^### (Figure|Diagram|Table) (\d)\.(T?\d+) — (.+?)$", re.M)
FIELD_RE = re.compile(r"^\*\*(.+?)\.\*\* (.+?)(?=\n\n\*\*|\n\n###|\n\n##|\Z)", re.M | re.S)
PLACE_RE = re.compile(r'Chapter (\d), [“"][^”"]+,[”"] (?:under|section) [“"](.+?)\.?[”"] Insert immediately after the '
                      r'paragraph ending: [“"](.+)[”"]\s*$', re.S)
CARD_RE = re.compile(r"`Q ([a-z0-9-]+)`")


def norm(s):
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("—", "-"), ("–", "-")):
        s = s.replace(a, b)
    s = re.sub(r"\*\*|\\", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def parse(text):
    """Every entry of the brief, in order, with its fields keyed by their bold label."""
    heads = list(ENTRY_RE.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end():end]
        body = re.split(r"^## ", body, maxsplit=1, flags=re.M)[0]
        fields = {k: v.strip() for k, v in FIELD_RE.findall(body)}
        kind, ch, num, title = m.group(1), int(m.group(2)), m.group(3), m.group(4).strip()
        e = {"id": f"{ch}.{num}", "kind": kind.lower(), "chapter": ch, "title": title,
             "question": fields.get("Updated question to ask") or fields.get("Question to answer", ""),
             "origin": fields.get("Origin question(s)") or fields.get("Origin source", ""),
             "cards": CARD_RE.findall(fields.get("Origin cards to regenerate", "")),
             "instructions": fields.get("Analysis and validation instructions") or fields.get("Production instructions", ""),
             "validation": fields.get("Validation", ""),
             "form": fields.get("Expected figure form", ""),
             "deliverable": fields.get("Deliverable", "").strip("`")}
        p = PLACE_RE.search(fields.get("Placement", ""))
        if p:
            anchor = p.group(3).strip()
            e.update({"section": p.group(2).strip(), "anchor": anchor.split("…")[-1].strip()})
            if int(p.group(1)) != ch:
                e["error"] = f"placement names chapter {p.group(1)}"
        else:
            e["error"] = "placement not parsed"
        out.append(e)
    return out


def chapters(book):
    """{n: (file, normalised prose without comments, section headings)}."""
    out = {}
    for f in sorted(glob.glob(os.path.join(book, "0*.md"))):
        n = int(os.path.basename(f)[:2])
        with open(f, encoding="utf-8") as fh:
            t = fh.read()
        prose = norm(re.sub(r"<!--.*?-->", "", t, flags=re.S))
        out[n] = (os.path.basename(f), prose, [h.strip() for h in re.findall(r"^## (.+)$", t, re.M)])
    return out


def check(entries, chaps):
    problems = 0
    for e in entries:
        if "error" in e:
            problems += 1
            print(f"{e['kind']} {e['id']}: {e['error']}")
            continue
        f, prose, heads = chaps[e["chapter"]]
        e["file"] = f
        # "Opening" is the untitled prose before a chapter's first `##`, which parse_book gives an empty title.
        sec_ok = e["section"] == "Opening" or any(norm(h) == norm(e["section"]) for h in heads)
        anc_ok = norm(e["anchor"]) in prose
        if not (sec_ok and anc_ok):
            problems += 1
            what = [] if sec_ok else [f"no section {e['section']!r}"]
            what += [] if anc_ok else [f"anchor not found: …{e['anchor'][-90:]}"]
            print(f"{e['kind']} {e['id']} ({f}): " + "; ".join(what))
    return problems


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--book", default=BOOK)
    ap.add_argument("--write", action="store_true", help=f"write {MANIFEST} beside the brief")
    args = ap.parse_args(argv)
    with open(os.path.join(args.book, BRIEF), encoding="utf-8") as f:
        entries = parse(f.read())
    problems = check(entries, chapters(args.book))
    kinds = {k: sum(e["kind"] == k for e in entries) for k in ("figure", "diagram", "table")}
    print(f"{len(entries)} entries ({kinds}), {problems} problem(s)")
    if args.write:
        path = os.path.join(args.book, MANIFEST)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=1, ensure_ascii=False)
            f.write("\n")
        print(path)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
