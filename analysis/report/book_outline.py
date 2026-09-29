"""Write the book's outline: every part and chapter, its section headings, and the questions it owns.

    python report/book_outline.py [--book .analysis/book]

The outline is generated from the chapter files, so it is a check on the book, not a plan for it:
a rewrite is done when the outline this prints matches the one written for it.
"""
import argparse
import json
import os
import re
import sys

BOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".analysis", "book")
NUMBERS = "One Two Three Four Five".split()


def headings(path):
    with open(path, encoding="utf-8") as f:
        return [(len(m.group(1)), m.group(2).strip()) for m in re.finditer(r"^(#{2,3}) (.+)$", f.read(), re.M)]


def outline(book):
    with open(os.path.join(book, "chapters.json"), encoding="utf-8") as f:
        toc = json.load(f)
    parts = {p["title"]: p for p in toc.get("parts", [])}
    out = ["# Book outline (generated: every part and chapter, its sections, and the questions it owns)"]
    seen = set()
    for ch in toc["chapters"]:
        part = parts.get(ch.get("group"))
        if part and part["title"] not in seen:
            seen.add(part["title"])
            out.append(f"\n## Part {NUMBERS[part['part'] - 1]}: {part['title']}  [{part['book']}]")
            out += [f"  {'  ' * (lvl - 2)}- {t}" for lvl, t in headings(os.path.join(book, part["book"]))]
        group = f"  ({ch['group']})" if ch.get("group") else ""
        out.append(f"\n## Chapter {ch['n']}: {ch['title']}{group}  [{ch['book']}]")
        out += [f"  {'  ' * (lvl - 2)}- {t}" for lvl, t in headings(os.path.join(book, ch["book"]))]
        out.append(f"  questions: {', '.join(ch['questions'])}")
    return "\n".join(out) + "\n"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--book", default=BOOK)
    args = ap.parse_args(argv)
    text = outline(args.book)
    with open(os.path.join(args.book, "_OUTLINE.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
