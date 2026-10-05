"""The print book: book.json set as a 7 x 10 in colour book through WeasyPrint.

    ./publish book          -> $PUBLISH_OUT/dist/book.pdf

Layout lives in `book/book.css`; this module only writes semantic HTML. A layout fault is fixed
there or here, never in the PDF.
"""
import html
import json
import os
import re

import paths
from inline import md_plain

HERE = os.path.join(paths.HERE, "book")

ONES = ("Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen Fifteen "
        "Sixteen Seventeen Eighteen Nineteen Twenty").split()

# The design system's faces, from files rather than a system lookup, so two machines set the
# same book. Manrope (OFL) is not vendored anywhere in the fleet, so it is fetched once.
DS_FONTS = os.path.join(paths.WORKSPACE, "aihero-design-system-design", "fonts")
FONTS = {
    "Geist": os.path.join(DS_FONTS, "Geist-VariableFont_wght.ttf"),
    "Geist Mono": os.path.join(DS_FONTS, "GeistMono-VariableFont_wght.ttf"),
    "Manrope": os.path.join(paths.OUT, "fonts", "Manrope[wght].ttf"),
}
GEIST_ITALIC = os.path.join(paths.WEBSITE, "ui", "node_modules", "@fontsource-variable", "geist", "files",
                            "geist-latin-wght-italic.woff2")
MANROPE_URL = "https://github.com/google/fonts/raw/main/ofl/manrope/Manrope%5Bwght%5D.ttf"


def esc(s):
    return html.escape(s or "", quote=True)


def font_faces():
    if not os.path.exists(FONTS["Manrope"]):
        import urllib.request
        os.makedirs(os.path.dirname(FONTS["Manrope"]), exist_ok=True)
        urllib.request.urlretrieve(MANROPE_URL, FONTS["Manrope"])
    missing = [p for p in FONTS.values() if not os.path.exists(p)]
    if missing:
        raise SystemExit("book: missing font files: " + ", ".join(missing))
    faces = [f'@font-face {{ font-family: "{name}"; src: url("file://{path}"); font-weight: 100 900; }}'
             for name, path in FONTS.items()]
    # The design system ships no italic; the website's Geist package has the drawn one, which
    # beats WeasyPrint slanting the upright.
    if os.path.exists(GEIST_ITALIC):
        faces.append(f'@font-face {{ font-family: "Geist"; font-style: italic; src: url("file://{GEIST_ITALIC}"); '
                     f'font-weight: 100 900; }}')
    return "\n".join(faces)


TABLE_W, TABLE_H = 7.45, 6.0
_TABLES = {}


def table_svg(b, cap):
    """A table too wide for the measure, set on its own landscape page and turned a quarter
    counter-clockwise (its top toward the spine on a verso, the book convention) as vector SVG.
    A long table runs on to further turned pages with its header repeated."""
    if fig_id(b) in _TABLES:
        return _TABLES[fig_id(b)]
    import fitz
    from weasyprint import HTML
    rows = b["rows"]
    head = "".join(f"<th>{c['html']}</th>" for c in rows[0])
    body = []
    for r in rows[1:]:
        if all(not c["md"] for c in r[1:]):
            body.append(f'<tr class="group"><td colspan="{len(r)}">{r[0]["html"]}</td></tr>')
        else:
            body.append("<tr>" + "".join(f"<td>{c['html']}</td>" for c in r) + "</tr>")
    with open(os.path.join(HERE, "table.css"), encoding="utf-8") as f:
        css = f.read()
    page = (f'<!doctype html><html lang="en"><head><style>{font_faces()}\n'
            f'@page {{ size: {TABLE_W}in {TABLE_H}in; margin: 0; }}\n{css}</style></head><body>'
            f'<table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>{cap}</body></html>')
    pdf = fitz.open(stream=HTML(string=page).write_pdf(), filetype="pdf")
    out = os.path.join(paths.BUILD, "book")
    os.makedirs(out, exist_ok=True)
    files = []
    for i, pg in enumerate(pdf):
        path = os.path.join(out, f"{fig_id(b)}-{i + 1}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(pg.get_svg_image(matrix=fitz.Matrix(0, -1, 1, 0, 0, pg.rect.width), text_as_path=True))
        files.append(path)
    _TABLES[fig_id(b)] = files
    return files


EVIDENCE = {}  # figure-pipeline id -> appendix anchor, filled by render_html


def figure(b, max_px=None):
    label = f'{b["label"]} {b["number"]}'
    fid = fig_id(b)
    anchor = EVIDENCE.get(b.get("rid"))
    ptr = f' <a class="evidence-ptr" href="#{anchor}">Evidence</a>' if anchor else ""
    cap = (f'<figcaption><span class="fig-label">{esc(label)}</span> {b["caption_html"]}{ptr}</figcaption>')
    if b["type"] == "table":
        alt = esc(md_plain(b["caption_md"]))
        pages = "".join(f'<div class="table-page"><img src="file://{p}" alt="{alt}"/></div>'
                        for p in table_svg(b, cap))
        return f'<figure class="table-figure" id="{fid}">{pages}</figure>'

    files = b.get("files") or {}
    src = files.get("svg") if b["type"] in ("diagram", "drawn") else files.get("png") or files.get("svg")
    src = src or files.get("png")
    if not src:
        return f'<figure class="missing" id="{fid}"><div class="placeholder">{esc(b["ref"])}</div>{cap}</figure>'
    kind = "diagram" if b["type"] in ("diagram", "drawn") else "chart"
    style = f' style="max-height: {max_px:.0f}px"' if max_px else ""
    return (f'<figure class="{kind}" id="{fid}"><img src="{esc(src)}" alt="{esc(b.get("alt"))}"{style}/>'
            f'{cap}</figure>')


def block(b, shrink=None, key=None):
    k = b["kind"]
    if k == "p":
        return f'<p id="{key}">{b["html"]}</p>' if key else f"<p>{b['html']}</p>"
    if k == "h3":
        return f"<h3>{b['html']}</h3>"
    if k == "quote":
        return f"<blockquote><p>{b['html']}</p></blockquote>"
    if k in ("ul", "ol"):
        return f"<{k}>" + "".join(f"<li>{i['html']}</li>" for i in b["items"]) + f"</{k}>"
    if k == "table":
        rows = b["rows"]
        head = "".join(f"<th>{c['html']}</th>" for c in rows[0])
        body = "".join("<tr>" + "".join(f"<td>{c['html']}</td>" for c in r) + "</tr>" for r in rows[1:])
        return f'<table class="prose-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
    if k == "figure":
        return figure(b, (shrink or {}).get(fig_id(b)))
    return ""


def fig_id(b):
    return f'fig-{b["label"].lower()}-{b["number"].replace(".", "-")}'


def mentioned_at(blocks, b):
    """Index of the first block in the section that names the figure by number ("Diagram 5.1"),
    or None. A figure may move up to just after that mention, never above it."""
    name = f'{b["label"]} {b["number"]}'
    pat = re.compile(re.escape(name) + r"(?![\d.])")
    for i, x in enumerate(blocks):
        if x is not b and x["kind"] in ("p", "quote", "ul", "ol") and pat.search(
                x.get("html", "") + " ".join(it["html"] for it in x.get("items", []))):
            return i
    return None


def place(blocks, defer):
    """Move each figure `defer[id]` blocks later (or, negative, earlier) in its section: a page
    float, done by hand because WeasyPrint has none. A move never crosses a heading (the section's
    `###` subheads included). Whether an earlier position is allowed depends on where the pages
    break, so `violations` checks it against the layout: the figure may not sit on an earlier
    two-page spread than the paragraph that introduces it."""
    out = list(blocks)
    for b in reversed([x for x in blocks if x["kind"] == "figure" and defer.get(fig_id(x))]):
        j = out.index(b)
        out.pop(j)
        heads = [i for i, x in enumerate(out) if x["kind"] == "h3"]
        hi = min([i for i in heads if i >= j] or [len(out)])
        lo = max([i + 1 for i in heads if i < j] or [0])
        out.insert(max(lo, min(j + defer[fig_id(b)], hi)), b)
    return out


def chapter(c, defer, shrink, splits=None):
    """`splits` floats a figure to the top of the next page the way a typesetter would: the figure
    goes after the sentence where the page breaks, and the paragraph carries on after it."""
    splits = splits or {}
    at = {pkey: (fid, cut) for fid, (pkey, cut) in splits.items()}
    out = [f'<section class="chapter" id="ch-{c["n"]}">',
           f'<header class="opener"><p class="chapter-number">Chapter {ONES[c["n"]]}</p>'
           f'<h1>{esc(c["title"])}</h1></header>']
    first = True
    for si, s in enumerate(c["sections"]):
        if s["title"]:
            out.append(f'<h2 id="ch-{c["n"]}-{s["slug"]}">{s["html"]}</h2>')
        keys = {id(b): f"k{c['n']}-{si}-{bi}" for bi, b in enumerate(s["blocks"])}
        figs = {fig_id(b): b for b in s["blocks"] if b["kind"] == "figure"}
        blocks = []
        for b in place(s["blocks"], defer):
            if b["kind"] == "figure" and fig_id(b) in splits:
                continue
            key = keys[id(b)]
            if key in at and at[key][0] in figs:
                fid, cut = at[key]
                head, tail = b["html"][:cut].rstrip(), b["html"][cut:].lstrip()
                blocks.append(f'<p id="{key}">{head}</p>')
                blocks.append(block(figs[fid], shrink))
                if tail:
                    blocks.append(f'<p class="cont">{tail}</p>')
                continue
            blocks.append(block(b, shrink, key))
        if first and blocks and blocks[0].startswith("<p"):
            blocks[0] = blocks[0].replace("<p ", '<p class="first" ', 1) if blocks[0].startswith("<p ") \
                else blocks[0].replace("<p>", '<p class="first">', 1)
        first = False
        out += blocks
    if c["sources"]:
        out.append(f'<h2 class="sources-head" id="ch-{c["n"]}-sources">Notes and sources</h2><div class="sources">')
        out += [f"<p>{s['html']}</p>" for s in c["sources"]]
        out.append("</div>")
    out.append("</section>")
    return "\n".join(out)


RUN_IN = re.compile(r"^((?:Finding in the chapter|Finding|Question|Source|Method)(?: \([a-z0-9-]+\))?):\s*")


def appendix_entry(e):
    """One curated entry: its heading and chart kept together, then the finding, question, method
    and source. Link-only lines point at repository files and are not printed."""
    head = esc(e["label"]) if e["label"] else ""
    slugs = (f'<span class="entry-slugs">{" · ".join(esc(x) for x in e["slugs"])}</span>' if e["slugs"]
             else f'<span class="entry-title">{esc(e.get("title") or "")}</span>')
    imgs = [f'<div class="entry-chart n{len(e["charts"])}"><img src="{esc(c["files"].get("png") or c["files"].get("svg"))}" alt=""/></div>'
            for c in e["charts"]]
    # The heading travels with the first chart only: holding a two-chart entry together as one
    # block leaves most of a page empty whenever it misses the page it starts on.
    out = [f'<section class="entry" id="{esc(e["anchor"])}"><div class="entry-head">'
           f'<h4>{f"<span class=entry-label>{head}</span>" if head else ""}{slugs}</h4>'
           f'{imgs[0] if imgs else ""}</div>'] + imgs[1:]
    for b in e["blocks"]:
        if b["kind"] == "link":
            continue
        if b["kind"] == "p":
            out.append("<p>" + RUN_IN.sub(lambda m: f'<span class="run-in">{m.group(1)}</span> ', b["html"], 1) + "</p>")
        else:
            out.append(block(b))
    out.append("</section>")
    return "\n".join(out)


def appendix(a):
    if not a or not a.get("parts"):
        return ""
    out = ['<section class="appendix-opener" id="appendix"><header class="opener">'
           '<p class="chapter-number">Appendix</p><h1 class="appendix-title">Evidence</h1></header>']
    out += [f"<p>{b['html']}</p>" for b in a["intro"]]
    out.append("</section>")
    for part in a["parts"]:
        out.append(f'<section class="appendix-part" id="appendix-{part["n"]}">'
                   f'<h2 class="appendix-part-head" data-running="{esc(part["title"])}" '
                   f'data-bookmark="Chapter {ONES[part["n"]]} · {esc(part["title"])}">'
                   f'<span class="chapter-number">Evidence for Chapter {ONES[part["n"]]}</span>'
                   f'{esc(part["title"])}</h2>')
        for g in part["groups"]:
            if len(part["groups"]) > 1 or g["title"].lower() != "figure evidence":
                out.append(f'<h3 class="appendix-group">{g["html"]}</h3>')
            out += [appendix_entry(e) for e in g["entries"]]
        out.append("</section>")
    return "\n".join(out)


def front(meta, chapters):
    title, sub = esc(meta["title"]), esc(meta.get("subtitle"))
    return f"""
<section class="half-title"><p>{title}</p></section>
<section class="blank"></section>
<section class="title-page">
  <div class="title-block"><p class="book-title">{title}</p><p class="subtitle">{sub}</p></div>
  <div class="title-foot"><p class="author">{esc(meta["author"])}</p><p class="imprint">{esc(meta.get("affiliation"))}</p></div>
</section>
<section class="copyright">
  <p>{esc(meta.get("copyright"))}</p>
  <p>{esc(meta.get("edition"))} · {esc(meta.get("date"))}</p>
</section>
"""


def render_html(doc, defer=None, shrink=None, only=None, splits=None):
    import cover
    with open(os.path.join(HERE, "book.css"), encoding="utf-8") as f:
        css = f.read().replace("size: TRIM;", f"size: {cover.TRIM_IN[0]}in {cover.TRIM_IN[1]}in;")
    meta = doc["meta"]
    EVIDENCE.clear()
    EVIDENCE.update({e["rid"]: e["anchor"] for p in (doc.get("appendix") or {}).get("parts", [])
                     for g in p["groups"] for e in g["entries"] if e["rid"]})
    if only is not None:
        body = chapter(only, defer or {}, shrink or {}, splits)
    else:
        body = (front(meta, doc["chapters"]) + "\n".join(chapter(c, defer or {}, shrink or {}, splits) for c in doc["chapters"])
                + appendix(doc.get("appendix")))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{esc(meta["title"])}</title>'
            f'<meta name="author" content="{esc(meta["author"])}">'
            f'<style>{font_faces()}\n{css}</style></head>'
            f'<body data-title="{esc(meta["title"])}">{body}</body></html>')


TRIES = [0, 1, 2, 3, 4, -1, -2, -3]
# A figure on an earlier spread than its introducing paragraph outweighs any gap it closes.
VIOLATION = 10.0
# A page may end this much early without the figure that follows it counting as misplaced.
GAP = 0.15
# The smallest print size a figure may be shrunk to: diagram SMALL text (24 px on a 1400 px
# canvas) at 6.5 pt, chart text at its drawn size, where figure_lib guarantees 7 pt. Never more
# than MAX_SHRINK either way.
DIAGRAM_MIN_IN = 6.5 * 1400 / (24 * 72)
MAX_SHRINK = 0.2


def boxes(box):
    """The box tree below `box`, leaving out running heads and folios (margin boxes)."""
    yield box
    for child in getattr(box, "children", []) or []:
        if type(child).__name__ != "MarginBox":
            yield from boxes(child)


def gaps(document):
    """Figures that start a page while the page before ends with a large empty band: the figure
    did not fit and was pushed, leaving the gap. Returns {figure id: gap as a share of the page}."""
    found = {}
    for i, page in enumerate(document.pages[1:], 1):
        flow = [b for b in boxes(page._page_box) if getattr(b, "element_tag", "") in ("figure", "h2", "p", "h3")
                and type(b).__name__ == "BlockBox"]
        if not flow or any(getattr(b, "element_tag", "") == "h1" for b in boxes(page._page_box)):
            continue
        flow.sort(key=lambda b: b.position_y)
        # A figure at the head of the page, or a heading kept with the figure that follows it.
        lead = flow[:2] if flow[0].element_tag == "h2" else flow[:1]
        first = next((b for b in lead if b.element_tag == "figure" and b.element.get("id")
                      and "table" not in b.element.get("class", "")), None)
        if first is None:
            continue
        prev = document.pages[i - 1]._page_box
        body_bottom = prev.margin_height() - prev.margin_bottom
        leaves = [b for b in boxes(prev) if type(b).__name__ in ("LineBox", "BlockReplacedBox", "TableRowBox")]
        used = max((b.position_y + b.margin_height() for b in leaves), default=body_bottom)
        free = (body_bottom - used) / (body_bottom - prev.margin_top)
        if free > GAP and flow[0].position_y - page._page_box.margin_top < 30:
            img = next((b for b in boxes(first) if type(b).__name__ == "BlockReplacedBox"), None)
            room = body_bottom - used - (first.margin_height() - (img.margin_height() if img else 0)) - 6
            found[first.element.get("id")] = (i + 1, round(free, 2), room, img.height if img else 0,
                                              min_scale(first, img))
    return found


def float_figures(doc, c, defer, HTML, budget=12):
    """For each figure the moves could not seat, earliest first, try floating it into the text
    after it, or back to the top of the page where its text ends; keep a float only when the
    chapter's total gap shrinks."""
    para = {f"k{c['n']}-{si}-{bi}": b["html"] for si, s in enumerate(c["sections"])
            for bi, b in enumerate(s["blocks"]) if b["kind"] == "p"}
    allowed = allowed_cuts(c)

    def layout(sp):
        return evaluate(doc, c, HTML, defer, sp)

    splits, tried = {}, set()
    document, found, best = layout(splits)
    for _ in range(budget):
        todo = sorted((v[0], fid) for fid, v in found.items() if fid not in tried)
        if not todo:
            break
        fid = todo[0][1]
        tried.add(fid)
        ok = allowed.get(fid, set())
        used = {k for k, _ in splits.values()}
        for cand in (float_split(document, fid, para), float_back(document, fid, para, ok)):
            if not cand or cand[0] not in ok or cand[0] in used:
                continue
            trial = {**splits, fid: cand}
            d, g, sc = layout(trial)
            if sc < best - 1e-6:
                splits, document, found, best = trial, d, g, sc
                break
    return splits


def fit_chapter(doc, c, HTML):
    """Moves, then floats, then legibility-bounded shrinking for one chapter, each step kept only
    when it lowers the chapter's total gap. Returns (defer, splits, shrink, before, after)."""
    def score(d, sp=None, sh=None):
        _, g, sc = evaluate(doc, c, HTML, d, sp, sh)
        return g, sc

    _, before = score({})
    defer = seat(doc, c, HTML)
    splits = float_figures(doc, c, defer, HTML)
    found, best = score(defer, splits)
    # A float can be blocked by the next figure's placement, so the largest remaining gaps each get
    # one more try: float the figure, re-seat the others around it, keep it if the chapter improves.
    para = {f"k{c['n']}-{si}-{bi}": b["html"] for si, s in enumerate(c["sections"])
            for bi, b in enumerate(s["blocks"]) if b["kind"] == "p"}
    allowed = allowed_cuts(c)
    for fid, _ in sorted(found.items(), key=lambda kv: -kv[1][1])[:3]:
        if fid in splits:
            continue
        document = HTML(string=render_html(doc, defer, only=c, splits=splits), base_url=paths.ASSETS + "/").render()
        ok = allowed.get(fid, set())
        used = {k for k, _ in splits.values()}
        for cand in (float_split(document, fid, para), float_back(document, fid, para, ok)):
            if not cand or cand[0] not in ok or cand[0] in used:
                continue
            sp = {**splits, fid: cand}
            d2 = {k: v for k, v in defer.items() if k != fid}
            d2 = seat(doc, c, HTML, passes=1, splits=sp, start=d2)
            g, sc = score(d2, sp)
            if sc < best - 1e-6:
                defer, splits, found, best = d2, sp, g, sc
                break
    shrink = {}
    for fid, (_, _, room, h, lo) in sorted(found.items(), key=lambda kv: kv[1][0]):
        if h and room >= lo * h:
            trial = {**shrink, fid: room}
            g, sc = score(defer, splits, trial)
            if sc < best - 1e-6:
                shrink, found, best = trial, g, sc
    return defer, splits, shrink, before, best


def seat(doc, c, HTML, passes=2, splits=None, start=None, budget=60):
    """Moves for one chapter's figures. First settle gaps one page at a time, earliest first: each
    try moves the figure at the head of the gapped page, since moving one figure reflows everything
    after it. Then refine by coordinate descent, each figure in turn taking the move that leaves the
    least total gap given the others, which catches a gap caused by the figure before it."""
    def found(d):
        _, g, sc = evaluate(doc, c, HTML, d, splits)
        return g, sc

    def score(d):
        return found(d)[1]

    order = [fig_id(b) for s in c["sections"] for b in s["blocks"] if b["kind"] == "figure"
             and fig_id(b) not in (splits or {})]
    if start is None:
        defer, settled, seq = {}, set(), None
        for _ in range(budget):
            g, sc = found(defer)
            if seq is None or sc < seq[0]:
                seq = (sc, dict(defer))
            todo = sorted((v[0], fid) for fid, v in g.items() if fid not in settled and fid in order)
            if not todo:
                break
            fid = todo[0][1]
            nxt = TRIES.index(defer.get(fid, 0)) + 1
            if nxt < len(TRIES):
                defer[fid] = TRIES[nxt]
            else:
                settled.add(fid)
                defer[fid] = seq[1].get(fid, 0)
        best, defer = seq[0], {k: v for k, v in seq[1].items() if v}
    else:
        defer = dict(start)
        best = score(defer)
    for _ in range(passes):
        improved = False
        for fid in order:
            if best == 0:
                return defer
            for t in TRIES:
                if t == defer.get(fid, 0):
                    continue
                trial = {k: v for k, v in {**defer, fid: t}.items() if v}
                sc = score(trial)
                if sc < best - 1e-6:
                    best, defer, improved = sc, trial, True
        if not improved:
            break
    return defer


SENT_END = re.compile(r"[.?!:][\"”’)]*$")
NOT_END = {"e.g.", "i.e.", "vs.", "cf.", "Dr.", "Mr.", "Ms.", "St.", "No."}


def cut_after_token(html_text, n):
    """Index in `html_text` just after its n-th (0-based) visible whitespace-separated token,
    or None when that point falls inside an inline element, where a split would break the markup."""
    depth, tok, in_tok, i = 0, -1, False, 0
    while i < len(html_text):
        ch = html_text[i]
        if ch == "<":
            end = html_text.index(">", i)
            tag = html_text[i + 1:end]
            if not tag.endswith("/") and not tag.startswith(("br", "!")):
                depth += -1 if tag.startswith("/") else 1
            i = end + 1
            continue
        if ch.isspace():
            if in_tok and tok == n:
                return i if depth == 0 else None
            in_tok = False
        elif not in_tok:
            in_tok, tok = True, tok + 1
        i += 1
    return len(html_text) if tok == n and depth == 0 else None


def float_split(document, fid, para):
    """Where to float `fid`: the paragraph key and html cut that put the text following the figure
    into the gap above it. Reads the current layout: the lines after the figure that would fit the
    free space on the page before move up, ending at the last whole sentence among them."""
    pages = document.pages
    for n, page in enumerate(pages[1:], 1):
        fig = next((b for b in boxes(page._page_box) if getattr(b, "element_tag", "") == "figure"
                    and b.element.get("id") == fid), None)
        if fig is not None:
            break
    else:
        return None
    prev = pages[n - 1]._page_box
    body_bottom = prev.margin_height() - prev.margin_bottom
    leaves = [b for b in boxes(prev) if type(b).__name__ in ("LineBox", "BlockReplacedBox", "TableRowBox")]
    room = body_bottom - max((b.position_y + b.margin_height() for b in leaves), default=body_bottom) - 4
    fig_bottom = fig.position_y + fig.margin_height()
    lines = []
    for pg in pages[n:n + 2]:
        for b in boxes(pg._page_box):
            if type(b).__name__ == "LineBox" and (pg is not page or b.position_y >= fig_bottom):
                lines.append(b)
    used, words, key = 0, 0, None
    for ln in lines:
        el = ln.element
        if el is None or el.tag != "p" or not el.get("id", "").startswith("k"):
            break
        if el.get("id") != key:
            # Whole paragraphs before the one that is cut move up ahead of the figure unchanged.
            key, words = el.get("id"), 0
        if used + ln.height > room:
            break
        used += ln.height
        text = "".join(t.text for t in boxes(ln) if type(t).__name__ == "TextBox").strip()
        toks = text.split()
        words += len(toks) - (1 if text.endswith("-") and toks else 0)
    if key is None or words == 0 or key not in para:
        return None
    plain = html.unescape(re.sub(r"<[^>]+>", "", para[key])).split()
    ends = [i for i, t in enumerate(plain[:words]) if SENT_END.search(t) and t not in NOT_END]
    for t in reversed(ends):
        cut = cut_after_token(para[key], t)
        if cut is not None:
            return key, cut
    return None


def float_back(document, fid, para, earliest):
    """The other float: put `fid` at the top of the page where the text before it ends, cutting the
    paragraph that runs onto that page at its last sentence on the page before. Only a paragraph
    at or after `earliest` (the anchor, or an earlier mention by number) may be cut, so the figure
    never lands above the text that introduces it."""
    pages = document.pages
    for n, page in enumerate(pages[1:], 1):
        if any(getattr(b, "element_tag", "") == "figure" and b.element.get("id") == fid
               for b in boxes(page._page_box)):
            break
    else:
        return None
    prev = pages[n - 1]._page_box
    first = next((b for b in boxes(prev) if type(b).__name__ == "LineBox"), None)
    if first is None or first.element is None or first.element.tag != "p":
        return None
    key = first.element.get("id", "")
    if key not in para or key not in earliest:
        return None
    before = pages[n - 2]._page_box if n >= 2 else None
    if before is None:
        return None
    words = 0
    for ln in (b for b in boxes(before) if type(b).__name__ == "LineBox"):
        if ln.element is not None and ln.element.get("id") == key:
            text = "".join(t.text for t in boxes(ln) if type(t).__name__ == "TextBox").strip()
            toks = text.split()
            words += len(toks) - (1 if text.endswith("-") and toks else 0)
    if not words:
        return None
    plain = html.unescape(re.sub(r"<[^>]+>", "", para[key])).split()
    ends = [i for i, t in enumerate(plain[:words]) if SENT_END.search(t) and t not in NOT_END]
    for t in reversed(ends):
        cut = cut_after_token(para[key], t)
        if cut is not None and cut < len(para[key]):
            return key, cut
    return None


def introducers(c):
    """The paragraph that introduces each figure: the first one naming it by number, if that comes
    before the figure, else the paragraph just before it (its anchor)."""
    out = {}
    for si, s in enumerate(c["sections"]):
        bl = s["blocks"]
        for fi, b in enumerate(bl):
            if b["kind"] != "figure":
                continue
            anchor = max([i for i in range(fi) if bl[i]["kind"] == "p"] or [-1])
            m = mentioned_at(bl, b)
            i = m if m is not None and m < fi else anchor
            out[fig_id(b)] = f"k{c['n']}-{si}-{i}" if i >= 0 else None
    return out


def spread(page_index):
    """Pages pair as spreads, even folio left and odd right; folio is index + 1, and a chapter
    rendered alone starts on a recto just as it does in the book, so parity carries over."""
    return (page_index + 1) // 2


def violations(document, intro):
    """Figures placed on an earlier spread than the paragraph that introduces them."""
    first = {}
    for i, page in enumerate(document.pages):
        for b in boxes(page._page_box):
            el = getattr(b, "element", None)
            if el is not None and getattr(b, "element_tag", "") in ("p", "figure"):
                first.setdefault(el.get("id"), i)
    return [fid for fid, key in intro.items()
            if key and fid in first and key in first and spread(first[fid]) < spread(first[key])]


# The target is few reported gaps and none over a quarter page, so a gap costs its size, a fixed
# charge for existing, and a steep charge for every point past 25%. A plain sum of sizes let two
# middling gaps score better than one small one, which is not how a reader sees the pages.
GAP_COUNT, GAP_LARGE, LARGE = 0.5, 4.0, 0.25


def cost(found):
    return sum(f + GAP_COUNT + GAP_LARGE * max(0.0, f - LARGE) for _, f, *_ in found.values())


def evaluate(doc, c, HTML, defer, splits=None, shrink=None):
    """Render one chapter and score it: the summed share of each page a pushed figure leaves empty,
    plus a penalty for every figure that precedes its introduction's spread."""
    document = HTML(string=render_html(doc, defer, shrink, only=c, splits=splits),
                    base_url=paths.ASSETS + "/").render()
    g = gaps(document)
    bad = violations(document, introducers(c))
    return document, g, cost(g) + VIOLATION * len(bad)


def allowed_cuts(c):
    """For each figure, the paragraphs it may be floated into: any in its run of text between
    headings. Whether the result respects the figure's introduction is checked on the layout."""
    out = {}
    for si, s in enumerate(c["sections"]):
        bl = s["blocks"]
        for fi, b in enumerate(bl):
            if b["kind"] != "figure":
                continue
            lo = max([i + 1 for i in range(fi) if bl[i]["kind"] == "h3"] or [0])
            hi = next((i for i in range(fi, len(bl)) if bl[i]["kind"] == "h3"), len(bl))
            out[fig_id(b)] = {f"k{c['n']}-{si}-{i}" for i in range(lo, hi) if bl[i]["kind"] == "p"}
    return out


def min_scale(fig, img):
    """How far this figure's image may shrink before its text drops below print size."""
    if img is None or not img.width:
        return 1.0
    shown_in = img.width / 96
    if "chart" in fig.element.get("class", ""):
        try:
            from PIL import Image
            src = img.element.get("src", "").replace("file://", "")
            with Image.open(os.path.join(paths.ASSETS, src)) as im:
                native_in = im.size[0] / (im.info.get("dpi") or (300, 300))[0]
        except (OSError, ValueError):
            return 1.0
    else:
        native_in = DIAGRAM_MIN_IN
    return min(1.0, max(1 - MAX_SHRINK, native_in / shown_in))


def with_cover(interior):
    """`book.pdf` for reading on screen: the front cover, then the interior. Printers get
    `book-interior.pdf` and `cover-wrap.pdf` instead, which is why the cover is not a page of the book."""
    import fitz

    import cover
    cover.main()
    out = os.path.join(paths.DIST, "book.pdf")
    doc = fitz.open(os.path.join(paths.BUILD, "cover-trim.pdf"))
    body = fitz.open(interior)
    toc = body.get_toc()
    doc.insert_pdf(body)
    doc.set_toc([[lvl, title, page + 1] for lvl, title, page in toc])
    doc.set_metadata(body.metadata)
    doc.save(out, garbage=3, deflate=True)
    return out


def main():
    from weasyprint import HTML
    with open(paths.SOURCE, encoding="utf-8") as f:
        doc = json.load(f)
    # Every chapter opens on a new recto, so a chapter's pages lay out the same alone as in the
    # book; seating its figures against a render of that chapter only is a tenth of the work per try.
    defer, splits, shrink, solved = {}, {}, {}, {}
    for c in doc["chapters"]:
        d, sp, sh, _, _ = fit_chapter(doc, c, HTML)
        defer.update(d), splits.update(sp), shrink.update(sh)
        _, g, _ = evaluate(doc, c, HTML, d, sp, sh)
        solved[c["n"]] = sorted(round(v[1], 2) for v in g.values())
        print(f"book: chapter {c['n']}: {len(g)} gaps {solved[c['n']]} "
              f"({len(d)} moved, {len(sp)} floated, {len(sh)} shrunk)")
    html_text = render_html(doc, defer, shrink, splits=splits)
    document = HTML(string=html_text, base_url=paths.ASSETS + "/").render()
    # The solve renders chapters alone; the book is the truth. Each chapter opens on a recto, so the
    # two should agree page for page, and a difference means that assumption broke.
    whole = {}
    for fid, v in gaps(document).items():
        whole.setdefault(int(fid.rsplit("-", 2)[-2]), []).append(round(v[1], 2))
    for n, g in solved.items():
        if sorted(whole.get(n, [])) != g:
            print(f"book: warning: chapter {n} lays out differently in the book {sorted(whole.get(n, []))} "
                  f"than alone {g}")
    os.makedirs(paths.DIST, exist_ok=True)
    with open(os.path.join(paths.BUILD, "book.html"), "w", encoding="utf-8") as f:
        f.write(html_text)
    interior = os.path.join(paths.DIST, "book-interior.pdf")
    document.write_pdf(interior)
    out = with_cover(interior)
    left = gaps(document)
    for fid, (page, free, _, _, _) in left.items():
        print(f"book: page {page - 1} ends {free:.0%} early because {fid} did not fit (deferred {defer.get(fid, 0)})")
    print(f"book: {len(document.pages)} pages, {len(defer)} figures deferred, {len(left)} gaps left -> {out}")
