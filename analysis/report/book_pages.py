"""Render the book: one page per chapter of a table of contents, not one per deck.

    python report/book_pages.py [--book .analysis/book] [--decks .analysis/decks] --out FOLDER [--lessons TALK]

Decks hold the evidence by topic; the book arranges it by argument. `chapters.json` in the book
folder lists each chapter and the questions it shows, by id (Q work-sources), and the parts that
group the chapters; a part's page is its introduction and shows no questions of its own. Every deck is read
once, a figure resolves from whichever deck holds it, and each question a chapter shows is placed
as a card in its prose, where the text first draws or cites it.
"""
import argparse
import base64
import glob
import json
import os
import re
import sys

import deck_html as D
import html_views
from pptx import Presentation

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BOOK = os.path.join(ROOT, ".analysis", "book")
DECKS = os.path.join(ROOT, ".analysis", "decks")


def load_decks(folder, lessons=None):
    """Every deck's question blocks by id and its diagrams by tag, plus each deck's numbers: the prose
    slides and notes are where a chapter's sources and dates are checked."""
    questions, diagrams, known = {}, [], {}
    lesson_hits = 0
    # A view is attached by its question id wherever the question is built, whichever views file saved it.
    views, attached = {}, set()
    for f in sorted(glob.glob(os.path.join(html_views.VIEWS_DIR, "*.json"))):
        for k, v in html_views.load(os.path.splitext(os.path.basename(f))[0]).items():
            views.setdefault(D.qkey(k) or k, []).extend(v)
    for path in sorted(glob.glob(os.path.join(folder, "*.pptx"))):
        deck = os.path.splitext(os.path.basename(path))[0]
        _, sections = D.group([D.classify(D.read_slide(s, f"{deck}, slide {i}"))
                               for i, s in enumerate(Presentation(path).slides, 1)])
        for s in sections:
            for b in s["blocks"]:
                k = D.qkey(b["key"])
                if k in views:
                    have = {v["label"].lower() for v in b["views"]}
                    b["views"] += [v for v in views[k] if v["label"].lower() not in have]
                    attached.add(k)
        if lessons:
            lesson_hits += D.attach_lessons(sections, lessons)
        known[deck] = D.haystack(sections)
        for s in sections:
            for b in s["blocks"]:
                k = D.qkey(b["key"])
                if k:
                    if k in questions:
                        D.warn(f"{k} is built in two decks; the page uses the first")
                        continue
                    b["key"] = k
                    questions[k] = {"block": b, "deck": deck}
                elif b["views"]:
                    diagrams.append({"block": b, "deck": deck})
    for k in sorted(set(views) - attached):
        D.warn(f"views for {k} match no question in any deck; they are dropped")
    if lessons and not lesson_hits:
        D.warn("--lessons matched no question in any deck; no lessons were attached")
    return questions, diagrams, known


BOOK_ASSETS = os.path.join(ROOT, ".analysis", "diagrams", "book")


def book_diagrams(folder=BOOK_ASSETS):
    """The manuscript's own drawn diagrams and tables, one block each, keyed `Diagram 1.5` or `Table 7.T1`
    from the sidecar `svg_lib.finish` writes beside every asset. A chapter draws one with `[[Diagram 1.5 |
    caption]]`; the SVG goes in as the view's image, a table's Markdown as the view's table."""
    out = []
    for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
        if not meta.get("id") or not meta.get("name"):
            continue
        key = f"{meta.get('kind', 'diagram').capitalize()} {meta['id']}"
        view = {"label": "", "title": meta.get("caption", ""), "points": [], "source": meta.get("source", ""),
                "extra": [], "notes": meta.get("alt", ""), "charts": [], "tables": [], "images": []}
        base = os.path.join(folder, meta["name"])
        if os.path.exists(base + ".svg"):
            with open(base + ".svg", "rb") as f:
                src = "data:image/svg+xml;base64," + base64.b64encode(f.read()).decode()
            view["images"].append({"src": src, "alt": meta.get("alt", "")})
        if os.path.exists(base + ".md"):
            with open(base + ".md", encoding="utf-8") as f:
                rows = [l.strip().strip("|").split("|") for l in f if l.strip().startswith("|")]
            rows = [[c.strip() for c in r] for r in rows if not re.fullmatch(r"[\s|:-]+", "|".join(r))]
            if rows:
                view["tables"].append(rows)
        if not view["images"] and not view["tables"]:
            D.warn(f"{key}: no .svg or .md beside {path}")
            continue
        out.append({"block": {"key": key, "question": None, "views": [view], "statements": []}, "deck": "book"})
    return out


def merge(questions, merged):
    """Fold each merged question into the one kept: its views become tabs of the kept card, named by the merge,
    and its question and lessons go with them, so nothing it showed is lost."""
    for m, spec in merged.items():
        mq, kq = questions.get(f"Q {m}"), questions.get(f"Q {spec['into']}")
        if mq is None or kq is None:
            missing = [f"Q {x}" for x, q in ((m, mq), (spec["into"], kq)) if q is None]
            D.warn(f"merge of Q {m} into Q {spec['into']}: {' and '.join(missing)} in no deck")
            continue
        questions.pop(f"Q {m}")
        kb, mb = kq["block"], mq["block"]
        for v in mb["views"]:
            own = v.get("label") or ""
            kb["views"].append({**v, "label": spec["label"] if own.upper() == "ANSWER" else f"{spec['label']} · {own.title()}"})
        q, k = mb.get("question") or {}, kb.get("question")
        if k is not None and q.get("question"):
            k["notes"] = (k.get("notes") or "") + f"\n\nAlso answers what was Q {m}: {q['question']}"
        if mb.get("lessons"):
            kl = kb.setdefault("lessons", {"insights": [], "hypotheses": []})
            kl["insights"] += mb["lessons"]["insights"]
            kl["hypotheses"] += mb["lessons"]["hypotheses"]


def find_diagram(diagrams, ref, prefer=()):
    """A diagram by its tag, from the decks this chapter's questions come from first: tags repeat across decks."""
    for d in sorted(diagrams, key=lambda d: d["deck"] not in prefer):
        _, v = D.find_view([{"blocks": [d["block"]]}], ref)
        if v is not None:
            return d, v
    return None, None


def card(b, number, caption="", view=None, compact=False):
    """A question's whole card, placed in the prose: every view, with the one the text drew first.
    A `[[I ...]]` line places the card `compact` (question, finding, chart, up to three views to switch
    between); `[[Q ...]]` and the appendix keep the whole card. Every view ships either way; the viewer
    decides what to show."""
    views = list(b["views"])
    if view is not None and view in views:
        views.insert(0, views.pop(views.index(view)))
    return {"kind": "card", "key": b["key"], "number": number, "caption": caption, "compact": compact,
            "block": {**b, "views": views}}


def build(ch, text, questions, diagrams, deck_known):
    """The chapter's prose with its evidence woven in: a question's card sits where the text first
    draws it as a figure, or else right after the paragraph that first cites it. A question the
    text never mentions stays off the page."""
    name, lab = (("appendix", "A") if ch.get("appendix") else (f"ch{ch['n']:02d}", str(ch["n"])))
    compact = not ch.get("appendix")
    own = {}
    for q in ch["questions"]:
        k = f"Q {q}"
        if k in questions:
            own[k] = questions[k]["block"]
        else:
            D.warn(f"{name}: {k} is in no deck")
    decks = {questions[k]["deck"] for k in own}
    known = set()
    for deck in decks:
        known |= deck_known.get(deck, set())
    sections = [{"blocks": list(own.values())}]

    def resolve(ref):
        b, v = D.find_view(sections, ref)
        if v is not None:
            return b, v, None
        # A chart from a card another chapter shows: drawn here as a figure, the card stays there.
        k = D.qkey(ref)
        if k in questions:
            b, v = D.find_view([{"blocks": [questions[k]["block"]]}], ref)
            if v is not None:
                return b, v, questions[k]["deck"]
        d, v = find_diagram(diagrams, ref, decks)
        if v is not None:
            return d["block"], v, d["deck"]
        return None, None, None

    book = D.parse_book(text)
    figures = [blk["ref"] for s in book for blk in s["blocks"] if blk["kind"] == "figure"]
    resolved = {ref: resolve(ref) for ref in figures}
    # Only a figure that resolves defers a card: one that fails must not keep its question off the page.
    drawn = {D.qkey(b["key"]) for b, v, _ in resolved.values() if v is not None}
    failed = {D.qkey(ref) for ref, (_, v, _) in resolved.items() if v is None}
    fig, placed, out = 0, set(), []
    for s in book:
        blocks = []
        for blk in s["blocks"]:
            if blk["kind"] == "figure":
                b, v, deck = resolved[blk["ref"]]
                if v is None:
                    D.warn(f"{name}: book figure [[{blk['ref']}]] matches no view in any deck")
                    continue
                if deck:
                    known |= deck_known.get(deck, set())
                fig += 1
                k = D.qkey(b["key"])
                if k in own and k not in placed:
                    placed.add(k)
                    blk = card(b, f"{lab}.{fig}", blk["caption"], v, blk.get("inline", False))
                else:
                    blk.update({"number": f"{lab}.{fig}", "key": b["key"], "view": v,
                                "caption": blk["caption"] or v["title"]})
            t = blk.get("text") or blk.get("caption", "") or " ".join(
                c for r in blk.get("rows", []) for c in r) or " ".join(blk.get("items", []))
            # Counts up to ten are ordinary prose ("two reasons", "3 repos"), not findings.
            for num in D.NUM_RE.findall(D.FREE_RE.sub(" ", t)):
                if D.bare(num) not in known and not (D.bare(num).isdigit() and int(D.bare(num)) <= 10) \
                        and not D.rounds_to(num, known):
                    D.warn(f"{name}: book number {num!r} is not in the chapter's data: {t[:80]}…")
            blocks.append(blk)
            if blk["kind"] in ("p", "quote", "table", "ul", "ol"):
                for m in D.Q_RE.finditer(t):
                    k = D.qkey(m.group(0))
                    if k in own and k not in placed and k not in drawn:
                        placed.add(k)
                        fig += 1
                        blocks.append(card(own[k], f"{lab}.{fig}", compact=compact))
        if blocks or s["title"]:
            out.append({**s, "blocks": blocks})
    # A question the prose never cites is left off the page, not appended: the warning is the
    # prompt to write the sentence that earns it a place.
    rest = [k for k in own if k not in placed and k not in failed]
    if rest:
        D.warn(f"{name}: {len(rest)} question(s) the text never cites, left off the page: {', '.join(rest)}")
    return out, sections


ONES = ("Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen Fifteen "
        "Sixteen Seventeen Eighteen Nineteen").split()
TENS = {2: "Twenty", 3: "Thirty", 4: "Forty"}


def spelled(n):
    if n < 20:
        return ONES[n]
    return TENS[n // 10] + (f"-{ONES[n % 10]}" if n % 10 else "")


APPENDIX = {"book": "_FIGURES_APPENDIX.md", "title": "Figures appendix"}


def appendix_chapter(toc, questions):
    """The figures appendix as a chapter that owns every card, so each figure line places its card.
    It is not in `chapters.json`: the Q links keep pointing at the chapter that argues from the card."""
    return {**APPENDIX, "n": max(c["n"] for c in toc["chapters"]) + 1, "label": "A", "group": None,
            "appendix": True, "questions": sorted(k[2:] for k in questions)}


def page_name(ch):
    if ch.get("appendix"):
        return "Appendix - Figures.html"
    if "part" in ch:
        return f"Part {ch['part']} - {re.sub(r'[?/:]', '', ch['title'])}.html"
    return f"Ch {ch['n']:02d} - {re.sub(r'[?/:]', '', ch['title'])}.html"


def part_before(toc, ch):
    """The part whose first chapter this is, so its page renders ahead of it."""
    first = {}
    for c in toc["chapters"]:
        first.setdefault(c.get("group"), c["n"])
    for part in toc.get("parts", []):
        if first.get(part["title"]) == ch["n"]:
            return part
    return None


def render_part(part, template, toc, book_dir, out_dir, index_href="index.html"):
    """A part's introduction, parsed like a chapter's prose. A [[...]] figure here is an error, not a
    card: the evidence belongs to the chapter that owns the question."""
    with open(os.path.join(book_dir, part["book"]), encoding="utf-8") as f:
        text = f.read()
    book = D.parse_book(text)
    for sec in book:
        for b in [b for b in sec["blocks"] if b["kind"] == "figure"]:
            D.warn(f"part {part['part']}: figure [[{b['ref']}]] dropped; parts show no evidence")
        sec["blocks"] = [b for b in sec["blocks"] if b["kind"] != "figure"]
    h1 = re.search(r"^# (.+)$", text, re.M)
    title = h1.group(1).strip() if h1 else part["title"]
    head = {"kind": "title", "title": title, "subtitle": f"Part {spelled(part['part'])}", "notes": ""}
    pages = {str(c["n"]): page_name(c) for c in toc["chapters"]}
    owners = {q: c["n"] for c in toc["chapters"] for q in c["questions"]}
    # No "chapter": every Q link then resolves to the owning chapter's page.
    payload = {"head": head, "sections": [], "index": index_href, "book": book, "pages": pages, "owners": owners}
    out = os.path.join(out_dir, page_name(part))
    with open(out, "w", encoding="utf-8") as f:
        f.write(D.fill(template, title, payload))
    return out


def render(ch, template, questions, diagrams, deck_known, toc, book_dir, out_dir, index_href="index.html"):
    with open(os.path.join(book_dir, ch["book"]), encoding="utf-8") as f:
        text = f.read()
    book, sections = build(ch, text, questions, diagrams, deck_known)
    h1 = re.search(r"^# (.+)$", text, re.M)
    title = h1.group(1).strip() if h1 else ch["title"]
    subtitle = "Appendix" if ch.get("appendix") else f"Chapter {spelled(ch['n'])}"
    head = {"kind": "title", "title": title,
            "subtitle": subtitle + (f" · {ch['group']}" if ch.get("group") else ""), "notes": ""}
    out = os.path.join(out_dir, page_name(ch))
    # slim() edits the chart dicts in place, and the cards in `book` share them.
    D.slim(sections)
    pages = {str(c["n"]): page_name(c) for c in toc["chapters"]}
    owners = {q: c["n"] for c in toc["chapters"] for q in c["questions"]}
    # The compact cards link to their full card on the appendix page, so it is named only when it renders.
    appendix = page_name({**APPENDIX, "appendix": True}) \
        if os.path.exists(os.path.join(book_dir, APPENDIX["book"])) and not ch.get("appendix") else None
    payload = {"head": head, "sections": [], "index": index_href, "book": book, "chapter": ch["n"],
               "pages": pages, "owners": owners, "appendix": appendix}
    with open(out, "w", encoding="utf-8") as f:
        f.write(D.fill(template, title, payload))
    return out


def render_index(out_dir, toc, template):
    groups = []
    parts = {p["title"]: p for p in toc.get("parts", [])}
    for ch in toc["chapters"]:
        g = ch.get("group") or ("Opening" if ch["n"] <= 2 else "Closing")
        if not groups or groups[-1]["title"] != g:
            part = parts.get(g)
            groups.append({"kicker": f"Part {spelled(part['part'])}" if part else "Chapters", "title": g,
                           "notes": "", "blocks": []})
            if part:
                groups[-1]["blocks"].append({"key": f"Part {part['part']}", "question": {
                    "question": "Introduction", "how": "", "originally": "", "notes": ""},
                    "views": [], "statements": [], "href": page_name(part)})
        groups[-1]["blocks"].append({"key": f"Ch {ch['n']:02d}", "question": {"question": ch["title"], "how": "",
                                     "originally": "", "notes": ""}, "views": [], "statements": [],
                                     "href": page_name(ch)})
    payload = {"head": {"title": "Architecting a Software Factory",
                        "subtitle": "One page per chapter: the argument first, then the evidence behind it."},
               "sections": groups, "index": None}
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(D.fill(template, "Research findings", payload))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--book", default=BOOK)
    ap.add_argument("--decks", default=DECKS)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lessons")
    ap.add_argument("--only", type=int, action="append", help="render just these chapter numbers")
    args = ap.parse_args(argv)
    if not os.path.exists(D.VIEWER):
        sys.exit(f"no viewer build at {D.VIEWER}: run `npm run build` in its folder first")
    with open(D.VIEWER, encoding="utf-8") as f:
        template = f.read()
    with open(os.path.join(args.book, "chapters.json"), encoding="utf-8") as f:
        toc = json.load(f)
    if args.only:
        unknown = sorted(set(args.only) - {ch["n"] for ch in toc["chapters"]})
        if unknown:
            sys.exit(f"--only {', '.join(map(str, unknown))}: no such chapter in chapters.json")
    os.makedirs(args.out, exist_ok=True)
    lessons = None
    if args.lessons:
        lessons = D.read_lessons(args.lessons)
        if not lessons:
            D.warn(f"--lessons {args.lessons}: no insight or hypothesis read from it")
    questions, diagrams, deck_known = load_decks(args.decks, lessons)
    # The book's own assets go first: a `Diagram N.M` ref must never fall through to a deck's tag.
    diagrams = book_diagrams() + diagrams
    merge(questions, toc.get("merged", {}))
    seen = {}
    for ch in toc["chapters"]:
        for q in ch["questions"]:
            if q in seen:
                D.warn(f"Q {q} is listed in chapters {seen[q]} and {ch['n']}; the page link goes to the last")
            seen[q] = ch["n"]
    shown = {f"Q {q}" for q in seen}
    for k in sorted(set(questions) - shown):
        D.warn(f"{k} is in a deck but no chapter shows it")
    for ch in toc["chapters"]:
        if not args.only or ch["n"] in args.only:
            part = part_before(toc, ch)
            if part:
                print(render_part(part, template, toc, args.book, args.out))
            print(render(ch, template, questions, diagrams, deck_known, toc, args.book, args.out))
    if os.path.exists(os.path.join(args.book, APPENDIX["book"])) and not args.only:
        print(render(appendix_chapter(toc, questions), template, questions, diagrams, deck_known, toc, args.book,
                     args.out))
    render_index(args.out, toc, template)
    if D.WARNINGS:
        print(f"{len(D.WARNINGS)} book warning(s) above: fix each before sharing the pages", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
