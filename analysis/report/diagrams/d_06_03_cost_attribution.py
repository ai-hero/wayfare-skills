"""Diagram 6.3: what the factory pays, what it would cost at list price, and how far each dollar can be traced."""
import svg_lib as S

c = S.Canvas(1400, 1090)

# Sources, left column.
sg = c.group(40, 40, 340, 790, "Cost sources")
agent = c.node(60, 90, 300, 110, "agent", "Agent usage", "645 sessions · planning, building, review · 25 Aug to 27 Sep logged")
auto = c.node(60, 220, 300, 110, "check", "Automated model calls", "auto-approve in CI, a separate key · not in the session logs, unpriced")
ci = c.node(60, 350, 300, 110, "delivery", "CI minutes", "115,057 this year; 91,033 in 28 runs that hung on 26 Aug · minutes, not dollars")
infra = c.node(60, 480, 300, 100, "delivery", "Deployment and test infrastructure", "no record", target=True)
human = c.node(60, 600, 300, 90, "person", "Human attention", "31 hours a full week · not priced")
rework = c.node(60, 710, 300, 90, "evidence", "Rework and incidents", "no record", target=True)

# Lane 1: cash.
cash = c.group(440, 40, 920, 170, "Cash lane · what was paid")
plan = c.node(460, 90, 300, 100, "policy", "Subscription", "$200 a month, about $46 a week · sells a pace: usage resets and weekly limits")
limits = c.node(800, 90, 260, 100, "evidence", "Limit stops", "the plan caps the pace: 150 limit events · 136 of 999 session hours")
ninv = c.node(1100, 90, 240, 100, "plain", "Not an invoice", "the lane below is a shadow price, never added to this one")
c.arrow(agent, plan, "dependency", ports=("right", "left"), via=((410, 145), (410, 140)))
c.arrow(plan, limits, "dependency")

# Lane 2: list-price equivalent, and where it can be traced.
lane = c.group(440, 260, 920, 540, "List-price-equivalent lane · what the harness reports")
sessions = c.node(460, 320, 260, 110, "agent", "Sessions", "$18,250 harness-reported · about $3,391 a full week")
ids = c.node(760, 320, 260, 110, "record", "Shared identifiers", "branch, PR link, work item id · the join that makes cost traceable")
shared = c.node(1060, 320, 280, 110, "evidence", "Shared sessions", "$15,349 of $18,250 spent in sessions on several branches, split evenly")
c.arrow(agent, sessions, "flow", ports=("right", "left"), via=((410, 145), (410, 375)))
c.arrow(sessions, ids, "flow")
c.arrow(ids, shared, "dependency", "weakens")

cs = c.node(460, 500, 180, 100, "record", "Change set", "median $9.70")
pr = c.node(660, 500, 200, 100, "delivery", "Pull request", "median $13.47 · review 6%: $1.32 a reviewed PR")
item = c.node(880, 500, 180, 100, "record", "Work item", "median $16.57 · none records its own cost")
goal = c.node(1080, 500, 140, 100, "record", "Goal", "median $47.20")
c.arrow(ids, cs, "flow", "83% reaches a merged PR", ports=("bottom", "top"), via=((890, 460), (550, 460)), label_at=0.5,
        label_dy=14)
c.arrow(cs, pr, "flow")
c.arrow(pr, item, "flow")
c.arrow(item, goal, "flow")
kinds = c.node(460, 660, 430, 100, "evidence", "By repository and kind of work", "apps 61%, allied repos 37% · features 26%, fixes 22%, dependencies 12%, security 10%")
unalloc = c.node(920, 660, 420, 100, "evidence", "Unallocated · 17%", "11% on main with no PR: planning, questions · 5% a branch with no PR · 1% never merged")
c.arrow(cs, (550, 660), "flow", ports=("bottom", None))
c.arrow(ids, (1270, 660), "flow", ports=("bottom", None), via=((890, 460), (1270, 460)))

# Sources with no lane.
c.arrow(auto, (440, 275), "flow", ports=("right", None), target=True)
c.arrow(ci, (440, 405), "flow", ports=("right", None), target=True)

c.text(440, 840, "Unit cost is the metric: cost per useful, deployed change, adjusted for rework. Reported spend per change "
                 "set rose from about $8 a week in August to $23 in September; the work mix changed, the window is "
                 "short, and the CI model cost lived under a separate key, so the factory cannot yet say whether its "
                 "token-saving changes worked.", size=S.SMALL, color=S.BODY, width=900)
c.legend(60, 990, kinds=("agent", "policy", "record", "delivery", "evidence"), target=True, cols=3, cell=300)

S.finish(
    c, id="6.3", name="diagram-06-03-cost-attribution",
    caption="The factory pays a flat subscription but reports list-price spend seventy times larger, and only the "
            "second number can be followed to a change set, a pull request and a goal; a sixth of it goes nowhere.",
    alt="Six cost sources on the left feed two separate lanes: a cash lane holding the $200-a-month subscription "
        "and its usage limits, and a list-price-equivalent lane where $18,250 of harness-reported session spend "
        "flows through shared identifiers to change sets, pull requests, work items and goals with median costs, "
        "with shared sessions and 17% unallocated spend marked; CI minutes and automated model calls reach neither "
        "lane in dollars.",
    source="Replaces D31 WHAT THE FACTORY COSTS, AND WHERE IT GOES. Sessions (645, $18,250; cost-state 481, priced "
           "from tokens 164; logged 25 Aug to 27 Sep): .analysis/data/harness.sqlite sessions; weekly $3,391 and "
           "apps 61%, allied 37%: Q weekly-spend. Subscription ($200 a month, $46 a week): Q paid-vs-reported-cost. "
           "Limit events (150) and limit hours (136 of 999): harness.sqlite limit_events and Q session-clock. "
           "Attribution (83% reaches a merged PR; 11% main no PR, 5% branch no PR, 1% unmerged; $15,349 in "
           "multi-branch sessions): Q traceable-spend via report/spend/data.py and detectors.sqlite session_spend. "
           "Medians ($9.70, $13.47, $16.57, $47.20): Q cost-rollup. Review ($1.32, 6%): Q review-cost. Work kinds: Q "
           "spend-by-work-kind. CI minutes: Q ci-minutes. Owner's 31 hours a week: Q weekly-spend, Week's cost view. "
           "No work item records its own cost, the separate CI key and $8 to $23: chapter 6.",
)
