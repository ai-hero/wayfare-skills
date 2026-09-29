"""1.1 From prompt to factory: five stages, what the person shapes and what proceeds without them."""
import svg_lib as S

# Stage, when (Ch 1, "From agentic engineering to the factory"), what the person shapes, what proceeds without
# the person, and the name of the boundary that runs without them.
STAGES = [
    ("Prompt engineering", "the earliest workflow",
     "The words of one request", "words, examples and a format; the person selects the files, applies and tests the answer",
     "One answer", "one answer, pasted into an editor",
     "One answer"),
    ("Context engineering", "named June 2025",
     "What the model can see", "the right files, documentation, conventions and task history; CLAUDE.md, AGENTS.md, design records, plans, memories",
     "One well-informed answer", "the context is kept, not assembled by hand each time",
     "One informed answer"),
    ("Harness engineering", "named by 2026",
     "The program around the model", "which tools, what it sees, delegation, the permission boundary; each mistake changes the setup",
     "A task inside the harness", "reads and edits files, executes commands, manages context, delegates, asks at a boundary",
     "One task"),
    ("Loop engineering", "Ralph loop, May 2025",
     "The two ends of the run", "the outcome, plan, tests and verifiers before; the evidence after",
     "A task until it passes", "the agent chooses the next action; files and git keep progress; it stops on a condition",
     "A task until it passes"),
    ("The software factory", "2026",
     "The design of the factory", "what may start work, what evidence a change must produce, where work proceeds autonomously, which decisions remain human",
     "Many concurrent streams", "across interdependent applications; a control plane continues, retries, asks for help or stops",
     "Many streams"),
]

W, GAP, X0 = 216, 60, 40
c = S.Canvas(1400, 1060)

heads, persons = [], []
for i, (name, when, p_label, p_sub, a_label, a_sub, boundary) in enumerate(STAGES):
    x = X0 + i * (W + GAP)
    heads.append(c.node(x, 40, W, 96, "plain", name, when))
    persons.append(c.node(x, 176, W, 230, "person", p_label, p_sub))
    gh = 236 + i * 60
    g = c.group(x, 470, W, gh, boundary)
    a = c.node(x + 8, 504, W - 16, 196 + (60 if i == 4 else 0), "agent", a_label, a_sub)
    c.arrow(persons[i], g, "authority", "shapes", label_at=0.3, ports=("bottom", "top"))
    if i == 4:
        t = c.node(x + 8, 790, W - 16, 120, "agent", "A trigger", "an issue, schedule, alert or another agent starts work",
                   target=True)
        c.arrow(t, a, "flow", target=True, ports=("top", "bottom"))

for a, b in zip(heads, heads[1:]):
    c.arrow((a.x + a.w + 6, a.cy), (b.x - 6, b.cy), "flow")

# The person's attention row: the label on the person nodes says what they shape; the band labels say the rows.
c.text(X0, 150, "WHAT THE PERSON SHAPES", size=S.MONO_SIZE, mono=True, color=S.MUTED)
# The band label sits between the first two arrows, which leave the person nodes at their centres.
c.text(X0 + 124, 452, "WHAT PROCEEDS WITHOUT THEM", size=S.MONO_SIZE, mono=True, color=S.MUTED)

# Bottom brackets: the first four are the interlude, the fifth rebuilds the team.
y = 980
x_end4 = X0 + 3 * (W + GAP) + W
c.line(X0, y, x_end4, y, stroke=S.GREY_DARK)
c.line(X0, y - 8, X0, y, stroke=S.GREY_DARK)
c.line(x_end4, y - 8, x_end4, y, stroke=S.GREY_DARK)
c.text((X0 + x_end4) / 2, y + 10, "The agentic interlude: the person gets faster; the team around them need not change",
       size=S.SMALL, anchor="middle", color=S.BODY)
x5 = X0 + 4 * (W + GAP)
c.line(x5, y, x5 + W, y, stroke=S.GREY_DARK)
c.line(x5, y - 8, x5, y, stroke=S.GREY_DARK)
c.line(x5 + W, y - 8, x5 + W, y, stroke=S.GREY_DARK)
c.text(x5 + W / 2, y + 10, "The lifecycle is rebuilt", size=S.SMALL, anchor="middle", color=S.BODY)

c.legend(X0, 1020, arrows=("flow", "authority"), target=True, cols=3, cell=260)

S.finish(
    c, id="1.1", name="diagram-01-01-from-prompt-to-factory",
    caption="Each stage widened what runs without the person, from one answer to many streams across applications; "
            "the first four made an individual faster, and only the fifth rebuilds the lifecycle around agents.",
    alt="Five stages left to right: prompt engineering, context engineering, harness engineering, loop engineering "
        "and the software factory. Each has a row for what the person shapes and, below it, a boundary box for what "
        "proceeds without the person; the boxes grow taller stage by stage. In the factory column a dashed box marks "
        "the trigger that would start work, proposed rather than observed.",
    source="Replaces D11 FROM PROMPT TO FACTORY · THE FIVE STEPS SIDE BY SIDE. Stage names, dates (context "
           "engineering named June 2025; harness engineering named by 2026; Ralph loop May 2025; factory 2026) and "
           "row wording from Chapter 1, 'From agentic engineering to the factory' and 'Rebuilding the SDLC around "
           "agents'. The trigger is proposed: Chapter 1, 'The fleet I built to study it' ('The missing part is the "
           "trigger').",
)
