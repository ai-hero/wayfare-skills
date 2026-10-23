"""Build the one source every edition renders from: the manuscript parsed, every figure resolved
to a static file, and the metadata.

    ./publish source

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
from inline import NOTE_RE, XREF_RE, md_html, md_plain, plain_repos

sys.path.insert(0, paths.REPORT)
import deck_html as D  # noqa: E402

WARN = []
ERRORS = []
DEF_RE = re.compile(r"^\[\^([a-z0-9][a-z0-9-]*)\]:\s*(.+)$", re.S)


# The print book's and the Kindle edition's front matter and metadata need each of these; the other
# editions use some.
# photo, linkedin and x are optional and left out when unset; subtitle is optional too, but the
# print and Kindle title pages still set an empty line for it.
META_REQUIRED = ("title", "author", "affiliation", "email", "edition", "date", "year", "copyright")


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
    sections, sources, defs = [], [], {}
    for s in D.parse_book(text):
        if s["title"].lower() == "sources":
            for b in s["blocks"]:
                if b["kind"] != "p":
                    continue
                m = DEF_RE.match(b["text"])
                if m and m.group(1) in defs:
                    ERRORS.append(f"chapter {n}: source [^{m.group(1)}] is defined twice")
                elif m:
                    defs[m.group(1)] = m.group(2).strip()
                else:
                    # Not yet tied to a sentence: kept as a trailing note until someone cites it.
                    sources.append({"md": b["text"], "html": md_html(b["text"])})
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
            "sources": sources, "defs": defs}


def holders(b):
    """Every dict in a block that carries running text (`md`, and the `html` made from it)."""
    k = b["kind"]
    if k in ("p", "h3", "quote"):
        return [b]
    if k in ("ul", "ol"):
        return list(b["items"])
    if k == "table":
        return [c for r in b["rows"] for c in r]
    return []


def figure_index(chapters):
    idx = {}
    for c in chapters:
        for s in c["sections"]:
            for b in s["blocks"]:
                if b["kind"] != "figure" or b["type"] == "missing":
                    continue
                if b["type"] == "card":
                    idx[f"fig:{b['key'][2:]}"] = b
                elif b.get("id"):
                    idx[f"{b['label'].lower()}:{b['id']}"] = b
    return idx


def xref_html(m, idx, evidence, n):
    if m.group(1) == "ev":  # a supporting finding: an appendix entry with no figure in the chapter
        anchor = evidence.get(m.group(2))
        if not anchor:
            ERRORS.append(f"chapter {n}: {m.group(0)} matches no appendix entry")
            return m.group(0)
        return f'(<a class="evi-ref" href="#{anchor}">evidence</a>)'
    b = idx.get(f"{m.group(1)}:{m.group(2)}")
    if not b:
        ERRORS.append(f"chapter {n}: {m.group(0)} matches no figure in the book")
        return m.group(0)
    link = f'<a class="xref" href="#fig-{b["label"].lower()}-{b["number"].replace(".", "-")}">{b["label"]} {b["number"]}</a>'
    if m.group(3):
        return link
    anchor = evidence.get(b["key"][2:]) if b["type"] == "card" else None
    if not anchor:
        return f"({link})"
    return f'({link}; <a class="evi-ref" href="#{anchor}">evidence</a>)'


# A bracketed [n] sits inside the sentence, before its punctuation: `text [^key].`, never `text.[^key]`.
CITE_RUN = re.compile(r"\s?((?:\[\^[a-z0-9][a-z0-9-]*\])+)")
CITE_AFTER_PUNCT = re.compile(r"[.,;:!?][\"\u201d\u2019)]*\[\^(?!note-)")
URL_TOKEN = re.compile(r"(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+[a-z]{2,})(/[^\s<>,;)]*)?", re.I)
TITLE = re.compile(r"[\u201c\"]([^\u201d\"]+)[\u201d\"]|\*([^*]+)\*")


def source_ids(md):
    """What makes two differently worded entries one source: a shared URL, a shared long title, or a
    short title under the same surname. A bare apex domain (harness.io, warp.dev) names a company, not a
    source, and several of its sources cite it, so only a host with a subdomain counts on its own."""
    ids = set()
    for m in URL_TOKEN.finditer(md):
        host, path = m.group(1).lower(), (m.group(2) or "").rstrip("/.").lower()
        if path:
            ids.add(f"url:{host}{path}")
        elif host.count(".") >= 2:
            ids.add(f"url:{host}")
    t = TITLE.search(md)
    if t:
        title = re.sub(r"[^a-z0-9]", "", (t.group(1) or t.group(2)).split(":")[0].lower())
        lead = re.sub(r"\([^)]*\)", "", md[:t.start()].split(",")[0])
        words = re.findall(r"[A-Za-z\u00c0-\u017f]+", lead)
        surname = words[-1].lower() if words else ""
        if len(title) >= 24:
            ids.add(f"title:{title}")
        elif title:
            ids.add(f"title:{surname}:{title}")
    return ids


def build_references(chapters):
    """One reference list for the whole book, numbered in reading order: each chapter's cited sources in
    the order the text cites them, then its uncited ones. Chapters word the same source differently
    (each was edited on its own), so entries sharing a URL or title are one source and the first wording
    stands. Every edition prints these numbers. A `note-` key is the author's aside, a footnote instead."""
    entries, by_id, parent = [], {}, []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def add(md):
        i = len(entries)
        entries.append(md)
        parent.append(i)
        for x in source_ids(md) | {"text:" + re.sub(r"[^a-z0-9]", "", md_plain(md).lower())}:
            if x in by_id:
                a, b = find(by_id[x]), find(i)
                parent[max(a, b)] = min(a, b)
            else:
                by_id[x] = i
        return i

    touched = []
    for c in chapters:
        cited = {k: add(c["defs"][k]) for k in c["order"]}
        uncited = [add(c["defs"][k]) for k in c["defs"] if k not in cited and not k.startswith("note-")]
        touched.append((c, cited, uncited + [add(src["md"]) for src in c["sources"]]))
    numbers = {}

    def number(i):
        return numbers.setdefault(find(i), len(numbers) + 1)

    for c, cited, further in touched:
        c["cite_n"] = {k: number(i) for k, i in cited.items()}
        seen = set(c["cite_n"].values())
        c["further"] = [n for n in dict.fromkeys(number(i) for i in further) if n not in seen]
        c["refs"] = sorted(seen | set(c["further"]))
    return [{"n": n, "md": entries[root], "html": md_html(entries[root])}
            for root, n in sorted(numbers.items(), key=lambda x: x[1])]


def cite_label(ns):
    """`[3, 5–7]`: sorted, and a run of three or more compressed, as natbib prints the paper's."""
    ns, runs = sorted(set(ns)), []
    for n in ns:
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    link = lambda n: f'<a class="cite" href="#ref-{n}">{n}</a>'  # noqa: E731
    parts = [link(a) if a == b else f"{link(a)}, {link(b)}" if b == a + 1 else f"{link(a)}\u2013{link(b)}"
             for a, b in runs]
    return "[" + ", ".join(parts) + "]"


def resolve_markers(chapters, appendix):
    """Source markers become a bracketed [n] into the book's one reference list, and figure markers
    become a link to the figure and to its appendix entry. `md` keeps the markers (the technical
    edition resolves them itself); `html` is rewritten here. Returns the reference list."""
    evidence = {sl: e["anchor"] for p in appendix["parts"] for g in p["groups"] for e in g["entries"]
                for sl in e["slugs"]}
    idx = figure_index(chapters)
    texts = {}
    for c in chapters:
        n, defs, order = c["n"], c["defs"], []
        for s in c["sections"]:
            for b in s["blocks"]:
                for h in holders(b):
                    if CITE_AFTER_PUNCT.search(h["md"]):
                        ERRORS.append(f"chapter {n}: a source marker follows punctuation in "
                                      f"\"{CITE_AFTER_PUNCT.search(h['md']).group(0)}\"; write `text [^key].`")
                    for m in NOTE_RE.finditer(h["md"]):
                        if m.group(1) not in defs:
                            ERRORS.append(f"chapter {n}: [^{m.group(1)}] is cited but not defined under Sources")
                        elif m.group(1) not in order and not m.group(1).startswith("note-"):
                            order.append(m.group(1))
        for k in defs:
            if k not in order and not k.startswith("note-"):
                WARN.append(f"chapter {n}: source [^{k}] is defined but never cited")
            if texts.setdefault(k, defs[k]) != defs[k]:
                WARN.append(f"chapter {n}: source [^{k}] is worded differently than in an earlier chapter; "
                            "the reference list shows the first wording")
        c["order"] = order
    references = build_references(chapters)
    for c in chapters:
        n, defs = c["n"], c["defs"]

        def run(m):
            keys = NOTE_RE.findall(m.group(1))
            notes = "".join(f'<span class="fn" data-key="{k}">{defs[k]}</span>' for k in keys
                            if k.startswith("note-") and k in defs)
            ns = [c["cite_n"][k] for k in keys if k in c["cite_n"]]
            # The space before a [n] is a no-break space, so the bracket never starts a line alone.
            return ("\u00a0" + cite_label(ns) if ns else "") + notes
        for s in c["sections"]:
            for b in s["blocks"]:
                for h in holders(b):
                    h["html"] = md_html(CITE_RUN.sub(run, XREF_RE.sub(lambda m: xref_html(m, idx, evidence, n),
                                                                      h["md"])))
        del c["order"]
    return references


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


EXAMPLE_FLAGS = ("example", "example_start", "example_end")


def convert(b, n, cards, drawn, results, assets, counters):
    """A block inside a worked example (`parse_book` marks it) keeps its `example` flags whatever its kind."""
    out = convert_kind(b, n, cards, drawn, results, assets, counters)
    if out:
        out.update({f: True for f in EXAMPLE_FLAGS if b.get(f)})
    elif b.get("example_start") or b.get("example_end"):
        ERRORS.append(f"chapter {n}: a worked example starts or ends on a dropped {b['kind']} block")
    return out


def convert_kind(b, n, cards, drawn, results, assets, counters):
    k = b["kind"]
    if k == "p":
        text = b["text"]
        return {"kind": "p", "md": text, "html": md_html(text),
                "cites": sorted({D.qkey(m.group(0)) for m in D.Q_RE.finditer(text)})}
    if k == "h3":
        return {"kind": "h3", "md": b["text"], "html": md_html(b["text"])}
    if k == "quote":
        ERRORS.append(f"chapter {n}: blockquote \"{b['text'][:50]}...\"; use italics for your own line "
                      "or double quotes inline for someone else's")
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
    for key in ("chart_id", "evidence_ids"):
        if meta.get(key):
            out[key] = meta[key]
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
    if not out["files"]:
        warn(f"chapter {n}: {ref} has a sidecar but no svg, pdf or png in {paths.DIAGRAMS}")
        out["type"] = "missing"
    return out


LINK_ONLY = re.compile(r"^\[[^\]]+\]\([^)]+\)\.?$")
ENTRY = re.compile(r"^(?:(\d+\.\d+):\s*)?(.+)$")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+")


def build_appendix(chapters, cards, assets):
    """The editor's curated evidence appendix, one part per chapter, each entry with its chart.

    An entry headed `4.7: ci-cost-vs-change-sets` is a chapter figure's card, keyed by the figure
    pipeline's id; an inline card supplies its display label (`Figure 4.3`), while an appendix-only
    card keeps its evidence id without an inline label. A supporting entry
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
                    if rid and not label and not any(f"Q {slug}" in cards for slug in slugs):
                        warn(f"appendix {n}: {rid} has no retained analysis card")
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
            # A `##` section that is only paragraphs is a case record: it carries no `###` entry of its
            # own, so every edition would drop it. It becomes one entry under the section's heading.
            if group.get("intro") and not group["entries"]:
                group["entries"].append({"rid": None, "slugs": [], "title": "Case record", "label": None,
                                         "anchor": f"evidence-{slugify(group['title'])}",
                                         "blocks": group.pop("intro"), "charts": []})
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


# Two old names of one repository ("hero-skills, wayfare-skills") map to the same plain name twice.
DOUBLED = re.compile(r"\b([a-z]+(?:-[a-z]+)+)(`?),\s*`?\1\b`?")


def plain_figure_text(chapters, appendix):
    """The text written around a figure (its alt, source line and question notes, and the appendix's
    paragraphs) names repositories by their plain names, as the pictures do. The manuscript's prose is the
    owner's and is left as written; tables keep their cells, since there the original names are quoted
    data (and the repository table lists them on purpose). An appendix table's prose cells are mapped; a cell
    holding a JSON list or record is raw data and stays as recorded."""
    def fix(d, keys):
        for k in keys:
            if isinstance(d.get(k), str):
                d[k] = plain_repos(d[k])

    def figure(b):
        fix(b, ("alt", "source", "caption_md", "caption_html", "validation"))
        if isinstance(b.get("question"), dict):
            fix(b["question"], ("question", "how", "originally", "notes"))
    for c in chapters:
        for s in c["sections"]:
            for b in s["blocks"]:
                if b["kind"] == "figure":
                    figure(b)
    for p in appendix["parts"]:
        for g in p["groups"]:
            fix(g, ("title", "html"))
            for e in g["entries"]:
                fix(e, ("title",))
                for b in e["blocks"]:
                    if b["kind"] != "table":
                        fix(b, ("md", "html"))
                        continue
                    for cell in (c for r in b["rows"] for c in r):
                        if not cell["md"].lstrip().startswith(("[", "{")):
                            cell["md"] = DOUBLED.sub(r"\1", plain_repos(cell["md"]))
                            cell["html"] = md_html(cell["md"])
                for ch in e["charts"]:
                    figure(ch)


def build_preface():
    """The front matter's preface, from `preface.md` beside the chapters; None without the file."""
    if not os.path.exists(paths.PREFACE):
        return None
    with open(paths.PREFACE, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^# (.+)$", text, re.M)
    blocks = [{"kind": "p", "md": b["text"], "html": md_html(b["text"])}
              for s in D.parse_book(text) for b in s["blocks"] if b["kind"] == "p"]
    return {"title": m.group(1).strip() if m else "Preface", "blocks": blocks}


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
    missing = [k for k in META_REQUIRED if not meta.get(k)]
    if missing:
        raise SystemExit(f"source: {paths.META} lacks {', '.join(missing)}; the front matter would print blank")
    words = sum(len(md_plain(b.get("md", "")).split()) for c in chapters for s in c["sections"] for b in s["blocks"])
    appendix = build_appendix(chapters, cards, assets)
    references = resolve_markers(chapters, appendix)
    plain_figure_text(chapters, appendix)
    if ERRORS:
        raise SystemExit("source: " + "\n  ".join(["fix these markers:"] + ERRORS))
    doc = {"meta": meta, "preface": build_preface(), "chapters": chapters, "appendix": appendix,
           "references": references, "words": words, "warnings": WARN}
    with open(os.path.join(build, "book.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    figs = sum(1 for c in chapters for s in c["sections"] for b in s["blocks"] if b["kind"] == "figure")
    entries = sum(len(g["entries"]) for p in appendix["parts"] for g in p["groups"])
    charts = sum(len(e["charts"]) for p in appendix["parts"] for g in p["groups"] for e in g["entries"])
    print(f"source: {len(chapters)} chapters, {figs} figures, appendix {entries} entries with {charts} charts, "
          f"~{words:,} words, {len(WARN)} warnings -> {build}")


if __name__ == "__main__":
    main()
