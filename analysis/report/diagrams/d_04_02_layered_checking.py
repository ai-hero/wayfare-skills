"""4.2 What catches a mistake: five checking layers, what each reads, the record it leaves, and where a failure
sends the work."""
import svg_lib as S

c = S.Canvas(1400, 900)
W = 216
X = [60 + i * (W + 60) for i in range(5)]
CX = [x + W / 2 for x in X]


def row(y, title):
    c.text(40, y, title, size=S.MONO_SIZE, mono=True, color=S.MUTED)


layers = [
    ("1 Local checks", "hooks: formatting, static analysis, unit tests, schema"),
    ("2 Integration", "CI repeats the checks in a clean environment"),
    ("3 Review", "review agents: correctness, security, architecture, tests"),
    ("4 Merge policy", "auto-approve: evidence, findings addressed, CI green, within the goal"),
    ("5 Production", "deploy health, smoke tests, telemetry, canary"),
]
kinds = ["check", "check", "agent", "check", "check"]
nodes = [c.node(X[i], 70, W, 140, kinds[i], t, s) for i, (t, s) in enumerate(layers)]
for a, b in zip(nodes, nodes[1:]):
    c.arrow(a, b, "flow")
c.text(CX[0] - 10, 40, "before the change leaves the working copy", size=S.SMALL, color=S.MUTED)
c.text(1340, 40, "after the merge", size=S.SMALL, color=S.MUTED, anchor="end")

row(250, "READS")
reads = ["the code, in the working copy", "the code, in a clean environment", "the diff, the plan and the repository",
         "evidence and descriptions, not the code again", "the running application"]
for i, t in enumerate(reads):
    c.node(X[i], 270, W, 70, "plain", t, size=S.SMALL, align="left")

row(370, "RECORD LEFT")
records = [
    ("Nothing durable", "a local block leaves no trace", True),
    ("10,686 CI runs", "a verdict per run", False),
    ("805 runs", "findings only as prose in transcripts", False),
    ("1,878 verdicts", "156 sent back; six named checks", False),
    ("799 health runs", "33 failed, 4 August outages", False),
]
recs = [c.node(X[i], 400, W, 110, "evidence", t, s, target=tg) for i, (t, s, tg) in enumerate(records)]

row(550, "ON FAILURE, THE WORK GOES")
fails = ["back to the agent, before a commit", "back to the pull request: a fix-up commit", "back to the pull request: 52% of in-PR catches",
         "back, with reasons: not merely failed", "forward, through the same path: 114 PRs fixed within 7 days"]
for i, t in enumerate(fails):
    c.node(X[i], 570, W, 90, "plain", t, size=S.SMALL, align="left")

agent = c.node(60, 720, 900, 100, "agent", "Producing agent, inside the pull request",
               "1,737 fix-up commits before merge; the agent itself caught 36% of in-PR mistakes")
item = c.node(1020, 720, 320, 100, "record", "Work item", "a failure enters the direction loop as new work")
for i in range(4):
    c.arrow((CX[i], 660), agent, "feedback", via=((CX[i], 690), (CX[i], 690)), ports=("bottom", "top"))
c.arrow((CX[4], 660), item, "feedback", ports=("bottom", "top"))

c.node(60, 845, 1280, 40, "policy", "A check counts only once it has been shown to fail on a known-bad case: 38 hollow checks found, 19 by the agent, 6 by review agents", size=S.SMALL, target=True)

S.finish(
    c, id="4.2", name="diagram-04-02-layered-checking",
    caption="Four of the five layers read the code and send a mistake back into the pull request; the merge policy "
            "reads evidence and descriptions, and only CI, the merge policy and the health check leave a verdict "
            "the factory can learn from.",
    alt="Five columns in reading order: local checks, integration in CI, independent review, merge policy and "
        "production verification. Under each, three rows say what it reads, the record it leaves and where a "
        "failure sends the work. Local checks leave no durable record (dashed). The first four columns feed "
        "dotted feedback arrows into a producing-agent node inside the pull request; production feeds a work item. "
        "A dashed bar at the bottom states that a check counts only once it has been shown to fail.",
    source="Replaces D27 WHAT CATCHES A MISTAKE. Layers and what each reads: Chapter 4, 'Layered checking' and "
           "'Done must be checked against the work'. 10,686 CI runs, 1,878 judge verdicts, 805 persona runs with "
           "findings only as prose, hooks record nothing: Q readable-gate-verdicts. 156 of 1,878 sent back, six "
           "named checks since 29 Aug: Q reviewer-and-judge-changes. 799 health runs, 33 failed in 4 August "
           "outages: Q production-uptime. 1,737 fix-up commits inside PRs, 114 PRs fixed within 7 days: Q "
           "where-rework-is-caught. Review agents 52% and the producing agent 36% of in-PR catches: Q "
           "who-catches-mistakes. 38 hollow checks, 19 noticed by the agent and 6 by review agents: Q hollow-checks.",
)
