"""1.3 With an IDE and with an agent work cell: what a person needs at the keyboard, what an agent needs instead."""
import svg_lib as S

c = S.Canvas(1400, 1000)

# ---------------------------------------------------------------- left: with an IDE
c.group(40, 40, 560, 880, "With an IDE")
dev = c.node(80, 100, 480, 110, "person", "The developer",
             "reads and writes code a screen at a time; judges, applies and tests each answer")
editor = c.node(80, 290, 260, 120, "agent", "The editor",
                "a visual tool for a person; an agent may assist a line or a request at a time")
cmds = c.node(400, 290, 160, 120, "check", "Commands", "run, test, read the error")
code = c.node(80, 480, 260, 110, "record", "The code", "the files the person selected")
team = c.node(80, 690, 480, 110, "delivery", "The team's usual path",
              "tickets, sprints, stand-ups and a colleague's pull-request review, unchanged")
c.arrow((210, 210), (210, 290), "flow", "types and reads")
c.arrow((480, 210), (480, 290), "flow", "runs by hand")
c.arrow((210, 410), (210, 480), "flow", "edits")
c.arrow((210, 590), (210, 690), "flow", "commit, pull request")

# ---------------------------------------------------------------- right: an agent work cell
op = c.node(660, 100, 680, 110, "person", "The operator",
            "settles the intent and the plan; decides at the permission boundary; examines the evidence")
c.group(660, 250, 500, 670, "An agent work cell")
intent = c.node(790, 290, 250, 90, "record", "Authorized intent", "work item, goal and plan; the decisions made")
agent = c.node(690, 420, 320, 120, "agent", "The coding agent",
               "a model inside a harness: reads and edits files, runs commands, delegates, asks at a boundary")
ctx = c.node(690, 600, 150, 170, "record", "Repository context", "HERO.md, AGENTS.md, DESIGN.md; messages from nearby cells")
mem = c.node(860, 600, 150, 170, "record", "Memory", "what earlier sessions learned")
sensors = c.node(690, 810, 320, 90, "check", "Sensors", "tests, CI, review agents, the approval check")
trigger = c.node(1180, 275, 160, 120, "agent", "A trigger", "an issue, schedule, alert or another agent", target=True)
evidence = c.node(1180, 600, 160, 170, "evidence", "Delivery evidence", "merged, deployed, observed running in production")
prod = c.node(1180, 810, 160, 90, "delivery", "Production", "the change, running")

c.arrow((915, 210), (915, 290), "authority", "authorizes")
c.arrow((660, 155), (690, 480), "authority", via=((630, 155), (630, 480)))
c.arrow((1180, 335), (1040, 335), "flow", "starts work", target=True)
c.arrow((915, 380), (915, 420), "flow")
c.arrow((765, 600), (765, 540), "dependency")
c.arrow((935, 600), (935, 540), "dependency")
# The first and last legs differ in length on purpose: `_along` mistakes equal-length first and last segments
# for each other and draws the label off the path.
c.arrow((990, 540), (1010, 855), "flow", "the change", via=((990, 570), (1085, 570), (1085, 855)), label_at=0.5)
c.arrow((1010, 855), (1180, 855), "flow", "ships")
c.arrow((1260, 810), (1260, 770), "feedback")
c.arrow((1340, 685), (1340, 155), "feedback", via=((1360, 685), (1360, 155)))
c.text(1330, 420, "the evidence, after the run", size=S.SMALL, anchor="end", color=S.BODY, width=150)

c.legend(40, 950, kinds=("person", "agent", "record", "check", "evidence", "delivery"), cols=6, cell=215)

S.finish(
    c, id="1.3", name="diagram-01-03-ide-and-agent-work-cell",
    caption="An editor puts the person at every keystroke; a work cell gives the agent intent, context, tools, memory "
            "and sensors, and keeps the person at the intent, the permission boundary and the evidence.",
    alt="Two panels. On the left, with an IDE: the developer types into and reads the editor, runs commands by "
        "hand, the editor edits the code, and the code joins the team's usual path of tickets and pull-request "
        "review. On the right, the operator authorizes intent into an agent work cell holding a work item and plan, "
        "the coding agent, repository context, memory and sensors; the operator also decides at the permission "
        "boundary. The change ships to production and delivery evidence returns to the operator. A dashed trigger "
        "outside the cell marks the proposed way work would start on its own.",
    source="Replaces D14 WITH AN IDE AND WITHOUT ONE. Labels from Chapter 1, 'From agentic engineering to the "
           "factory' (the conversation workflow; the coding agent as a model inside a program that reads and edits "
           "files, executes commands, delegates and asks permission at a boundary; the person's attention at the two "
           "ends of the run), 'What I mean by a software factory' (the editor as a visual tool for a person; what the "
           "agent needs; the team's ceremonies unchanged) and Chapter 3, 'The harness' (guides and sensors). The "
           "trigger is proposed: 'I still begin every session' (Chapter 1, 'The fleet I built to study it').",
)
