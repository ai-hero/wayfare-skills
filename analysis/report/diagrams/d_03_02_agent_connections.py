"""Diagram 3.2: one repository work cell, the six connection kinds it reads, the states a connection can be in,
and the credential boundary only a person crosses."""
import svg_lib as S

c = S.Canvas(1400, 1080)

cell = c.node(490, 410, 520, 120, "agent", "One agent, one repository",
              "the work cell; HERO.md ## Connections: kind, type, locator, reach")

# The six kinds, the closed list in docs/CONNECTIONS.md; type and reach values are what the fleet's HERO.md files declare.
top = [
    ("design", "the product's own surface", "claude-design, figma · reach: designsync"),
    ("design-system", "the component registry", "registry · reach: checkout of the producer"),
    ("reference", "the template this repo should still resemble", "repo · reach: checkout"),
]
bottom = [
    ("architecture", "where the decision record lives", "self (root DESIGN.md), repo, docs"),
    ("infrastructure", "the Terraform or manifests for this system", "terraform, kubernetes, self · reach: checkout"),
    ("issues", "the tracker work is filed in", "github via gh, linear via MCP"),
]
xs = [215, 590, 965]
tops, bots = [], []
for x, (k, what, tr) in zip(xs, top):
    tops.append(c.node(x, 60, 300, 150, "record", k, f"{what} · {tr}"))
for x, (k, what, tr) in zip(xs, bottom):
    bots.append(c.node(x, 640, 300, 150, "record", k, f"{what} · {tr}"))

# Authority on every edge: the cell reads; the one write outside the repo is a message (3.4).
c.arrow((560, 410), (365, 210), "dependency", "reads; 82 findings back", via=((560, 300), (365, 300)), label_at=0.5, label_dy=-12)
c.arrow((740, 410), (740, 210), "dependency", "reads · proposes by message", label_at=0.5, label_dy=0)
c.arrow((920, 410), (1115, 210), "dependency", "reads", via=((920, 300), (1115, 300)), label_at=0.5, label_dy=-12)
c.arrow((560, 530), (365, 640), "dependency", "reads; changes if self", via=((560, 590), (365, 590)), label_at=0.5, label_dy=12)
c.arrow((740, 530), (740, 640), "dependency", "reads", label_at=0.5, label_dy=0)
c.arrow((920, 530), (1115, 640), "dependency", "reads · files an issue", via=((920, 590), (1115, 590)), label_at=0.5, label_dy=12)

# Credentials and human-only login: a boundary the connectors cannot cross on their own.
c.group(40, 300, 310, 340, "Credentials and human-only login")
owner = c.node(70, 360, 250, 240, "person", "Owner",
               "signs in, carries files for reach: manual; 149 login or credential stops since November, 55 since August; median wait 2 min, three over an hour")
c.arrow(owner, cell, "authority", "signs in", ports=("right", "left"), label_dy=-12)

# The states a declared connection can be in, and the observed failures.
c.group(40, 840, 1320, 210, "Reach check at the point of use · three states, never two, plus in-repo")
c.node(70, 890, 190, 130, "record", "unset", "no block: nobody looked; ask once")
c.node(285, 890, 230, 130, "record", "absent", "type: none; looked, it does not exist; proceed without it")
c.node(540, 890, 190, 130, "record", "in-repo", "type: self; exists and lives here")
c.node(755, 890, 220, 130, "check", "unreachable", "type set, reach unavailable: report, degrade loudly")
c.node(1000, 890, 340, 130, "evidence", "Observed", "DesignSync: 11 of 1,861 calls failed; 8 runs said so and went on; 4 repos declared design manual when it was readable")

S.finish(
    c, id="3.2", name="diagram-03-02-agent-connections",
    caption="Every connection is something the cell reads; the only write outside the repository is a message, a person crosses the credential boundary, and a check at the point of use must tell absent from unreachable.",
    alt="One agent in the centre, the repository work cell. Six connection kinds surround it, three above (design, design-system, reference) and three below (architecture, infrastructure, issues), each reached by a read arrow whose label says what the cell may also propose. On the left a boundary box holds the owner, who signs in and unblocks a reach. Along the bottom a strip names the four states a connection can be in, unset, absent, in-repo and unreachable, and an evidence box with the observed failures.",
    source="Replaces D06 WHAT ONE AGENT CONNECTS TO. Kinds, types, reach values and the four states from docs/CONNECTIONS.md; declared type and reach values from the fleet's HERO.md ## Connections blocks (auth, design-system, elevate-commons, hero-template, pterodactyl, read-only). DesignSync 11 of 1,861 failed: .analysis/data/harness.sqlite tool_calls (tool DesignSync, is_error). Chapter 3, Connections and tools: 8 runs proceeded without design; 4 repos declared design manual, another account for 1 to 11 days; 149 login or credential stops since November, 55 since August, median 2 minutes, three over an hour. Design as a connected source: 82 findings sent back to design.",
)
