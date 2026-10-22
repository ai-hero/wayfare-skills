"""The technical edition: the manuscript as a numbered research paper, compiled with tectonic.

    ./publish technical

Chapters become sections, figures and diagrams one numbered figure series, the chapters' Sources
one deduplicated bibliography, and each curated appendix entry with its question, source and
validation. Writes a self-contained arXiv source bundle to `build/technical/`, then
`dist/technical.pdf` and `dist/technical-arxiv.tar.gz`. The abstract and keywords come from
`editions/technical.json` and must be verbatim from the text.
"""
import json
import os
import re
import shutil
import subprocess
import tarfile

import paths
from inline import CITE_MAP, EXAMPLE_TITLE, NOTES, REPOS, XREF_RE, md_latex, md_plain, tex_escape

HERE = os.path.join(paths.HERE, "technical")
BUILD = os.path.join(paths.BUILD, "technical")
MANIFEST = os.path.join(paths.EDITIONS, "technical.json")
STY = "neurips_2025.sty"

WORDS = ("Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve").split()
NUM = "|".join(WORDS[1:])
CHAP_RE = re.compile(rf"\b(Chapters?)\s+((?:{NUM}|\d+)(?:(?:,\s+|\s+and\s+|\s+to\s+)(?:{NUM}|\d+))*)\b")
FIG_RE = re.compile(r"\b(Diagram|Figure|Table)\s+(\d+\.T?\d+)\b")
Q_RE = re.compile(r"\bQ\s([a-z][a-z0-9]*(?:-[a-z0-9]+)+)\b")


# The manuscript says book and chapter; the paper says paper and section, and a chapter's own
# sections become subsections. One pass, so a word is never rewritten twice. "Chapter Four" is left
# for CHAP_RE, which turns it into a numbered cross-reference.
# "address book" is a contact list, not this book.
TERM = re.compile(rf"(?<!address )\b(book|chapter|section)(s?)\b(?!\s+(?:{NUM}|\d)\b)", re.I)
TERMS = {"book": "paper", "chapter": "section", "section": "subsection"}


def terms(text):
    def swap(m):
        word = TERMS[m.group(1).lower()] + m.group(2)
        return word.capitalize() if m.group(1)[0].isupper() else word
    return TERM.sub(swap, text)


def quotes(s):
    """Straight double quotes in the manuscript become curly pairs; the font would close both."""
    return re.sub(r'"([^"\n]*)"', "\u201c\\1\u201d", s)


class Refs:
    """Labels for everything the prose can point at, and the rewriting of its references."""

    def __init__(self, doc):
        self.chapters = {c["n"]: f"sec:{c['slug']}" for c in doc["chapters"]}
        self.figs, self.cards, self.rids = {}, {}, {}
        for c in doc["chapters"]:
            for s in c["sections"]:
                for b in s["blocks"]:
                    if b["kind"] != "figure" or b["type"] == "missing":
                        continue
                    lab = f"{'tab' if b['type'] == 'table' else 'fig'}:{b['label'].lower()}-{b['number']}"
                    b["_label"] = lab
                    self.figs[f"{b['label']} {b['number']}"] = lab
                    if b.get("id"):
                        self.figs[f"{b['label']} {b['id']}"] = lab
                    if b["type"] == "card":
                        self.cards[b["key"][2:]] = lab
                    if b.get("rid"):
                        self.rids[b["rid"]] = lab
        self.unmapped = set()
        self.index = {}
        for c in doc["chapters"]:
            for s in c["sections"]:
                for b in s["blocks"]:
                    if b["kind"] == "figure" and b["type"] != "missing":
                        self.index[f"fig:{b['key'][2:]}" if b["type"] == "card"
                                   else f"{b['label'].lower()}:{b['id']}"] = b
        self.evidenced = {sl for p in doc.get("appendix", {}).get("parts", []) for g in p["groups"]
                          for e in g["entries"] for sl in e["slugs"]}

    def chapter(self, m):
        nums = re.split(r",\s+|\s+and\s+|\s+to\s+", m.group(2))
        seps = re.findall(r",\s+|\s+and\s+|\s+to\s+", m.group(2))
        refs = [f"\\ref{{{self.chapters[int(n) if n.isdigit() else WORDS.index(n)]}}}" for n in nums]
        if len(refs) == 1:
            return f"Section~{refs[0]}"
        out = refs[0]
        for sep, r in zip(seps, refs[1:]):
            out += "--" + r if sep.strip() == "to" else ((", " if sep.strip() == "," else " and~") + r)
        return f"Sections~{out}"

    def figure(self, m):
        key = f"{m.group(1)} {m.group(2)}"
        lab = self.figs.get(key)
        if not lab:
            self.unmapped.add(key)
            return m.group(0)
        word = "Table" if lab.startswith("tab:") else "Figure"
        return f"{word}~\\ref{{{lab}}}"

    def evidence(self, m):
        return f"\\evidence{{{m.group(1)}}}" if m.group(1) in self.evidenced else f"Q~{m.group(1)}"

    def tex(self, md):
        stash = []

        def xref(m):
            stash.append(m)
            return f"\u27e6{len(stash) - 1}\u27e7"
        s = md_latex(XREF_RE.sub(xref, md), terms)
        s = CHAP_RE.sub(self.chapter, s)
        s = FIG_RE.sub(self.figure, s)
        s = quotes(Q_RE.sub(self.evidence, s))
        s = re.sub(r"(?:\\citep\{[^}]*\})+", lambda m: "\\citep{" + ",".join(re.findall(r"\{([^}]*)\}", m.group(0))) + "}", s)
        s = re.sub(r"\s+\\citep", r"~\\citep", s)
        for i, m in enumerate(stash):
            s = s.replace(f"\u27e6{i}\u27e7", self.xref(m))
        return s

    def xref(self, m):
        if m.group(1) == "ev":
            if m.group(2) not in self.evidenced:
                self.unmapped.add(m.group(0))
                return m.group(0)
            return f"(\\hyperref[ev:{m.group(2)}]{{evidence}})"
        b = self.index.get(f"{m.group(1)}:{m.group(2)}")
        if not b:
            self.unmapped.add(m.group(0))
            return m.group(0)
        name = f"{'Table' if b['_label'].startswith('tab:') else 'Figure'}~\\ref{{{b['_label']}}}"
        if m.group(3):
            return name
        slug = b["key"][2:] if b["type"] == "card" else None
        if slug in self.evidenced:
            return f"({name}; \\hyperref[ev:{slug}]{{evidence}})"
        return f"({name})"


def abstract(doc, manifest):
    """Each manifest sentence must still be in the named chapter, word for word, except a `text`
    entry: the summary the body only points to, so the paper does not print it twice."""
    by_n = {c["n"]: c for c in doc["chapters"]}
    out = []
    for item in manifest["abstract"]:
        if "text" in item:
            out.append(tex_escape(terms(item["text"])))
            continue
        ch = by_n[item["chapter"]]
        text = " ".join(md_plain(b.get("md", "")) for s in ch["sections"]
                        if s["title"] == item["section"] for b in s["blocks"])
        if item["sentence"] not in text:
            raise SystemExit(f"technical.json: not found verbatim in chapter {item['chapter']} "
                             f"'{item['section']}': {item['sentence']}")
        out.append(tex_escape(terms(item["sentence"])))
    corpus = " ".join(md_plain(b.get("md", "")) for c in doc["chapters"] for s in c["sections"] for b in s["blocks"])
    for kw in manifest.get("keywords", []):
        if kw.lower() not in corpus.lower():
            raise SystemExit(f"technical.json: keyword not in the text: {kw}")
    return " ".join(out), manifest.get("keywords", [])


URL_RE = re.compile(r"(?<![<(])(https?://[^\s<>]+?)([.,;:]?)(?=\s|$)")


def source_tex(md):
    """A source entry with each bare URL set as `\\url`, which breaks at slashes inside the narrow
    measure and sets it in the mono face as the reference does."""
    out, last = [], 0
    for m in URL_RE.finditer(md):
        out.append(quotes(md_latex(md[last:m.start()])) + "\\url{" + m.group(1).replace("%", "\\%").replace("#", "\\#") + "}" + m.group(2))
        last = m.end()
    out.append(quotes(md_latex(md[last:])))
    return "".join(out)


def bibliography(doc):
    """The book's one reference list, keyed `s<n>` so the paper's [n] are the book's and the web's. A
    source cited in the text is cited where the sentence is (`\\citep` through `CITE_MAP`); one still
    uncited stays in its chapter's trailing `\\sources` line. A `note-` key is the author's aside and
    becomes a footnote instead."""
    for c in doc["chapters"]:
        NOTES.update({k: md_latex(md, terms) for k, md in c["defs"].items() if k.startswith("note-")})
        for k, n in c["cite_n"].items():
            CITE_MAP.setdefault(k, f"s{n}")
    items = [(f"s{r['n']}", r["md"]) for r in doc["references"]]
    return items, {c["n"]: [f"s{n}" for n in c["further"]] for c in doc["chapters"]}


# The paper's text block is 5.5 in, so 300 ppi needs at most this many pixels across.
MAX_PX = 1650


def place(name):
    """Copy a figure into the bundle, a drawn diagram's paper copy when one is drawn. A chart PNG is flat colour with antialiased text, so a
    256-colour palette at print resolution looks the same and is about a third smaller; vector
    figures are copied as they are."""
    paper = os.path.join(paths.DIAGRAMS_PAPER, name)
    src = paper if os.path.exists(paper) else os.path.join(paths.ASSETS, name)
    dst = os.path.join(BUILD, "figures", name)
    if name.endswith(".svg"):
        # XeTeX can't size an SVG and halts; print it through the cover's Chrome path, which sets the
        # design system's fonts.
        from cover import chrome_pdf
        with open(src, encoding="utf-8") as f:
            svg = f.read()
        w, h = (float(re.search(rf'<svg[^>]*\b{a}="([\d.]+)', svg).group(1)) for a in ("width", "height"))
        name = name[:-4] + ".pdf"
        chrome_pdf(svg, w * 0.75, h * 0.75, os.path.join(BUILD, "figures", name))
        return name
    if not name.endswith(".png"):
        shutil.copyfile(src, dst)
        return name
    from PIL import Image
    with Image.open(src) as im:
        im = im.convert("RGBA")
        flat = Image.new("RGB", im.size, "white")
        flat.paste(im, mask=im.getchannel("A"))
        if flat.width > MAX_PX:
            flat = flat.resize((MAX_PX, round(flat.height * MAX_PX / flat.width)), Image.LANCZOS)
        # 256, not fewer: a heatmap's colour scale bands into visible steps at 64, and no pixel
        # measure separated those charts from the flat ones.
        flat.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(dst, optimize=True)
    return name


def asset(b):
    f = b["files"]
    return f"figures/{place(f.get('pdf') or f.get('png') or f.get('svg'))}"


def figure_tex(b, refs):
    if b["type"] == "missing":
        return f"% unresolved figure {b['ref']}\n"
    cap = refs.tex(b["caption_md"])
    if b["type"] == "table":
        return table_tex(b, refs, cap)
    if b["type"] == "card" and b["key"][2:] in refs.evidenced:
        slug = b["key"][2:]
        cap += f" \\hyperref[ev:{slug}]{{Evidence notes in Appendix~\\ref*{{app:evidence}}}}."
    tall = (b.get("height") or 0) > 1.05 * (b.get("width") or 1)
    size = "width=0.8\\linewidth" if tall else "width=\\linewidth"
    return ("\\begin{figure}[htbp]\n\\centering\n"
            f"\\includegraphics[{size},height=0.5\\textheight,keepaspectratio]{{{asset(b)}}}\n"
            f"\\caption{{{cap}}}\\label{{{b['_label']}}}\n\\end{{figure}}\n")


def table_tex(b, refs, cap):
    """A drawn table is too wide for portrait at a legible size, so it turns."""
    rows = b["rows"]
    ncol = len(rows[0])
    spec = "@{}>{\\raggedright\\arraybackslash}p{\\firstcol}" + \
        ">{\\raggedright\\arraybackslash}X" * (ncol - 1) + "@{}"
    names = [n for r in rows[1:] for n in re.findall(r"`([^`]+)`", r[0]["md"]) if n in REPOS]
    longest = f"\\settowidth{{\\firstcol}}{{\\texttt{{{tex_escape(max(names, key=len))}}}}}\n" if names else ""
    head = " & ".join(f"\\textbf{{{refs.tex(c['md'])}}}" for c in rows[0]) + " \\\\"
    body = []
    for r in rows[1:]:
        if all(not c["md"] for c in r[1:]):
            body.append(f"\\midrule\n\\multicolumn{{{ncol}}}{{@{{}}l}}{{\\textit{{{md_plain(r[0]['md'])}}}}} \\\\*")
        else:
            body.append(" & ".join(refs.tex(c["md"]) for c in r) + " \\\\\n\\addlinespace[4pt]")
    return ("\\begin{landscape}\n\\scriptsize\n\\setlength{\\tabcolsep}{4pt}\n\\setlength{\\firstcol}{0pt}\n"
            f"{longest}\\ifdim\\firstcol<2.4cm\\setlength{{\\firstcol}}{{2.4cm}}\\fi\n"
            f"\\begin{{xltabular}}{{\\linewidth}}{{{spec}}}\n"
            f"\\caption{{{cap}}}\\label{{{b['_label']}}}\\\\\n\\toprule\n{head}\n\\midrule\n\\endfirsthead\n"
            f"\\multicolumn{{{ncol}}}{{@{{}}l}}{{\\textit{{Table~\\ref{{{b['_label']}}}, continued}}}}\\\\\n"
            f"\\toprule\n{head}\n\\midrule\n\\endhead\n\\bottomrule\n\\endlastfoot\n"
            + "\n".join(body) + "\n\\end{xltabular}\n\\end{landscape}\n")


def column_weights(rows, line=88):
    """tabularx \\hsize factors (summing to the column count): each column first gets the width of
    its longest piece that cannot break, a repository name being one piece however many hyphens it
    has (and wider by a third, being typewriter), then the rest of the line in proportion to its text. Widths are in characters of the table
    font, `line` to the text width."""
    n = len(rows[0])
    cols = [[md_plain(r[i]["md"]) for r in rows] for i in range(n)]
    names = [[n for r in rows for n in re.findall(r"`([^`]+)`", r[i]["md"]) if n in REPOS] for i in range(n)]
    need = [max([len(p) for cell in col for p in re.split(r"\s+|(?<=-)", cell)] + [round(1.3 * len(x)) for x in names[i]],
                default=1) + 1 for i, col in enumerate(cols)]
    text = [max(1, sum(len(cell) for cell in col)) for col in cols]
    rest = max(0, line - 2 * (n - 1) - sum(need))
    w = [need[i] + rest * text[i] / sum(text) for i in range(n)]
    return [x * n / sum(w) for x in w]


def blocks_tex(blocks, refs):
    """A section's blocks, each `{{example}}` inside a `factoryexample` card. Its figures and tables
    float, and a float inside a framed box is lost, so they follow the card instead."""
    out, held = [], []
    for b in blocks:
        if b.get("example_start"):
            out.append("\\begin{factoryexample}\n")
        tex = block_tex(b, refs) + "\n"
        (held if b.get("example") and b["kind"] in ("figure", "table") else out).append(tex)
        if b.get("example_end"):
            out.append("\\end{factoryexample}\n")
            out += held
            held = []
    return out + held


def block_tex(b, refs):
    k = b["kind"]
    if k == "p":
        if b.get("example"):
            return "\\noindent " + refs.tex(b["md"]) + ("\n" if b.get("example_end") else "\\par\\smallskip\n")
        return refs.tex(b["md"]) + "\n"
    if k == "h3":
        return f"\\paragraph{{{refs.tex(b['md'])}}}"
    if k == "quote":
        return f"\\begin{{quote}}\\small\n{refs.tex(b['md'])}\n\\end{{quote}}\n"
    if k in ("ul", "ol"):
        env = "itemize" if k == "ul" else "enumerate"
        return f"\\begin{{{env}}}\n" + "".join(f"\\item {refs.tex(i['md'])}\n" for i in b["items"]) + f"\\end{{{env}}}\n"
    if k == "table":
        rows, n = b["rows"], len(b["rows"][0])
        spec = "@{}" + "".join(f">{{\\hsize={w:.3f}\\hsize\\raggedright\\arraybackslash}}X"
                                for w in column_weights(rows)) + "@{}"
        lines = [" & ".join(("\\textbf{%s}" % refs.tex(c["md"])) if i == 0 else refs.tex(c["md"]) for c in r)
                 + " \\\\" + ("\n\\midrule" if i == 0 else "") for i, r in enumerate(rows)]
        # Five equal columns at \small leave less than the width of `infrastructure-` in typewriter.
        size = "\\footnotesize\\setlength{\\tabcolsep}{4pt}" if n >= 5 else "\\small"
        return (f"\\begin{{table}}[tbp]\n\\centering{size}\n"
                f"\\begin{{tabularx}}{{\\linewidth}}{{{spec}}}\n\\toprule\n" + "\n".join(lines)
                + "\n\\bottomrule\n\\end{tabularx}\n\\end{table}\n")
    if k == "figure":
        return figure_tex(b, refs)
    return ""


RUN_IN = re.compile(r"^(Finding in the chapter|Finding|Question|Source|Evidence limitation|Firsthand context|Limits|Operating practice|Recorded sources|Selection|Sources|Method(?: \([^)]*\))?):\s+(.*)$", re.S)


def appendix_title():
    """The appendix's own heading, as the editor wrote it in its README."""
    with open(os.path.join(paths.APPENDIX, "README.md"), encoding="utf-8") as f:
        m = re.search(r"^# (.+)$", f.read(), re.M)
    return m.group(1).strip() if m else "Evidence"


def appendix_block(b, refs):
    """An entry's body in place: its tables do not float, or they drift away from the entry."""
    k = b["kind"]
    if k == "link":
        return ""
    if k == "p":
        m = RUN_IN.match(b["md"])
        if m:
            label = m.group(1).replace("Method (", "Method (\\texttt{").replace(")", "})") \
                if m.group(1).startswith("Method (") else terms(m.group(1))
            return f"\\noindent\\textit{{{label}.}} {refs.tex(m.group(2))}\\par\\smallskip\n"
        return refs.tex(b["md"]) + "\\par\\smallskip\n"
    if k == "table":
        n = len(b["rows"][0])
        rows = b["rows"]
        spec = "@{}>{\\raggedright\\arraybackslash}p{0.24\\linewidth}" + ">{\\raggedright\\arraybackslash}X" * (n - 1) + "@{}"
        if n >= 3:
            spec = "@{}" + "".join(f">{{\\hsize={w:.3f}\\hsize\\raggedright\\arraybackslash}}X"
                                    for w in column_weights(rows, line=96)) + "@{}"
        lines = [" & ".join(("\\textbf{%s}" % refs.tex(c["md"])) if i == 0 else refs.tex(c["md"]) for c in r)
                 + " \\\\" + ("\n\\midrule" if i == 0 else "") for i, r in enumerate(rows)]
        return ("{\\footnotesize\\noindent\n"
                f"\\begin{{tabularx}}{{\\linewidth}}{{{spec}}}\n\\toprule\n" + "\n".join(lines)
                + "\n\\bottomrule\n\\end{tabularx}\\par}\\smallskip\n")
    return block_tex(b, refs)


def appendix_chart(c):
    name = place(c["files"].get("pdf") or c["files"].get("png") or c["files"].get("svg"))
    return ("\\begin{center}\n"
            f"\\includegraphics[width=0.8\\linewidth,height=0.36\\textheight,keepaspectratio]{{figures/{name}}}\n"
            f"\\captionof{{figure}}{{Chart for \\texttt{{{tex_escape(c['slug'])}}}.}}\\label{{fig:appendix-{c['slug']}}}\n"
            "\\end{center}\n")


def evidence_appendix(doc, refs):
    """The editor's curated appendix (analysis/manuscript/appendix), not the full research collection:
    the author chose to publish only the evidence the chapters use."""
    app = doc["appendix"]
    out = [f"\\section{{{tex_escape(appendix_title())}}}\\label{{app:evidence}}\n", "\\raggedright\n"]
    out += [refs.tex(b["md"]) + "\\par\\medskip\n" for b in app["intro"]]
    labelled = set()
    for part in app["parts"]:
        if not any(g["entries"] for g in part["groups"]):
            continue
        out.append(f"\\subsection{{Section~\\ref{{{refs.chapters[part['n']]}}}: {tex_escape(part['title'])}}}\n")
        for g in part["groups"]:
            if not g["entries"]:
                continue
            out.append(f"\\subsubsection*{{{refs.tex(g['title'])}}}\n")
            for e in g["entries"]:
                slugs = ", ".join(f"\\texttt{{{tex_escape(sl)}}}" for sl in e["slugs"])
                lab = refs.rids.get(e["rid"]) if e["rid"] else None
                head = f"Figure~\\ref{{{lab}}} ({slugs})" if lab else (slugs or refs.tex(e.get("title") or ""))
                anchors = "".join(f"\\label{{ev:{sl}}}" for sl in e["slugs"] if sl not in labelled)
                labelled.update(e["slugs"])
                out.append(f"\\paragraph{{{head}.}}\\phantomsection{anchors}\\par\\smallskip\n")
                for b in e["blocks"]:
                    out.append(appendix_block(b, refs))
                for c in e["charts"]:
                    shown = refs.cards.get(c["slug"])
                    if shown:
                        out.append(f"\\noindent\\textit{{Chart:}} see Figure~\\ref{{{shown}}}.\\par\\smallskip\n")
                    else:
                        out.append(appendix_chart(c))
    return "".join(out)


def paper(doc, manifest):
    refs = Refs(doc)
    meta = doc["meta"]
    abs_text, keywords = abstract(doc, manifest)
    items, per_chapter = bibliography(doc)
    with open(os.path.join(HERE, "preamble.tex"), encoding="utf-8") as f:
        tex = [f.read(), f"\\newcommand{{\\exampletitle}}{{{tex_escape(EXAMPLE_TITLE.upper())}}}\n"]
    tex.append(f"\\title{{{tex_escape(meta['title'])}"
               + (f": {tex_escape(meta['subtitle'])}" if meta.get("subtitle") else "") + "}\n")
    tex.append(f"\\author{{{tex_escape(meta['author'])}\\\\{tex_escape(meta['affiliation'])}\\\\"
               f"\\href{{mailto:{meta['email']}}}{{\\texttt{{{tex_escape(meta['email'])}}}}}}}\n")
    when = f"{meta['edition']} edition · {meta['date']}" if meta.get("edition") else meta["date"]
    tex.append(f"\\date{{{tex_escape(when)}}}\n\\begin{{document}}\n\\maketitle\n")
    tex.append(f"\\begin{{abstract}}\n\\noindent {abs_text}\n\\par\\medskip\\noindent\\textbf{{Keywords:}} "
               f"{'; '.join(tex_escape(k) for k in keywords)}.\n\\end{{abstract}}\n")
    for c in doc["chapters"]:
        tex.append(f"\n\\section{{{tex_escape(c['title'])}}}\\label{{{refs.chapters[c['n']]}}}\n")
        for s in c["sections"]:
            if s["title"]:
                tex.append(f"\n\\FloatBarrier\n\\subsection{{{refs.tex(s['title'])}}}\\label{{sec:{c['slug']}:{s['slug']}}}\n")
            tex += blocks_tex(s["blocks"], refs)
        if per_chapter[c["n"]]:
            tex.append(f"\\sources{{{','.join(per_chapter[c['n']])}}}\n")
    if doc.get("preface"):
        tex.append(f"\n\\section*{{{tex_escape(terms(doc['preface']['title']))}}}\n")
        tex += [refs.tex(b["md"]) + "\n\n" for b in doc["preface"]["blocks"]]
    tex.append("\n\\clearpage\n\\appendix\n" + evidence_appendix(doc, refs))
    tex.append("\n\\clearpage\n\\begin{thebibliography}{99}\\small\\raggedright\n")
    tex += [f"\\bibitem{{{k}}} {source_tex(md)}\n" for k, md in items]
    tex.append("\\end{thebibliography}\n\\end{document}\n")
    return "".join(tex), refs


def compile_pdf():
    log = os.path.join(BUILD, "tectonic.log")
    with open(log, "w") as f:
        r = subprocess.run(["tectonic", "--keep-logs", "--keep-intermediates", "paper.tex"], cwd=BUILD,
                           stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        raise SystemExit(f"technical: tectonic failed, see {log}")
    with open(os.path.join(BUILD, "paper.log"), encoding="utf-8", errors="replace") as f:
        text = f.read()
    overfull = re.findall(r"Overfull \\hbox \((\d+\.\d+)pt", text)
    bad = [float(x) for x in overfull if float(x) > 2]
    undefined = sorted(set(re.findall(r"(?:Reference|Citation) `([^']+)' .*undefined", text)))
    missing = sorted(set(re.findall(r"Missing character: There is no (.) in font", text)))
    for msg, items in (("overfull boxes > 2pt", bad), ("undefined references", undefined),
                       ("missing glyphs", missing)):
        if items:
            print(f"warn: technical: {len(items)} {msg}: {items[:8]}")


def bundle():
    tar = os.path.join(paths.DIST, "technical-arxiv.tar.gz")
    with tarfile.open(tar, "w:gz") as t:
        t.add(os.path.join(BUILD, "paper.tex"), "paper.tex")
        t.add(os.path.join(BUILD, STY), STY)
        t.add(os.path.join(BUILD, "figures"), "figures")
        if os.path.exists(os.path.join(BUILD, "paper.bbl")):
            t.add(os.path.join(BUILD, "paper.bbl"), "paper.bbl")
    return tar


def main():
    with open(paths.SOURCE, encoding="utf-8") as f:
        doc = json.load(f)
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    shutil.rmtree(BUILD, ignore_errors=True)
    os.makedirs(os.path.join(BUILD, "figures"))
    shutil.copyfile(os.path.join(HERE, STY), os.path.join(BUILD, STY))
    os.makedirs(paths.DIST, exist_ok=True)
    tex, refs = paper(doc, manifest)
    with open(os.path.join(BUILD, "paper.tex"), "w", encoding="utf-8") as f:
        f.write(tex)
    if refs.unmapped:
        print(f"warn: technical: references with no figure: {sorted(refs.unmapped)}")
    compile_pdf()
    import fitz
    pdf = fitz.open(os.path.join(BUILD, "paper.pdf"))
    pdf.save(os.path.join(paths.DIST, "technical.pdf"), garbage=4, deflate=True, deflate_fonts=True, clean=True)
    print(f"technical: {os.path.join(paths.DIST, 'technical.pdf')} and {bundle()}")


if __name__ == "__main__":
    main()
