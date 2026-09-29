"""Diagram 6.2: the improvement loop, guide and sensor changed together, inside the constraints that bound it."""
import svg_lib as S

c = S.Canvas(1400, 1070)

outer = c.group(40, 40, 1320, 940, "Constraints · attention · cost · authority · blast radius")

observe = c.node(80, 100, 300, 130, "person", "Observe the work", "go and see: traces, PRs, plans, sessions · not a report or a vivid memory")
pattern = c.node(460, 100, 300, 130, "evidence", "Find the pattern", "errors were 26 to 42% of corrections; scope judgments rose from 26% to 45%")
locus = c.node(840, 100, 300, 130, "policy", "Choose the locus", "plugin, template, register or the approval workflow: fix it once")

guide = c.node(920, 300, 400, 130, "agent", "Improve the guide", "instructions, a clearer skill, a repository map, an example, a safer tool · the producing agent avoids the mistake")
sensor = c.node(920, 470, 400, 130, "check", "Improve the sensor", "a test, linter, policy or independent review · catches it if it happens anyway · 163 of 164 rules state why")

deploy = c.node(840, 700, 300, 150, "delivery", "Stage and deploy", "a reviewed PR to the plugin · versions 1.0.0, 1.1.0, 2.0.0 · @main reaches 14 repos at once")
canary = c.node(840, 880, 300, 70, "check", "Canary in one repo first", target=True)
measure = c.node(460, 700, 300, 150, "evidence", "Measure recurrence and false positives", "no evidence yet: spend per change set rose from $8 to $23 as token-saving changes landed",
                 target=True)
decide = c.node(80, 700, 300, 150, "person", "Retain, revise or roll back", "roll back by reverting on main")

incident = c.node(80, 400, 300, 130, "record", "Incident record", "the observation that justified the change, linked to the skill, test or policy",
                  target=True)

c.arrow(observe, pattern, "flow")
c.text(460, 240, "61% of the plugin's changes since 9 Aug began with the owner's feedback", size=S.SMALL, color=S.BODY, width=300)
c.arrow(pattern, locus, "flow")
c.arrow(locus, guide, "flow", ports=("bottom", "top"), via=((990, 260), (1120, 260)))
c.arrow(locus, (920, 535), "flow", ports=("bottom", None), via=((990, 260), (880, 260), (880, 535)))
c.arrow(guide, deploy, "flow", "together", ports=("bottom", "top"), via=((1120, 450), (1345, 450), (1345, 660), (990, 660)),
        label_at=0.75, label_dy=-12)
c.arrow(sensor, deploy, "flow", ports=("bottom", "top"), via=((1120, 640), (990, 640)))
c.arrow(deploy, canary, "flow", ports=("bottom", "top"), target=True)
c.arrow(deploy, measure, "flow", "then", label_at=0.5, target=True)
c.arrow(measure, decide, "flow", target=True)
c.arrow(decide, observe, "feedback", "again", ports=("left", "left"), via=((58, 775), (58, 165)), label_at=0.5)
c.arrow(pattern, incident, "flow", "keep the reason", ports=("bottom", "top"), via=((610, 330), (230, 330)),
        label_at=0.5, label_dy=-12, target=True)
c.arrow(incident, (920, 575), "dependency", "linked", ports=("right", None), via=((620, 465), (620, 575)),
        label_at=0.15, label_dy=-12, target=True)

c.legend(60, 1000, kinds=("person", "agent", "check", "record", "evidence"), arrows=("flow", "feedback"), target=True,
         cols=4, cell=320)

S.finish(
    c, id="6.2", name="diagram-06-02-improvement-loop",
    caption="A recurring failure should change both the guide the agent follows and the sensor that catches the "
            "miss, ship as versioned software, and be measured; the last step is the one this factory has not built.",
    alt="A loop: observe the work, find the recurring pattern, choose the shared locus, improve the guide and the "
        "sensor together, stage and deploy through a reviewed plugin release, measure recurrence, then retain, "
        "revise or roll back and observe again; a canary, the measurement step and an incident record linked to "
        "the sensor are drawn dashed as proposed; the surrounding box names attention, cost, authority and blast "
        "radius as the constraints.",
    source="Replaces D21 and D30 HOW I DECIDE WHAT TO CHANGE. Guide and sensor definitions, the constraints and "
           "the rollback rule: chapter 6 and AGENTS.md. Corrections (errors 26 to 42%; scope 26% to 45%): chapter 6. "
           "Plugin change triggers (61% of 62 since 9 Aug from the owner's feedback): Q plugin-change-triggers. "
           "Rules that state why (163 of 164): Q written-reasons. Plugin versions 1.0.0 (7 Mar), 1.1.0 (29 Mar), "
           "2.0.0 (22 Sep): .analysis/data/knowledge.sqlite plugin_versions. Auto-approve at @main in 14 repos: "
           ".analysis/data/mirrors. Spend per change set $8 to $23 and the missing evidence: chapter 6.",
)
