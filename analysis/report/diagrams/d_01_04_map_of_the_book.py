"""1.4 Map of the nine-chapter book: the introduction at the base, the five operating loops, then the reconstruction."""
import svg_lib as S

# Titles are the `# ` headings of .analysis/book/0N-*.md; the loop each of Chapters 2 to 6 follows is from Chapter 1,
# the opening (the five loops) and "How this book is organized".
LOOPS = [
    ("Two", "Who guides the work", "the direction loop: signals into authorized work"),
    ("Three", "How the work is done", "the production loop: context, harness, memory, messages"),
    ("Four", "How the work ships", "the delivery loop: the unit counted, review, deployment"),
    ("Five", "How the applications stay consistent", "the consistency loop: drift, conformance across the fleet"),
    ("Six", "Running the factory", "the improvement loop: observability, cost, failures into guides and checks"),
]

X0, W = 40, 1320
c = S.Canvas(1400, 940)


def chapter(x, y, w, h, number, title, sub):
    """A chapter is a region of the book, so it is drawn as a group with the title set inside it."""
    c.group(x, y, w, h, f"Chapter {number}")
    lines = S.wrap(title, w - 32, S.LABEL)
    subs = S.wrap(sub, w - 32, S.SMALL)
    total = len(lines) * S.LABEL * 1.2 + 6 + len(subs) * S.SMALL * 1.25
    ty = y + 36 + (h - 36 - total) / 2
    c.text(x + w / 2, ty, title, size=S.LABEL, weight=500, anchor="middle", width=w - 32)
    c.text(x + w / 2, ty + len(lines) * S.LABEL * 1.2 + 6, sub, size=S.SMALL, anchor="middle", color=S.MUTED, width=w - 32)
    return S.Node(x, y, w, h, "group", title)


# Top: the close of the book, read last.
eight = chapter(X0, 40, 630, 120, "Eight", "The field and what generalizes",
                "what is likely to transfer from what may be peculiar to this case")
nine = chapter(X0 + 690, 40, 630, 120, "Nine", "Conclusion and next steps",
               "the practical next steps for this factory and the discipline")
seven = chapter(X0, 240, W, 110, "Seven", "Toward an architecture",
                "the pieces put together as an architecture, and an order in which to build them")

# Middle: the factory's work, one loop per chapter.
band = c.group(X0, 430, W, 270, "The operating loops, following the factory's work", fill=S.GREY_TINT)
cw = (W - 48 - 4 * 24) / 5
loops = []
for i, (n, title, sub) in enumerate(LOOPS):
    x = X0 + 24 + i * (cw + 24)
    loops.append(chapter(x, 472, cw, 204, n, title, sub))

# Base: the premise.
one = chapter(X0, 790, W, 110, "One", "Introduction",
              "where the idea came from, what a software factory is, the fleet built to study it, and the evidence")

c.arrow((X0 + W / 2, 790), (X0 + W / 2, 700), "flow", "follows the factory's work")
c.arrow((X0 + W / 2, 430), (X0 + W / 2, 350), "flow", "steps back to reconstruct the system")
c.arrow((X0 + 315, 240), (X0 + 315, 160), "flow")
c.arrow((X0 + 690 + 315, 240), (X0 + 690 + 315, 160), "flow")

S.finish(
    c, id="1.4", name="diagram-01-04-map-of-the-book",
    caption="Read upward: the introduction sets the premise, Chapters Two to Six each follow one of the five loops, "
            "Chapter Seven reconstructs the architecture, and Chapters Eight and Nine ask what transfers and what "
            "comes next.",
    alt="A map of the nine chapters stacked from bottom to top. At the base, Chapter One, Introduction. Above it a "
        "band of five operating loops: Chapter Two, Who guides the work; Three, How the work is done; Four, How the "
        "work ships; Five, How the applications stay consistent; Six, Running the factory. Above the band, Chapter "
        "Seven, Toward an architecture, and at the top Chapter Eight, The field and what generalizes, beside Chapter "
        "Nine, Conclusion and next steps. Arrows lead upward.",
    source="Replaces D15 THE MAP OF THE BOOK. Chapter titles are the `# ` headings of .analysis/book/01- to 09-*.md; "
           "the loop each chapter follows and the one-line descriptions are from Chapter 1, the opening paragraph on "
           "the five loops and 'How this book is organized'.",
)
