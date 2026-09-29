"""Diagram 5.2: how a fleet expectation becomes an executable control, and what happens to each audit result."""
import svg_lib as S

c = S.Canvas(1400, 1010)

# Where rules come from.
src = c.group(40, 40, 330, 400, "Where a rule starts")
owner = c.node(60, 90, 290, 96, "person", "Owner and agent", "33 of 40 register changes carry a Claude co-author; the owner commits them")
origins = c.node(60, 210, 290, 200, "evidence", "23 of 36 controls name a failure seen in the fleet",
                 "17 from comparing repositories · 9 from design work · 9 from a bug · 1 from an outside incident")

# The register, in two layers since 13 September.
reg = c.group(430, 40, 420, 400, "The register · since 13 Sep")
baseline = c.node(450, 90, 380, 110, "policy", "Baseline in the plugin", "wayfare-skills assets/compliance, changed by reviewed PR · a rule: title, severity, intent, why", align="left")
overlay = c.node(450, 220, 380, 190, "policy", "Fleet overlay in .fleet/",
                 "36 controls · 128 checks, 118 scripted, 10 need a person · a check: scope, layer, applies_to, rule, detect · a local repo with no remote: 15 of 20 changes since 13 Sep had no PR, CI or review",
                 align="left")
c.arrow(owner, baseline, "flow", ports=("right", "left"))
c.arrow(origins, overlay, "flow", ports=("right", "left"))
fields = c.node(450, 460, 380, 90, "policy", "Owner, effective date, expiry", "fields the chapter asks for; not in the schema",
                target=True, align="left")
template = c.node(910, 460, 390, 90, "record", "hero-template, until 13 Sep", "held the rules before; every change went through a reviewed PR")

# The audit and its outcomes.
audit = c.node(910, 90, 390, 130, "agent", "Audit", "audit.py in the plugin, every check against 13 repos · run by hand inside sync-plan: 12 days in 10 weeks, never in CI")
c.arrow(overlay, audit, "flow", ports=("right", "left"), via=((880, 315), (880, 155)))
ci = c.node(910, 260, 390, 70, "check", "On every PR and nightly", "the CI mode exists; no workflow calls it", target=True)
c.arrow(ci, audit, "flow", ports=("top", "bottom"), target=True)
c.arrow(template, overlay, "flow", "moved out 13 Sep", ports=("left", "bottom"), via=((880, 495), (880, 430), (640, 430)),
        label_at=0.4, label_dy=-12)

results = c.group(40, 580, 1260, 360, "Each check x repo result · 1,664 cells as of 21 Sep")
ok = c.node(60, 640, 250, 100, "evidence", "Pass · 1,089")
fail = c.node(340, 640, 300, 100, "evidence", "Fail · 112 open", "65% high severity · 58% of all 361 violations fixed in the sweep that found them")
person = c.node(670, 640, 210, 100, "evidence", "Needs a person · 146", "14 manual checks")
na = c.node(900, 640, 160, 100, "evidence", "Does not apply · 317")
cons = c.node(1080, 640, 220, 100, "record", "CONSISTENCY.md", "the fleet at merged state")
item = c.node(340, 780, 300, 120, "record", "Remediation work item", "proposed by sync-plan · deadlines set 24 Sep: high 14 d, medium 30 d, low 90 d")
exc = c.node(670, 780, 300, 120, "record", "Time-limited exception", "approver and expiry · the register records none", target=True)
c.arrow(audit, (980, 640), "flow", "results", ports=("right", None), via=((1320, 155), (1320, 580), (980, 580)),
        label_at=0.85, label_dy=14)
c.arrow(fail, item, "flow", ports=("bottom", "top"))
c.arrow(fail, exc, "flow", "or", ports=("bottom", "top"), via=((490, 760), (820, 760)), label_at=0.5, target=True)
c.arrow(item, audit, "feedback", "next audit", ports=("bottom", "top"), via=((490, 920), (1350, 920), (1350, 60), (1105, 60)), label_at=0.2)

c.legend(60, 965, kinds=("policy", "agent", "record", "evidence"), target=True, cols=5, cell=250)

S.finish(
    c, id="5.2", name="diagram-05-02-control-register",
    caption="The register turns an expectation into a check that runs against every repository, but the audit is "
            "still started by hand and the exception branch has never been used.",
    alt="Rules from the owner and an agent enter a two-layer register, a baseline in the plugin and a fleet "
        "overlay in .fleet, replacing the template's copy on 13 September; an audit run by hand sorts 1,664 "
        "check-by-repository cells into pass, fail, needs a person and does not apply; failures become "
        "remediation work items with deadlines; a time-limited exception and a CI-triggered audit are drawn "
        "dashed as proposed.",
    source="Replaces D02 THE REGISTER. Controls (36), checks (128), fields and detect methods (105 script, 14 "
           "manual, 7 file_exists, 1 http, 1 file_content): ~/workspaces/aihero/.fleet/CONTROLS.yaml and "
           "CHECKS.yaml; the chapter's 118 scripted counts every non-manual method. Results (1,089 pass, 112 fail, "
           "146 needs a person, 317 does not apply; 13 repos; as of 21 Sep): .analysis/data/knowledge.sqlite "
           "check_results. Register history (fleet overlay from 13 Sep; template copy before): knowledge.sqlite "
           "register_history. Audit cadence (12 days in 10 weeks, never in CI; CI mode uncalled): Q audit-frequency "
           "and chapter 5. Rule governance (15 of 20 changes with no PR; 33 of 40 with a Claude co-author): Q "
           "rule-change-review. Origins (23 of 36; 17, 9, 9, 1): Q control-origins. Open failures (65% high), "
           "deadlines set 24 Sep, no exceptions recorded: Q open-violations. Sweep repair (58% of 361): Q "
           "violation-fix-time.",
)
