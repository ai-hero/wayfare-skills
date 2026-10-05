"""Resolve manifest references to the author's own words.

Every string a slide shows is found verbatim in the built source (`book.json`): a reference that no
longer matches is an error naming the slide, so an edit to the manuscript surfaces here instead of
leaving a slide that quotes text the book no longer has."""
import re
from inline import md_plain


class RefError(Exception):
    pass


def chapter(doc, n):
    for c in doc["chapters"]:
        if c["n"] == n:
            return c
    raise RefError(f"no chapter {n}")


def section(ch, title):
    for s in ch["sections"]:
        if (s["title"] or "") == (title or ""):
            return s
    raise RefError(f"chapter {ch['n']} has no section {title!r}")


def paragraphs(sec):
    return [b for b in sec["blocks"] if b["kind"] == "p"]


def find_sentence(doc, n, sec_title, text):
    """The paragraph (plain text) holding `text` verbatim; `text` itself is what the slide shows."""
    sec = section(chapter(doc, n), sec_title)
    for b in paragraphs(sec):
        if text in md_plain(b["md"]):
            return md_plain(b["md"])
    raise RefError(f"chapter {n}, {sec_title or 'opening'}: no paragraph contains {text!r}")


def find_figure(doc, ref):
    for c in doc["chapters"]:
        for s in c["sections"]:
            prev = None
            for b in s["blocks"]:
                if b["kind"] == "figure" and (f"{b['label']} {b['number']}" == ref or b["ref"] == ref):
                    return c, s, b, prev
                if b["kind"] == "p":
                    prev = b
    raise RefError(f"no figure {ref}")


def takeaway(caption, rule):
    """A headline cut from the caption at a clause boundary; never reworded."""
    cap = md_plain(caption).strip()
    if rule == "full":
        out = cap
    elif rule == "clause":
        out = re.split(r";\s", cap, maxsplit=1)[0]
    elif rule == "comma":
        out = re.split(r",\s", cap, maxsplit=1)[0]
    elif isinstance(rule, dict) and "until" in rule:
        if not cap.startswith(rule["until"]):
            raise RefError(f"caption does not start with {rule['until']!r}")
        out = rule["until"]
    else:
        raise RefError(f"unknown takeaway rule {rule!r}")
    out = out.rstrip(" ,;:")
    return out if out.endswith((".", "?", "!")) else out + "."
