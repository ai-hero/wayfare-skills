"""One inline Markdown reading, three outputs: HTML for the book and the web, LaTeX for the
technical edition, plain text for slides and alt text."""
import json
import os
import re

from markdown_it import MarkdownIt

import paths

# The label every edition sets at the top of an `{{example}}` card.
EXAMPLE_TITLE = "Inside this factory:"

MD = MarkdownIt("commonmark")

# `[^key]` is a source marker, `{{fig:slug}}` a figure marker. Both are resolved per edition; the
# editions that do not resolve them (plain text for slides and alt text) must drop them.
NOTE_RE = re.compile(r"\[\^([a-z0-9][a-z0-9-]*)\]")
XREF_RE = re.compile(r"\{\{(fig|diagram|figure|table|ev):([A-Za-z0-9.-]+)(\|name)?\}\}")
_MARKER_GAP = re.compile(r"\s*(?:\[\^[a-z0-9][a-z0-9-]*\]|\{\{[^}]*\}\})")
CITE_MAP = {}  # source key -> bibliography key, set by the technical edition
NOTES = {}  # `note-` source key -> footnote LaTeX: the author's aside rather than a source
_NOTE_OPEN = re.compile(r'<span class="fn"[^>]*>')
_SPAN_TAG = re.compile(r"<span\b[^>]*>|</span>")


def note_end(html_text, i):
    """Where the author's note opening at `i` ends, or None when none opens there. A note may hold
    spans of its own, so its close is found by depth: the first `</span>` would cut it short."""
    m = _NOTE_OPEN.match(html_text, i)
    if not m:
        return None
    depth = 1
    for t in _SPAN_TAG.finditer(html_text, m.end()):
        depth += -1 if t.group(0) == "</span>" else 1
        if depth == 0:
            return t.end()
    raise ValueError(f"unclosed author's note: {html_text[i:i + 80]}")


def sub_notes(html_text, repl):
    """`html_text` with each author's note replaced by `repl(the note's inner HTML)`."""
    out, pos = [], 0
    while (m := _NOTE_OPEN.search(html_text, pos)):
        end = note_end(html_text, m.start())
        out += [html_text[pos:m.start()], repl(html_text[m.end():end - len("</span>")])]
        pos = end
    return "".join(out) + html_text[pos:]


def _repo_pairs():
    """The manuscript's `repo-names.json` as (real name, plain name) pairs. A missing or malformed
    map stops the build: without it the book prints the real repository names."""
    path = os.path.join(paths.MANUSCRIPT, "repo-names.json")
    try:
        with open(path, encoding="utf-8") as f:
            return [(r["old"], r["new"]) for r in json.load(f)["repos"]]
    except (OSError, KeyError, ValueError) as e:
        raise SystemExit(f"cannot read {path}: {e}")


_PAIRS = _repo_pairs()
REPOS = {n for pair in _PAIRS for n in pair}  # names, plain and original, set as a grey chip
REPO_MAP = dict(_PAIRS)


# Inside a longer label only a hyphenated name is swapped: `auth` and `website` are also ordinary words.
_REPO_WORD = re.compile(r"(?<![\w-])(" + "|".join(re.escape(k) for k in sorted(
    (k for k, v in REPO_MAP.items() if "-" in k and k != v), key=len, reverse=True)) + r")(?![\w-])") \
    if any("-" in k and k != v for k, v in REPO_MAP.items()) else None


def repo_display(label):
    """A label that is exactly a repository's name becomes its plain name, and a hyphenated repository name
    inside a longer label ("The plugin (wayfare-skills)") is swapped in place."""
    if not isinstance(label, str):
        return label
    if label.strip() in REPO_MAP:
        return REPO_MAP[label.strip()]
    return _REPO_WORD.sub(lambda m: REPO_MAP[m.group(1)], label) if _REPO_WORD else label


# `auth` and `website` are also ordinary words ("auth features", "the marketing website"), so in running
# text they are swapped only where the context makes them a repository: in backticks, possessive, as the
# first field of a `repo|pr|n` record, before " session", or listed beside another repository's name.
_AMBIGUOUS = {"auth", "website"}
_NAMES = "|".join(re.escape(n) for n in sorted({n for k, v in REPO_MAP.items() for n in (k, v)}, key=len, reverse=True))
_PLAIN_CLEAR = re.compile(r"(?<![\w./-])(" + "|".join(re.escape(k) for k in sorted(
    (k for k, v in REPO_MAP.items() if k != v and k not in _AMBIGUOUS), key=len, reverse=True)) + r")(?![\w/-]|\.\w)") \
    if any(k != v and k not in _AMBIGUOUS for k, v in REPO_MAP.items()) else None
_PLAIN_AMBIGUOUS = re.compile(
    r"(?<![\w./-])(auth|website)(?=`|'s\b|\||\s+session\b|,\s*`?(?:" + _NAMES + r")\b|\s+(?:and|to)\s+`?(?:" + _NAMES + r")\b)"
    r"|(?<=`)(auth|website)(?=`)") if _NAMES else None
_AFTER_NAME = re.compile(r"(\b(?:" + _NAMES + r")`?,?\s+(?:and\s+)?`?)(auth|website)(?![\w/-]|\.\w)") if _NAMES else None


def plain_repos(text):
    """Running text with every repository named by its plain name. URLs and paths keep the original
    (a `/` or `.` beside the name), since renaming them would break the link or the path."""
    if not isinstance(text, str) or not REPO_MAP:
        return text
    if _PLAIN_CLEAR:
        text = _PLAIN_CLEAR.sub(lambda m: REPO_MAP[m.group(1)], text)
    if _PLAIN_AMBIGUOUS:
        text = _PLAIN_AMBIGUOUS.sub(lambda m: REPO_MAP[next(g for g in m.groups() if g)], text)
        text = _AFTER_NAME.sub(lambda m: m.group(1) + REPO_MAP[m.group(2)], text)
    return text


def chip_repos(html):
    """`<code>name</code>` for a repository becomes `<code class="repo">`; other code stays plain."""
    return re.sub(r"<code>([^<]+)</code>", lambda m: f'<code class="repo">{m.group(1)}</code>' if m.group(1) in REPOS else m.group(0), html)

LATEX_ESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
             "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def md_html(text):
    return chip_repos(MD.renderInline(text or "").strip())


def _children(text):
    toks = MD.parseInline(text or "")
    return toks[0].children if toks else []


def md_plain(text):
    text = _MARKER_GAP.sub("", text or "")
    return "".join(t.content for t in _children(text) if t.type in ("text", "code_inline")).strip() \
        if text else ""


def tex_escape(s):
    s = "".join(LATEX_ESC.get(c, c) for c in s)
    # A bare URL-like token (github.com/x/y) has no break points; \allowbreak after slashes and dots
    # lets it wrap instead of running into the margin.
    s = re.sub(r"(?<=[a-z])([/.])(?=[a-z])", r"\1\\allowbreak{}", s) if "/" in s else s
    return s


def _text_latex(content, words):
    out = []
    for part in NOTE_RE.split(content):
        if len(out) % 2:
            out.append(r"\footnote{" + NOTES[part] + "}" if part in NOTES else r"\citep{" + CITE_MAP.get(part, part) + "}")
        else:
            out.append(tex_escape(words(part) if words else part))
    return "".join(out)


def md_latex(text, words=None):
    """`words` rewrites the running text only (not code, links or URLs): the technical edition's
    book-to-paper vocabulary."""
    out = []
    for t in _children(text):
        if t.type == "text":
            out.append(_text_latex(t.content, words))
        elif t.type == "code_inline":
            if t.content in REPOS:
                out.append(r"\repo{\texttt{" + tex_escape(t.content) + "}}")
            else:
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
