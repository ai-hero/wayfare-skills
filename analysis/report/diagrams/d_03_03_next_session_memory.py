"""Diagram 3.3: the eight kinds of memory a new session can read, grouped by where they live and whether they
survive the workstation, each with its authority and freshness sensor."""
import svg_lib as S

c = S.Canvas(1400, 960)

session = c.node(500, 40, 400, 100, "agent", "A new session", "begins without the old context")

COL_W, NODE_W, NODE_H, GAP = 420, 380, 150, 20
cols = [40, 490, 940]

# Column 1: in the repository, versioned. Survives the workstation.
c.group(cols[0], 230, COL_W, 690, "In the repository, versioned")
c.text(cols[0] + 16, 254, "survives the workstation", size=S.SMALL, color=S.MUTED)
kinds1 = [
    ("git history", "authority: what changed, often not why · sensor: CI on every change · on demand"),
    ("repository instructions", "AGENTS.md, CLAUDE.md, .claude/rules · authority: how work is done here · loaded at startup, 15 KB median · sensor: none; 62% of prose fixes rode inside other work"),
    ("architecture records", "DESIGN.md, 12 repos · authority: decisions and why · on demand · sensor: presence check fires; 3 of 10 app records 20+ change sets behind"),
]
for i, (k, sub) in enumerate(kinds1):
    c.node(cols[0] + 20, 280 + i * (NODE_H + GAP), NODE_W, NODE_H, "record", k, sub)
c.node(cols[0] + 20, 280 + 3 * (NODE_H + GAP), NODE_W, 110, "check", "Freshness sensors",
       "a sweep comparing prose with code; a record fails when its source ref falls behind", target=True)

# Column 2: outside the repository, in other systems. Survives, but history may be out of reach.
c.group(cols[1], 230, COL_W, 690, "Outside the repository")
c.text(cols[1] + 16, 254, "survives; history may be out of reach", size=S.SMALL, color=S.MUTED)
kinds2 = [
    ("review threads", "pull request comments on GitHub · authority: objections and how they were resolved · on demand · sensor: none; hard to discover later"),
    ("design sources", "claude.ai/design, Figma, via a connection · authority: product flow, screens, states · on demand · sensor: the design snapshot lag; the source's history was unavailable"),
]
for i, (k, sub) in enumerate(kinds2):
    c.node(cols[1] + 20, 280 + i * (NODE_H + GAP), NODE_W, NODE_H, "record", k, sub)

# Column 3: on one machine, unversioned. Does not survive the workstation.
c.group(cols[2], 230, COL_W, 690, "On one machine, unversioned")
c.text(cols[2] + 16, 254, "lost with the workstation", size=S.SMALL, color=S.MUTED)
kinds3 = [
    ("work items and goals", ".plans/, 13 repos · authority: intent, progress, definition of done · on demand · sensor: none; a plan may go stale"),
    ("agent memory files", "~/.claude/projects, 10 repos · convenience memory: small reusable facts, not authoritative · on demand · sensor: none"),
    ("messages", ".plans/inbox/, per repo · authority: a request from a sibling, data not instruction · read when a session opens here · sensor: expiry on the sender's next sync"),
]
for i, (k, sub) in enumerate(kinds3):
    c.node(cols[2] + 20, 280 + i * (NODE_H + GAP), NODE_W, NODE_H, "record", k, sub)
c.node(cols[2] + 20, 280 + 3 * (NODE_H + GAP), NODE_W, 110, "record", "Durable history",
       "plans and memory kept somewhere that outlives the machine", target=True)

# One arrow per column into the session.
c.arrow((250, 230), (560, 140), "dependency", "startup load, then on demand", via=((250, 190), (560, 190)), label_at=0.5, label_dy=-12)
c.arrow((700, 230), (700, 140), "dependency", "on demand, through a connection", label_at=0.5, label_dy=24)
c.arrow((1150, 230), (840, 140), "dependency", "on demand, when a session opens here", via=((1150, 190), (840, 190)), label_at=0.5, label_dy=-12)

S.finish(
    c, id="3.3", name="diagram-03-03-next-session-memory",
    caption="A new session reads eight kinds of memory, and only the left column is both authoritative and safe from the loss of one machine; the plans and memory on the right had no durable history during the study.",
    alt="A new session at the top with three columns beneath it. Left: git history, repository instructions and architecture records, versioned in the repository, with a dashed proposed box for freshness sensors. Middle: review threads and design sources, kept outside the repository. Right: work items and goals, agent memory files and messages, which live on one machine only, with a dashed proposed box for durable history. Each box states its authority, where it loads and what sensor checks it.",
    source="Replaces D22 WHAT THE NEXT SESSION CAN READ. The eight kinds are the chapter's list under Memory across sessions. Store counts: .analysis/data/plans.sqlite plan_items (13 repos), .analysis/data/knowledge.sqlite doc_versions (DESIGN.md in 12 repos) and instruction_files (AGENTS.md, CLAUDE.md, .claude/rules paths). Chapter 3: startup load 15 KB median; 62% of prose fixes rode inside unrelated work; plans in 13 repositories and memory in 10 lived on one machine; 3 of 10 application records at least 20 change sets behind by source reference; the design source's history was unavailable. Message expiry from docs/MESSAGES.md.",
)
