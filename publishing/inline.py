"""One inline Markdown reading, three outputs: HTML for the book and the web, LaTeX for the
technical edition, plain text for slides and alt text."""
import re

from markdown_it import MarkdownIt

MD = MarkdownIt("commonmark")

LATEX_ESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
             "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def md_html(text):
    return MD.renderInline(text or "").strip()


def _children(text):
    toks = MD.parseInline(text or "")
    return toks[0].children if toks else []


def md_plain(text):
    return "".join(t.content for t in _children(text) if t.type in ("text", "code_inline")).strip() \
        if text else ""


def tex_escape(s):
    s = "".join(LATEX_ESC.get(c, c) for c in s)
    # A bare URL-like token (github.com/x/y) has no break points; \allowbreak after slashes and dots
    # lets it wrap instead of running into the margin.
    s = re.sub(r"(?<=[a-z])([/.])(?=[a-z])", r"\1\\allowbreak{}", s) if "/" in s else s
    return s


def md_latex(text):
    out = []
    for t in _children(text):
        if t.type == "text":
            out.append(tex_escape(t.content))
        elif t.type == "code_inline":
            out.append(r"\texttt{" + tex_escape(t.content) + "}")
        elif t.type == "em_open":
            out.append(r"\emph{")
        elif t.type == "strong_open":
            out.append(r"\textbf{")
        elif t.type in ("em_close", "strong_close", "link_close"):
            out.append("}")
        elif t.type == "link_open":
            out.append(r"\href{" + t.attrGet("href").replace("%", r"\%").replace("#", r"\#") + "}{")
        elif t.type in ("softbreak", "hardbreak"):
            out.append(" ")
        elif t.type == "html_inline":
            continue
    return "".join(out)
