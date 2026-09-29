"""Diagram 3.4: findings and requests travel upward through the mailbox, approved changes travel downward by sweep,
and the message lifecycle with its dead-letter path sits between."""
import svg_lib as S

c = S.Canvas(1400, 1120)

# Owning repositories: the recipients of every conversation the record holds.
c.group(40, 40, 1320, 170, "Owning repositories · every conversation went upward to one of these")
owners = []
for i, (name, sub) in enumerate([
    ("hero-template", "the template clones start from"),
    ("design-system", "the registry consumers install from"),
    ("auth", "the identity provider the apps rely on"),
    ("wayfare plugin", "the skills every repo runs"),
]):
    owners.append(c.node(80 + i * 320, 90, 280, 90, "agent", name, sub))

# Consumers: the applications, from the fleet map.
c.group(40, 920, 1320, 160, "Applications · consumers, cloned from the template")
apps = []
for i, name in enumerate(["elevate-commons", "ah-cozy", "aihero-wayfare", "aihero-mehr", "aihero-dokyu", "aihero-steadfast"]):
    apps.append(c.node(70 + i * 215, 965, 195, 90, "agent", name))

# The mailbox: one deposit into the recipient's inbox, and the lifecycle around it.
c.group(40, 290, 990, 540, "The mailbox · one write outside the repo: a file in the recipient's .plans/inbox/")
W, H = 200, 150
created = c.node(70, 340, W, H, "record", "created", "the sender's item suspends: awaiting, expires, the full text kept")
routed = c.node(310, 340, W, H, "check", "routed?", "the recipient must already have .plans/inbox/")
inbox = c.node(550, 340, W, H, "record", "in the inbox", "status new; claimed by one session; data, not instruction")
decided = c.node(790, 340, W, H, "check", "accepted or declined", "the promotion gate: never work by itself")
planned = c.node(790, 530, W, H, "record", "planned, done", "an item with origin: message, built under the owner's gates")
acked = c.node(550, 530, W, H, "record", "acknowledged", "a reply into the sender's inbox clears its await")
dead = c.node(310, 530, W, H, "record", "undelivered", "stays with the sender: 2 replies never arrived")
dead_target = c.node(310, 710, W, 100, "record", "Dead-letter channel", "visible to a person", target=True)

c.arrow(created, routed, "flow", "deposit")
c.arrow(routed, inbox, "flow", "yes")
c.arrow(inbox, decided, "flow", "claim")
c.arrow(decided, planned, "flow", "accept", ports=("bottom", "top"), label_dy=0)
c.arrow(planned, acked, "flow", "reply")
c.arrow(routed, dead, "flow", "no inbox", ports=("bottom", "top"), label_dy=0)
c.arrow(dead, dead_target, "flow", target=True, ports=("bottom", "top"))

# Upward and downward, as observed.
c.arrow((140, 965), (140, 480), "flow")
c.text(160, 845, "upward: 7 conversations opened, all asks and bug reports", size=S.SMALL, color=S.BODY, halo=True)
c.arrow((650, 680), (230, 965), "feedback", via=((650, 875), (230, 875)))
c.text(250, 893, "reply, when the sender has an inbox", size=S.SMALL, color=S.BODY, halo=True, baseline="middle")
c.arrow(planned, owners[1], "flow", "the owner's own PR ships it", ports=("right", "bottom"), via=((1010, 605), (1010, 250), (540, 250)),
        label_at=0.6, label_dy=-12)
c.arrow(owners[3], apps[5], "flow", ports=("bottom", "top"), via=((1180, 250), (1340, 250), (1340, 875), (1242, 875)))
c.text(1320, 745, "downward: 27 one-pass sweeps,", size=S.SMALL, color=S.BODY, anchor="end")
c.text(1320, 767, "not messages", size=S.SMALL, color=S.BODY, anchor="end")
c.node(1060, 380, 250, 130, "check", "Update bot", "proposes a PR when a consumer falls behind a release", target=True)
c.node(1060, 560, 250, 150, "check", "Wake the receiver", "a message arrival starts bounded work; today it waits for a session", target=True)

S.finish(
    c, id="3.4", name="diagram-03-04-cross-repository-movement",
    caption="Requests and findings climb to the repository that owns the fix, through a mailbox that never edits another repository, while approved changes still come down by sweep rather than by message.",
    alt="Four owning repositories across the top, six applications across the bottom. Between them a mailbox box traces one message: created with the sender suspended, a routing check for the recipient's inbox, in the inbox, accepted or declined at the promotion gate, planned and completed as the owner's own item, acknowledged by a reply; a branch from the routing check leads to undelivered and a dashed proposed dead-letter channel. An upward arrow from the applications carries the seven conversations; a downward arrow on the right carries 27 one-pass sweeps. Two dashed proposed boxes, an update bot and waking the receiver, sit beside the sweep.",
    source="Replaces D23 WHAT MOVES BETWEEN REPOS. Lifecycle and the no-inbox rule from docs/MESSAGES.md. Messages from .analysis/data/plans.sqlite messages: nine rows, recipients auth, design-system and the plugin (hero-skills); two replies from auth to design-system sit in the sender's .plans/.outbox and never arrived. Owning repositories are the to_repo values plus hero-template as the template; applications are the FLEET.md apps rows at ~/workspaces/aihero, minus the three owners. Chapter 3, Messages between cells: 7 conversations opened, all upward; 2 of 4 replies never arrived; 27 one-pass sweeps downward; the update bot and waking the receiver are the chapter's proposals.",
)
