"""Build the one source every edition renders from: the manuscript parsed, every figure resolved
to a static file, and the metadata.

    publishing/publish source

Writes `$PUBLISH_OUT/build/book.json` and `$PUBLISH_OUT/build/assets/`. The manuscript is read
with the editor's own parser (`deck_html.parse_book`), so a figure line means here exactly what it
means in the editor. Nothing here edits the manuscript: a figure that will not resolve is a
warning and a placeholder, and the fix belongs in the book or its figure pipeline.
"""
import base64
import glob
import json
import os
import re
import shutil
import sys

import paths
from inline import md_html, md_plain

sys.path.insert(0, paths.REPORT)
import deck_html as D  # noqa: E402

WARN = []


def warn(msg):
    WARN.append(msg)
    print(f"warn: {msg}", file=sys.stderr)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", md_plain(text).lower()).strip("-")


def sidecars():
    """Drawn diagrams, figures and tables keyed `diagram 1.5`, `figure 5.1`, `table 7.T1`."""
    out = {}
    for path in sorted(glob.glob(os.path.join(paths.DIAGRAMS, "*.json"))):
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("id") and meta.get("name"):
            out[f"{meta.get('kind', 'diagram')} {meta['id']}".lower()] = meta
    return out


def results_by_ref():
    """The figure agents' sidecars (alt text, source, validation) keyed by `Q slug`."""
    out = {}
    for path in glob.glob(os.path.join(paths.BOOK, "results", "*.json")):
        with open(path, encoding="utf-8") as f:
            r = json.load(f)
        out.setdefault(r["ref"].strip(), r)
    return out


def copy_drawn(meta, assets):
    files = {}
    for ext in ("svg", "pdf", "png"):
        src = os.path.join(paths.DIAGRAMS, f"{meta['name']}.{ext}")
        if os.path.exists(src):
            dst = f"{meta['name']}.{ext}"
            shutil.copyfile(src, os.path.join(assets, dst))
            files[ext] = dst
    return files


def table_rows(meta):
    src = os.path.join(paths.DIAGRAMS, f"{meta['name']}.md")
    rows = []
    with open(src, encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
    return rows


def card_files(view, name, assets):
    """A card's answer view as files: the deck's own picture when it has one, else its chart data
    drawn by `charts.draw`. The deck is the authority because the editor shows the same view."""
    images = view.get("images") or []
    if images:
        src = images[0]["src"]
        head, _, data = src.partition(",")
        ext = "svg" if "svg" in head else "png"
        dst = f"{name}.{ext}"
        with open(os.path.join(assets, dst), "wb") as f:
            f.write(base64.b64decode(data))
        return {ext: dst}
    if view.get("charts"):
        import charts
        return charts.draw(view["charts"], os.path.join(assets, name))
    return {}


def load_cards():
    sys.path.insert(0, paths.REPORT)
    import book_pages as B
    questions, _, _ = B.load_decks(paths.DECKS)
    return questions


def build_chapter(ch, cards, drawn, results, assets, counters):
    with open(os.path.join(paths.BOOK, ch["book"]), encoding="utf-8") as f:
        text = f.read()
    title = re.search(r"^# (.+)$", text, re.M).group(1).strip()
    n = ch["n"]
    sections, sources = [], []
    for s in D.parse_book(text):
        if s["title"].lower() == "sources":
            sources = [{"md": b["text"], "html": md_html(b["text"])} for b in s["blocks"] if b["kind"] == "p"]
            continue
        blocks = []
        for b in s["blocks"]:
            blk = convert(b, n, cards, drawn, results, assets, counters)
            if blk:
                blocks.append(blk)
        if blocks or s["title"]:
            sections.append({"title": s["title"], "html": md_html(s["title"]) if s["title"] else "",
                             "slug": slugify(s["title"]) if s["title"] else "opening", "blocks": blocks})
    return {"n": n, "slug": ch["slug"], "title": title, "file": ch["book"], "sections": sections,
            "sources": sources}


def unescape_pipes(cells):
    """parse_book splits a row on every `|`, including Markdown's escaped `\\|` inside a cell; rejoin
    those pieces so a cell reading `a | b` stays one cell."""
    out = []
    for c in cells:
        if out and out[-1].endswith("\\"):
            out[-1] = out[-1][:-1] + "|" + c
        else:
            out.append(c)
    return [c.strip() for c in out]


def convert(b, n, cards, drawn, results, assets, counters):
    k = b["kind"]
    if k == "p":
        return {"kind": "p", "md": b["text"], "html": md_html(b["text"]),
                "cites": sorted({D.qkey(m.group(0)) for m in D.Q_RE.finditer(b["text"])})}
    if k == "h3":
        return {"kind": "h3", "md": b["text"], "html": md_html(b["text"])}
    if k == "quote":
        return {"kind": "quote", "md": b["text"], "html": md_html(b["text"])}
    if k in ("ul", "ol"):
        return {"kind": k, "items": [{"md": i, "html": md_html(i)} for i in b["items"]]}
    if k == "table":
        return {"kind": "table", "rows": [[{"md": c, "html": md_html(c)} for c in unescape_pipes(r)]
                                          for r in b["rows"]]}
    if k == "figure":
        return figure(b, n, cards, drawn, results, assets, counters)
    warn(f"chapter {n}: unknown block kind {k}")
    return None


def figure(b, n, cards, drawn, results, assets, counters):
    ref, caption = b["ref"].strip(), b["caption"]
    kind_word, _, ident = ref.partition(" ")
    out = {"kind": "figure", "ref": ref, "caption_md": caption, "caption_html": md_html(caption),
           "files": {}, "alt": "", "source": "", "question": "", "width": None, "height": None}
    if D.qkey(ref):
        counters["figure"] += 1
        key = D.qkey(ref)
        out.update(type="card", key=key, label="Figure", number=f"{n}.{counters['figure']}")
        card = cards.get(key)
        if not card:
            warn(f"chapter {n}: {ref} is in no deck")
            out["type"] = "missing"
            return out
        block = card["block"]
        view = block["views"][0]
        slug = key[2:]
        out["files"] = card_files(view, f"card-{slug}", assets)
        out["question"] = block.get("question") or ""
        out["source"] = view.get("source") or ""
        r = results.get(key)
        if r:
            out["rid"] = r["id"]
            out["alt"] = r.get("alt", "")
            out["source"] = r.get("source") or out["source"]
            out["validation"] = r.get("validation", "")
        if not out["files"]:
            warn(f"chapter {n}: {ref} has no picture or chart data in its deck view")
            out["type"] = "missing"
        return out
    meta = drawn.get(ref.lower())
    if not meta:
        warn(f"chapter {n}: [[{ref}]] matches no drawn asset in {paths.DIAGRAMS}")
        out.update(type="missing", label=kind_word, number=ident)
        return out
    out.update(alt=meta.get("alt", ""), source=meta.get("source", ""), width=meta.get("width"),
               height=meta.get("height"))
    if meta.get("kind") == "table":
        counters["table"] += 1
        out.update(type="table", label="Table", number=f"{n}.{counters['table']}", id=meta["id"],
                   rows=[[{"md": c, "html": md_html(c)} for c in r] for r in table_rows(meta)])
        return out
    if meta.get("kind") == "figure":
        counters["figure"] += 1
        number = f"{n}.{counters['figure']}"
        if number != meta["id"]:
            warn(f"chapter {n}: authored Figure {meta['id']} falls at position {number} among the chapter's figures")
        out.update(type="drawn", label="Figure", number=number, id=meta["id"])
    else:
        out.update(type="diagram", label="Diagram", number=meta["id"], id=meta["id"])
    out["files"] = copy_drawn(meta, assets)
    return out


LINK_ONLY = re.compile(r"^\[[^\]]+\]\([^)]+\)\.?$")
ENTRY = re.compile(r"^(?:(\d+\.\d+):\s*)?(.+)$")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+")


def build_appendix(chapters, cards, assets):
    """The editor's curated evidence appendix, one part per chapter, each entry with its chart.

    An entry headed `4.7: ci-cost-vs-change-sets` is a chapter figure's card, keyed by the figure
    pipeline's id; it is tied to the number the reader sees on the figure (`Figure 4.3`), because
    the ids follow the figures brief, not the order the chapter places them in. A supporting entry
    is headed by its question slugs and carries those cards' charts. Lines that are only a link
    point at files inside this repository (numerical tables, the historical cards) that a reader of
    an edition cannot open, so they are kept as `link` blocks for editions to drop.
    """
    shown = {b["rid"]: (c["n"], f'{b["label"]} {b["number"]}') for c in chapters for s in c["sections"]
             for b in s["blocks"] if b["kind"] == "figure" and b.get("rid")}
    parts = []
    for path in sorted(glob.glob(os.path.join(paths.APPENDIX, "[0-9][0-9]-evidence.md"))):
        n = int(os.path.basename(path)[:2])
        with open(path, encoding="utf-8") as f:
            text = f.read()
        groups = []
        for s in D.parse_book(text):
            if not s["title"]:
                continue
            group = {"title": s["title"], "html": md_html(s["title"]), "entries": []}
            for b in s["blocks"]:
                if b["kind"] == "h3":
                    rid, rest = ENTRY.match(b["text"].strip()).groups()
                    names = [x.strip() for x in rest.split(",")]
                    # A heading of question slugs names cards; anything else is a written entry's title.
                    slugs = names if all(SLUG.fullmatch(x) for x in names) else []
                    title = None if slugs else b["text"].strip()
                    ch, label = shown.get(rid, (None, None))
                    if rid and not label:
                        warn(f"appendix {n}: {rid} matches no figure the chapters show")
                    entry = {"rid": rid, "slugs": slugs, "title": title, "label": label,
                             "anchor": f"evidence-{slugs[0] if slugs else slugify(title)}",
                             "blocks": [], "charts": []}
                    for slug in slugs:
                        card = cards.get(f"Q {slug}")
                        if not card:
                            warn(f"appendix {n}: Q {slug} is in no deck; its entry has no chart")
                            continue
                        files = card_files(card["block"]["views"][0], f"appendix-{slug}", assets)
                        if files:
                            entry["charts"].append({"slug": slug, "files": files,
                                                    "question": card["block"].get("question") or ""})
                    group["entries"].append(entry)
                    continue
                if not group["entries"]:
                    group.setdefault("intro", []).append(convert_text(b))
                    continue
                blk = convert_text(b)
                if blk:
                    group["entries"][-1]["blocks"].append(blk)
            groups.append(group)
        title = next((c["title"] for c in chapters if c["n"] == n), "")
        parts.append({"n": n, "title": title, "groups": groups})
    intro = []
    readme = os.path.join(paths.APPENDIX, "README.md")
    if os.path.exists(readme):
        with open(readme, encoding="utf-8") as f:
            for s in D.parse_book(f.read()):
                intro += [convert_text(b) for b in s["blocks"] if b["kind"] == "p"]
    return {"intro": [b for b in intro if b and b["kind"] == "p"], "parts": parts}


def convert_text(b):
    if b["kind"] == "p" and LINK_ONLY.match(b["text"].strip()):
        return {"kind": "link", "md": b["text"], "html": md_html(b["text"])}
    if b["kind"] in ("p", "h3", "quote", "ul", "ol", "table"):
        return convert(b, 0, {}, {}, {}, None, None)
    return None


def main():
    with open(os.path.join(paths.BOOK, "chapters.json"), encoding="utf-8") as f:
        toc = json.load(f)["chapters"]
    build = os.path.join(paths.OUT, "build")
    assets = os.path.join(build, "assets")
    shutil.rmtree(assets, ignore_errors=True)
    os.makedirs(assets)
    cards, drawn, results = load_cards(), sidecars(), results_by_ref()
    chapters = []
    for ch in toc:
        chapters.append(build_chapter(ch, cards, drawn, results, assets, {"figure": 0, "table": 0}))
    with open(paths.META, encoding="utf-8") as f:
        meta = json.load(f)
    words = sum(len(md_plain(b.get("md", "")).split()) for c in chapters for s in c["sections"] for b in s["blocks"])
    appendix = build_appendix(chapters, cards, assets)
    doc = {"meta": meta, "chapters": chapters, "appendix": appendix, "words": words, "warnings": WARN}
    with open(os.path.join(build, "book.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    figs = sum(1 for c in chapters for s in c["sections"] for b in s["blocks"] if b["kind"] == "figure")
    entries = sum(len(g["entries"]) for p in appendix["parts"] for g in p["groups"])
    charts = sum(len(e["charts"]) for p in appendix["parts"] for g in p["groups"] for e in g["entries"])
    print(f"source: {len(chapters)} chapters, {figs} figures, appendix {entries} entries with {charts} charts, "
          f"~{words:,} words, {len(WARN)} warnings -> {build}")


if __name__ == "__main__":
    main()
