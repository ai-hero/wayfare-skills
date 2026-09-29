"""2.1 One piece of work: the durable path from signal to evidence, and what loops back into intake."""
import svg_lib as S

c = S.Canvas(1400, 820)

# Intake, above the authorization boundary.
prio = c.node(500, 30, 260, 100, "policy", "Prioritization", "proposed: a cap on open work per repo", target=True)
signals = c.node(80, 160, 200, 100, "person", "Signals", "people, systems and agents propose work")
item = c.node(340, 160, 260, 100, "record", "Work item", ".plans/: problem, outcome, constraints, done")
ready = c.node(660, 160, 240, 100, "person", "Ready mark", "owner; 60% of items since 25 Aug")
goal = c.node(960, 160, 260, 100, "record", "Goal", "related items grouped; median 3, done in 1 day")

c.arrow(signals, item, "flow")
c.arrow(item, ready, "authority")
c.arrow(prio, (630, 202), "authority", "would sit here", target=True, label_at=0.45, label_dy=0,
        ports=("bottom", "top"))
c.arrow(ready, goal, "flow")

# The boundary the factory executes within.
c.group(40, 340, 1320, 160, "Authorized")
c.text(60, 508, "the factory executes within it", size=S.SMALL, color=S.MUTED)
plan = c.node(80, 375, 200, 90, "agent", "Plan", "person and agent, one prompt at a time")
build = c.node(340, 375, 200, 90, "agent", "Build", "one agent, one item")
review = c.node(600, 375, 200, 90, "check", "Review", "independent review agents")
merge = c.node(860, 375, 200, 90, "check", "Merge policy", "auto-approve reads the evidence")
deploy = c.node(1120, 375, 200, 90, "delivery", "Deploy", "on merge, 4 launched apps")

c.arrow(goal, plan, "authority", "owner types go: the manual start", via=((1090, 296), (180, 296)), label_at=0.55)
c.arrow(plan, build, "flow")
c.arrow(build, review, "flow", "pull request", label_dy=52)
c.arrow(review, merge, "flow", "findings fixed", label_dy=52)
c.arrow(merge, deploy, "flow", "approved", label_dy=52)

# What bypasses the saved plan, and what comes back.
oneshot = c.node(1240, 160, 120, 100, "person", "One-shot", "72% of change sets")
c.arrow(oneshot, build, "authority", "no item, no saved plan", via=((1300, 322), (440, 322)), label_at=0.3, label_dy=-12)

found = c.node(80, 580, 200, 100, "record", "Found work", "34% of items found while building; 84% completed")
c.arrow((830, 500), found, "flow", "a finding outside the task", via=((830, 530), (180, 530)), label_at=0.5,
        ports=("bottom", "top"))
c.arrow(found, signals, "feedback", via=((50, 630), (50, 210)), ports=("left", "left"))
c.text(60, 290, "a new item,", size=S.SMALL, color=S.BODY)
c.text(60, 311, "not an edit", size=S.SMALL, color=S.BODY)

evidence = c.node(600, 580, 460, 100, "evidence", "Evidence chain",
                  "goal and item · change set and tests · review findings · merge verdict · deploy run · health")
c.arrow(deploy, evidence, "flow", "run and result", via=((1220, 530), (830, 530)))
c.arrow(evidence, found, "feedback", "a failure returns as new work", target=True, ports=("left", "right"))

c.legend(60, 730, kinds=("person", "agent", "record", "policy", "check", "delivery", "evidence"), target=True)

S.finish(
    c, id="2.1", name="diagram-02-01-one-piece-of-work",
    caption="Once the owner marks an item ready and types go, agents carry it through plan, build, review, merge and "
            "deploy inside one authorization; anything found on the way is filed as a new item, and most change "
            "sets still enter through a one-shot instruction that skips the saved plan.",
    alt="Flow diagram. Signals become a work item, the owner marks it ready and related items form a goal. "
        "Inside a boundary labelled authorized, agents plan, build, review, apply the merge policy and deploy, "
        "leaving an evidence chain. A one-shot instruction enters the build directly, skipping the item and the "
        "plan. Found work is filed as a new item and loops back to the signals. A proposed prioritization step "
        "and the return of failures as new work are dashed.",
    source="Replaces D32 ONE PIECE OF WORK. Ready mark 60% of finished items since 25 Aug: Q owner-gates-per-item. "
           "Goal median 3 items, median 1 day: Q goal-duration-and-scope. One-shot instruction 72% of change sets "
           "since late July: Q owner-decision-share. Found while building 34%, 84% of 296 completed: Q work-sources, "
           "Q found-problem-follow-up. 4 launched apps deploy on merge: Q deploy-on-merge. Prioritization step and "
           "failure-as-new-work are proposals from Chapter 2 'What I would change' and Chapter 4 'Delivery evidence'.",
)
