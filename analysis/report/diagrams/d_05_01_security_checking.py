"""Diagram 5.1: where each security sensor sits on the lifecycle, and how a finding becomes owned work."""
import svg_lib as S

c = S.Canvas(1400, 1000)

# Lane 1: sensors on the change, in the order a change meets them.
lane1 = c.group(40, 40, 1320, 250, "On the change · before merge")
change = c.node(60, 110, 150, 96, "plain", "A change", "on a branch")
hook = c.node(230, 100, 240, 120, "check", "Secret scan", "detect-secrets · local hook in 14 of 15 repos, in CI in 5; saga has none")
ci = c.node(500, 100, 250, 120, "check", "CI scans", "dependency scan in CI in 10 of 15 · image scan in 8 of 12 image repos · semgrep on push")
review = c.node(780, 100, 240, 120, "agent", "Security review", "wayfare-review-pr's security pass · found 2 of 175 security change sets")
gate = c.node(1050, 100, 210, 120, "check", "Auto-approve", "model reads the diff, secrets stripped · @main in 14 repos")
c.arrow(change, hook, "flow")
c.arrow(hook, ci, "flow")
c.arrow(ci, review, "flow")
c.arrow(review, gate, "flow")
main = c.node(1200, 320, 160, 70, "delivery", "main")
c.arrow(gate, main, "flow", "merge", ports=("right", "top"), via=((1280, 160),), label_at=0.6)

# Lane 2: sensors on the repository, whether or not anything changed.
lane2 = c.group(40, 420, 1320, 220, "On the repository · on a schedule or by hand")
dep = c.node(60, 470, 240, 130, "check", "Dependabot", "advisories in 14 of 15 repos · 593 PRs, 325 closed unmerged · daily image scan")
audit = c.node(330, 470, 300, 130, "agent", "Security audit", "wayfare-audit-security, read-only, whole repo · Scout, Trivy, code · run by hand inside sync-plan")
deploy = c.node(660, 470, 320, 130, "check", "Deployment config checks", "71 infrastructure risks recorded; none has a live check", target=True)
expose = c.node(1010, 470, 330, 130, "check", "Production exposure checks", "live exploitability, separate from a flaw on main", target=True)

# Lane 3: a finding becomes owned work and reaches siblings.
lane3 = c.group(40, 700, 1320, 260, "From finding to owned work")
finding = c.node(60, 780, 230, 120, "evidence", "Finding", "flaw sat on main a median 32 days; 24 for agent-written · 58 of 92 shipped first")
item = c.node(340, 780, 260, 120, "record", "Security work item", ".plans · 322 items: 203 closed the same day, median 0 days · fix, or a VEX exception")
fix = c.node(650, 780, 200, 120, "delivery", "Fix PR", "reviewed, approved, merged")
sibling = c.node(900, 780, 260, 120, "record", "Message to siblings", "the same fix, propagated · 91 of 114 arrivals within a day")
finder = c.node(1190, 780, 170, 120, "evidence", "What found it", "103 of 175 have no record", target=True)
c.arrow(finding, item, "flow")
c.arrow(item, fix, "flow")
c.arrow(fix, sibling, "flow")
c.arrow(item, finder, "feedback", "record the sensor", ports=("bottom", "bottom"), via=((470, 935), (1275, 935)),
        label_at=0.5, target=True)

# Sensors on the change return their findings to the change; the repository sensors produce findings.
c.arrow(review, change, "feedback", "the change sensors block or return findings to the branch · secret hits: 8, all fixtures",
        ports=("bottom", "bottom"), via=((900, 262), (135, 262)), label_at=0.5, label_dy=-12)
c.arrow(dep, (180, 780), "flow", "44 of 175 from a scanner or alert", ports=("bottom", None), label_at=0.5)
c.arrow(audit, (480, 780), "flow", "25 of 175 from an audit", ports=("bottom", None), label_at=0.3)
c.arrow(deploy, (560, 780), "flow", ports=("bottom", None), via=((820, 670), (560, 670)), target=True)

c.legend(60, 970, kinds=("check", "agent", "record", "evidence"), target=True, cols=5, cell=250)

S.finish(
    c, id="5.1", name="diagram-05-01-security-checking",
    caption="Most sensors sit on the change, but the flaws that mattered were found late by an audit run by hand, "
            "and three of five checks still run only on a laptop or not at all.",
    alt="Three lanes: sensors on a change before merge (secret scan, CI scans, security review, auto-approve), "
        "sensors on the whole repository (Dependabot, security audit, and two proposed deployment and exposure "
        "checks drawn dashed), and the path from a finding to a work item, a fix and a message to sibling "
        "repositories, with a proposed feedback arrow recording which sensor found it.",
    source="Replaces D29 WHERE SECURITY IS CHECKED. Scanner coverage (secret scan 14 of 15, CI 5, saga none; dependency "
           "scan in CI 10; image scan 8 of 12; Dependabot 14): .analysis/data/security.sqlite snap, week 2026-W39, "
           "and Q scanner-coverage. Secret hits (8, all fixtures): security.sqlite secret_hits. Auto-approve callers: "
           ".analysis/data/mirrors. Review pass and audit: skills/wayfare-review-pr and skills/wayfare-audit-security "
           "descriptions; audit run by hand inside sync-plan: Q audit-frequency. Finders (44 scanner, 25 audit, 2 "
           "review, 103 unrecorded of 175): Q security-finders. Flaw lifetime (median 32 days, 24 agent-written, 58 "
           "of 92 shipped): Q agent-security-defects. Items (203 of 322 same day, median 0): Q security-fix-time. "
           "Dependabot PRs (593, 325 closed unmerged): chapter 5. Propagation (91 of 114 within a day): chapter 5. "
           "Infrastructure risks (71, none with a live check): Q infra-security-risks. Semgrep on push and the daily "
           "image scan: hero-template's security-scan.yaml and image-scan.yaml.",
)
