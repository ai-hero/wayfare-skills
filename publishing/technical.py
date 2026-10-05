"""The technical edition: the manuscript as a numbered research paper, compiled with tectonic.

    ./publish technical

Chapters become sections, figures and diagrams one numbered figure series, the chapters' Sources
one deduplicated bibliography, and every evidence card an appendix entry with its question,
source and validation. Writes a self-contained arXiv source bundle to `build/technical/`, then
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
from inline import md_latex, md_plain, tex_escape

HERE = os.path.join(paths.HERE, "technical")
BUILD = os.path.join(paths.BUILD, "technical")
MANIFEST = os.path.join(paths.EDITIONS, "technical.json")
STY = "neurips_2025.sty"

WORDS = ("Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve").split()
NUM = "|".join(WORDS[1:])
CHAP_RE = re.compile(rf"\b(Chapters?)\s+((?:{NUM}|\d+)(?:(?:,\s+|\s+and\s+|\s+to\s+)(?:{NUM}|\d+))*)\b")
FIG_RE = re.compile(r"\b(Diagram|Figure|Table)\s+(\d+\.T?\d+)\b")
Q_RE = re.compile(r"\bQ\s([a-z][a-z0-9]*(?:-[a-z0-9]+)+)\b")


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
        s = md_latex(md)
        s = CHAP_RE.sub(self.chapter, s)
        s = FIG_RE.sub(self.figure, s)
        return quotes(Q_RE.sub(self.evidence, s))


def abstract(doc, manifest):
    """Each manifest sentence must still be in the named chapter, word for word."""
    by_n = {c["n"]: c for c in doc["chapters"]}
    out = []
    for item in manifest["abstract"]:
        ch = by_n[item["chapter"]]
        text = " ".join(md_plain(b.get("md", "")) for s in ch["sections"]
                        if s["title"] == item["section"] for b in s["blocks"])
        if item["sentence"] not in text:
            raise SystemExit(f"technical.json: not found verbatim in chapter {item['chapter']} "
                             f"'{item['section']}': {item['sentence']}")
        out.append(tex_escape(item["sentence"]))
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
    """Sources deduplicated by their plain text, numbered in order of first appearance."""
    keys, items, per_chapter = {}, [], {}
    for c in doc["chapters"]:
        per_chapter[c["n"]] = []
        for src in c["sources"]:
            norm = re.sub(r"\s+", " ", md_plain(src["md"])).strip().lower()
            if norm not in keys:
                keys[norm] = f"s{len(keys) + 1}"
                items.append((keys[norm], src["md"]))
            if keys[norm] not in per_chapter[c["n"]]:
                per_chapter[c["n"]].append(keys[norm])
    return items, per_chapter


def asset(b):
    f = b["files"]
    name = f.get("pdf") or f.get("png") or f.get("svg")
    shutil.copyfile(os.path.join(paths.ASSETS, name), os.path.join(BUILD, "figures", name))
    return f"figures/{name}"


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
    return ("\\begin{figure}[tbp]\n\\centering\n"
            f"\\includegraphics[{size},height=0.5\\textheight,keepaspectratio]{{{asset(b)}}}\n"
            f"\\caption{{{cap}}}\\label{{{b['_label']}}}\n\\end{{figure}}\n")


def table_tex(b, refs, cap):
    """Seven text columns do not fit portrait at a legible size, so the part-by-part table turns."""
    rows = b["rows"]
    ncol = len(rows[0])
    spec = "@{}>{\\raggedright\\arraybackslash}p{2.4cm}" + \
        ">{\\raggedright\\arraybackslash}X" * (ncol - 1) + "@{}"
    head = " & ".join(f"\\textbf{{{refs.tex(c['md'])}}}" for c in rows[0]) + " \\\\"
    body = []
    for r in rows[1:]:
        if all(not c["md"] for c in r[1:]):
            body.append(f"\\midrule\n\\multicolumn{{{ncol}}}{{@{{}}l}}{{\\textit{{{md_plain(r[0]['md'])}}}}} \\\\*")
        else:
            body.append(" & ".join(refs.tex(c["md"]) for c in r) + " \\\\\n\\addlinespace[4pt]")
    return ("\\begin{landscape}\n\\scriptsize\n\\setlength{\\tabcolsep}{4pt}\n"
            f"\\begin{{xltabular}}{{\\linewidth}}{{{spec}}}\n"
            f"\\caption{{{cap}}}\\label{{{b['_label']}}}\\\\\n\\toprule\n{head}\n\\midrule\n\\endfirsthead\n"
            f"\\multicolumn{{{ncol}}}{{@{{}}l}}{{\\textit{{Table~\\ref{{{b['_label']}}}, continued}}}}\\\\\n"
            f"\\toprule\n{head}\n\\midrule\n\\endhead\n\\bottomrule\n\\endlastfoot\n"
            + "\n".join(body) + "\n\\end{xltabular}\n\\end{landscape}\n")


def block_tex(b, refs):
    k = b["kind"]
    if k == "p":
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
        spec = "@{}" + ">{\\raggedright\\arraybackslash}X" * n + "@{}"
        lines = [" & ".join(("\\textbf{%s}" % refs.tex(c["md"])) if i == 0 else refs.tex(c["md"]) for c in r)
                 + " \\\\" + ("\n\\midrule" if i == 0 else "") for i, r in enumerate(rows)]
        return ("\\begin{table}[tbp]\n\\centering\\small\n"
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
                if m.group(1).startswith("Method (") else m.group(1)
            return f"\\noindent\\textit{{{label}.}} {refs.tex(m.group(2))}\\par\\smallskip\n"
        return refs.tex(b["md"]) + "\\par\\smallskip\n"
    if k == "table":
        n = len(b["rows"][0])
        # The shared parser splits on every `|`, including Markdown's escaped `\|` inside a cell, so a
        # row longer than its header is one cell broken apart; rejoin it with the pipes restored.
        rows = [r[:n - 1] + [{"md": " | ".join(c["md"].rstrip("\\") for c in r[n - 1:])}] if len(r) > n else r
                for r in b["rows"]]
        spec = "@{}>{\\raggedright\\arraybackslash}p{0.24\\linewidth}" + ">{\\raggedright\\arraybackslash}X" * (n - 1) + "@{}"
        lines = [" & ".join(("\\textbf{%s}" % refs.tex(c["md"])) if i == 0 else refs.tex(c["md"]) for c in r)
                 + " \\\\" + ("\n\\midrule" if i == 0 else "") for i, r in enumerate(rows)]
        return ("{\\footnotesize\\noindent\n"
                f"\\begin{{tabularx}}{{\\linewidth}}{{{spec}}}\n\\toprule\n" + "\n".join(lines)
                + "\n\\bottomrule\n\\end{tabularx}\\par}\\smallskip\n")
    return block_tex(b, refs)


def appendix_chart(c):
    name = c["files"].get("pdf") or c["files"].get("png") or c["files"].get("svg")
    shutil.copyfile(os.path.join(paths.ASSETS, name), os.path.join(BUILD, "figures", name))
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
        tex = [f.read()]
    tex.append(f"\\title{{{tex_escape(meta['title'])}"
               + (f": {tex_escape(meta['subtitle'])}" if meta.get("subtitle") else "") + "}\n")
    tex.append(f"\\author{{{tex_escape(meta['author'])}\\\\{tex_escape(meta['affiliation'])}"
               f"\\thanks{{Correspondence to: \\href{{mailto:{meta['email']}}}{{\\texttt{{{tex_escape(meta['email'])}}}}}.}}}}\n")
    when = f"{meta['edition']} · {meta['date']}" if meta.get("edition") else meta["date"]
    tex.append(f"\\date{{{tex_escape(when)}}}\n\\begin{{document}}\n\\maketitle\n")
    tex.append(f"\\begin{{abstract}}\n\\noindent {abs_text}\n\\par\\medskip\\noindent\\textbf{{Keywords:}} "
               f"{'; '.join(tex_escape(k) for k in keywords)}.\n\\end{{abstract}}\n")
    for c in doc["chapters"]:
        tex.append(f"\n\\section{{{tex_escape(c['title'])}}}\\label{{{refs.chapters[c['n']]}}}\n")
        for s in c["sections"]:
            if s["title"]:
                tex.append(f"\n\\subsection{{{refs.tex(s['title'])}}}\\label{{sec:{c['slug']}:{s['slug']}}}\n")
            for b in s["blocks"]:
                tex.append(block_tex(b, refs) + "\n")
        if per_chapter[c["n"]]:
            tex.append(f"\\sources{{{','.join(per_chapter[c['n']])}}}\n")
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
    shutil.copyfile(os.path.join(BUILD, "paper.pdf"), os.path.join(paths.DIST, "technical.pdf"))
    print(f"technical: {os.path.join(paths.DIST, 'technical.pdf')} and {bundle()}")


if __name__ == "__main__":
    main()
