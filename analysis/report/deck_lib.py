"""Shared slide builder for the research-findings decks (one deck per topic, TOPICS below).

Every topic deck is built with these functions so they read as one set:

    prs = open_template()                               # A.I. Hero template, no slides
    title_slide(prs, "Research setting, method and the baseline", "Method · 22 questions")
    section_slide(prs, "METHOD", "Research setting, method and the baseline")
    question_slide(prs, "Q commits-per-change-set", question, originally=..., how=..., notes=...)
    answer_slide(prs, "Q commits-per-change-set", title, points, chart=lambda box: timeline(...), source=..., notes=...)
    breakdown_slide(prs, "Q commits-per-change-set", title, points, chart=..., source=..., notes=...)
    prs.save(path)

Layout of an answer slide: the chart fills the left two-thirds; the answer title sits top
right with the supporting points below it and a one-line source at the bottom. Method,
caveats and code references go in the speaker notes, not on the slide.

Charts take a `box` (x, y, w, h in inches) and label both axes. Weekly and monthly
charts draw the factory's milestones (MILESTONES) as dotted lines with their names on
the chart; question-specific events are drawn the same way in the accent colour.
"""
import os
import shutil
import tempfile
import zipfile
from datetime import date

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

TEMPLATE = os.environ.get("DECK_TEMPLATE", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), ".analysis", "A.I. Hero.potx"))
BRAND = "A.I. HERO, INC.  /  RESEARCH FINDINGS"

INK, BODY, MUTED, RULE = "0B0D14", "383D49", "666D7B", "E3E5EA"
PINK, PINK_LIGHT, PINK_DARK, GREY, GREY_DARK, GREY_LIGHT = "E93A61", "F1839A", "A5153E", "C6C9D0", "383D49", "DDE0E5"
SANS, MONO = "Geist Light", "Geist Mono Light"
REPO_COLORS = [PINK, GREY_DARK, PINK_LIGHT, "8A8F9C", PINK_DARK, "B9BDC6", "F4A6B7", "5A5F6B", "D46A84", "2E323B"]

CHART_BOX = (0.5, 0.95, 8.35, 5.75)
SIDE_X, SIDE_W = 9.15, 3.7

# When wayfare shipped each piece of the factory (wayfare-skills history): date, label, commit.
MILESTONES = [
    ("2026-03-07", "Skills", "a2bb70d hero skills plugin, HERO.md"),
    ("2026-05-04", "Review loop", "5548869 self-review + gated auto-approve"),
    ("2026-07-05", "Work items", "36786de grill emits work-items to plan-work/"),
    ("2026-07-22", ".plans + roadmap", "366658b/5662e7e .plans store, wayfare"),
    ("2026-08-16", "Design repos removed", "4894f14 claude.ai/design project"),
    ("2026-08-28", "Goals", "6a0c0b6 /goal-driven runs"),
    ("2026-09-13", "Messages", "7181504 mailbox"),
    ("2026-09-18", "1 commit per feature", "597dd87 a goal is one branch, one PR"),
]
WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]


# Each evidence deck's folder under report/ and the short name its charts give it, in deck order.
TOPICS = {"intro": "Introduction", "method": "Research setting and method", "agent_harness": "The harness",
          "owner": "Human in the loop", "skills": "Skills and factory evolution", "connectors": "Connectors",
          "memory": "Knowledge and memory", "architecture": "Architecture records", "work_items": "Work items and flow",
          "mistakes": "Mistakes and rework", "security": "Security", "fleet": "Fleet scope and apps",
          "messages": "Cross-repo messaging", "compliance": "Compliance and drift", "deployment": "Deployment",
          "spend": "Spend and cost", "efficiency": "Floor efficiency", "manager": "Manager's thinking",
          "components": "Toward an architecture", "field": "The field", "conclusion": "Conclusion"}


# ------------------------------------------------------------------ basics

def rgb(h):
    return RGBColor.from_string(h)


def pct(v):
    return "–" if v is None else f"{round(100 * v)}%"


def mlabel(m):
    d = date(int(m[:4]), int(m[5:7]), 1)
    return d.strftime("%b") if m.startswith("2026") else d.strftime("%b '%y")


def wlabel(w):
    return date.fromisocalendar(int(w[:4]), int(w[6:]), 1).strftime("%-d %b")


def open_template(path=TEMPLATE, brand=BRAND):
    """The .potx opened as a presentation with no slides, its brand line set."""
    tmp = tempfile.mkdtemp()
    out = os.path.join(tmp, "template.pptx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "[Content_Types].xml":
                data = data.replace(b"presentationml.template.main+xml", b"presentationml.presentation.main+xml")
            zout.writestr(item, data)
    prs = Presentation(out)
    shutil.rmtree(tmp, ignore_errors=True)
    for layout in prs.slide_layouts:
        for sh in layout.shapes:
            if sh.name == "Brand line" and sh.has_text_frame:
                runs = [r for p in sh.text_frame.paragraphs for r in p.runs]
                if runs:
                    runs[0].text = brand
                    for r in runs[1:]:
                        r.text = ""
    return prs


def layout(prs, name):
    for l in prs.slide_layouts:
        if l.name == name:
            return l
    raise KeyError(name)


def ph(slide, idx):
    for s in slide.placeholders:
        if s.placeholder_format.idx == idx:
            return s
    raise KeyError(idx)


def drop_placeholder(slide, idx):
    try:
        el = ph(slide, idx)._element
        el.getparent().remove(el)
    except KeyError:
        pass


def run(p, text, size, color, font, bold=False):
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.color.rgb = rgb(color)
    r.font.name = font
    r.font.bold = bold
    return r


def para(tf, first=False):
    return tf.paragraphs[0] if first else tf.add_paragraph()


def label(tf, text, first=False, before=10, color=MUTED):
    p = para(tf, first)
    p.space_before = Pt(0 if first else before)
    p.space_after = Pt(4)
    run(p, text.upper(), 9, color, MONO)
    return p


def body(tf, text, size=12, color=BODY, after=0, first=False):
    p = para(tf, first)
    p.space_after = Pt(after)
    run(p, text, size, color, SANS)
    return p


def clear(shape):
    tf = shape.text_frame
    for p in list(tf.paragraphs)[1:]:
        p._p.getparent().remove(p._p)
    for r in list(tf.paragraphs[0].runs):
        r._r.getparent().remove(r._r)
    return tf


def textbox(slide, x, y, w, h):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tf


def notes(slide, text):
    if text:
        slide.notes_slide.notes_text_frame.text = text


def eyebrow(slide, text, x=0.78, y=0.55, w=11.6):
    e = ph(slide, 0)
    e.left, e.top, e.width, e.height = Inches(x), Inches(y), Inches(w), Inches(0.25)
    run(clear(e).paragraphs[0], text.upper(), 9.5, MUTED, MONO)


# ------------------------------------------------------------------ slides

def title_slide(prs, title, subtitle, note=None):
    s = prs.slides.add_slide(layout(prs, "Title"))
    run(clear(ph(s, 0)).paragraphs[0], title, 40, "FFFFFF", SANS)
    run(clear(ph(s, 1)).paragraphs[0], subtitle, 16, "FFFFFF", SANS)
    drop_placeholder(s, 11)
    notes(s, note)
    return s


def section_slide(prs, kicker, title, note=None):
    s = prs.slides.add_slide(layout(prs, "Section divider"))
    run(clear(ph(s, 10)).paragraphs[0], kicker.upper(), 9.5, "FFFFFF", MONO)
    run(clear(ph(s, 0)).paragraphs[0], title, 40, "FFFFFF", SANS)
    notes(s, note)
    return s


def question_slide(prs, tag, question, originally=None, how=None, note=None):
    """The question large; one line each for what was asked before and how it is answered."""
    s = prs.slides.add_slide(layout(prs, "Blank"))
    eyebrow(s, f"{tag} · Question", y=1.6)
    tf = textbox(s, 0.78, 2.0, 11.2, 2.2)
    run(tf.paragraphs[0], question, 32 if len(question) < 90 else 28 if len(question) < 140 else 24, INK, SANS)
    tf = textbox(s, 0.78, 4.55, 10.5, 1.8)
    first = True
    if how:
        label(tf, "How we answer it", first=True)
        body(tf, how, size=13, color=BODY, after=4)
        first = False
    if originally and originally != question:
        label(tf, "Originally asked", first=first, before=12)
        body(tf, originally, size=11, color=MUTED)
    notes(s, note)
    return s


def side_text(slide, tag, title, points, source=None, y=0.95):
    tf = textbox(slide, SIDE_X, 0.55, SIDE_W, 0.3)
    run(tf.paragraphs[0], tag.upper(), 9.5, MUTED, MONO)
    tf = textbox(slide, SIDE_X, y, SIDE_W, 2.2)
    run(tf.paragraphs[0], title, 19 if len(title) < 110 else 17 if len(title) < 150 else 15.5, INK, SANS)
    n_lines = max(3, len(title) // 26 + 1)
    top = y + 0.1 + n_lines * (0.32 if len(title) < 110 else 0.29)
    tf = textbox(slide, SIDE_X, top, SIDE_W, 6.3 - top)
    for i, pt in enumerate(points or []):
        p = body(tf, pt, size=11, color=BODY, after=7, first=(i == 0))
    if source:
        tf = textbox(slide, SIDE_X, 6.35, SIDE_W, 0.45)
        run(tf.paragraphs[0], "SOURCE  ", 7.5, PINK, MONO)
        run(tf.paragraphs[0], source, 7.5, MUTED, MONO)


def answer_slide(prs, tag, title, points, chart, source=None, note=None):
    """chart: a function (slide, box) that draws into CHART_BOX."""
    s = prs.slides.add_slide(layout(prs, "Blank"))
    drop_placeholder(s, 0)
    chart(s, CHART_BOX)
    side_text(s, f"{tag} · Answer", title, points, source)
    notes(s, note)
    return s


def breakdown_slide(prs, tag, title, points, chart, source=None, note=None, kicker="By repo"):
    s = prs.slides.add_slide(layout(prs, "Blank"))
    drop_placeholder(s, 0)
    chart(s, CHART_BOX)
    side_text(s, f"{tag} · {kicker}", title, points, source)
    notes(s, note)
    return s


def statement_slide(prs, kicker, headline, body_text=None, note=None):
    s = prs.slides.add_slide(layout(prs, "Blank"))
    eyebrow(s, kicker, y=1.9)
    tf = textbox(s, 0.78, 2.3, 11.2, 2.0)
    run(tf.paragraphs[0], headline, 30, INK, SANS)
    if body_text:
        tf = textbox(s, 0.78, 4.5, 10.0, 1.6)
        body(tf, body_text, size=14, first=True)
    notes(s, note)
    return s


# ------------------------------------------------------------------ charts

def set_plot_area(c, inner):
    """Pin the inner plot area to fractions (x, y, w, h) of the chart frame."""
    pa = c._chartSpace.chart.plotArea
    old = pa.find(qn("c:layout"))
    if old is not None:
        pa.remove(old)
    lay = etree.SubElement(pa, qn("c:layout"))
    pa.remove(lay)
    pa.insert(0, lay)
    ml = etree.SubElement(lay, qn("c:manualLayout"))
    for tag, val in (("layoutTarget", "inner"), ("xMode", "edge"), ("yMode", "edge"),
                     ("x", inner[0]), ("y", inner[1]), ("w", inner[2]), ("h", inner[3])):
        etree.SubElement(ml, qn(f"c:{tag}")).set("val", str(val))


def axis_title(axis, text):
    if not text:
        return
    axis.has_title = True
    tf = axis.axis_title.text_frame
    tf.text = text
    for p in tf.paragraphs:
        for r in p.runs:
            r.font.size = Pt(9)
            r.font.bold = False
            r.font.color.rgb = rgb(MUTED)
            r.font.name = SANS


INNER = (0.09, 0.16, 0.88, 0.68)  # plot area inside the chart frame, leaving room for axis titles and labels


def chart(slide, kind, cats, series, colors, box=CHART_BOX, x_title=None, y_title=None, pct_axis=False, fmt=None,
          labels=None, label_fmt=None, gap=60, stacked=False, val_max=None, legend=None, inner=INNER, markers=True):
    """A native chart in the brand style; returns the chart. Fixed inner plot area so overlays can be placed."""
    cd = CategoryChartData()
    cd.categories = cats
    for name, vals in series.items():
        cd.add_series(name, vals)
    gf = slide.shapes.add_chart(kind, *(Inches(v) for v in box), cd)
    c = gf.chart
    c.font.name, c.font.size = SANS, Pt(10)
    c.font.color.rgb = rgb(BODY)
    c.has_title = False
    c.has_legend = legend if legend is not None else len(series) > 1
    if c.has_legend:
        c.legend.position = XL_LEGEND_POSITION.TOP
        c.legend.include_in_layout = False
        c.legend.font.size = Pt(9.5)
    va, ca = c.value_axis, c.category_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = rgb(RULE)
    va.major_gridlines.format.line.width = Pt(0.5)
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(9)
    va.tick_labels.font.color.rgb = rgb(MUTED)
    if pct_axis or fmt:
        va.tick_labels.number_format = fmt or "0%"
        va.tick_labels.number_format_is_linked = False
    lowest = min((v for vals in series.values() for v in vals if v is not None), default=0)
    if lowest >= 0:
        va.minimum_scale = 0
    if val_max is not None or pct_axis:
        va.maximum_scale = val_max if val_max is not None else 1.0
    ca.format.line.color.rgb = rgb(GREY)
    ca.tick_labels.font.size = Pt(8.5)
    ca.tick_labels.font.color.rgb = rgb(MUTED)
    ca.has_major_gridlines = False
    axis_title(ca, x_title)
    axis_title(va, y_title)
    if box[2] < 5 and inner == INNER:
        inner = (0.17, 0.16, 0.8, 0.68)
    set_plot_area(c, inner)
    plot = c.plots[0]
    line = kind in (XL_CHART_TYPE.LINE_MARKERS, XL_CHART_TYPE.LINE)
    if not line:
        plot.gap_width = gap
        plot.overlap = 100 if stacked else (-10 if len(series) > 1 else 0)
    for s, col in zip(plot.series, colors):
        if line:
            s.format.line.color.rgb = rgb(col)
            s.format.line.width = Pt(2 if len(series) <= 4 else 1.5)
            s.smooth = False
            if kind == XL_CHART_TYPE.LINE_MARKERS:
                s.marker.size = 4 if markers else 2
                s.marker.format.fill.solid()
                s.marker.format.fill.fore_color.rgb = rgb(col)
                s.marker.format.line.color.rgb = rgb(col)
        else:
            s.invert_if_negative = False
            s.format.fill.solid()
            s.format.fill.fore_color.rgb = rgb(col)
            s.format.line.fill.background()
    if labels:
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.font.size = Pt(8.5)
        dl.font.color.rgb = rgb("FFFFFF" if stacked else BODY)
        if label_fmt or stacked:
            dl.number_format = label_fmt or "#,##0;;;"
            dl.number_format_is_linked = False
        dl.position = labels
    return c


def point_colors(c, colors):
    s = c.plots[0].series[0]
    for i, col in enumerate(colors):
        pt = s.points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = rgb(col)


def marks(slide, box, fracs, names, color=GREY_DARK, inner=INNER):
    """Dotted verticals at fractions of the plot width, each named by a small rotated label."""
    fx, fy, fw, fh = box
    top, bottom = fy + fh * inner[1], fy + fh * (inner[1] + inner[3])
    for f, name in zip(fracs, names):
        if f is None or not 0 <= f <= 1:
            continue
        x = fx + fw * (inner[0] + inner[2] * f)
        ln = slide.shapes.add_connector(1, Inches(x), Inches(top), Inches(x), Inches(bottom))
        ln.line.color.rgb = rgb(color)
        ln.line.width = Pt(0.75)
        ln.line.dash_style = MSO_LINE_DASH_STYLE.ROUND_DOT
        h = 1.7
        tb = slide.shapes.add_textbox(Inches(x + 0.02 - h / 2 + 0.07), Inches(top + h / 2 - 0.07), Inches(h), Inches(0.14))
        tb.rotation = 270
        tf = tb.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.word_wrap = False
        p = tf.paragraphs[0]
        p.alignment = 3  # right: the text ends at the top of the plot
        run(p, name, 7, color, SANS)


def week_frac(day, weeks):
    y, w, wd = date.fromisoformat(day).isocalendar()
    first = int(weeks[0][6:])
    return ((w - first) + (wd - 1) / 7) / len(weeks)


def month_frac(day, months=MONTHS):
    d = date.fromisoformat(day)
    key = d.strftime("%Y-%m")
    if key not in months:
        return None
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return (months.index(key) + (d.day - 1) / (nxt - date(d.year, d.month, 1)).days) / len(months)


def draw_milestones(slide, box, frac, events=(), milestones=MILESTONES):
    marks(slide, box, [frac(m[0]) for m in milestones], [m[1] for m in milestones])
    if events:
        marks(slide, box, [frac(e[0]) for e in events], [e[1] for e in events], color=PINK)


def timeline(slide, box, weeks, series, colors, kind="stacked", y_title=None, pct_axis=False, fmt=None,
             events=(), milestones=True, val_max=None):
    """Weekly chart from 1 Jan with the factory's milestones named on it."""
    types = {"stacked": XL_CHART_TYPE.COLUMN_STACKED, "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
             "line": XL_CHART_TYPE.LINE_MARKERS}
    every = 1 if len(weeks) <= 12 else 4
    cats = [wlabel(w) if i % every == 0 else " " for i, w in enumerate(weeks)]
    c = chart(slide, types[kind], cats, series, colors, box=box, x_title="Week of 2026", y_title=y_title,
              pct_axis=pct_axis, fmt=fmt, stacked=kind == "stacked", gap=25, val_max=val_max,
              markers=len(series) <= 4)
    if every == 1:
        # LibreOffice and PowerPoint thin crowded labels on their own; force every week to show.
        from pptx.oxml.ns import qn as _qn
        cax = c._chartSpace.chart.plotArea.find(_qn("c:catAx"))
        if cax is not None and cax.find(_qn("c:tickLblSkip")) is None:
            skip = etree.Element(_qn("c:tickLblSkip"))
            skip.set("val", "1")
            after = cax.find(_qn("c:tickMarkSkip")) or cax.find(_qn("c:noMultiLvlLbl"))
            if after is not None:
                after.addprevious(skip)
            else:
                cax.append(skip)
    frac = lambda d: week_frac(d, weeks)
    if milestones:
        draw_milestones(slide, box, frac, events)
    elif events:
        marks(slide, box, [frac(e[0]) for e in events], [e[1] for e in events], color=PINK)
    return c


def month_lines(slide, box, series, colors=None, y_title=None, pct_axis=False, fmt=None, events=(), val_max=None,
                months=MONTHS):
    c = chart(slide, XL_CHART_TYPE.LINE_MARKERS, [mlabel(m) for m in months], series, colors or REPO_COLORS, box=box,
              x_title="Month of 2026", y_title=y_title, pct_axis=pct_axis, fmt=fmt, val_max=val_max)
    draw_milestones(slide, box, lambda d: month_frac(d, months), events)
    return c


def bars(slide, box, cats, series, colors, horizontal=False, x_title=None, y_title=None, pct_axis=False, fmt=None,
         labels=True, label_fmt=None, stacked=False, val_max=None):
    kind = ((XL_CHART_TYPE.BAR_STACKED if stacked else XL_CHART_TYPE.BAR_CLUSTERED) if horizontal else
            (XL_CHART_TYPE.COLUMN_STACKED if stacked else XL_CHART_TYPE.COLUMN_CLUSTERED))
    inner = (0.3, 0.12, 0.66, 0.74) if horizontal else INNER
    return chart(slide, kind, cats, series, colors, box=box, x_title=x_title, y_title=y_title, pct_axis=pct_axis,
                 fmt=fmt, labels=(XL_LABEL_POSITION.CENTER if stacked else XL_LABEL_POSITION.OUTSIDE_END) if labels else None,
                 label_fmt=label_fmt or ("0%" if pct_axis else None), stacked=stacked, val_max=val_max, gap=45,
                 inner=inner)


def split_box(box, n=2, gap=0.3):
    x, y, w, h = box
    cw = (w - gap * (n - 1)) / n
    return [(x + i * (cw + gap), y, cw, h) for i in range(n)]
