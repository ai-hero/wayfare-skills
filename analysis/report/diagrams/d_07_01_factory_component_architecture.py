"""Diagram 7.1: the component architecture of the factory, control plane above one work cell.

The old eight parts (D03/D13: harness, process, connectors, state, gates, messages, policy, observability)
are resolved into the chapter's two layers. Process becomes work intake and goals plus shared skills; state
becomes the durable objects on the arrows plus fleet inventory and local context; gates split into the
merge policy (control plane) and local sensors (cell); observability becomes the evidence index and the
proposed operational view. Table 7.T1 keeps one row per node drawn here.
"""
import svg_lib as S

W = 188          # control-plane column width; six columns fit the 1320 px plane at this width
CW = 228         # cell column width
c = S.Canvas(1400, 1200)

# ------------------------------------------------------------------ people and signals
owner = c.node(76, 40, W, 80, "person", "Owner", "sets direction, owns risk")
signals = c.node(288, 40, W, 80, "evidence", "Signals", "feedback, alerts, findings")

# ------------------------------------------------------------------ control plane
c.group(40, 160, 1320, 440, "Control plane")
cols = [76 + i * (W + 24) for i in range(6)]
ya, yb = 205, 445
creds = c.node(cols[3], ya, W, 100, "record", "Credentials", "repository secrets")
fleet = c.node(cols[4], ya, W, 100, "record", "Fleet inventory", "FLEET.md: repos, ports")
evidx = c.node(cols[5], ya, W, 100, "evidence", "Evidence index", "logs, git, PRs, plans")
intake = c.node(cols[0], yb, W, 110, "record", "Work intake and goals", ".plans/: item, goal, plan")
skills = c.node(cols[1], yb, W, 110, "policy", "Shared skills", "the wayfare plugin")
register = c.node(cols[2], yb, W, 110, "policy", "Policy register", "controls, checks, audit")
merge = c.node(cols[3], yb, W, 110, "check", "Merge policy", "auto-approve workflow")
routing = c.node(cols[4], yb, W, 110, "record", "Message routing", "mailbox: inbox per repo")
opview = c.node(cols[5], yb, W, 110, "evidence", "Operational view", "live view of all cells", target=True)

# ------------------------------------------------------------------ one work cell
c.group(40, 680, 936, 400, "Work cell: one repository and its agent")
cx = [76, 394, 712]
yc, yd = 725, 920
harness = c.node(cx[0], yc, CW, 110, "agent", "Harness", "Claude Code: model, subagents, hooks")
sensors = c.node(cx[1], yc, CW, 110, "check", "Local sensors", "hooks, CI, tests, review agents")
delivery = c.node(cx[2], yc, CW, 110, "delivery", "Delivery path", "merge, build, deploy, health")
context = c.node(cx[0], yd, CW, 110, "record", "Local context", "code, AGENTS.md, HERO.md, DESIGN.md")
connectors = c.node(cx[1], yd, CW, 110, "record", "Connectors", "HERO.md: declared reach")

# ------------------------------------------------------------------ neighbours
c.group(1130, 680, 190, 160, "Other cells")
others = c.node(1146, 752, 158, 80, "plain", "Other work cells", "inbox where present")
c.group(1130, 900, 190, 190, "Connected")
external = c.node(1146, 948, 158, 130, "plain", "Connected systems", "design, design system, template, infrastructure")

# ------------------------------------------------------------------ arrows, durable objects on them
c.arrow(owner, intake, "authority", "authorizes", label_at=0.55)
c.arrow(signals, (230, yb), "flow", "signal", via=((382, 150), (230, 150)), ports=("bottom", "top"), label_at=0.3)
c.arrow((130, yb + 110), (130, yc), "flow", "goal, plan", label_at=0.75)
c.arrow((190, yb + 110), (190, yc), "flow", "trigger", target=True, label_at=0.3)
c.arrow(skills, (260, yc), "dependency", "skills", via=((382, 640), (260, 640)), ports=("bottom", "top"), label_at=0.2)
c.arrow(register, (508, yc), "dependency", "policy", via=((594, 660), (508, 660)), ports=("bottom", "top"), label_at=0.25)
c.arrow((cx[0] + CW, 760), (cx[1], 760), "flow", "change set")
c.arrow((cx[1], 805), (cx[0] + CW, 805), "feedback", "findings")
c.arrow(sensors, merge, "flow", "evidence record", via=((660, 780), (660, 620), (806, 620)), ports=("right", "bottom"),
        label_at=0.66)
c.arrow((860, yb + 110), (860, yc), "authority", "approval", label_at=0.5)
c.arrow(delivery, evidx, "feedback", "health evidence", via=((826, 890), (1342, 890), (1342, 255)), ports=("bottom", "right"),
        label_at=0.25)
c.arrow(evidx, signals, "feedback", "follow-up work", via=((evidx.cx, 80),), ports=("top", "right"), label_at=0.6)
c.arrow(evidx, opview, "dependency", target=True)
c.arrow(creds, merge, "dependency", "token")
c.arrow(fleet, routing, "dependency", "ownership")
c.arrow((250, yc + 110), routing, "flow", "message", via=((250, 860), (1000, 860)), ports=("bottom", "bottom"), label_at=0.5)
c.arrow((1060, yb + 110), (1225, 740), "flow", "message", via=((1060, 620), (1225, 620)), label_at=0.6)
c.arrow((150, yd), (150, yc + 110), "dependency", "context")
c.arrow((cx[0] + CW, 975), (cx[1], 975), "dependency", "declares")
c.arrow(connectors, external, "dependency", "reach", via=((1050, 975), (1050, external.cy)), ports=("right", "left"), label_at=0.3)

c.legend(40, 1110, kinds=("person", "agent", "record", "policy", "check", "delivery", "evidence"),
         arrows=("flow", "authority", "dependency", "feedback"), target=True, cols=6, cell=215)

S.finish(
    c, id="7.1", name="diagram-07-01-factory-component-architecture",
    caption="The control plane says which goal is authorized, which rule applies and where a message goes; the "
            "cell decides how to satisfy the goal in its own code, and only the trigger that would start work "
            "without a person and the live operational view are still proposed.",
    alt="Two layers. A control plane holds work intake and goals, shared skills, the policy register, the merge "
        "policy, message routing, credentials, the fleet inventory and an evidence index, with a dashed proposed "
        "operational view. Below it one work cell holds the harness, local sensors, the delivery path, local "
        "context and connectors. Arrows carry goals, plans, skills, policy, change sets, evidence records, "
        "approvals, health evidence and messages between the layers; a dashed arrow marks the proposed trigger.",
    source="Replaces D03 THE PARTS OF A FACTORY [components deck] and D13 THE PARTS OF A FACTORY [intro deck]. "
           "Components and objects from Chapter 7, 'The control plane and the work cells' and 'The objects that "
           "travel through the factory'; implementations from the components deck's part-by-part table "
           "(analysis/report/components/deck.py, PARTS_TABLE). Proposed: the trigger (Chapter 9, 'The next "
           "constraint') and the operational view (Chapter 9, 'What I would change next').",
)
