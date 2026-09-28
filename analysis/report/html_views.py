"""Extra tabs for a chapter's HTML page, kept out of the .pptx deck.

A chapter's views.py computes a view per question and saves them; deck_html.py merges each
one into its question as another tab ("Commits", "Change sets"):

    v = Views("method")
    v.add("Q counting-units-compared", "Change sets", title, points,
          v.timeline(WEEKS, {"Skills": [...], ...}, [GREY, PINK], y_title="Change sets per week"),
          source="change sets (D1)", notes="How it's computed ...")
    v.save()                                  # -> .analysis/data/views/method.json

Chart specs match what deck_html.py reads out of a deck's native charts, and timelines get
the factory's milestones the way deck_lib draws them, so a view tab reads like the deck's own.
Views hold findings, so they are written under the gitignored .analysis/, never into the repo.
"""
import json
import os

from deck_lib import MILESTONES, MONTHS, PINK, REPO_COLORS, mlabel, month_frac, week_frac, wlabel

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VIEWS_DIR = os.path.join(ROOT, ".analysis", "data", "views")


def _hex(c):
    return (c or "").lstrip("#").upper() or None


def _fmt(pct, fmt):
    return fmt or ("0%" if pct else "General")


def _series(series, colors):
    colors = list(colors or REPO_COLORS)
    return [{"name": name, "values": [None if v is None or v != v else float(v) for v in vals],
             "color": _hex(colors[i % len(colors)]), "pointColors": None}
            for i, (name, vals) in enumerate(series.items())]


def _spec(kind, cats, series, colors, horizontal=False, stacked=False, labels=False, pct=False, fmt=None,
          x_title=None, y_title=None, val_max=None, val_min=None, marks=(), bands=()):
    return {"kind": kind, "horizontal": horizontal, "stacked": stacked, "cats": [str(c) for c in cats],
            "series": _series(series, colors), "labels": labels, "fmt": _fmt(pct, fmt), "legend": len(series) > 1,
            "xTitle": x_title, "yTitle": y_title, "max": 1.0 if pct and val_max is None else val_max,
            "min": val_min, "marks": list(marks), "bands": list(bands)}


def _marks(frac, n, events, milestones=True):
    out = []
    if milestones:
        out += [{"at": round(frac(d) * n, 3), "name": name, "color": None} for d, name, *_ in MILESTONES
                if frac(d) is not None]
    out += [{"at": round(frac(d) * n, 3), "name": name, "color": PINK} for d, name, *_ in events
            if frac(d) is not None]
    return [m for m in out if 0 <= m["at"] <= n]


class Views:
    def __init__(self, chapter):
        self.chapter = chapter
        self.views = {}

    def add(self, question, label, title, points, charts, source="", notes="", tables=()):
        """One tab on `question` ("Q counting-units-compared"). charts: a spec or a list of specs, side by side."""
        charts = charts if isinstance(charts, list) else [charts]
        self.views.setdefault(question, []).append({
            "label": label, "title": title, "points": list(points), "source": source, "extra": [],
            "notes": notes, "charts": charts, "tables": [list(map(list, t)) for t in tables]})

    def save(self):
        os.makedirs(VIEWS_DIR, exist_ok=True)
        path = os.path.join(VIEWS_DIR, f"{self.chapter}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.views, f, indent=1)
        return path

    @staticmethod
    def timeline(weeks, series, colors=None, kind="stacked", y_title=None, pct=False, fmt=None, events=(),
                 milestones=True, val_max=None, unavailable=None):
        """Weekly chart; kind is stacked, column or line. unavailable: (first_day, last_day, label) shaded."""
        frac = lambda d: week_frac(d, weeks)
        n = len(weeks)
        bands = []
        if unavailable:
            a, b, name = unavailable
            bands = [{"from": round(frac(a) * n, 3), "to": round(frac(b) * n, 3), "name": name, "color": None}]
        return _spec("line" if kind == "line" else "bar", [wlabel(w) for w in weeks], series, colors,
                     stacked=kind == "stacked", pct=pct, fmt=fmt, x_title="Week of 2026", y_title=y_title,
                     val_max=val_max, marks=_marks(frac, n, events, milestones), bands=bands)

    @staticmethod
    def months(series, colors=None, months=MONTHS, y_title=None, pct=False, fmt=None, events=(), val_max=None,
               kind="line"):
        frac = lambda d: month_frac(d, months)
        return _spec("line" if kind == "line" else "bar", [mlabel(m) for m in months], series, colors,
                     stacked=kind == "stacked", pct=pct, fmt=fmt, x_title="Month of 2026", y_title=y_title,
                     val_max=val_max, marks=_marks(frac, len(months), events))

    @staticmethod
    def bars(cats, series, colors=None, horizontal=False, stacked=False, labels=True, pct=False, fmt=None,
             x_title=None, y_title=None, val_max=None):
        return _spec("bar", cats, series, colors, horizontal=horizontal, stacked=stacked, labels=labels, pct=pct,
                     fmt=fmt, x_title=x_title, y_title=y_title, val_max=val_max)


def load(chapter):
    path = os.path.join(VIEWS_DIR, f"{chapter}.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    print(VIEWS_DIR, sorted(os.listdir(VIEWS_DIR)) if os.path.isdir(VIEWS_DIR) else "(none yet)")
