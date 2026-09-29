"""1.5 The fleet and its repository types: the 15 repositories of six kinds, and the edges a change travels."""
import os
import sqlite3
from datetime import date

import svg_lib as S

DATA = os.path.join(S.ROOT, ".analysis", "data")
# Which apps deploy on merge: report/deployment/data.py DEPLOYED_APPS (deploy workflows in ci_runs).
DEPLOYED = ["auth", "design-system", "elevate-commons", "website"]
# Owner's answers in CHAPTER_BRIEF.md: hiro was deprecated when its platform was retired; the five -design
# repos were replaced by Claude Design projects (MILESTONES, 16 Aug).
HIRO_RETIRED, DESIGN_REPOS_REMOVED = "2026-08-21", "2026-08-16"


def first_commits():
    con = sqlite3.connect(os.path.join(DATA, "git.sqlite"))
    out = {r[0]: (r[1][:10], r[2][:10], r[3]) for r in con.execute(
        "SELECT repo, first_commit_ts, last_commit_ts, role FROM repos")}
    con.close()
    return out


def d(iso):
    return date.fromisoformat(iso).strftime("%-d %b %Y")


repos = first_commits()
fleet = [r for r, (_, _, role) in repos.items() if role != "design source"]
assert len(fleet) == 15, fleet
design_repos = [r for r in repos if r not in fleet]
since = lambda r: f"since {d(repos[r][0])}"

c = S.Canvas(1400, 1360)

# Key, top-left, outside the fleet boundary.
c.legend(56, 60, kinds=("record", "delivery", "policy", "agent"), arrows=("flow", "dependency"), cols=3, cell=230)
c.text(56, 140, "Record: a repository. Delivery: a shared service the other apps run on. Policy: the template. "
       "Agent: the plugin, the process every repository runs. Flow: what one repository gives another. "
       "Dependency: what one repository relies on.", size=S.SMALL, color=S.BODY, width=860)

# Design sources sit outside the repository count.
c.group(1000, 40, 360, 226, "Design sources · not counted")
design_now = c.node(1020, 76, 320, 78, "record", "Claude Design projects",
                    f"since {d(DESIGN_REPOS_REMOVED)}, read through a tool")
c.node(1020, 168, 320, 78, "record", "-design repositories",
       f"{len(design_repos)} repos, retired {d(DESIGN_REPOS_REMOVED)}")

fleet_box = c.group(40, 280, 1320, 1020, "The fleet · 15 repositories of six kinds")

c.group(120, 330, 860, 130, "Factory plugin")
plugin = c.node(140, 362, 820, 80, "agent", "wayfare-skills",
                f"process: the skills, hooks, review agents and auto-approve workflow every repository runs · "
                f"{since('wayfare-skills')}")

shared = c.group(120, 640, 440, 360, "Shared services · applications too")
auth = c.node(140, 700, 400, 110, "delivery", "auth", f"every product signs in here · {since('auth')}")
ds = c.node(140, 850, 400, 110, "delivery", "design-system", f"components for every app · {since('design-system')}")

infra = c.group(120, 1040, 440, 230, "Infrastructure")
env = c.node(140, 1078, 400, 96, "record", "infrastructure-environments",
             f"{since('infrastructure-environments')} · deploys {', '.join(DEPLOYED)} on merge")
c.node(140, 1194, 400, 56, "record", "infrastructure-root", since("infrastructure-root"))

c.group(660, 500, 340, 120, "Template")
template = c.node(680, 536, 300, 60, "policy", "hero-template", since("hero-template"))

apps = c.group(660, 680, 700, 580, "Applications · what the factory builds")
products = [
    ("website", f"before the template · {since('website')}"),
    ("saga", f"before the template · stopped {d(repos['saga'][1])}"),
    ("hiro", f"before the template · retired {d(HIRO_RETIRED)}"),
    ("elevate-commons", f"from the template · {since('elevate-commons')}"),
    ("aihero-wayfare", f"from the template · {since('aihero-wayfare')}"),
    ("aihero-steadfast", f"from the template · {since('aihero-steadfast')}"),
]
for i, (name, sub) in enumerate(products):
    c.node(680 + (i // 3) * 340, 720 + (i % 3) * 106, 300, 80, "record", name, sub)

c.group(680, 1090, 660, 140, "No feature work yet")
for i, name in enumerate(("ah-cozy", "aihero-dokyu", "aihero-mehr")):
    c.node(700 + i * 213, 1128, 194, 64, "record", name, f"cloned {d(repos[name][0])}")

# Process: the plugin's skills and workflows run in every repository.
c.arrow((340, 442), (340, 640), "flow", "process")
c.arrow((830, 442), (830, 500), "flow", "process", label_dy=4)
c.arrow((960, 402), (1060, 680), "flow", "process", via=((1060, 402),), label_at=0.5)
# Template: the clones start from it.
c.arrow((830, 596), (830, 680), "flow", "template")
# Runtime: every product signs in through auth and takes components from design-system.
c.arrow((540, 755), (660, 755), "dependency", "runtime")
c.arrow((540, 905), (660, 905), "dependency", "runtime")
# Delivery: infrastructure-environments deploys the four apps that deploy on merge.
c.arrow((340, 1078), (340, 1000), "flow", "delivery")
c.arrow((540, 1126), (660, 1050), "flow", "delivery", via=((610, 1126), (610, 1050)), label_at=0.5)
# Design: applications are designed outside the repositories and read through a tool.
c.arrow((1180, 266), (1180, 680), "dependency", "design")

S.finish(
    c, id="1.5", name="diagram-01-05-fleet-map",
    caption="The fleet is fifteen repositories of six kinds, and a change in one of them travels along five kinds "
            "of edge: process from the plugin, template into the clones, runtime through the two shared services, "
            "delivery from infrastructure, and design from sources that sit outside the repository count.",
    alt="A map of the fleet: a factory plugin band across the top, shared services auth and design-system on the "
        "left, the template and nine applications on the right, three of them with no feature work yet, and "
        "infrastructure at the bottom. Design sources sit outside the fleet boundary. Arrows are labelled process, "
        "template, runtime, delivery and design.",
    source="D16 THE FLEET; D17 THE FLEET · KINDS OF REPO. Roster, roles and first and last commits: "
           ".analysis/data/git.sqlite repos (15 fleet repos plus 5 design sources); categories: "
           "ingest/fleet.py category_of with .analysis/config.json; groups and ports: ~/workspaces/aihero/FLEET.md. "
           "Deployed apps: report/deployment/data.py DEPLOYED_APPS. hiro retired 21 Aug 2026 and saga's last commit "
           "29 Aug 2026: owner's answers in CHAPTER_BRIEF.md and git.sqlite repos.last_commit_ts. Design repos "
           "removed 16 Aug 2026: deck_lib.MILESTONES.",
)
