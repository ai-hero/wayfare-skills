"""The talk: a .pptx built on the A.I. Hero template (`.analysis/A.I. Hero.potx`), from a manifest.

    ./publish slides

The manifest, `$PUBLISH_OUT/editions/slides.json`, is the deck's source: an ordered list of slides,
each naming a template layout and pointing at the book by chapter, section, figure and verbatim
sentence. It lives beside the build (gitignored) because it quotes the findings. With no manifest,
`slides/slide_seed.py` writes a starting one from the book's structure; edit it, never the .pptx.

Every slide is a template layout with its placeholders filled; the theme does the styling. Slide
text is the author's words, and speaker notes carry the paragraph each slide stands for.
`dist/slides.pdf` is converted by LibreOffice for review (`./publish qa slides`).
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "slides"))

import paths  # noqa: E402
import slide_template as P  # noqa: E402
from inline import md_plain  # noqa: E402
from slide_text import RefError, chapter, find_figure, find_sentence, section, takeaway  # noqa: E402

MANIFEST = os.path.join(paths.EDITIONS, "slides.json")
ONES = "Zero One Two Three Four Five Six Seven Eight Nine Ten".split()
LIST_SLOTS = 4


def asset(fig):
    f = fig["files"].get("png")
    if not f:
        raise RefError(f"{fig['label']} {fig['number']} has no PNG to place")
    return os.path.join(paths.ASSETS, f)


def first_sentence(text):
    return re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]


def title(prs, doc, spec):
    meta = doc["meta"]
    s = P.add(prs, "Title")
    P.fill(s, 0, meta["title"])
    if meta.get("subtitle"):
        P.fill(s, 1, meta["subtitle"])
    else:
        P.drop(s, 1)
    P.fill(s, 11, f"{meta['author']} · {meta['affiliation']} · {meta['date']}")
    return [s], [[]]


def divider(prs, doc, spec):
    ch = chapter(doc, spec["chapter"])
    s = P.add(prs, "Section divider")
    P.fill(s, 10, f"{ch['n']:02d} — Chapter {ONES[ch['n']]}")
    P.fill(s, 0, ch["title"])
    opening = section(ch, "")
    return [s], [[md_plain(b["md"]) for b in opening["blocks"] if b["kind"] == "p"][:2]]


def quote(prs, doc, spec):
    para = find_sentence(doc, spec["chapter"], spec.get("section", ""), spec["sentence"])
    ch = chapter(doc, spec["chapter"])
    s = P.add(prs, "Quote")
    P.fill(s, 0, spec["sentence"])
    where = md_plain(spec["section"]) if spec.get("section") else ch["title"]
    P.fill(s, 1, spec.get("attribution") or f"Chapter {ONES[ch['n']]} · {where}")
    return [s], [[para]]


def picture(prs, doc, spec):
    ch, sec, fig, prev = find_figure(doc, spec["figure"])
    s = P.add(prs, "Picture")
    P.picture(s, 1, asset(fig))
    P.fill(s, 0, takeaway(fig["caption_md"], spec.get("takeaway", "clause")))
    P.figure_label(s, f"{fig['label']} {fig['number']}")
    return [s], [[md_plain(prev["md"]) if prev else "",
                  f"{fig['label']} {fig['number']}. {md_plain(fig['caption_md'])}"]]


def list_items(sec, kind):
    """`bold`: each paragraph's bold lead (ordinal dropped), noted with the sentence after it;
    `h3`: the numbered subheads (number dropped, the layout numbers them), noted with the first
    sentence of the paragraph under each."""
    out = []
    blocks = sec["blocks"]
    for k, b in enumerate(blocks):
        if kind == "bold" and b["kind"] == "p" and b["md"].startswith("**"):
            lead, _, rest = b["md"][2:].partition("**")
            lead = lead.split(": ", 1)[1] if ": " in lead else lead
            out.append((lead[:1].upper() + lead[1:], first_sentence(md_plain(rest).strip()), md_plain(b["md"])))
        elif kind == "h3" and b["kind"] == "h3":
            nxt = blocks[k + 1] if k + 1 < len(blocks) and blocks[k + 1]["kind"] == "p" else None
            body = md_plain(nxt["md"]) if nxt else ""
            out.append((md_plain(b["md"]).split(". ", 1)[-1], first_sentence(body), f"{md_plain(b['md'])}: {body}"))
    if not out:
        raise RefError(f"section {sec['title']!r} has no {kind} items")
    return out


def listing(prs, doc, spec):
    """The List layout holds four; a longer list continues on the next slide, numbered on."""
    ch = chapter(doc, spec["chapter"])
    sec = section(ch, spec["section"])
    items = list_items(sec, spec["items"])
    per = -(-len(items) // -(-len(items) // LIST_SLOTS))
    slides, notes = [], []
    for start in range(0, len(items), per):
        chunk = items[start:start + per]
        s = P.add(prs, "List")
        P.fill(s, 10, f"Chapter {ONES[ch['n']]} · {ch['title']}")
        P.fill(s, 0, spec.get("title") or md_plain(sec["title"]))
        for k in range(LIST_SLOTS):
            if k >= len(chunk):
                P.drop(s, 20 + k, 30 + k)
                continue
            item, note, _ = chunk[k]
            if P.lines(s, 20 + k, item) > 1 or not note or P.lines(s, 30 + k, note) > 1:
                # Two lines of item, or no one-line note: the item takes the note's slot too.
                P.drop(s, 30 + k)
                P.fill(s, 20 + k, item, height=0.72)
            else:
                P.fill(s, 20 + k, item)
                P.fill(s, 30 + k, note)
        P.numbers(s, "List num ", start, len(chunk))
        slides.append(s)
        notes.append([full for _, _, full in chunk])
    return slides, notes


BUILD = {"Title": title, "Section divider": divider, "Quote": quote, "Picture": picture, "List": listing}


def to_pdf(pptx):
    soffice = shutil.which("soffice") or "/opt/homebrew/bin/soffice"
    # A private profile: a running LibreOffice holds the default one and makes --headless exit silently.
    profile = "file://" + os.path.join(paths.OUT, ".soffice-profile")
    r = subprocess.run([soffice, f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf",
                        "--outdir", paths.DIST, pptx], capture_output=True, text=True, timeout=300)
    pdf = os.path.splitext(pptx)[0] + ".pdf"
    if r.returncode or not os.path.exists(pdf):
        raise SystemExit(f"slides: PDF conversion failed: {r.stderr or r.stdout}")
    return pdf


def main():
    with open(paths.SOURCE, encoding="utf-8") as f:
        doc = json.load(f)
    if not os.path.exists(MANIFEST):
        import slide_seed
        slide_seed.write(doc, MANIFEST)
        print(f"slides: no manifest; wrote a starting one to {MANIFEST}")
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    prs = P.open_deck()
    errors = []
    for i, spec in enumerate(manifest["slides"], 1):
        build = BUILD.get(spec.get("layout"))
        try:
            if not build:
                raise RefError(f"layout {spec.get('layout')!r} is not one this deck builds: {', '.join(BUILD)}")
            slides, notes = build(prs, doc, spec)
            for s, paras in zip(slides, notes):
                if paras:
                    s.notes_slide.notes_text_frame.text = "\n\n".join(p for p in paras if p)
        except (RefError, P.FitError) as e:
            errors.append(f"manifest entry {i} ({spec.get('layout')}): {e}")
    if errors:
        raise SystemExit("slides: the manifest no longer matches the book or the template:\n  " + "\n  ".join(errors))
    os.makedirs(paths.DIST, exist_ok=True)
    out = os.path.join(paths.DIST, "slides.pptx")
    prs.save(out)
    pdf = to_pdf(out)
    print(f"slides: {len(prs.slides)} slides -> {out}, {pdf}")


if __name__ == "__main__":
    main()
