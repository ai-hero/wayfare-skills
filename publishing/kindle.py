"""The Kindle edition: book.json as a reflowable EPUB 3 for Kindle Direct Publishing.

    ./publish kindle        -> $PUBLISH_OUT/dist/book.epub

The same text, figures, case records and references as the print book, one XHTML file per
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
from book import ONES, case_records_only, esc, example, fig_id
from inline import md_plain

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
XHTML_NS = 'xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"'
XML_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}


def xml_safe(s):
    """Named HTML entities other than XML's five are undefined in XHTML and fail the whole file."""
    return re.sub(r"&([A-Za-z][A-Za-z0-9]*);",
                  lambda m: m.group(0) if m.group(1) in XML_ENTITIES
                  else f"&#{html.entities.name2codepoint.get(m.group(1), 0xFFFD)};", s)


def page(title, body, kind=None):
    attr = f' epub:type="{kind}"' if kind else ""
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
        href = f"images/{os.path.splitext(os.path.basename(name))[0]}.png"
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


def table_html(rows, cls=""):
    head = "".join(f"<th>{c['html']}</th>" for c in rows[0])
    body = []
    for r in rows[1:]:
        if len(r) > 1 and all(not c["md"] for c in r[1:]):
            body.append(f'<tr class="group"><td colspan="{len(r)}">{r[0]["html"]}</td></tr>')
        else:
            body.append("<tr>" + "".join(f"<td>{c['html']}</td>" for c in r) + "</tr>")
    cls = f' class="{cls}"' if cls else ""
    return f'<table{cls}><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def figure(b, images):
    label = f'{b["label"]} {b["number"]}'
    anchor = EVIDENCE.get(b.get("rid"))
    ptr = f' <a class="evidence-ptr" href="#{anchor}">Evidence</a>' if anchor else ""
    title = f'<p class="panel-title">{esc(label)}</p>'
    cap = f'<figcaption>{b["caption_html"]}{ptr}</figcaption>'
    if b["type"] == "table":
        return f'<figure id="{fig_id(b)}">{title}{table_html(b["rows"])}{cap}</figure>'
    files = b.get("files") or {}
    src = images.add(files.get("png") or files.get("svg"))
    if not src:
        return f'<figure id="{fig_id(b)}">{title}<p>[{esc(b["ref"])} is missing from this build]</p>{cap}</figure>'
    alt = b.get("alt") or md_plain(b["caption_md"])
    return f'<figure id="{fig_id(b)}">{title}<img src="{src}" alt="{esc(alt)}"/>{cap}</figure>'


def block(b, images):
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
        out = table_html(b["rows"], "prose-table")
    elif k == "figure":
        out = figure(b, images)
    else:
        return ""
    return example(b, out)


def chapter(c, images):
    out = [f'<section epub:type="chapter" id="ch-{c["n"]}"><p class="chapter-number">Chapter {ONES[c["n"]]}</p>'
           f'<h1>{esc(c["title"])}</h1>']
    for s in c["sections"]:
        if s["title"]:
            out.append(f'<h2 id="ch-{c["n"]}-{s["slug"]}">{s["html"]}</h2>')
        out += [block(b, images) for b in s["blocks"]]
    if c.get("further"):
        refs = ", ".join(f'<a class="cite" href="#ref-{n}">{n}</a>' for n in c["further"])
        out.append(f'<p class="first">Further sources: [{refs}].</p>')
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
              f'<section class="title-page"><p class="book-title">{esc(meta["title"])}</p>'
              f'<p class="subtitle">{esc(meta.get("subtitle"))}</p><p>{esc(meta["author"])}</p>'
              f'<p>{esc(meta.get("affiliation"))}</p></section>'),
             ("copyright", "Copyright", "copyright-page",
              f'<section class="copyright"><p>{esc(meta.get("copyright"))}</p>'
              f'<p>{esc(meta.get("edition"))} edition · {esc(meta.get("date"))}</p>'
              f'<p>All rights reserved. Corrections are welcome at {esc(meta.get("email"))}.</p></section>')]
    if preface:
        body = "".join(f"<p>{b['html']}</p>" for b in preface["blocks"])
        pages.append(("preface", preface["title"], "preface", f'<section id="preface"><h1>{esc(preface["title"])}</h1>{body}</section>'))
    return pages


FN = re.compile(r'<span class="fn" data-key="[^"]*">(.*?)</span>', re.S)


def footnotes(name, body):
    """The author's notes as EPUB footnotes: a numbered call in the text and the note at the end of
    its file, which Kindle shows as a pop-up. Left as the span, the note runs into the sentence."""
    notes = []

    def call(m):
        notes.append(m.group(1))
        n = len(notes)
        return (f'<a epub:type="noteref" class="noteref" id="{name}-fnref-{n}" href="#{name}-fn-{n}">'
                f'<sup>{n}</sup></a>')
    body = FN.sub(call, body)
    if notes:
        body += "".join(f'<aside epub:type="footnote" class="footnote" id="{name}-fn-{n}"><p>'
                        f'<a href="#{name}-fnref-{n}">{n}.</a> {t}</p></aside>'
                        for n, t in enumerate(notes, 1))
    return body


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


def nav(meta, chapters, has_preface, appendix_parts, appendix_title, has_refs):
    rows = []
    if has_preface:
        rows.append('<li><a href="preface.xhtml">Use of AI tools</a></li>')
    for c in chapters:
        subs = "".join(f'<li><a href="ch-{c["n"]}.xhtml#ch-{c["n"]}-{s["slug"]}">{md_plain(s["title"])}</a></li>'
                       for s in c["sections"] if s["title"])
        rows.append(f'<li><a href="ch-{c["n"]}.xhtml">{ONES[c["n"]]}. {esc(c["title"])}</a>'
                    + (f"<ol>{subs}</ol>" if subs else "") + "</li>")
    if appendix_parts:
        parts = "".join(f'<li><a href="appendix-{p["n"]}.xhtml">Chapter {ONES[p["n"]]} · {esc(p["title"])}</a></li>'
                        for p in appendix_parts)
        rows.append(f'<li><a href="appendix.xhtml">Appendix: {esc(appendix_title)}</a><ol>{parts}</ol></li>')
    if has_refs:
        rows.append('<li><a href="references.xhtml">References</a></li>')
    first = f"ch-{chapters[0]['n']}.xhtml"
    body = (f'<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>{"".join(rows)}</ol></nav>'
            f'<nav epub:type="landmarks" hidden=""><ol>'
            f'<li><a epub:type="cover" href="cover.xhtml">Cover</a></li>'
            f'<li><a epub:type="toc" href="nav.xhtml">Contents</a></li>'
            f'<li><a epub:type="bodymatter" href="{first}">Start</a></li></ol></nav>')
    return page("Contents", body), first


def ncx(meta, ident, xhtml_nav):
    """The EPUB 2 table of contents, which older Kindle devices read instead of the nav document."""
    points, n = [], 0
    for href, label in re.findall(r'<a href="([^"]+)">([^<]+)</a>', xhtml_nav.split('epub:type="landmarks"')[0]):
        n += 1
        points.append(f'<navPoint id="np{n}" playOrder="{n}"><navLabel><text>{label}</text></navLabel>'
                      f'<content src="{href}"/></navPoint>')
    return ('<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
            f'<head><meta name="dtb:uid" content="urn:uuid:{ident}"/><meta name="dtb:depth" content="1"/>'
            '<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>'
            f'<docTitle><text>{esc(meta["title"])}</text></docTitle><navMap>{"".join(points)}</navMap></ncx>')


def opf(meta, ident, docs, images, first):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
             '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
             '<item id="css" href="kindle.css" media-type="text/css"/>',
             '<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>']
    items += [f'<item id="{name}" href="{name}.xhtml" media-type="application/xhtml+xml"/>' for name, *_ in docs]
    items += [f'<item id="img{i}" href="{href}" media-type="image/png"/>' for i, (href, _) in enumerate(images.files.values())]
    spine = ['<itemref idref="cover" linear="yes"/>']
    for name, *_ in docs:
        if name == "cover":
            continue
        spine.append(f'<itemref idref="{name}"/>')
        if name == "copyright":
            spine.append('<itemref idref="nav"/>')
    sub = f'<meta refines="#title" property="title-type">main</meta>'
    subtitle = (f'<dc:title id="subtitle">{esc(meta["subtitle"])}</dc:title>'
                f'<meta refines="#subtitle" property="title-type">subtitle</meta>') if meta.get("subtitle") else ""
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="en">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:identifier id="uid">urn:uuid:{ident}</dc:identifier>'
            f'<dc:title id="title">{esc(meta["title"])}</dc:title>{sub}{subtitle}'
            f'<dc:creator>{esc(meta["author"])}</dc:creator><dc:language>en-US</dc:language>'
            f'<dc:publisher>{esc(meta.get("affiliation"))}</dc:publisher><dc:date>{meta.get("year")}</dc:date>'
            f'<dc:rights>{esc(meta.get("copyright"))}</dc:rights>'
            f'<meta property="dcterms:modified">{now}</meta><meta name="cover" content="cover-image"/>'
            f'</metadata><manifest>{"".join(items)}</manifest>'
            f'<spine toc="ncx">{"".join(spine)}</spine>'
            f'<guide><reference type="cover" title="Cover" href="cover.xhtml"/>'
            f'<reference type="toc" title="Contents" href="nav.xhtml"/>'
            f'<reference type="text" title="Start" href="{first}"/></guide></package>')


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
    return problems


def main():
    with open(paths.SOURCE, encoding="utf-8") as f:
        doc = case_records_only(json.load(f))
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
    docs = [("cover", "Cover", "cover", '<div class="cover"><img src="images/cover.jpg" alt="Cover"/></div>')]
    docs += front_matter(meta, doc.get("preface"))
    docs += [(f"ch-{c['n']}", c["title"], "bodymatter", chapter(c, images)) for c in doc["chapters"]]
    if appx.get("parts"):
        intro = "".join(f"<p>{b['html']}</p>" for b in appx["intro"])
        docs.append(("appendix", appx["title"], "backmatter",
                     f'<section epub:type="appendix" id="appendix"><p class="chapter-number">Appendix</p>'
                     f'<h1>{esc(appx["title"])}</h1>{intro}</section>'))
        docs += [(f"appendix-{p['n']}", p["title"], "backmatter", appendix_part(p, appx["title"], images))
                 for p in appx["parts"]]
    if doc.get("references"):
        refs = "".join(f'<p id="ref-{r["n"]}">[{r["n"]}] {r["html"]}</p>' for r in doc["references"])
        docs.append(("references", "References", "backmatter",
                     f'<section epub:type="bibliography" id="references"><h1>References</h1>'
                     f'<div class="reference-list">{refs}</div></section>'))
    docs = [(name, title, kind, footnotes(name, body)) for name, title, kind, body in docs]
    docs, broken, unlinked = link(docs)
    xhtml_nav, first = nav(meta, doc["chapters"], bool(doc.get("preface")), appx.get("parts"), appx.get("title"),
                             bool(doc.get("references")))
    ident = uuid.uuid5(uuid.NAMESPACE_URL, f"aihero.studio/book/{meta['title']}")
    with open(os.path.join(HERE, "kindle.css"), encoding="utf-8") as f:
        css = f.read()

    files = {"OEBPS/kindle.css": css, "OEBPS/nav.xhtml": xhtml_nav, "OEBPS/toc.ncx": ncx(meta, ident, xhtml_nav),
             "OEBPS/content.opf": opf(meta, ident, docs, images, first), "OEBPS/images/cover.jpg": cover_jpeg()}
    files.update({f"OEBPS/{name}.xhtml": page(title, body, kind) for name, title, kind, body in docs})
    files.update({f"OEBPS/{href}": data for href, data in images.files.values()})
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

    for name in images.missing:
        print(f"kindle: warning: figure file missing from the build: {name}")
    if unlinked:
        print(f"kindle: warning: {unlinked} link(s) to manuscript files kept as plain text")
    for ref in sorted(broken):
        print(f"kindle: warning: link to #{ref}, which no file defines")
    for p in problems:
        print(f"kindle: error: {p}")
    mb = os.path.getsize(OUT) / 1e6
    print(f"kindle: {len(doc['chapters'])} chapters, {len(images.files)} figures, {mb:.1f} MB "
          f"(delivery fee about ${0.15 * mb:.2f} a sale at 70%) -> {OUT}")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
