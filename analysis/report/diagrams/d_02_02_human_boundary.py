"""2.2 Where the person must intervene: the decisions a person owns, the transitions that only wait for one
today, and what the factory does inside prior authorization. Solid is what the record shows; dashed is the target."""
import svg_lib as S

c = S.Canvas(1400, 850)
W, H = 216, 150
X = [40 + i * (W + 60) for i in range(5)]
CX = [x + W / 2 for x in X]

# Band 1: the person.
c.group(40, 40, 1320, 220, "Person")
c.text(1340, 52, "defines value and risk", size=S.SMALL, color=S.MUTED, anchor="end")
value = c.node(X[0], 80, W, H, "person", "Product value", "what to build and why; 87% of change sets trace to an owner decision")
risk = c.node(X[2], 80, W, H, "person", "Material risk", "one-way doors: migrations, permissions, public contracts, money")
owner = c.node(X[3], 80, W, H, "person", "Ownership", "which proposals enter the plan; a material scope change returns here")
creds = c.node(X[4], 80, W, H, "person", "Credentials", "accounts and keys agents cannot hold")
for i, ln in enumerate(("no decision lives here:", "only the keystroke that", "wakes a session")):
    c.text(CX[1], 130 + i * 22, ln, size=S.SMALL, color=S.MUTED, anchor="middle")

# Band 2: the transitions across the boundary.
c.text(40, 282, "BOUNDARY", size=S.MONO_SIZE, mono=True, color=S.MUTED)
ready = c.node(X[0], 310, W, H, "policy", "Ready mark", "60% of finished items; 81% marked in batches of four or more")
start = c.node(X[1], 310, W, H, "person", "Start or resume", "the owner types it; no session open for 56% of PR time")
door = c.node(X[2], 310, W, H, "policy", "One-way door", "a careful read of the plan; 63% now merge on auto-approve alone",
              target=True)
prio = c.node(X[3], 310, W, H, "policy", "Prioritization", "which proposals enter the plan; open work grew 30 to 141", target=True)
login = c.node(X[4], 310, W, H, "person", "Log in", "tokens and keys set by hand; stays manual")

# Band 3: the factory.
c.group(40, 510, 1320, 220, "Factory")
c.text(60, 706, "selects methods, checks progress, surfaces discoveries", size=S.SMALL, color=S.MUTED)
build = c.node(X[0], 550, W, H, "agent", "Plan and build", "most commits co-authored; 91% of agent time within 30 min of a prompt")
trigger = c.node(X[1], 550, W, H, "agent", "Trigger", "a ready item, a failed check, a message, a goal stopped at a limit",
                 target=True)
check = c.node(X[2], 550, W, H, "check", "Check", "hooks, CI, review agents, auto-approve; a person read 7 of 1,519 PRs")
route = c.node(X[3], 550, W, H, "agent", "Discoveries", "34% of items found while building; filed, not edited")
deploy = c.node(X[4], 550, W, H, "delivery", "Deploy", "on merge through the platform's path; 4 launched apps")

# Authority runs down each column; proposals come back up.
c.arrow(value, ready, "authority")
c.arrow(ready, build, "authority", "authorizes")
c.arrow(start, build, "authority", "today", via=((CX[1], 490), (X[0] + W + 24, 490)), ports=("bottom", "right"), label_at=0.2)
c.arrow(start, trigger, "authority", "target: replaces the keystroke", target=True, label_dy=32)
c.arrow(risk, door, "authority", target=True)
c.arrow(door, check, "authority", "escalates by consequence", target=True)
c.arrow(owner, prio, "authority", target=True)
c.arrow(route, prio, "feedback", "proposals, with evidence")
c.arrow(creds, login, "authority")
c.arrow(login, deploy, "authority", "by hand")

c.legend(60, 770, kinds=("person", "agent", "policy", "check", "delivery"), arrows=("authority", "feedback"), target=True)

S.finish(
    c, id="2.2", name="diagram-02-02-human-boundary",
    caption="The person owns value, risk, ownership and credentials; the factory owns methods, checks and discoveries; "
            "the transition that still waits for a person is the keystroke that starts or resumes a session, and the "
            "careful read for one-way doors does not yet exist.",
    alt="Three bands in five columns. Top: the person defines product value, material risk, ownership and "
        "credentials. Middle, the boundary: a ready mark and a manual log-in are solid; start or resume is a solid "
        "person node that today feeds the build and would be replaced by a dashed trigger; a one-way-door read and a "
        "prioritization step are dashed. Bottom: the factory plans and builds, checks, files discoveries and "
        "deploys. Pink authority arrows run down each column; proposals come back up as a dotted feedback arrow.",
    source="Replaces D28 WHEN I HAVE TO BE THERE (the design from the talk), reconciled with the record. Owner "
           "decision 87%: Q owner-decision-share. Ready mark 60% of finished items since 25 Aug: Q "
           "owner-gates-per-item; 81% in batches of four or more: Q ready-mark-batching. One-way-door PRs 63% merged "
           "on auto-approve alone: Q one-way-door-changes. No session open 56% of PR time: Q pr-time-breakdown. "
           "Open work 30 to 141: Q backlog-trend. 91% of agent working time within 30 min of a prompt: Q "
           "work-while-away. A person reviewed 7 of 1,519 merged PRs: Q who-really-reviews. Found while building "
           "34%: Q work-sources. 4 launched apps deploy on merge: Q deploy-on-merge. Trigger, one-way-door read and "
           "prioritization are Chapter 2's 'What I would change'; the log-in stays manual by the chapter's own rule.",
)
