"""The Kindle edition: book.json as a reflowable EPUB 3 for Kindle Direct Publishing.

    ./publish kindle        -> $PUBLISH_OUT/dist/book.epub

The same text, figures and references as the print book (no appendix: `book.without_appendix`), one XHTML file per
chapter. `editions/kindle.json`, when present, overrides fields of `meta.json` for this edition
only. The cover is `dist/cover-ebook.png`, which `./publish cover` draws.
"""
import datetime
import html
import html.entities
import io
import json
import os
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile

import paths
from book import FONTS, GEIST_ITALIC, ONES, esc, fig_id, font_faces, without_appendix
from inline import EXAMPLE_TITLE, md_plain, sub_notes

HERE = os.path.join(paths.HERE, "kindle")
OVERRIDES = os.path.join(paths.EDITIONS, "kindle.json")
OUT = os.path.join(paths.DIST, "book.epub")
COVER = os.path.join(paths.DIST, "cover-ebook.png")
# KDP can reject a book that presents itself as unfinished, and its reviews stay with the listing, so
# the store edition never inherits the print book's "Beta" unless kindle.json says so.
DEFAULTS = {"edition": "First"}
# At the 70% royalty Amazon charges a delivery fee per megabyte on every sale, so figures are
# downscaled and reduced to a small palette; the charts are flat colour and lose nothing visible.
IMAGE_W, COLOURS = 1100, 64
# Only what the book can stand behind: textual alone is not sufficient while complex figures lack
# certified text equivalents, so no WCAG conformance is claimed.
ACCESSIBILITY = [("rendition:layout", "reflowable"), ("schema:accessMode", "textual"), ("schema:accessMode", "visual"),
                 ("schema:accessModeSufficient", "textual,visual")] + \
    [("schema:accessibilityFeature", f) for f in ("alternativeText", "structuralNavigation", "tableOfContents",
                                                  "readingOrder", "displayTransformability")] + \
    [("schema:accessibilityHazard", h) for h in ("noFlashingHazard", "noMotionSimulationHazard", "noSoundHazard")]
# The print book's faces, cut to static instances (Kindle does not read variable fonts) and
# subset to the book's characters, so each costs tens of kilobytes rather than hundreds.
FACES = [("Geist", 300, "normal"), ("Geist", 400, "normal"), ("Geist", 600, "normal"), ("Geist", 400, "italic"),
         ("Geist Mono", 400, "normal"), ("Manrope", 300, "normal")]
XHTML_NS = 'xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"'
XML_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}


def xml_safe(s):
    """Named HTML entities other than XML's five are undefined in XHTML and fail the whole file."""
    return re.sub(r"&([A-Za-z][A-Za-z0-9]*);",
                  lambda m: m.group(0) if m.group(1) in XML_ENTITIES
                  else f"&#{html.entities.name2codepoint.get(m.group(1), 0xFFFD)};", s)


def page(title, body, kind=None, main=True):
    # `preface` goes on the inner section with role doc-preface: EPUBCheck rejects that role on <body>.
    attr = f' epub:type="{kind}"' if kind and kind != "preface" else ""
    if main:
        body = f"<main>{body}</main>"
    return (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html {XHTML_NS} lang="en" xml:lang="en">'
            f'<head><meta charset="utf-8"/><title>{esc(title)}</title>'
            f'<link rel="stylesheet" type="text/css" href="kindle.css"/></head>'
            f'<body{attr}>{xml_safe(body)}</body></html>')


class Images:
    """Copies each figure once, resized and palette-reduced, and names it by its source file."""

    def __init__(self):
        self.files, self.missing = {}, []

    def add(self, name):
        if not name:
            return None
        if name in self.files:
            return self.files[name][0]
        src = name if os.path.isabs(name) else os.path.join(paths.ASSETS, name)
        if not os.path.exists(src):
            self.missing.append(name)
            return None
        from PIL import Image
        im = svg_image(src) if src.endswith(".svg") else Image.open(src)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            flat = Image.new("RGB", im.size, "white")
            flat.paste(im, mask=im.split()[-1])
            im = flat
        im = im.convert("RGB")
        if im.width > IMAGE_W:
            im = im.resize((IMAGE_W, round(im.height * IMAGE_W / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.quantize(COLOURS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(buf, "PNG", optimize=True)
        stem, n = os.path.splitext(os.path.basename(name))[0], 1
        taken = {h for h, _ in self.files.values()}
        href = f"images/{stem}.png"
        while href in taken:
            n += 1
            href = f"images/{stem}-{n}.png"
        self.files[name] = (href, buf.getvalue())
        return href


EVIDENCE = {}  # figure-pipeline id -> appendix anchor


def svg_image(src):
    """A drawn diagram that has no PNG, rendered through the same Chrome path as the cover, so its
    text is set in the design system's fonts rather than a rasterizer's fallback."""
    import fitz
    from PIL import Image
    from cover import chrome_pdf
    with open(src, encoding="utf-8") as f:
        svg = f.read()
    w, h = (float(re.search(rf'<svg[^>]*\b{a}="([\d.]+)', svg).group(1)) for a in ("width", "height"))
    pdf = os.path.join(paths.BUILD, "kindle-svg.pdf")
    chrome_pdf(svg, w * 0.75, h * 0.75, pdf)
    page = fitz.open(pdf)[0]
    z = IMAGE_W / page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
    os.remove(pdf)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def table_html(rows, tid, labelledby, cls=""):
    """A data table whose every cell names its column, row and group headers, so a screen reader
    can announce them; each group row opens its own <tbody>."""
    cols = [f"{tid}-c{j}" for j in range(len(rows[0]))]
    head = "".join(f'<th scope="col" id="{h}">{c["html"]}</th>' for h, c in zip(cols, rows[0]))
    bodies, current, group = [], [], None
    for i, r in enumerate(rows[1:], 1):
        if len(r) > 1 and all(not c["md"] for c in r[1:]):
            if current:
                bodies.append(current)
            group = f"{tid}-g{i}"
            current = [f'<tr class="group"><th scope="rowgroup" colspan="{len(r)}" id="{group}">{r[0]["html"]}</th></tr>']
            continue
        row = f"{tid}-r{i}"
        cells = [f'<th scope="row" id="{row}" headers="{" ".join(filter(None, (cols[0], group)))}">{r[0]["html"]}</th>']
        cells += [f'<td headers="{" ".join(filter(None, (cols[j], row, group)))}">{c["html"]}</td>'
                  for j, c in enumerate(r[1:], 1)]
        current.append("<tr>" + "".join(cells) + "</tr>")
    if current:
        bodies.append(current)
    classes = " ".join(filter(None, (cls, "wide-table" if len(cols) >= 5 else "")))
    cls = f' class="{classes}"' if classes else ""
    body = "".join(f'<tbody>{"".join(b)}</tbody>' for b in bodies)
    # class first: `book.example` adds its classes to the first tag's existing class attribute,
    # and a second class attribute after `id` would make the file malformed XML.
    return (f'<table{cls} id="{tid}" aria-labelledby="{labelledby}"><thead><tr>{head}</tr></thead>{body}</table>')


def figure(b, images):
    label = f'{b["label"]} {b["number"]}'
    anchor = EVIDENCE.get(b.get("rid"))
    ptr = f' <a class="evidence-ptr" href="#{anchor}">Evidence</a>' if anchor else ""
    title = f'<p class="panel-title">{esc(label)}</p>'
    cap = f'<figcaption id="{fig_id(b)}-caption">{b["caption_html"]}{ptr}</figcaption>'
    if b["type"] == "table":
        table = table_html(b["rows"], f"{fig_id(b)}-table", f"{fig_id(b)}-caption")
        return f'<figure class="table-figure" id="{fig_id(b)}">{title}{table}{cap}</figure>'
    files = b.get("files") or {}
    src = images.add(files.get("png") or files.get("svg"))
    if not src:
        if not (files.get("png") or files.get("svg")):
            images.missing.append(b["ref"])
        return f'<figure id="{fig_id(b)}">{title}<p>[{esc(b["ref"])} is missing from this build]</p>{cap}</figure>'
    alt = b.get("alt") or md_plain(b["caption_md"])
    return f'<figure id="{fig_id(b)}">{title}<img src="{src}" alt="{esc(alt)}"/>{cap}</figure>'


def block(b, images, heading=None, tid=None):
    """`heading` is the id of the section heading that names a prose table, `tid` that table's id."""
    k = b["kind"]
    if k == "p":
        out = f"<p>{b['html']}</p>"
    elif k == "h3":
        out = f"<h3>{b['html']}</h3>"
    elif k == "quote":
        out = f"<blockquote><p>{b['html']}</p></blockquote>"
    elif k in ("ul", "ol"):
        out = f"<{k}>" + "".join(f"<li>{i['html']}</li>" for i in b["items"]) + f"</{k}>"
    elif k == "table":
        out = table_html(b["rows"], tid, heading, "prose-table")
    elif k == "figure":
        out = figure(b, images)
    else:
        return ""
    # One element per card, unlike the print book's per-block borders: a reader's pagination splits
    # bordered siblings into stray boxes.
    if b.get("example_start"):
        out = f'<div class="example"><p class="example-title">{EXAMPLE_TITLE}</p>{out}'
    if b.get("example_end"):
        out += "</div>"
    return out


def chapter(c, images):
    out = [f'<section epub:type="chapter" role="doc-chapter" id="ch-{c["n"]}">'
           f'<hr class="opener-rule" aria-hidden="true"/><p class="chapter-number">Chapter {ONES[c["n"]]}</p><h1 id="ch-{c["n"]}-title">{esc(c["title"])}</h1>']
    heading = f"ch-{c['n']}-title"
    # Counted per heading, not per section: an untitled section keeps the heading before it, and
    # restarting its count would repeat that heading's table ids.
    tables = {}
    for s in c["sections"]:
        if s["title"]:
            heading = f'ch-{c["n"]}-{s["slug"]}'
            out.append(f'<h2 id="{heading}">{s["html"]}</h2>')
        for b in s["blocks"]:
            if b["kind"] == "table":
                tables[heading] = tables.get(heading, 0) + 1
            out.append(block(b, images, heading, f"{heading}-table-{tables.get(heading, 0)}"))
    if c.get("further"):
        refs = ", ".join(f'<a class="cite" href="#ref-{n}">{n}</a>' for n in c["further"])
        out.append(f'<p class="further-sources">Further sources: [{refs}].</p>')
    out.append("</section>")
    return "".join(out)


RUN_IN = re.compile(r"^((?:Finding in the chapter|Finding|Question|Source|Method)(?: \([a-z0-9-]+\))?):\s*")


def appendix_entry(e, images):
    name = esc(e["label"]) + " · " if e["label"] else ""
    name += " · ".join(esc(x) for x in e["slugs"]) if e["slugs"] else esc(e.get("title") or "")
    out = [f'<section class="entry" id="{esc(e["anchor"])}"><h4>{name}</h4>']
    for ch in e["charts"]:
        src = images.add(ch["files"].get("png") or ch["files"].get("svg"))
        if src:
            out.append(f'<img src="{src}" alt="{esc(md_plain(ch.get("alt") or e.get("title") or ""))}"/>')
    for b in e["blocks"]:
        if b["kind"] == "link":
            continue
        if b["kind"] == "p":
            out.append("<p>" + RUN_IN.sub(lambda m: f'<span class="run-in">{m.group(1)}</span> ', b["html"], 1) + "</p>")
        else:
            out.append(block(b, images))
    out.append("</section>")
    return "".join(out)


def appendix_part(part, title, images):
    out = [f'<section epub:type="appendix" id="appendix-{part["n"]}">'
           f'<p class="chapter-number">{esc(title)} for Chapter {ONES[part["n"]]}</p><h1>{esc(part["title"])}</h1>']
    for g in part["groups"]:
        if len(part["groups"]) > 1 or g["title"].lower() != "figure evidence":
            out.append(f'<h2>{g["html"]}</h2>')
        out += [appendix_entry(e, images) for e in g["entries"]]
    out.append("</section>")
    return "".join(out)


def front_matter(meta, preface):
    pages = [("title", "Title page", "titlepage",
              f'<section class="title-page"><hr class="opener-rule" aria-hidden="true"/>'
              f'<h1 class="book-title">{esc(meta["title"])}</h1>'
              f'<p class="subtitle">{esc(meta.get("subtitle"))}</p><p class="author">{esc(meta["author"])}</p>'
              f'<p class="affiliation">{esc(meta.get("affiliation"))}</p></section>'),
             ("copyright", "Copyright", "copyright-page",
              f'<section class="copyright"><p>{esc(meta.get("copyright"))}</p>'
              f'<p>{esc(meta.get("edition"))} edition · {esc(meta.get("date"))}</p>'
              f'<p>All rights reserved. Corrections are welcome at {esc(meta.get("email"))}.</p></section>')]
    if preface:
        body = "".join(f"<p>{b['html']}</p>" for b in preface["blocks"])
        pages.append(("preface", preface["title"], "preface",
                      f'<section epub:type="preface" role="doc-preface" id="preface"><h1>{esc(preface["title"])}</h1>'
                      f'{body}</section>'))
    return pages


def footnotes(name, body):
    """The author's notes as EPUB footnotes: a numbered call in the text and the note at the end of
    its file, which Kindle shows as a pop-up. Left as the span, the note runs into the sentence."""
    notes = []

    def call(note):
        notes.append(note)
        n = len(notes)
        return (f'<a epub:type="noteref" role="doc-noteref" class="noteref" id="{name}-fnref-{n}" '
                f'href="#{name}-fn-{n}"><sup>{n}</sup></a>')
    body = sub_notes(body, call)
    if notes:
        body += "".join(f'<aside epub:type="footnote" role="doc-footnote" class="footnote" id="{name}-fn-{n}"><p>'
                        f'<a href="#{name}-fnref-{n}" role="doc-backlink" '
                        f'aria-label="Return to footnote reference {n}">{n}.</a> {t}</p></aside>'
                        for n, t in enumerate(notes, 1))
    return body


# A URL stops at whitespace, a tag, a quote or an escaped quote or bracket. `&amp;` stays: it joins a
# query string's parameters.
URL = re.compile(r"https?://(?:(?!&quot;|&#39;|&#x27;|&lt;|&gt;)[^\s<\"'])+")


def url_link(m):
    """A reference's bare URL as a link. Terminal punctuation stays outside the anchor, and so does a
    closing parenthesis the URL never opened, but a DOI's balanced parentheses stay in."""
    url, tail = m.group(0), ""
    while url and (url[-1] in ".,;:!?" or (url[-1] == ")" and url.count(")") > url.count("("))):
        url, tail = url[:-1], url[-1] + tail
    return f'<a href="{url}">{url}</a>{tail}'


def link_urls(text):
    # Split on existing anchors so a URL already inside one is never wrapped a second time.
    parts = re.split(r"(<a\b.*?</a>)", text, flags=re.S)
    return "".join(p if p.startswith("<a") else URL.sub(url_link, p) for p in parts)


def link(docs):
    """Point every `#id` at the file that holds it, since each chapter is its own file."""
    where = {i: f"{name}.xhtml" for name, _, _, body in docs for i in re.findall(r'\sid="([^"]+)"', body)}
    broken = set()

    def fix(m):
        target = where.get(m.group(1))
        if not target:
            broken.add(m.group(1))
            return m.group(0)
        return f'href="{target}#{m.group(1)}"'
    out = [(name, title, kind, re.sub(r'href="#([^"]+)"', fix, body)) for name, title, kind, body in docs]
    # A relative link points into the manuscript folder, which a reader of the store copy does not have.
    local = re.compile(r'<a href="(?![#a-z]+:|[^"]*\.xhtml)[^"]*">(.*?)</a>')
    unlinked = sum(len(local.findall(body)) for *_, body in out)
    out = [(name, title, kind, local.sub(r"\1", body)) for name, title, kind, body in out]
    return out, broken, unlinked


def contents_tree(chapters, has_preface, appendix_parts, appendix_title, has_refs):
    """The contents as (href, label, children), labels escaped: the nav document and the NCX are
    both drawn from it, so the two menus cannot disagree."""
    tree = []
    if has_preface:
        tree.append(("preface.xhtml", "Use of AI tools", []))
    for c in chapters:
        subs = [(f'ch-{c["n"]}.xhtml#ch-{c["n"]}-{s["slug"]}', esc(md_plain(s["title"])), [])
                for s in c["sections"] if s["title"]]
        tree.append((f'ch-{c["n"]}.xhtml', f'{ONES[c["n"]]}. {esc(c["title"])}', subs))
    if appendix_parts:
        parts = [(f'appendix-{p["n"]}.xhtml', f'Chapter {ONES[p["n"]]} · {esc(p["title"])}', []) for p in appendix_parts]
        tree.append(("appendix.xhtml", f"Appendix: {esc(appendix_title)}", parts))
    if has_refs:
        tree.append(("references.xhtml", "References", []))
    return tree


def nav(tree, first):
    def ol(entries):
        return "<ol>" + "".join(f'<li><a href="{h}">{label}</a>{ol(kids) if kids else ""}</li>'
                                for h, label, kids in entries) + "</ol>"
    # No cover landmark: KDP builds its cover from the cover-image, and an HTML cover page beside it
    # shows the reader the cover twice.
    body = (f'<nav epub:type="toc" role="doc-toc" id="toc"><h1>Contents</h1>{ol(tree)}</nav>'
            f'<nav epub:type="landmarks" hidden=""><ol>'
            f'<li><a epub:type="toc" href="nav.xhtml">Contents</a></li>'
            f'<li><a epub:type="bodymatter" href="{first}">Start</a></li></ol></nav>')
    return page("Contents", body, main=False)


def ncx(meta, ident, tree):
    """The EPUB 2 table of contents, which older Kindle devices read instead of the nav document."""
    order = iter(range(1, 10000))

    def points(entries):
        out = []
        for h, label, kids in entries:
            n = next(order)
            out.append(f'<navPoint id="np{n}" playOrder="{n}"><navLabel><text>{label}</text></navLabel>'
                       f'<content src="{h}"/>{points(kids)}</navPoint>')
        return "".join(out)
    depth = 2 if any(kids for *_, kids in tree) else 1
    return ('<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
            f'<head><meta name="dtb:uid" content="urn:uuid:{ident}"/><meta name="dtb:depth" content="{depth}"/>'
            '<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>'
            f'<docTitle><text>{esc(meta["title"])}</text></docTitle><navMap>{points(tree)}</navMap></ncx>')


def opf(meta, ident, docs, images, fonts, first):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
             '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
             '<item id="css" href="kindle.css" media-type="text/css"/>',
             '<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>']
    items += [f'<item id="{name}" href="{name}.xhtml" media-type="application/xhtml+xml"/>' for name, *_ in docs]
    items += [f'<item id="font{i}" href="{href}" media-type="font/ttf"/>' for i, href in enumerate(fonts)]
    items += [f'<item id="img{i}" href="{href}" media-type="image/png"/>' for i, (href, _) in enumerate(images.files.values())]
    spine = []
    for name, *_ in docs:
        spine.append(f'<itemref idref="{name}"/>')
        if name == "copyright":
            spine.append('<itemref idref="nav"/>')
    sub = f'<meta refines="#book-title" property="title-type">main</meta>'
    summary = (f"Reflowable text with a two-level contents menu, descriptive alternatives supplied for all "
               f"{len(images.files)} interior images, and programmatic table headers. Dense diagrams and screenshots "
               "may require magnification. Full textual equivalence of complex images has not been certified. "
               "No WCAG conformance claim is made.")
    access = "".join(f'<meta property="{k}">{v}</meta>' for k, v in ACCESSIBILITY)
    access += f'<meta property="schema:accessibilitySummary">{summary}</meta>'
    subtitle = (f'<dc:title id="subtitle">{esc(meta["subtitle"])}</dc:title>'
                f'<meta refines="#subtitle" property="title-type">subtitle</meta>') if meta.get("subtitle") else ""
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="en">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:identifier id="uid">urn:uuid:{ident}</dc:identifier>'
            f'<dc:title id="book-title">{esc(meta["title"])}</dc:title>{sub}{subtitle}'
            f'<dc:creator>{esc(meta["author"])}</dc:creator><dc:language>en-US</dc:language>'
            f'<dc:publisher>{esc(meta.get("affiliation"))}</dc:publisher><dc:date>{meta.get("year")}</dc:date>'
            f'<dc:rights>{esc(meta.get("copyright"))}</dc:rights>'
            f'<meta property="dcterms:modified">{now}</meta><meta name="cover" content="cover-image"/>{access}'
            f'</metadata><manifest>{"".join(items)}</manifest>'
            f'<spine toc="ncx">{"".join(spine)}</spine>'
            f'<guide><reference type="toc" title="Contents" href="nav.xhtml"/>'
            f'<reference type="text" title="Start" href="{first}"/></guide></package>')


def embedded_fonts(text):
    """The faces as {href: TrueType bytes} and the @font-face rules that load them. `text` is upper-cased
    too, since the labels set in small caps draw glyphs the source never spells."""
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    font_faces()
    chars = text + text.upper() + "".join(map(chr, range(0x20, 0x7f)))
    files, css = {}, []
    for family, weight, style in FACES:
        src = GEIST_ITALIC if style == "italic" else FONTS[family]
        if not os.path.exists(src):
            continue
        font = instantiateVariableFont(TTFont(src), {"wght": weight})
        font.flavor = None
        options = subset.Options()
        options.layout_features = ["*"]
        options.drop_tables += ["meta"]
        sub = subset.Subsetter(options)
        sub.populate(text=chars)
        sub.subset(font)
        buf = io.BytesIO()
        font.save(buf)
        href = f"fonts/{family.replace(' ', '')}-{weight}{'-italic' if style == 'italic' else ''}.ttf"
        files[href] = buf.getvalue()
        css.append(f'@font-face {{ font-family: "{family}"; font-weight: {weight}; font-style: {style}; '
                   f'src: url("{href}"); }}')
    return files, "\n".join(css) + "\n"


def visible_text(markup):
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def cover_jpeg():
    if not os.path.exists(COVER):
        raise SystemExit(f"kindle: no {COVER}; run ./publish cover first")
    from PIL import Image
    buf = io.BytesIO()
    Image.open(COVER).convert("RGB").save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def check(files):
    """Every XHTML file parses as XML and every local link and image resolves: a malformed file is
    dropped silently by some readers and fails KDP's conversion outright on others."""
    problems = []
    for name, data in files.items():
        if not name.endswith((".xhtml", ".opf", ".ncx")):
            continue
        try:
            ET.fromstring(data)
        except ET.ParseError as e:
            problems.append(f"{name}: not well-formed XML ({e})")
            continue
        text = data.decode("utf-8") if isinstance(data, bytes) else data
        for ref in re.findall(r'(?:href|src)="([^"#]+)', text):
            if ":" not in ref and f"OEBPS/{ref}" not in files:
                problems.append(f"{name}: {ref} is not in the book")
        found = re.findall(r'\sid="([^"]+)"', text)
        problems += [f"{name}: id {i} is used twice" for i in sorted({i for i in found if found.count(i) > 1})]
    # A fragment is checked against the ids in its file: a contents entry or cross-reference to a
    # heading that is not there opens the right file at the wrong place, and nothing else notices.
    ids = {name: set(re.findall(r'\sid="([^"]+)"', data.decode("utf-8") if isinstance(data, bytes) else data))
           for name, data in files.items() if name.endswith(".xhtml")}
    for name, data in files.items():
        if not name.endswith((".xhtml", ".ncx")):
            continue
        text = data.decode("utf-8") if isinstance(data, bytes) else data
        for ref, frag in re.findall(r'(?:href|src)="([^"#:]*)#([^"]+)"', text):
            target = f"OEBPS/{ref}" if ref else name
            if target in ids and frag not in ids[target]:
                problems.append(f"{name}: {ref}#{frag} names no element")
    return problems


def main():
    with open(paths.SOURCE, encoding="utf-8") as f:
        doc = without_appendix(json.load(f))
    meta = {**doc["meta"], **DEFAULTS}
    if os.path.exists(OVERRIDES):
        with open(OVERRIDES, encoding="utf-8") as f:
            meta.update(json.load(f))
    if meta.get("confirm"):
        print(f"kindle: note: meta.json still says: {meta['confirm']}")
    EVIDENCE.clear()
    appx = doc.get("appendix") or {}
    EVIDENCE.update({e["rid"]: e["anchor"] for p in appx.get("parts", [])
                     for g in p["groups"] for e in g["entries"] if e["rid"]})
    images = Images()
    docs = front_matter(meta, doc.get("preface"))
    docs += [(f"ch-{c['n']}", c["title"], "bodymatter", chapter(c, images)) for c in doc["chapters"]]
    if appx.get("parts"):
        intro = "".join(f"<p>{b['html']}</p>" for b in appx["intro"])
        docs.append(("appendix", appx["title"], "backmatter",
                     f'<section epub:type="appendix" id="appendix"><p class="chapter-number">Appendix</p>'
                     f'<h1>{esc(appx["title"])}</h1>{intro}</section>'))
        docs += [(f"appendix-{p['n']}", p["title"], "backmatter", appendix_part(p, appx["title"], images))
                 for p in appx["parts"]]
    if doc.get("references"):
        refs = "".join(f'<p id="ref-{r["n"]}"><span class="ref-n">[{r["n"]}]</span>{link_urls(r["html"])}</p>' for r in doc["references"])
        docs.append(("references", "References", "backmatter",
                     f'<section epub:type="bibliography" role="doc-bibliography" id="references"><h1>References</h1>'
                     f'<div class="reference-list">{refs}</div></section>'))
    docs = [(name, title, kind, footnotes(name, body)) for name, title, kind, body in docs]
    docs, broken, unlinked = link(docs)
    tree = contents_tree(doc["chapters"], bool(doc.get("preface")), appx.get("parts"), appx.get("title"),
                         bool(doc.get("references")))
    first = f"ch-{doc['chapters'][0]['n']}.xhtml"
    xhtml_nav = nav(tree, first)
    ident = uuid.uuid5(uuid.NAMESPACE_URL, f"aihero.studio/book/{meta['title']}")
    with open(os.path.join(HERE, "kindle.css"), encoding="utf-8") as f:
        css = f.read()
    fonts, faces = embedded_fonts(visible_text("".join(body for *_, body in docs) + xhtml_nav)
                                  + meta["title"] + meta.get("subtitle", ""))
    css = faces + css

    files = {"OEBPS/kindle.css": css, "OEBPS/nav.xhtml": xhtml_nav, "OEBPS/toc.ncx": ncx(meta, ident, tree),
             "OEBPS/content.opf": opf(meta, ident, docs, images, fonts, first), "OEBPS/images/cover.jpg": cover_jpeg()}
    files.update({f"OEBPS/{name}.xhtml": page(title, body, kind) for name, title, kind, body in docs})
    files.update({f"OEBPS/{href}": data for href, data in images.files.values()})
    files.update({f"OEBPS/{href}": data for href, data in fonts.items()})
    problems = check({k: v.encode("utf-8") if isinstance(v, str) else v for k, v in files.items()})

    os.makedirs(paths.DIST, exist_ok=True)
    with zipfile.ZipFile(OUT, "w") as z:
        # OCF: `mimetype` is the first entry and stored uncompressed, or readers cannot sniff the
        # file as an EPUB; letting zipfile deflate it, or writing it later, breaks the book.
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0" encoding="utf-8"?>\n<container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                   '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                   '</rootfiles></container>', compress_type=zipfile.ZIP_DEFLATED)
        for name, data in files.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

    # This edition exists only to be uploaded to KDP, so what a draft would let pass stops it.
    problems += [f"figure missing from the build: {name}" for name in images.missing]
    problems += [f"link to #{ref}, which no file defines" for ref in sorted(broken)]
    if unlinked:
        print(f"kindle: warning: {unlinked} link(s) to manuscript files kept as plain text")
    for p in problems:
        print(f"kindle: error: {p}")
    mb = os.path.getsize(OUT) / 1e6
    print(f"kindle: {len(doc['chapters'])} chapters, {len(images.files)} figures, {mb:.1f} MB "
          f"(delivery fee about ${0.15 * mb:.2f} a sale at 70%) -> {OUT}")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
