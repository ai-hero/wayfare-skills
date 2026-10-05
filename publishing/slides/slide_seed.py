"""A starting manifest drawn from the book's structure alone: title, then per chapter a divider and
its first two drawn diagrams, then the last sentence of the book as the close. It is a scaffold for
the editor to curate, not a selection: the curated deck is the manifest it writes."""
import json
import os
import re

from inline import md_plain


def write(doc, path):
    slides = [{"layout": "Title"}]
    for c in doc["chapters"]:
        slides.append({"layout": "Section divider", "chapter": c["n"]})
        figs = [b for s in c["sections"] for b in s["blocks"] if b["kind"] == "figure" and b.get("files", {}).get("png")]
        figs.sort(key=lambda b: b["type"] != "diagram")
        slides += [{"layout": "Picture", "figure": f"{b['label']} {b['number']}", "takeaway": "clause"} for b in figs[:2]]
    last = doc["chapters"][-1]
    sec = [s for s in last["sections"] if any(b["kind"] == "p" for b in s["blocks"])][-1]
    para = md_plain([b for b in sec["blocks"] if b["kind"] == "p"][-1]["md"])
    sentence = re.split(r"(?<=[.!?])\s+", para)[-1]
    slides.append({"layout": "Quote", "chapter": last["n"], "section": sec["title"], "sentence": sentence})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "slides": slides}, f, indent=1, ensure_ascii=False)
