"""1.2 The lifecycle compared: Waterfall, Scrum, a person with an agent, and the software factory, row by row."""
import svg_lib as S

COLS = [
    ("Waterfall", "Royce, 1970"),
    ("Scrum", "Agile Manifesto, 2001"),
    ("A person with an agent", "2023 on"),
    ("The software factory", "2026"),
]
# Wording from Chapter 1: the opening, "From agentic engineering to the factory", "Rebuilding the SDLC around
# agents" and "What I mean by a software factory".
ROWS = [
    ("Initiating signal", [
        "Requirements specified in advance; phases follow one another",
        "A backlog the team works from, committed to a sprint",
        "The person's request, or an objective given to the harness",
        "A person, or an issue, schedule, failed test, alert or another agent",
    ]),
    ("Planning unit", [
        "A specified phase, handed to specialists",
        "Sprint of backlog items; epics and stories a team can estimate",
        "A prompt with its context; a plan before the run",
        "Work items grouped into goals with a plan; logical change sets",
    ]),
    ("Coordination", [
        "Formal handoffs between specialists",
        "Daily meeting, demonstration and reflection",
        "The team's ceremonies, unchanged: tickets, sprints, stand-ups",
        "Written, inspectable progress; triggers and policies; shared context across cells",
    ]),
    ("Reviewer", [
        "Specialists at each formal handoff",
        "A colleague reviews the pull request",
        "The person judges the result; a colleague still reviews the PR",
        "Review agents and automated sensors; people at the design and the plan",
    ]),
    ("Delivery boundary", [
        "The end of the last phase",
        "Sprint demonstration; later, continuous delivery from merge to production",
        "The merged pull request, on the team's usual path",
        "Running software in production; a change on a branch is inventory",
    ]),
    ("Scarce resource", [
        "Engineering capacity",
        "Engineering capacity",
        "The developer's time, made faster by the model",
        "The operator's focused attention",
    ]),
]

X0, HEAD_W, GAP, CW = 40, 190, 20, 262
ROW_H, TOP, HEAD_H = 140, 40, 140
# The first row holds the proposed trigger beneath the person, so it is taller.
ROW_HS = [176] + [ROW_H] * (len(ROWS) - 1)
ROW_Y = [TOP + HEAD_H + sum(ROW_HS[:i]) for i in range(len(ROWS))]
c = S.Canvas(1400, TOP + HEAD_H + sum(ROW_HS) + 120)


def col_x(j):
    return X0 + HEAD_W + GAP + j * (CW + GAP)


# What each of the last two columns changes, from Chapter 1: "The agentic interlude changes who types without
# necessarily changing how the team coordinates. The factory challenges ceremonies created for a human team."
table_bottom = TOP + HEAD_H + sum(ROW_HS)
for j, tag in ((2, "Changes who types"), (3, "Changes coordination")):
    c.group(col_x(j) - 10, TOP, CW + 20, table_bottom - TOP + 12, tag, fill=S.GREY_TINT if j == 3 else "none")

for j, (name, year) in enumerate(COLS):
    c.node(col_x(j), TOP + 36, CW, HEAD_H - 40, "plain", name, year)

for i, (label, cells) in enumerate(ROWS):
    y, rh = ROW_Y[i], ROW_HS[i]
    c.line(X0, y, X0 + 1320, y, stroke=S.GREY)
    c.node(X0, y, HEAD_W, rh, "plain", label, align="left", size=S.LABEL)
    for j, cell in enumerate(cells):
        if i == 0 and j == 3:
            c.node(col_x(j), y + 8, CW, 40, "plain", "A person")
            c.node(col_x(j) + 10, y + 58, CW - 20, 108, "agent", "or a trigger",
                   "an issue, schedule, failed test, alert or another agent", target=True)
        else:
            c.node(col_x(j), y, CW, rh, "plain", cell, size=S.LABEL)
c.line(X0, table_bottom, X0 + 1320, table_bottom, stroke=S.GREY)

c.legend(X0, table_bottom + 40, target=True, cols=1)

S.finish(
    c, id="1.2", name="diagram-01-02-lifecycle-compared",
    caption="A person with an agent changes who types and leaves the team's coordination where it was; the factory "
            "changes what starts work, who reviews it and what counts as delivered, and the scarce resource becomes "
            "the operator's attention.",
    alt="A matrix with four columns, Waterfall, Scrum, a person with an agent, and the software factory, and six "
        "rows: initiating signal, planning unit, coordination, reviewer, delivery boundary and scarce resource. The "
        "third column is marked 'changes who types' and the fourth 'changes how work is coordinated'. In the "
        "factory's initiating-signal cell, a trigger is drawn dashed as proposed, beside the person who starts work "
        "today.",
    source="Replaces D12 THE LIFECYCLE COMPARED. Years from the chapter's Sources (Royce 1970; Agile Manifesto "
           "2001), '2023 on' and '2026' from the chapter opening and 'Who is building factories in 2026'. Cell wording "
           "from Chapter 1: the opening paragraphs on Waterfall and Scrum, 'From agentic engineering to the factory', "
           "'Rebuilding the SDLC around agents' (the table paragraph and the scarcity sentence) and 'What I mean by a "
           "software factory'. The trigger is proposed: 'I still begin every session' ('The fleet I built to study "
           "it').",
)
