"""Place each finished figure and diagram in the manuscript, right after the paragraph its brief names.

    python report/book_place.py [--book .analysis/book] [--write] [--purge-old] [--check] [--only N ...]

Reads `figures.json` (the manifest `book_spec.py` writes from the owner's brief) and the results each
agent left: `.analysis/book/results/<id>.json` for an evidence figure ({"ref": "Q fixes-by-model",
"caption": ..., "alt": ..., "changed": ...}) and `.analysis/diagrams/book/<name>.json` for a diagram or
table (written by `svg_lib.finish`). For every entry with a result it finds the anchor paragraph in the
chapter and puts the figure line after it:

    [[Q fixes-by-model | caption]]          an evidence card, placed by the page builder
    [[Diagram 1.5 | caption]]               a drawn asset, resolved from the manifest by the page builder
    [[Table 7.T1 | caption]]

A line already in the chapter for the same ref is removed first, so re-running moves a figure whose
anchor moved rather than duplicating it. With --purge-old, the placeholders the manuscript carried before
the brief (`[[Figure N: ...]]` specs, `\\[Figure: ...]` notes, and the decks' upper-case diagram tags) are
removed; without it they are only reported. Without --write nothing is changed and the report says what
would happen.
"""
import argparse
import glob
import json
import os
import re
import sys

import book_spec as SPEC

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIAGRAMS = os.path.join(ROOT, ".analysis", "diagrams", "book")
RESULTS = "results"

# Part One conceptual entries the owner's brief also draws in Part Two: one asset, placed once at the
# Part Two anchor. Placing both would put the same drawing in a chapter twice.
MERGED = {"1.1": "diagram 1.2", "1.2": "diagram 1.3", "1.3": "diagram 1.5", "1.4": "diagram 1.5",
          "1.6": "diagram 1.7", "1.7": "diagram 1.6", "1.8": "diagram 1.8"}

OLD_RE = re.compile(r"^(\[\[Figure(?: \d+)?:.*\]\]|\\\[Figure:.*\]|\[\[[A-Z][A-Z0-9 ,·’'&-]+(?:\s*\|.*)?\]\])\s*$")
FIG_RE = re.compile(r"^\[\[([^|\]]+?)\s*(?:\|\s*(.*?))?\]\]\s*$")


def rkey(e):
    """Figures and diagrams share ids (figure 3.1, diagram 3.1), so results are keyed by kind and id."""
    return f"{e['kind']} {e['id']}"


def load_results(book):
    """{"figure 3.1": result, "diagram 3.1": result, ...} from the figure and diagram sidecars."""
    out = {}
    for f in glob.glob(os.path.join(book, RESULTS, "*.json")):
        with open(f, encoding="utf-8") as fh:
            r = json.load(fh)
        r.setdefault("id", os.path.basename(f)[:-5])
        r.setdefault("kind", "figure")
        out[rkey(r)] = r
    for f in glob.glob(os.path.join(DIAGRAMS, "*.json")):
        with open(f, encoding="utf-8") as fh:
            r = json.load(fh)
        if r.get("id") and r.get("name"):
            r.setdefault("kind", "diagram")
            r.setdefault("ref", f"{r['kind'].capitalize()} {r['id']}")
            if rkey(r) in out:
                print(f"book_place: {rkey(r)} has a result sidecar and a diagram sidecar; the diagram wins", file=sys.stderr)
            out[rkey(r)] = r
    return out


def paragraphs(lines):
    """[(start, end)] line spans of prose paragraphs: runs of non-blank lines that are not headings,
    figure lines or comments. The comment on its own line above a paragraph stays outside the span."""
    spans, start = [], None
    for i, line in enumerate(lines + [""]):
        s = line.strip()
        prose = s and not s.startswith("#") and not s.startswith("[[") and not s.startswith("\\[") \
            and not re.fullmatch(r"<!--.*?-->", s)
        if prose and start is None:
            start = i
        elif not prose and start is not None:
            spans.append((start, i))
            start = None
    return spans


def find_anchor(lines, anchor, section):
    """The line index after the paragraph ending with the anchor, within the named section."""
    sec = None
    in_section = section == "Opening"
    starts = {}
    for i, line in enumerate(lines):
        if line.startswith("## "):
            sec = line[3:].strip()
            in_section = SPEC.norm(sec) == SPEC.norm(section)
        if in_section:
            starts[i] = True
    want = SPEC.norm(anchor)
    for a, b in paragraphs(lines):
        if a not in starts:
            continue
        text = SPEC.norm(re.sub(r"<!--.*?-->", "", " ".join(lines[a:b]), flags=re.S))
        if text.endswith(want) or want in text and text.index(want) + len(want) >= len(text) - 2:
            return b
    return None


def ref_key(ref):
    return re.sub(r"\s+", " ", ref.split("·")[0]).strip().lower()


def place(lines, entries, results, purge_old, report):
    """Returns the new lines. Entries sharing an anchor are placed in id order after it."""
    old = [i for i, l in enumerate(lines) if OLD_RE.match(l)]
    if old:
        report.append(f"  {len(old)} old placeholder line(s)" + (" removed" if purge_old else " kept (--purge-old removes)"))
    keep = set(range(len(lines))) - (set(old) if purge_old else set())
    todo = []
    for e in entries:
        if e["kind"] == "figure" and e["id"] in MERGED:
            report.append(f"  figure {e['id']} is drawn once as {MERGED[e['id']]}")
            continue
        r = results.get(rkey(e))
        if not r:
            report.append(f"  {e['kind']} {e['id']} {e['title']!r}: no result yet, not placed")
            continue
        # An anchor the prose no longer holds must not delete the line already placed for it.
        if find_anchor(lines, e["anchor"], e["section"]) is None:
            have = any(FIG_RE.match(l) and ref_key(FIG_RE.match(l).group(1)) == ref_key(r["ref"]) for l in lines)
            report.append(f"  {e['kind']} {e['id']}: anchor not found in section {e['section']!r}; "
                          + ("existing line kept" if have else "not placed"))
            continue
        ref = r["ref"]
        for i, l in enumerate(lines):
            m = FIG_RE.match(l)
            if m and ref_key(m.group(1)) == ref_key(ref):
                keep.discard(i)
        todo.append((e, r))
    lines2 = [l for i, l in enumerate(lines) if i in keep]
    inserts = {}
    for e, r in todo:
        at = find_anchor(lines2, e["anchor"], e["section"])
        if at is None:
            report.append(f"  {e['kind']} {e['id']}: anchor lost while placing; not placed")
            continue
        cap = r.get("caption", "").replace("\n", " ").strip()
        inserts.setdefault(at, []).append(f"[[{r['ref']} | {cap}]]" if cap else f"[[{r['ref']}]]")
        report.append(f"  {e['kind']} {e['id']} -> after line {at} in {e['section']!r}: {r['ref']}")
    out = []
    for i, l in enumerate(lines2 + [None]):
        if i in inserts:
            if out and out[-1].strip():
                out.append("")
            for line in inserts[i]:
                out += [line, ""]
        if l is not None:
            out.append(l)
    # Collapse runs of blank lines the removals and inserts left behind.
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).rstrip("\n") + "\n"
    return text.split("\n")[:-1]


def check(book, manifest, results, chaps, only=None):
    """The completion checklist: every entry has a result and a summary, its line sits right after its
    anchor, and no old placeholder remains. Returns the number of problems."""
    problems = 0
    for n, (fname, _, _) in sorted(chaps.items()):
        if only and n not in only:
            continue
        with open(os.path.join(book, fname), encoding="utf-8") as f:
            lines = f.read().split("\n")
        for i, l in enumerate(lines):
            if OLD_RE.match(l):
                problems += 1
                print(f"{fname}:{i + 1}: old placeholder remains: {l[:70]}")
        for e in (e for e in manifest if e["chapter"] == n and "error" not in e):
            if e["kind"] == "figure" and e["id"] in MERGED:
                continue
            r = results.get(rkey(e))
            if not r:
                problems += 1
                print(f"{fname}: {e['kind']} {e['id']} has no result")
                continue
            if e["kind"] == "figure" and not r.get("name") and not os.path.exists(os.path.join(SPEC.BOOK, "..", "data", "figures", f"{e['id']}.json")):
                problems += 1
                print(f"{fname}: figure {e['id']} has no summary table in .analysis/data/figures")
            at = find_anchor(lines, e["anchor"], e["section"])
            if at is None:
                problems += 1
                print(f"{fname}: {e['kind']} {e['id']}: anchor not found")
                continue
            after = [l for l in lines[at:at + 8] if l.strip()]
            hits = [l for l in after[:4] if FIG_RE.match(l) and ref_key(FIG_RE.match(l).group(1)) == ref_key(r["ref"])]
            if not hits:
                problems += 1
                print(f"{fname}: {e['kind']} {e['id']} ({r['ref']}) is not placed after its anchor")
    print(f"check: {problems} problem(s)")
    return problems


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--book", default=SPEC.BOOK)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--purge-old", action="store_true")
    ap.add_argument("--check", action="store_true", help="verify placement instead of placing")
    ap.add_argument("--only", type=int, nargs="*", help="chapter numbers")
    args = ap.parse_args(argv)
    with open(os.path.join(args.book, SPEC.MANIFEST), encoding="utf-8") as f:
        manifest = json.load(f)
    results = load_results(args.book)
    chaps = SPEC.chapters(args.book)
    if args.check:
        return 1 if check(args.book, manifest, results, chaps, args.only) else 0
    placed = missing = 0
    for n, (fname, _, _) in sorted(chaps.items()):
        if args.only and n not in args.only:
            continue
        entries = sorted((e for e in manifest if e["chapter"] == n and "error" not in e),
                         key=lambda e: (e["kind"] != "table", e["id"]))
        path = os.path.join(args.book, fname)
        with open(path, encoding="utf-8") as f:
            lines = f.read().split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        report = []
        new = place(lines, entries, results, args.purge_old, report)
        placed += sum("->" in r for r in report)
        missing += sum("not placed" in r for r in report)
        print(f"{fname}:")
        print("\n".join(report))
        if args.write and new != lines:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(new) + "\n")
            print("  written")
    print(f"{placed} placed, {missing} not placed" + ("" if args.write else " (dry run; --write to apply)"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
