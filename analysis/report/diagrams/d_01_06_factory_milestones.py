"""1.6 Factory capability milestones and the missing trigger: when each capability was introduced in the plugin,
first used by a repository and used by half the fleet, and the trigger that is still missing."""
import ast
import os
import sqlite3
from datetime import date

import svg_lib as S



def milestones():
    """deck_lib.MILESTONES read from the source: importing deck_lib needs python-pptx, which the system python lacks."""
    src = open(os.path.join(S.ROOT, "analysis", "report", "deck_lib.py"), encoding="utf-8").read()
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "MILESTONES":
            return ast.literal_eval(node.value)
    raise KeyError("MILESTONES")


MILESTONES = milestones()

DATA = os.path.join(S.ROOT, ".analysis", "data")
FLEET = 15
HALF = 8
START, END = date(2026, 3, 1), date(2026, 9, 30)
X0, X1 = 430, 1160
# The register's first recorded version predates the plugin's engine (13 Sep, bc49826); the capability
# dates from the template's register, so its introduction comes from knowledge.register_history, not MILESTONES.


def q(db, sql):
    con = sqlite3.connect(os.path.join(DATA, db))
    rows = con.execute(sql).fetchall()
    con.close()
    return rows


def first_file(path_like):
    return {r[0]: r[1] for r in q("git.sqlite", f"""
        SELECT c.repo, MIN(c.day) FROM commit_files f JOIN commits c ON c.repo = f.repo AND c.sha = f.sha
        JOIN repos r ON r.repo = c.repo WHERE f.path LIKE '{path_like}' AND r.role != 'design source'
        GROUP BY c.repo""")}


hero = first_file("HERO.md")
approve = first_file(".github/workflows/auto-approve.y%")
items = {r[0]: r[1] for r in q("plans.sqlite", "SELECT repo, MIN(day) FROM plan_items WHERE type != 'goal' AND day IS NOT NULL GROUP BY repo")}
goals = {r[0]: r[1] for r in q("plans.sqlite", "SELECT repo, MIN(day) FROM plan_items WHERE type = 'goal' AND day IS NOT NULL GROUP BY repo")}
msgs = {}
for a, b, d in q("plans.sqlite", "SELECT from_repo, to_repo, SUBSTR(created_ts, 1, 10) FROM messages"):
    for r in (a, b):
        r = {"hero-skills": "wayfare-skills"}.get(r, r)  # the plugin's name before 21 Sep (config repo_aliases)
        if r and d < msgs.get(r, "9999"):
            msgs[r] = d
register_first = q("knowledge.sqlite", "SELECT MIN(SUBSTR(ts, 1, 10)) FROM register_history")[0][0]
design_last = q("git.sqlite", "SELECT MIN(SUBSTR(last_commit_ts, 1, 10)), MAX(SUBSTR(last_commit_ts, 1, 10)) "
                              "FROM repos WHERE role = 'design source'")[0]
assert len(hero) == FLEET, hero


def x_of(iso):
    return X0 + (date.fromisoformat(iso) - START).days / (END - START).days * (X1 - X0)


def d(iso):
    return date.fromisoformat(iso).strftime("%-d %b")


def spread(dates):
    """(first repo, the day the 8th repo adopted or None, repos adopted by the end)."""
    s = sorted(dates.values())
    return s[0], (s[HALF - 1] if len(s) >= HALF else None), len(s)


ms = {m[1]: m[0] for m in MILESTONES}
rows = [
    ("Skills and HERO.md", ms["Skills"], hero),
    ("Review loop: reviewer agents, auto-approve", ms["Review loop"], approve),
    ("Work items", ms["Work items"], items),
    (".plans store and roadmap", ms[".plans + roadmap"], "items"),
    ("Register of rules", register_first, "fleet"),
    ("Design repos removed for Claude Design", ms["Design repos removed"], "design"),
    ("Goals", ms["Goals"], goals),
    ("Messages between repositories", ms["Messages"], msgs),
    ("One branch, one PR, a commit per feature", ms["1 commit per feature"], None),
]

c = S.Canvas(1400, 1080)

# Key for the markers.
kx, ky = 430, 52
c.circle(kx, ky, 9, S.PINK)
c.text(kx + 20, ky - 10, "introduced in the plugin", size=S.SMALL, color=S.BODY)
c.circle(kx + 250, ky, 7, S.INK)
c.text(kx + 270, ky - 10, "first repository", size=S.SMALL, color=S.BODY)
c.circle(kx + 440, ky, 9, "#FFFFFF", S.INK, 2)
c.text(kx + 460, ky - 10, f"half the fleet ({HALF} of {FLEET})", size=S.SMALL, color=S.BODY)
c.text(X1 + 16, ky - 10, "n of 15: repositories using it by the end of September", size=S.SMALL, color=S.BODY, width=190)

# Axis with month ticks.
AY = 110
c.line(X0, AY, X1, AY, S.GREY_DARK, 1.5)
for m in range(3, 10):
    x = x_of(f"2026-{m:02d}-01")
    c.line(x, AY - 6, x, AY + 6, S.GREY_DARK, 1.5)
    c.text(x + 6, AY - 30, date(2026, m, 1).strftime("%b 2026" if m == 3 else "%b"), size=S.SMALL, color=S.BODY)

ROW0, ROWH = 150, 78
for i, (name, intro, adopt) in enumerate(rows):
    y = ROW0 + i * ROWH
    cy = y + 30
    c.line(X0, y + ROWH - 8, 1360, y + ROWH - 8, S.RULE, 1)
    c.text(40, y + 8, name, size=S.LABEL, color=S.INK, width=370)
    xi = x_of(intro)
    note, unresolved = None, False
    if isinstance(adopt, dict):
        first, half, n = spread(adopt)
        xf = x_of(first)
        c.line(min(xi, xf), cy, x_of(half) if half else max(xi, xf), cy, S.GREY, 3)
        c.text(xf, cy + 14, d(first), size=S.SMALL, anchor="middle", color=S.BODY, halo=True)
        if half:
            xh = x_of(half)
            c.circle(xh, cy, 9, "#FFFFFF", S.INK, 2)
            c.text(xh, cy + 14, d(half), size=S.SMALL, anchor="middle", color=S.BODY, halo=True)
        note = f"{n} of {FLEET}"
    elif adopt == "items":
        note = "same records as work items"
    elif adopt == "fleet":
        note = "fleet-wide; engine in the plugin 13 Sep"
    elif adopt == "design":
        note = f"5 repos, last commits {d(design_last[0])} to {d(design_last[1])}"
    else:
        note, unresolved = "adoption not measured", True
    c.circle(xi, cy, 9, S.PINK)
    if isinstance(adopt, dict):
        c.circle(x_of(spread(adopt)[0]), cy, 7, S.INK)  # on top: it often falls within days of the introduction
    c.text(xi, cy - 30, d(intro), size=S.SMALL, anchor="middle", color=S.PINK_DARK, halo=True)
    c.text(X1 + 16, cy - 10, note, size=S.SMALL, color=S.MUTED if unresolved else S.BODY, width=190)

# The missing trigger: today the owner starts every session; a trigger would start or resume work.
TY = ROW0 + len(rows) * ROWH + 40
c.text(40, TY, "What still starts the work", size=S.LABEL, color=S.INK)
owner = c.node(40, TY + 44, 280, 90, "person", "The owner", "starts every session")
work = c.node(500, TY + 44, 320, 90, "record", "Authorized work", "work items and goals in .plans")
trigger = c.node(1040, TY + 44, 320, 90, "agent", "A trigger", "an event, schedule, alert or message", target=True)
c.arrow(owner, work, "authority", "starts and resumes")
c.arrow(trigger, work, "flow", "would start or resume", target=True)

S.finish(
    c, id="1.6", name="diagram-01-06-factory-milestones",
    caption="Each capability took weeks to months to go from the plugin commit that introduced it to half the "
            "fleet, goals and messages never got that far by the end of September, and the trigger that would "
            "start work without the owner is still not built.",
    alt="A horizontal timeline from March to September 2026 with nine rows, one per factory capability. Each row "
        "marks the plugin commit that introduced it, the first repository that used it and, where reached, the "
        "day half the fleet used it, with the number of repositories using it by the end. Below, the owner starts "
        "authorized work today; a dashed trigger that would start or resume it is proposed, not built.",
    source="D18 THE FACTORY · MILESTONES; D19 WHERE IT STANDS · THE FIVE STEPS IN THIS FLEET. Introduction dates: "
           "deck_lib.MILESTONES (wayfare-skills commits); register: first version in "
           ".analysis/data/knowledge.sqlite register_history. First-repository and half-fleet dates: first commit "
           "of HERO.md and of .github/workflows/auto-approve.y* per repo (git.sqlite commit_files), first work "
           "item and goal per repo (plans.sqlite plan_items), first message per repo (plans.sqlite messages); "
           "design repos' last commits: git.sqlite repos. The trigger: Chapter 1, 'The missing part is the trigger'.",
)
