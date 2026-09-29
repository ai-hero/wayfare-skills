"""Diagram 9.1: the five priorities of Chapter 9 as dependent capabilities over the path already built.

All five are proposed, so every node and arrow above the path is target. Dependencies drawn are the ones
the chapter states: governance and staged releases live in the control plane; integration must leave
evidence; evaluation needs a baseline and a measure; both foundations need stable identifiers on the path.
"""
import svg_lib as S

c = S.Canvas(1400, 760)
W, GAP, Y, H = 240, 30, 170, 160
xs = [40 + i * (W + GAP) for i in range(5)]
p = [
    c.node(xs[0], Y, W, H, "agent", "1 · Independent control plane",
           "off one workstation; shows items, goals, decisions, evidence, exceptions", target=True),
    c.node(xs[1], Y, W, H, "agent", "2 · Bidirectional integration",
           "design feedback, sibling fixes, production diagnosis to bounded repair", target=True),
    c.node(xs[2], Y, W, H, "check", "3 · Evaluation built into change",
           "mechanism, baseline, expected movement, disconfirming evidence", target=True),
    c.node(xs[3], Y, W, H, "evidence", "4 · Repaired evidence chain",
           "session events from day one; work identifier on every session and branch", target=True),
    c.node(xs[4], Y, W, H, "policy", "5 · Team governance",
           "roles, separation of duties, exceptions, escalation, audit", target=True),
]

c.group(40, 460, 1320, 190, "The trustworthy path from intent to production, as built")
PW, PG = 160, 30
px = [70 + i * (PW + PG) for i in range(7)]
path = [
    c.node(px[0], 520, PW, 90, "record", "Work item, goal"),
    c.node(px[1], 520, PW, 90, "record", "Plan"),
    c.node(px[2], 520, PW, 90, "record", "Change set"),
    c.node(px[3], 520, PW, 90, "check", "Review and CI"),
    c.node(px[4], 520, PW, 90, "check", "Merge policy"),
    c.node(px[5], 520, PW, 90, "delivery", "Delivery"),
    c.node(px[6], 520, PW, 90, "evidence", "Production evidence"),
]
for a, b in zip(path, path[1:]):
    c.arrow(a, b, "flow")

top, bot = Y, Y + H
c.arrow((150, 460), (150, bot), "dependency", "stable identifiers", target=True, label_at=0.5)
c.arrow((1000, 460), (1000, bot), "dependency", "work identifier", target=True, label_at=0.5)
c.arrow((100, top), (1250, top), "dependency", "roles live in the control plane", target=True,
        via=((100, 60), (1250, 60)), label_at=0.5)
c.arrow((160, top), (650, top), "dependency", "staged releases", target=True, via=((160, 100), (650, 100)),
        label_at=0.5)
c.arrow((220, top), (400, top), "dependency", "ownership, routing", target=True, via=((220, 140), (400, 140)),
        label_at=0.5)
c.arrow((900, bot), (700, bot), "dependency", "baseline, measure", target=True, via=((900, 370), (700, 370)),
        label_at=0.5)
c.arrow((960, bot), (450, bot), "dependency", "leaves evidence", target=True, via=((960, 400), (450, 400)),
        label_at=0.5)

c.legend(40, 670, kinds=("record", "check", "delivery", "evidence"), arrows=("flow", "dependency"), target=True,
         cols=4, cell=300)

S.finish(
    c, id="9.1", name="diagram-09-01-what-comes-next",
    caption="None of the five is built, and they do not stand alone: the control plane and the evidence chain "
            "rest on identifiers the path already carries, and the other three rest on those two.",
    alt="Five dashed boxes in a row, numbered in the chapter's order: independent control plane, bidirectional "
        "integration, evaluation built into change, repaired evidence chain and team governance. Dashed "
        "dependency arrows run from the control plane to integration, evaluation and governance, and from the "
        "evidence chain to integration and evaluation. Below, a solid row shows the path already built: work "
        "item and goal, plan, change set, review and CI, merge policy, delivery, production evidence, with "
        "arrows up to the control plane and the evidence chain.",
    source="Replaces D05 WHAT COMES NEXT. Priorities and their order from Chapter 9, 'What I would change next'; "
           "the path from Chapter 9, 'A practical order for building one' and Chapter 7, 'A minimal factory, in "
           "adoption order'. Dependencies from the same sections: governance 'must become first-class parts of "
           "the control plane'; connections 'leave evidence'; improvements state 'baseline, expected movement'; "
           "'give the change and its evidence stable identifiers'.",
)
