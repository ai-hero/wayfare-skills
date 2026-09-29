"""Print a chapter's figure appendix: one figure line per question the chapter lists, for the owner to move
into the prose where a figure earns its place.

    python report/book_figures.py [--book .analysis/book] [--decks .analysis/decks] --chapter N [--write]
    python report/book_figures.py --all [--previous _old/pre-manuscript-2026-09-28]

Each line is `[[Q slug | title]]` followed by an HTML comment with the question and its verdict; the page
builder strips the comment and renders the card. With --write, the block replaces the chapter's `## Figures`
section, or is appended before `## Sources` when there is none.

--all writes `_FIGURES_APPENDIX.md` in the book folder: every card and diagram the decks hold, by chapter,
each with its figure line, what it asks, what its charts show, a one-line TL;DR, its verdict, where the
previous draft placed it and where the current text cites it. It is the brief for an agent placing figures
into the manuscript, and book_pages.py renders it as the Appendix page after the chapters.
"""
import argparse
import json
import os
import re
import sys

import book_pages as B
import book_place as P
import deck_html as D


def appendix(ch, questions, verdicts):
    lines = ["## Figures", "",
             "Every figure this chapter's data holds, by id. Move a line up into the prose where the argument needs it; "
             "what stays here is the appendix.", ""]
    for q in ch["questions"]:
        k = f"Q {q}"
        if k not in questions:
            D.warn(f"ch{ch['n']:02d}: {k} is in no deck")
            continue
        b = questions[k]["block"]
        title = (b["views"][0].get("title") if b["views"] else "") or (b.get("question") or {}).get("question") or q
        v = verdicts.get(q, {})
        note = f"{(b.get('question') or {}).get('question', '')} Verdict: {v.get('verdict', '?')}."
        lines += [f"[[{k} | {title}]]", f"<!-- {note.strip()} -->", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def scan_refs(book_dir, files):
    """Where each question and diagram is referred to: {ref: [(chapter file, section, figure label)]}."""
    refs = {}
    for f in files:
        path = os.path.join(book_dir, f)
        if not os.path.exists(path):
            continue
        sec = None
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^## (.+)", line)
                if m:
                    sec = m.group(1).strip()
                    continue
                fig = re.match(r"^\[\[(Figure[^|\]]*?)(?:\s*\||\]\])", line)
                label = fig.group(1).strip().rstrip(":") if fig else None
                for m in re.finditer(r"\[\[Q ([a-z0-9-]+)(?: · [^|\]]+)?\s*(?:\|\s*([^\]]*))?\]\]", line):
                    refs.setdefault(m.group(1), []).append((f, sec, label, (m.group(2) or "").strip()))
                if fig or not line.startswith("[["):
                    for m in re.finditer(r"(?<!\[\[)\bQ ([a-z0-9-]+)", line):
                        refs.setdefault(m.group(1), []).append((f, sec, label, ""))
                m = re.match(r"^\[\[([A-Z][^|\]]*?)\s*(?:\|\s*([^\]]*))?\]\]", line)
                if m and not m.group(1).startswith("Figure"):
                    refs.setdefault(m.group(1).strip().upper(), []).append((f, sec, None, (m.group(2) or "").strip()))
    return refs


def where(refs, key, in_prose_only=False):
    seen, out = set(), []
    for f, sec, label, _ in refs.get(key, []):
        if in_prose_only and sec == "Figures":
            continue
        spot = f.split("-", 1)[0].lstrip("0")
        spot = f"Ch {spot}" + (f", {sec}" if sec else "")
        if label:
            spot += f" ({label})"
        if spot not in seen:
            seen.add(spot)
            out.append(spot)
    return out


def tldr(q, refs_prev, b):
    """The finding the previous draft put in the prose beside the card, else the card's headline."""
    for _, sec, _, caption in refs_prev.get(q, []):
        if sec != "Figures" and caption:
            return caption
    views = b["views"]
    return (views[0].get("title") if views else "") or q


def card_entry(k, entry, verdicts, refs_prev, refs_now, merged_into):
    """Plain paragraphs, one per field: the page builder joins bullet lines into one paragraph and
    renders no inline Markdown, so bullets and bold would reach the page as literal dashes and stars."""
    b, q = entry["block"], k[2:]
    qq = b.get("question") or {}
    line = tldr(q, refs_prev, b)
    out = [f"### {k}", "", f"[[{k} | {line}]]", "", f"TL;DR: {line}", "", f"Asks: {qq.get('question', '')}", ""]
    if qq.get("how"):
        out += [f"How: {qq['how']}", ""]
    n = len(b["views"])
    out += [f"Shows {n} chart{'s' if n != 1 else ''} (deck {entry['deck']}):", ""]
    for i, v in enumerate(b["views"]):
        label = v.get("label") or (v.get("tag") or "").split(" · ")[-1].title()
        pts = " ".join(v.get("points", [])) if i == 0 else ""
        out += [f"{label}: {v.get('title', '')}" + (f" {pts}" if pts else ""), ""]
    src = (b["views"][0].get("source") if b["views"] else "") or ""
    if src:
        out += [f"Source data: {src}", ""]
    v = verdicts.get(q, {})
    out += [f"Verdict: {v.get('verdict', '?')}" + (f" ({v['basis']})" if v.get("basis") else ""), ""]
    for m in merged_into.get(q, []):
        out += [f"Also holds Q {m['id']} as the view \"{m['label']}\".", ""]
    prev = where(refs_prev, q, in_prose_only=True)
    now = where(refs_now, q)
    out += ["Previous draft placed it: " + ("; ".join(prev) if prev else "appendix only") + ". "
            "Current text cites it: " + ("; ".join(now) if now else "nowhere") + ".", ""]
    return out


def placed_section(book_dir):
    """The figures the owner's brief selects, with the ref and caption each result gave and the Origin
    diagrams each replaces: the reconciliation the brief's checklist asks for, ahead of the inventory."""
    path = os.path.join(book_dir, "figures.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)
    results = P.load_results(book_dir)
    out = ["## Figures in the manuscript", "",
           f"The {len(manifest)} entries of `_FIGURES_BRIEF.md`, each with the card or asset that answers it. "
           "A Chapter 1 entry drawn once is listed under the diagram that carries it.", ""]
    for e in manifest:
        if "error" in e:
            D.warn(f"figures.json: {e['kind']} {e['id']} has no placement ({e['error']})")
            continue
        if e["kind"] == "figure" and e["id"] in P.MERGED:
            out += [f"{e['kind'].capitalize()} {e['id']} — {e['title']}: drawn once as {P.MERGED[e['id']]}.", ""]
            continue
        r = results.get(P.rkey(e))
        if not r:
            out += [f"{e['kind'].capitalize()} {e['id']} — {e['title']}: not yet regenerated.", ""]
            continue
        out += [f"{e['kind'].capitalize()} {e['id']} — {e['title']}", "", f"[[{r['ref']} | {r.get('caption', '')}]]", "",
                f"Asks: {e['question']}", "", f"Placed: Chapter {e['chapter']}, {e['section']}.", ""]
        if r.get("source"):
            out += [f"Source: {r['source']}", ""]
        if e["kind"] == "figure" and r.get("validation"):
            out += [f"Validation: {r['validation']}", ""]
        if e["kind"] != "figure" and e.get("origin"):
            out += [f"Replaces: {e['origin']}", ""]
    return out


def all_appendix(book_dir, toc, questions, diagrams, verdicts, previous):
    files = [c["book"] for c in toc["chapters"]]
    refs_now = scan_refs(book_dir, files)
    refs_prev = scan_refs(os.path.join(book_dir, previous), files)
    merged_into = {}
    for m, spec in toc.get("merged", {}).items():
        merged_into.setdefault(spec["into"], []).append({"id": m, "label": spec["label"]})
    out = ["# Figures appendix", "", "",
           "Every image the decks hold, by the chapter that owns it. A card is one question with one or more charts; "
           "the reader sees the whole card where the prose places its figure line. Diagrams are drawn, not computed.", "",
           "Each entry opens with its figure line, `[[Q slug | finding]]`: paste that line on its own into a chapter to "
           "place the card there. TL;DR is the one-line finding to put beside the figure; Asks is the question the "
           "card answers; Shows lists its charts with the headline of each and the answer chart's points. Previous "
           f"draft placed it is where `{previous}` had the card in the prose; Current text cites it is where the "
           "manuscript refers to the question today, and a Figure N label there means the owner asked for a figure "
           "built from it.", ""]
    out += placed_section(book_dir)
    total = 0
    for ch in toc["chapters"]:
        out += [f"## Chapter {ch['n']}: {ch['title']} ({len(ch['questions'])} cards)", ""]
        for q in ch["questions"]:
            k = f"Q {q}"
            if k not in questions:
                D.warn(f"ch{ch['n']:02d}: {k} is in no deck")
                continue
            total += 1
            out += card_entry(k, questions[k], verdicts, refs_prev, refs_now, merged_into)
    listed = {q for c in toc["chapters"] for q in c["questions"]} | set(toc.get("merged", {}))
    loose = sorted(k for k in questions if k[2:] not in listed)
    if loose:
        out += [f"## In a deck but in no chapter ({len(loose)} cards)", ""]
        for k in loose:
            total += 1
            out += card_entry(k, questions[k], verdicts, refs_prev, refs_now, merged_into)
    out += [f"## Diagrams ({len(diagrams)})", "",
            "Referenced from the prose as `[[TAG]]` or `[[TAG | caption]]`, TAG being the text after `DIAGRAM · ` "
            "in the deck. Tags repeat across decks; a chapter resolves the one from the deck its questions come from.", ""]
    for d in diagrams:
        v = d["block"]["views"][0]
        tag = (v.get("tag") or "").replace("DIAGRAM · ", "")
        ref = tag.split(" · ")[-1]
        out += [f"### {tag}", "", f"[[{ref} | {v.get('title', '')}]]", "", f"TL;DR: {v.get('title', '')}", "",
                f"Deck {d['deck']}" + (", with a drawn image." if v.get("images") else ", text only, no image."), ""]
        pts = v.get("points", [])
        if pts:
            out += ["Shows: " + " ".join(pts), ""]
        now = where(refs_now, ref) + where(refs_now, tag)
        prev = where(refs_prev, ref) + where(refs_prev, tag)
        out += ["Previous draft placed it: " + ("; ".join(dict.fromkeys(prev)) if prev else "nowhere") + ". "
                "Current text cites it: " + ("; ".join(dict.fromkeys(now)) if now else "nowhere") + ".", ""]
    out[2] = f"{total} cards and {len(diagrams)} diagrams.\n"
    return "\n".join(out).rstrip("\n") + "\n"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--book", default=B.BOOK)
    ap.add_argument("--decks", default=B.DECKS)
    ap.add_argument("--chapter", type=int)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--all", action="store_true", help="write _FIGURES_APPENDIX.md with every card and diagram")
    ap.add_argument("--previous", default="_old/pre-manuscript-2026-09-28",
                    help="draft, relative to --book, whose figure placements the appendix reports")
    args = ap.parse_args(argv)
    with open(os.path.join(args.book, "chapters.json"), encoding="utf-8") as f:
        toc = json.load(f)
    with open(os.path.join(args.book, "verdicts.json"), encoding="utf-8") as f:
        verdicts = json.load(f)["questions"]
    questions, diagrams, _ = B.load_decks(args.decks)
    B.merge(questions, toc.get("merged", {}))
    if args.all:
        path = os.path.join(args.book, "_FIGURES_APPENDIX.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(all_appendix(args.book, toc, questions, diagrams, verdicts, args.previous))
        print(path)
        return
    ch = next((c for c in toc["chapters"] if c["n"] == args.chapter), None)
    if ch is None:
        sys.exit(f"no chapter {args.chapter} in chapters.json")
    block = appendix(ch, questions, verdicts)
    if not args.write:
        print(block)
        return
    path = os.path.join(args.book, ch["book"])
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if re.search(r"^## Figures$", text, re.M):
        text = re.sub(r"^## Figures$.*?(?=^## |\Z)", block + "\n", text, count=1, flags=re.M | re.S)
    elif re.search(r"^## Sources$", text, re.M):
        text = re.sub(r"^## Sources$", block + "\n## Sources", text, count=1, flags=re.M)
    else:
        text = text.rstrip("\n") + "\n\n" + block
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"{path}: {len(ch['questions'])} figure lines")


if __name__ == "__main__":
    main(sys.argv[1:])
