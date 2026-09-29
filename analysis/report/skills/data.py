"""Skills and factory evolution series: skills and factory evolution. One function per question.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/skills/data.py [q_skill_set_history q_factory_work_per_week ...]

Each q_<slug>(con) returns what that question's answer slide (and breakdown slide) plots.
Weeks run 2026-W01..W39; the plugin's history comes from its own git log (gitwalk),
invocations from harness.prompts (typed, Nov 2025 →) and harness.tool_calls (agent, 9 Aug →).
"""
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import gitwalk as G  # noqa: E402
import lineage as LN  # noqa: E402
from record import adoption, changeset_facts, rows, stage_of, week_of  # noqa: E402
from cube.db import connect  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE, REPO_ALIASES, category_of  # noqa: E402

WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
PLUGIN = G.PLUGIN
SESSIONS_FROM = "2026-08-09"
TODAY = "2026-09-24"


def con_():
    return connect("skills")


def wk_days(week):
    end = G.week_end(week)
    return end - timedelta(6), end


def share(a, b):
    return a / b if b else None


def median(v):
    return statistics.median(v) if v else None


# ---------------------------------------------------------------- plugin snapshots

@lru_cache(maxsize=None)
def plugin_tree(day):
    sha = G.sha_at(PLUGIN, day)
    return (sha, G.tree(PLUGIN, sha)) if sha else (None, {})


def skill_dirs(tree):
    return sorted({p.split("/")[1] for p in tree if p.startswith("skills/") and p.endswith("/SKILL.md")
                   and p.count("/") == 2})


def week_snapshots():
    """{week: (sha, tree)} for each week's last day, from the plugin's first commit."""
    out = {}
    for w in WEEKS:
        end = min(G.week_end(w), date.fromisoformat(TODAY)).isoformat()
        sha, t = plugin_tree(end)
        out[w] = (sha, t)
    return out


# ---------------------------------------------------------------- Q skill-set-history skills over time

def skill_events():
    """[(day, kind, old, new)] adds, renames and deletes of skills/*/SKILL.md on main."""
    out = G.git(PLUGIN, "log", "--first-parent", "--reverse", "-M30", "--name-status", "--format=@@%cs",
                "--", "skills/*/SKILL.md")
    ev, day = [], None
    for line in out.splitlines():
        if line.startswith("@@"):
            day = line[2:]
            continue
        parts = line.split("\t")
        if len(parts) < 2 or not re.fullmatch(r"skills/[^/]+/SKILL\.md", parts[-1]):
            continue
        name = lambda p: p.split("/")[1]
        k = parts[0][0]
        if k == "R":
            ev.append((day, "rename", name(parts[1]), name(parts[2])))
        elif k == "A":
            ev.append((day, "add", None, name(parts[1])))
        elif k == "D":
            ev.append((day, "delete", name(parts[1]), None))
    return ev


def q_skill_set_history(con):
    snaps = week_snapshots()
    live = [len(skill_dirs(t)) if sha else None for w, (sha, t) in snaps.items()]
    ev = skill_events()
    per = {k: [0] * len(WEEKS) for k in ("Added", "Renamed", "Retired")}
    kind = {"add": "Added", "rename": "Renamed", "delete": "Retired"}
    for d, k, _, _ in ev:
        w = week_of(d)
        if w in WEEKS:
            per[kind[k]][WEEKS.index(w)] += 1
    names = set()
    for d, k, old, new in ev:
        names.update(n for n in (old, new) if n)
    now = skill_dirs(plugin_tree(TODAY)[1])
    # a name that is not a current dir was renamed away or retired
    renamed_away = {old for _, k, old, _ in ev if k == "rename"}
    retired = {old for _, k, old, _ in ev if k == "delete"} - renamed_away
    lineage = {cur: sorted({o for o in LN.CURRENT.get(cur, []) if o in names}) for cur in now}
    peak_i = max(range(len(live)), key=lambda i: live[i] or 0)
    return {"weeks": WEEKS, "live": live, "events": per, "names_ever": len(names), "now": len(now),
            "renamed_away": len(renamed_away), "retired": len(retired - set(now)),
            "peak": live[peak_i], "peak_week": WEEKS[peak_i], "first": next(v for v in live if v),
            "lineage": lineage, "n_events": {k: sum(v) for k, v in per.items()},
            "waves": LN.WAVES}


# ---------------------------------------------------------------- Q factory-work-per-week the factory's own work

KINDS = ["Feature", "Fix", "Refactor", "Docs", "CI, build and tests", "Other upkeep"]
KIND_OF = {"feature": "Feature", "feat": "Feature", "fix": "Fix", "refactor": "Refactor", "docs": "Docs",
           "ci_build": "CI, build and tests", "test": "CI, build and tests"}
COMPONENTS = ["Skill instructions", "Shared references and docs", "Scripts", "Tests", "Auto-approve workflow",
              "Vendored assets", "Other"]


def component_of(path):
    base = path.rsplit("/", 1)[-1]
    if base.endswith(".test.sh") or base.endswith("_test.py") or base.startswith("test_"):
        return "Tests"
    if path.startswith("skills/"):
        return "Skill instructions"
    if path.startswith(("references/", "docs/")) or path in ("README.md", "AGENTS.md", "CLAUDE.md", "DESIGN.md",
                                                            "HERO.md"):
        return "Shared references and docs"
    if path.startswith("scripts/"):
        return "Scripts"
    if path.startswith(".github/workflows/auto-approve") or path.startswith(".github/workflows/pr-auto-approv"):
        return "Auto-approve workflow"
    if path.startswith("assets/"):
        return "Vendored assets"
    return "Other"


@lru_cache(maxsize=None)
def plugin_changesets(con):
    """The plugin's change sets with work type (cs_worktype) and the files their commits touched."""
    wt = {(r["unit_kind"], r["unit_id"], r["set_idx"]): r for r in rows(con, """
        SELECT unit_kind, unit_id, set_idx, work_type, theme FROM detectors.cs_worktype WHERE repo = 'wayfare-skills'""")}
    files = defaultdict(list)
    for r in rows(con, "SELECT sha, files_json FROM pr_commits.pr_commits WHERE repo = 'wayfare-skills'"):
        files[r["sha"]] = [f["path"] for f in json.loads(r["files_json"] or "[]")]
    for r in rows(con, "SELECT sha, path FROM git.commit_files WHERE repo = 'wayfare-skills'"):
        if r["sha"] not in files or not files[r["sha"]]:
            files.setdefault(r["sha"], []).append(r["path"])
    main = {r["pr_number"]: r["sha"] for r in rows(con, "SELECT pr_number, sha FROM git.commits WHERE repo='wayfare-skills' "
                                                         "AND pr_number IS NOT NULL")}
    out = []
    for f in changeset_facts(con):
        if f["repo"] != "wayfare-skills":
            continue
        w = wt.get((f["unit_kind"], f["unit_id"], f["set_idx"]), {})
        paths = sorted({p for s in f["shas"] for p in files.get(s, [])})
        main_sha = main.get(f["pr"]) if f["pr"] else (f["shas"][0] if f["shas"] else None)
        out.append({**f, "work_type": w.get("work_type"), "kind": KIND_OF.get(w.get("work_type"), "Other upkeep"),
                    "theme": w.get("theme"), "paths": paths,
                    "components": sorted({component_of(p) for p in paths}) or ["Other"], "main_sha": main_sha})
    return out


CAPABILITIES = [
    ("Skills plugin", "skills/"), ("Tests for the plugin's scripts", "scripts/*.test.sh"),
    ("Auto-approve workflow", ".github/workflows/*approve*"),
    ("Self-review skill", "skills/hero-self-review/SKILL.md"), ("One-shot pipeline", "skills/one-shot/SKILL.md"),
    ("Grill an idea", "skills/relentless/SKILL.md"), ("Work-item store (.plans)", "skills/wayfare/SKILL.md"),
    ("Architecture record skill", "skills/architecture/SKILL.md"), ("Fleet map (FLEET.md)", "docs/FLEET-MD.md"),
    ("Compliance register", "assets/compliance/CONTROLS.yaml"), ("Cross-repo mailbox", "grep:bug reports in the mailbox"),
    ("Plan standard, schema 1", "docs/PLAN.md"), ("Recalibrate verb", "docs/RECALIBRATE.md"),
    ("Connections", "docs/CONNECTIONS.md"),
]


def q_factory_work_per_week(con):
    cs = plugin_changesets(con)
    series = {k: [0] * len(WEEKS) for k in KINDS}
    for c in cs:
        if c["week"] in WEEKS:
            series[c["kind"]][WEEKS.index(c["week"])] += 1
    comp = {k: [0.0] * len(MONTHS) for k in COMPONENTS}
    comp_total = Counter()
    for c in cs:
        if c["month"] in MONTHS:
            for k in c["components"]:
                comp[k][MONTHS.index(c["month"])] += 1 / len(c["components"])
                comp_total[k] += 1 / len(c["components"])
    caps = []
    for name, path in CAPABILITIES:
        if path.startswith("grep:"):
            out = G.git(PLUGIN, "log", "--first-parent", "--reverse", "--format=%cs\t%h\t%s", f"--grep={path[5:]}")
        else:
            out = G.git(PLUGIN, "log", "--first-parent", "--reverse", "--format=%cs\t%h\t%s", "--", path)
        if out.strip():
            d, h, s = out.splitlines()[0].split("\t", 2)
            caps.append((d, name, h, s[:70]))
    kinds = Counter(c["kind"] for c in cs)
    by_month = Counter(c["month"] for c in cs)
    sep = [c for c in cs if c["month"] == "2026-09"]
    return {"weeks": WEEKS, "series": series, "n": len(cs), "kinds": dict(kinds), "months": MONTHS,
            "components": {k: [round(v, 1) for v in comp[k]] for k in COMPONENTS},
            "component_total": {k: round(v, 1) for k, v in comp_total.most_common()},
            "by_month": dict(by_month), "sep_share": share(len(sep), len(cs)),
            "fix_share": share(kinds["Fix"], len(cs)), "feature_share": share(kinds["Feature"], len(cs)),
            "capabilities": sorted(caps),
            "sep_fix_share": share(sum(1 for c in sep if c["kind"] == "Fix"), len(sep))}


# ---------------------------------------------------------------- Q plugin-follow-up-fixes the plugin's follow-up fixes

LIFE = ["Same day", "1–3 days", "4–14 days", "15+ days", "Inside its own PR", "No traceable origin"]


def life_bucket(t):
    d = t["life"]
    if d is None:
        return LIFE[4] if t["origin"] == "own PR" else LIFE[5]
    return LIFE[0] if d == 0 else LIFE[1] if d <= 3 else LIFE[2] if d <= 14 else LIFE[3]


def q_plugin_follow_up_fixes(con):
    cs = plugin_changesets(con)
    fixes = [c for c in cs if c["kind"] == "Fix"]
    day_of = {}
    for line in G.git(PLUGIN, "log", "--format=%H\t%cs").splitlines():
        h, d = line.split("\t")
        day_of[h] = d
    first_parent = set(G.git(PLUGIN, "rev-list", "--first-parent", "HEAD").split())
    subj = dict(l.split("\t", 1) for l in G.git(PLUGIN, "log", "--format=%H\t%s").splitlines())
    mirror = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), ".analysis", "data", "mirrors",
                          "wayfare-skills.git")
    pr_of = {r["sha"]: r["pr_number"] for r in rows(con, "SELECT sha, pr_number FROM pr_commits.pr_commits "
                                                         "WHERE repo = 'wayfare-skills'")}
    merged = {r["pr_number"]: r["day"] for r in rows(con, "SELECT pr_number, day FROM git.commits "
                                                          "WHERE repo = 'wayfare-skills' AND pr_number IS NOT NULL")}

    def landed(origin):
        """(unit, day the origin line landed on main)."""
        if origin in pr_of:
            return ("pr", pr_of[origin]), merged.get(pr_of[origin])
        return ("main", origin), day_of.get(origin)

    traced, cache = [], {}
    for c in fixes:
        own = ("pr", c["pr"]) if c["pr"] else ("pr", pr_of[c["shas"][0]]) if c["shas"] and c["shas"][0] in pr_of else None
        origins = Counter()
        if c["unit_kind"] == "pr":
            for sha in c["shas"]:
                if sha not in cache:
                    cache[sha] = G.blame_origins(mirror, sha)
                origins.update(cache[sha])
        else:
            sha = c["main_sha"]
            if sha:
                if sha not in cache:
                    cache[sha] = G.blame_origins(PLUGIN, sha)
                origins.update(cache[sha])
        by_unit = Counter()
        land = {}
        in_pr = 0
        for o, n in origins.items():
            u, d = landed(o)
            if u == own or o in c["shas"]:
                in_pr += n
                continue
            if not d:
                continue
            by_unit[u] += n
            land[u] = d
        if not by_unit or in_pr > sum(by_unit.values()):
            traced.append({**c, "origin": "own PR" if in_pr else None, "life": None})
            continue
        top = max(by_unit, key=by_unit.get)
        life = (date.fromisoformat(c["day"]) - date.fromisoformat(land[top])).days
        label = f"#{top[1]}" if top[0] == "pr" else subj.get(top[1], "")[:60]
        traced.append({**c, "origin": top, "origin_subject": label, "life": max(life, 0), "origin_day": land[top]})
    by = defaultdict(Counter)
    for c in cs:
        by[c["week"]]["fix" if c["kind"] == "Fix" else "other"] += 1
    fix_share = [share(by[w]["fix"], by[w]["fix"] + by[w]["other"]) if by[w] else None for w in WEEKS]
    counts = {"Fix change sets": [by[w]["fix"] for w in WEEKS], "Other change sets": [by[w]["other"] for w in WEEKS]}
    life_m = {b: [0] * len(MONTHS) for b in LIFE}
    for t in traced:
        if t["month"] in MONTHS:
            life_m[life_bucket(t)][MONTHS.index(t["month"])] += 1
    lives = [t["life"] for t in traced if t["life"] is not None]
    med_m = {}
    for m in MONTHS:
        v = [t["life"] for t in traced if t["life"] is not None and t["month"] == m]
        med_m[m] = median(v)
    within3 = sum(1 for v in lives if v <= 3)
    buckets = Counter(life_bucket(t) for t in traced)
    # fixes to the auto-approve workflow, which ~25 repos call at @main
    aa = [t for t in traced if "Auto-approve workflow" in t["components"]]
    msgs = rows(con, "SELECT from_repo, created_ts, subject FROM plans.messages WHERE to_repo IN ('hero-skills', 'wayfare-skills', 'wayfare')")
    return {"weeks": WEEKS, "fix_share": fix_share, "counts": counts, "n_cs": len(cs), "n_fix": len(fixes),
            "fix_share_all": share(len(fixes), len(cs)), "life_by_month": life_m, "median_by_month": med_m,
            "n_traced": len(lives), "median_life": median(lives), "within3": within3,
            "within3_share": share(within3, len(lives)), "months": MONTHS,
            "auto_approve_fixes": len(aa), "buckets": dict(buckets), "downstream_messages": msgs,
            "examples": [(t["day"], t["label"][:70], t.get("origin_subject"), t["life"]) for t in traced
                         if t["life"] is not None][-12:]}


# ---------------------------------------------------------------- Q scripted-step-share scripted share of steps

def skill_of_path(p):
    if p.startswith("references/"):
        return "shared references"
    parts = p.split("/")
    return LN.OLD_TO_CURRENT.get(parts[1], parts[1]) if len(parts) > 2 else p


def q_scripted_step_share(con):
    tables = {r[0] for r in con.execute("SELECT name FROM skills.sqlite_master WHERE type='table'")}
    if "step_index" not in tables:
        return None
    lab = {r["h"]: r for r in rows(con, "SELECT h, kind, mode FROM skills.step_cache")}
    idx = rows(con, "SELECT day, path, h FROM skills.step_index")
    snaps = sorted({r["day"] for r in idx})
    score = {"scripted": 1.0, "mixed": 0.5, "judgement": 0.0}
    by_day = defaultdict(Counter)
    per_skill = defaultdict(lambda: defaultdict(list))
    files = defaultdict(set)
    unlabelled = 0
    for r in idx:
        l = lab.get(r["h"])
        if not l:
            unlabelled += 1
            continue
        if l["kind"] != "step" or l["mode"] not in score:
            continue
        by_day[r["day"]][l["mode"]] += 1
        per_skill[r["day"]][skill_of_path(r["path"])].append(score[l["mode"]])
        files[r["day"]].add(r["path"])
    month_of = {d: d[:7] for d in snaps}
    series = {"Scripted": [None] * len(MONTHS), "Mixed": [None] * len(MONTHS), "Judgement": [None] * len(MONTHS)}
    shares = {}
    for d in snaps:
        c = by_day[d]
        n = sum(c.values())
        i = MONTHS.index(month_of[d])
        series["Scripted"][i] = share(c["scripted"], n)
        series["Mixed"][i] = share(c["mixed"], n)
        series["Judgement"][i] = share(c["judgement"], n)
        shares[d] = share(c["scripted"] + 0.5 * c["mixed"], n)
    last, first = snaps[-1], snaps[0]
    per_now = sorted(((k, statistics.mean(v)) for k, v in per_skill[last].items()), key=lambda kv: -kv[1])
    return {"months_plot": MONTHS, "series": series, "shares": shares, "first_share": shares[first],
            "last_share": shares[last], "last_judgement": series["Judgement"][MONTHS.index(last[:7])],
            "first_scripted": series["Scripted"][MONTHS.index(first[:7])],
            "last_scripted": series["Scripted"][MONTHS.index(last[:7])],
            "n_steps_now": sum(by_day[last].values()), "n_steps_first": sum(by_day[first].values()),
            "n_files_now": len(files[last]), "per_skill_now": per_now, "top_now": per_now[:5],
            "skills_all_judgement": sum(1 for _, v in per_now if v == 0), "counts": {d: dict(by_day[d]) for d in snaps},
            "unlabelled": unlabelled, "snapshots": snaps}


# ---------------------------------------------------------------- Q plugin-change-triggers what sets off a plugin change

TRIGGERS = ["owner_feedback", "downstream_report", "review_or_audit", "planned", "unknown"]
TRIGGER_NAMES = {"owner_feedback": "Owner's feedback", "downstream_report": "Report from a fleet repo",
                 "review_or_audit": "Review, audit or test", "planned": "Planned work", "unknown": "Unknown"}


def q_plugin_change_triggers(con):
    tables = {r[0] for r in con.execute("SELECT name FROM skills.sqlite_master WHERE type='table'")}
    if "trigger_index" not in tables:
        return None
    lab = {r["h"]: r for r in rows(con, "SELECT h, trigger, evidence FROM skills.trigger_cache")}
    day_pr = {r["number"]: r["day"] for r in rows(con, "SELECT number, day FROM github.prs WHERE repo='wayfare-skills' "
                                                       "AND merged_ts IS NOT NULL")}
    day_c = {r["sha"]: r["day"] for r in rows(con, "SELECT sha, day FROM git.commits WHERE repo='wayfare-skills'")}
    units = []
    for r in rows(con, "SELECT unit, h FROM skills.trigger_index"):
        kind, key = r["unit"].split(":", 1)
        day = day_pr.get(int(key)) if kind == "pr" else day_c.get(key)
        l = lab.get(r["h"])
        t = l["trigger"] if l and l["trigger"] in TRIGGERS else "unknown"
        units.append({"unit": r["unit"], "day": day, "month": (day or "")[:7], "trigger": t,
                      "evidence": l["evidence"] if l else ""})
    monthly = {TRIGGER_NAMES[t]: [sum(1 for u in units if u["month"] == m and u["trigger"] == t) for m in MONTHS]
               for t in TRIGGERS}
    tot = Counter(u["trigger"] for u in units)
    since = [u for u in units if u["day"] and u["day"] >= SESSIONS_FROM]
    tot_since = Counter(u["trigger"] for u in since)
    return {"monthly": monthly, "total": dict(tot), "n": len(units), "since": dict(tot_since), "n_since": len(since),
            "examples": {t: [(u["unit"], u["day"], u["evidence"]) for u in units if u["trigger"] == t][:5] for t in TRIGGERS}}


# ---------------------------------------------------------------- Q skill-prose-vs-scripts prose, scripts, tests

def classify_path(p):
    """prose the model follows / code / tests / None (not part of the procedure)."""
    if p.startswith(("analysis/", ".plans/", ".superpowers/", "docs/superpowers/", "memory/", ".claude/")):
        return None
    base = p.rsplit("/", 1)[-1]
    if base.endswith(".test.sh") or base.endswith("_test.py") or base.startswith("test_") or "/tests/" in p:
        return "tests"
    if p.endswith(".md") and p.startswith(("skills/", "references/", "docs/")):
        return "prose"
    if p.endswith((".sh", ".py", ".js", ".ts")) or (p.startswith(".github/workflows/") and p.endswith((".yaml", ".yml"))):
        return "code"
    return None


def lines_by_class(tree):
    ids = {p: b for p, b in tree.items() if classify_path(p)}
    text = G.blobs(PLUGIN, list(ids.values()))
    out = Counter()
    for p, b in ids.items():
        out[classify_path(p)] += text[b].count("\n")
    return out


def q_skill_prose_vs_scripts(con):
    snaps = week_snapshots()
    series = {"Prose the model follows": [], "Scripts and workflows": [], "Tests": []}
    for w in WEEKS:
        sha, t = snaps[w]
        c = lines_by_class(t) if sha else None
        series["Prose the model follows"].append(c["prose"] if c else None)
        series["Scripts and workflows"].append(c["code"] if c else None)
        series["Tests"].append(c["tests"] if c else None)
    # per current skill: SKILL.md lines at its first version (any ancestor name) vs now
    now_t = plugin_tree(TODAY)[1]
    first_lines = {}
    for cur, olds in LN.CURRENT.items():
        hist = []
        for n in [cur] + olds:
            for sha, d, _ in G.file_history(PLUGIN, f"skills/{n}/SKILL.md"):
                hist.append((d, sha, n))
        if not hist:
            continue
        d, sha, n = min(hist)
        blob = G.tree(PLUGIN, sha).get(f"skills/{n}/SKILL.md")
        if blob:
            first_lines[cur] = G.blobs(PLUGIN, [blob])[blob].count("\n")
    cur_lines = {p.split("/")[1]: G.blobs(PLUGIN, [b])[b].count("\n") for p, b in now_t.items()
                 if re.fullmatch(r"skills/[^/]+/SKILL\.md", p)}
    first_w = next(i for i, v in enumerate(series["Tests"]) if v is not None)
    return {"weeks": WEEKS, "series": series, "first_week": WEEKS[first_w],
            "first": {k: v[first_w] for k, v in series.items()}, "last": {k: v[-1] for k, v in series.items()},
            "skill_first": first_lines, "skill_now": cur_lines}


# ---------------------------------------------------------------- invocations (Q skill-run-frequency, Q who-starts-skills, Q old-skill-names, Q skill-use-by-repo)

@lru_cache(maxsize=None)
def invocations(con):
    """Every invocation of a wayfare skill: typed by the owner (prompts) or called by an agent (Skill tool)."""
    out = []
    for r in rows(con, "SELECT ts, day, repo, command FROM harness.prompts WHERE is_slash_command = 1"):
        cur, bare = LN.canonical(r["command"])
        if cur:
            out.append({"ts": r["ts"], "day": r["day"], "week": week_of(r["day"]), "month": r["day"][:7],
                        "repo": r["repo"], "who": "owner", "cur": cur, "typed": r["command"], "bare": bare,
                        "session": None})
    for r in rows(con, """SELECT t.ts, t.skill_name, t.session_id_hash, s.repo FROM harness.tool_calls t
                          LEFT JOIN harness.sessions s USING (session_id_hash) WHERE t.tool = 'Skill'"""):
        cur, bare = LN.canonical(r["skill_name"])
        if cur:
            d = r["ts"][:10]
            out.append({"ts": r["ts"], "day": d, "week": week_of(d), "month": d[:7], "repo": r["repo"],
                        "who": "agent", "cur": cur, "typed": r["skill_name"], "bare": bare,
                        "session": r["session_id_hash"]})
    return [o for o in out if o["repo"] not in OUT_OF_SCOPE]


def q_skill_run_frequency(con):
    inv = [i for i in invocations(con) if i["day"] >= "2026-01-01"]
    series = {f: [0] * len(WEEKS) for f in LN.FAMILIES}
    for i in inv:
        if i["week"] in WEEKS:
            series[LN.family(i["cur"])][WEEKS.index(i["week"])] += 1
    per_skill = Counter(i["cur"] for i in inv)
    total = sum(per_skill.values())
    top3 = per_skill.most_common(3)
    now = skill_dirs(plugin_tree(TODAY)[1])
    last60 = (date.fromisoformat(TODAY) - timedelta(60)).isoformat()
    used60 = {i["cur"] for i in inv if i["day"] >= last60}
    unused = [s for s in now if s not in used60]
    pipeline = sum(per_skill[s] for s in ("wayfare-push-pr", "wayfare-review-pr", "wayfare-ship-pr", "wayfare-respond-pr",
                                          "wayfare-build-task"))
    since = [i for i in inv if i["day"] >= SESSIONS_FROM]
    return {"weeks": WEEKS, "series": series, "per_skill": per_skill.most_common(), "total": total,
            "top3": top3, "top3_share": share(sum(v for _, v in top3), total), "unused60": unused,
            "pipeline_share": share(pipeline, total), "n_now": len(now),
            "since_sessions": len(since), "first_day": min(i["day"] for i in inv)}


def q_who_starts_skills(con):
    inv = [i for i in invocations(con) if i["day"] >= SESSIONS_FROM]
    by = defaultdict(Counter)
    for i in inv:
        by[i["week"]][i["who"]] += 1
    agent_share = [share(by[w]["agent"], by[w]["agent"] + by[w]["owner"]) if w in by and w >= week_of(SESSIONS_FROM)
                   else None for w in WEEKS]
    counts = {"Started by the owner": [by[w]["owner"] if w in by else 0 for w in WEEKS],
              "Started by an agent": [by[w]["agent"] if w in by else 0 for w in WEEKS]}
    per_skill = defaultdict(Counter)
    for i in inv:
        per_skill[i["cur"]][i["who"]] += 1
    # human-only: skills whose SKILL.md on that day disables model invocation
    flagged = []
    for i in inv:
        if i["who"] != "agent":
            continue
        t = plugin_tree(i["day"])[1]
        names = [i["bare"]] + ([i["cur"]] if i["cur"] != i["bare"] else [])
        for n in names:
            b = t.get(f"skills/{n}/SKILL.md")
            if b:
                head = G.blobs(PLUGIN, [b])[b].split("\n---", 1)[0]
                if re.search(r"disable-model-invocation:\s*true", head):
                    flagged.append((i["day"], n, "disable-model-invocation"))
                break
    tot = Counter(i["who"] for i in inv)
    return {"weeks": WEEKS, "agent_share": agent_share, "counts": counts,
            "per_skill": {k: dict(v) for k, v in sorted(per_skill.items(), key=lambda kv: -sum(kv[1].values()))},
            "total": dict(tot), "agent_share_all": share(tot["agent"], sum(tot.values())), "human_only_by_agent": flagged}


# ---------------------------------------------------------------- Q old-skill-names retired names

@lru_cache(maxsize=None)
def live_names():
    """{bare skill dir name: [(first day, last day live)]} from the plugin's history, daily."""
    ev = skill_events()
    alive, spans = {}, defaultdict(list)
    for d, k, old, new in ev:
        if old and old in alive:
            spans[old].append((alive.pop(old), d))
        if new:
            alive.setdefault(new, d)
    for n, d in alive.items():
        spans[n].append((d, None))
    return dict(spans)


def was_live(bare, day):
    return any(a <= day and (b is None or day < b) for a, b in live_names().get(bare, []))


def prefix_ok(typed, day):
    if ":" not in typed:
        return True
    p = typed.split(":", 1)[0]
    return (p == "hero-skills" and day < "2026-09-22") or (p == "wayfare" and day >= "2026-09-22")


def q_old_skill_names(con):
    typed = [i for i in invocations(con) if i["who"] == "owner" and i["day"] >= "2026-03-07"]
    for i in typed:
        i["retired"] = not (was_live(i["bare"], i["day"]) and prefix_ok(i["typed"], i["day"]))
    by = defaultdict(Counter)
    for i in typed:
        by[i["week"]]["retired" if i["retired"] else "ok"] += 1
    sh = [share(by[w]["retired"], by[w]["retired"] + by[w]["ok"]) if w in by else None for w in WEEKS]
    counts = {"Retired name": [by[w]["retired"] for w in WEEKS], "Live name": [by[w]["ok"] for w in WEEKS]}
    # per retired name: its retirement day and the last day it was typed after that
    lag = {}
    for i in typed:
        if not i["retired"]:
            continue
        key = i["typed"]
        spans = live_names().get(i["bare"], [])
        ended = max((b for a, b in spans if b and b <= i["day"]), default=None)
        if ":" in key and was_live(i["bare"], i["day"]):
            ended = "2026-09-22"
        rec = lag.setdefault(key, {"retired": ended, "last": i["day"], "n": 0})
        rec["last"] = max(rec["last"], i["day"])
        rec["n"] += 1
    for k, v in lag.items():
        v["days"] = (date.fromisoformat(v["last"]) - date.fromisoformat(v["retired"])).days if v["retired"] else None
    tot = Counter(i["retired"] for i in typed)
    return {"weeks": WEEKS, "share": sh, "counts": counts, "lag": dict(sorted(lag.items(), key=lambda kv: -kv[1]["n"])),
            "n_typed": len(typed), "n_retired": tot[True], "retired_share": share(tot[True], len(typed))}


# ---------------------------------------------------------------- Q skill-chain-completion chains

@lru_cache(maxsize=None)
def session_sequences(con):
    """{session: [(ts, current skill, who)]} from 9 Aug: typed commands from the transcript, agent Skill calls."""
    seq = defaultdict(list)
    for r in rows(con, """SELECT session_id_hash s, ts, text_redacted t FROM harness.turns
                          WHERE role = 'user' AND text_redacted LIKE '%<command-name>%'"""):
        m = re.search(r"<command-name>/?([^<]+)</command-name>", r["t"] or "")
        cur = LN.canonical(m.group(1))[0] if m else None
        if cur:
            seq[r["s"]].append((r["ts"], cur, "owner"))
    for i in invocations(con):
        if i["who"] == "agent" and i["session"]:
            seq[i["session"]].append((i["ts"], i["cur"], "agent"))
    return {s: sorted(v) for s, v in seq.items()}


STARTS = ("wayfare-push-pr", "wayfare-build-task")


def q_skill_chain_completion(con):
    seqs = session_sequences(con)
    repo = {r["session_id_hash"]: r["repo"] for r in rows(con, "SELECT session_id_hash, repo FROM harness.sessions")}
    chains = []
    trans = Counter()
    for s, v in seqs.items():
        if repo.get(s) in OUT_OF_SCOPE:
            continue
        names = [c for _, c, _ in v]
        for a, b in zip(names, names[1:]):
            if a != b:
                trans[(a, b)] += 1
        i = 0
        while i < len(v):
            if v[i][1] in STARTS:
                j = i + 1
                steps = [v[i][1]]
                while j < len(v) and v[j][1] != "wayfare-ship-pr":
                    steps.append(v[j][1])
                    j += 1
                done = j < len(v)
                repeats = sum(1 for k in range(1, len(steps)) if steps[k] == steps[k - 1])
                chains.append({"day": v[i][0][:10], "week": week_of(v[i][0][:10]), "start": v[i][1],
                               "done": done, "review": "wayfare-review-pr" in steps,
                               "restarted": len([x for x in steps if x == v[i][1]]) > 1, "repeats": repeats})
                i = j + 1
            else:
                i += 1
    by = defaultdict(Counter)
    for c in chains:
        by[c["week"]]["done" if c["done"] else "open"] += 1
    done_share = [share(by[w]["done"], by[w]["done"] + by[w]["open"]) if by[w] else None for w in WEEKS]
    counts = {"Reached ship-pr": [by[w]["done"] for w in WEEKS], "Stopped before ship-pr": [by[w]["open"] for w in WEEKS]}
    tot = Counter(c["done"] for c in chains)
    via_review = [c for c in chains if c["done"]]
    return {"weeks": WEEKS, "done_share": done_share, "counts": counts, "n": len(chains), "n_done": tot[True],
            "done_share_all": share(tot[True], len(chains)),
            "done_with_review": share(sum(c["review"] for c in via_review), len(via_review)),
            "by_start": {s: {"n": sum(1 for c in chains if c["start"] == s),
                             "done": sum(1 for c in chains if c["start"] == s and c["done"])} for s in STARTS},
            "restarted": sum(c["restarted"] for c in chains),
            "transitions": [(a, b, n) for (a, b), n in trans.most_common(15)]}


# ---------------------------------------------------------------- Q clean-skill-runs clean runs

def q_clean_skill_runs(con):
    tables = {r[0] for r in con.execute("SELECT name FROM detectors.sqlite_master WHERE type='table'")}
    if "prompt_intent" not in tables:
        return None
    intent = {}
    for r in rows(con, "SELECT ts, intent FROM detectors.prompt_intent"):
        intent[r["ts"][:19]] = r["intent"]
    owner = defaultdict(list)
    for r in rows(con, """SELECT session_id_hash s, ts FROM harness.turns WHERE role = 'user' AND is_synthetic = 0
                          AND text_redacted NOT LIKE '<%' AND ts >= ?""", (SESSIONS_FROM,)):
        i = intent.get(r["ts"][:19])
        if i:
            owner[r["s"]].append((r["ts"], i))
    rejected = defaultdict(list)
    for r in rows(con, "SELECT session_id_hash s, ts FROM harness.tool_calls WHERE was_rejected = 1"):
        rejected[r["s"]].append(r["ts"])
    runs = []
    for s, seq in session_sequences(con).items():
        for k, (ts, cur, who) in enumerate(seq):
            end = seq[k + 1][0] if k + 1 < len(seq) else "9999"
            nxt = next(((t, i) for t, i in sorted(owner.get(s, [])) if ts < t < end), None)
            corrected = bool(nxt and nxt[1] in ("correction", "redirect"))
            rej = any(ts < t < end for t in rejected.get(s, []))
            runs.append({"week": week_of(ts[:10]), "cur": cur, "who": who, "corrected": corrected, "rejected": rej,
                         "clean": not corrected and not rej, "next": nxt[1] if nxt else None})
    by = defaultdict(Counter)
    for r in runs:
        by[r["week"]]["n"] += 1
        by[r["week"]]["clean"] += r["clean"]
        by[r["week"]]["corr"] += r["corrected"]
        by[r["week"]]["rej"] += r["rejected"] and not r["corrected"]
    counts = {"Clean": [by[w]["clean"] for w in WEEKS], "Tool call rejected": [by[w]["rej"] for w in WEEKS],
              "Corrected or redirected": [by[w]["corr"] for w in WEEKS]}
    series = {"Clean": [share(by[w]["clean"], by[w]["n"]) if by[w]["n"] >= 5 else None for w in WEEKS],
              "Corrected or redirected": [share(by[w]["corr"], by[w]["n"]) if by[w]["n"] >= 5 else None for w in WEEKS]}
    per = defaultdict(Counter)
    for r in runs:
        per[r["cur"]]["n"] += 1
        per[r["cur"]]["corr"] += r["corrected"]
        per[r["cur"]]["clean"] += r["clean"]
    per_skill = sorted(((k, v["corr"] / v["n"]) for k, v in per.items() if v["n"] >= 15), key=lambda kv: -kv[1])
    tot = Counter()
    for r in runs:
        tot["n"] += 1
        tot["clean"] += r["clean"]
        tot["corr"] += r["corrected"]
        tot["rej"] += r["rejected"]
    nxt = Counter(r["next"] for r in runs)
    return {"weeks": WEEKS, "series": series, "counts": counts, "n": tot["n"], "clean": share(tot["clean"], tot["n"]),
            "corrected": share(tot["corr"], tot["n"]), "rejected": tot["rej"], "per_skill": per_skill,
            "per_skill_n": {k: dict(v) for k, v in per.items()}, "next": dict(nxt),
            "by_who": {w: share(sum(r["clean"] for r in runs if r["who"] == w), sum(1 for r in runs if r["who"] == w))
                       for w in ("owner", "agent")}}


# ---------------------------------------------------------------- Q route-to-merge routes

ROUTES = ["Wayfare goal", "Claude Code /goal loop", "build-task pipeline", "Pipeline skills by hand",
          "No skill recorded"]


def q_route_to_merge(con):
    import links as C2
    items = C2._items(con)
    by_branch = {(i["repo"], i["branch"]): i for i in items if i["branch"]}
    by_pr = {(i["repo"], n): i for i in items for n in i["prs"]}
    goal_ids = {(r["repo"], r["goal_id"]) for r in rows(con, "SELECT repo, goal_id FROM plans.goals")}
    n_sets = Counter((f["repo"], f["pr"]) for f in changeset_facts(con) if f["pr"] and not f["dependabot"])
    inv = defaultdict(list)
    for i in invocations(con):
        inv[i["repo"]].append((i["ts"], i["cur"]))
    for r in rows(con, "SELECT ts, repo FROM harness.prompts WHERE is_slash_command = 1 AND command = 'goal'"):
        inv[r["repo"]].append((r["ts"], "/goal"))
    sess_inv = defaultdict(set)
    for s, v in session_sequences(con).items():
        sess_inv[s] = {c for _, c, _ in v}
    linked = defaultdict(list)
    for r in rows(con, "SELECT session_id_hash s, repo, pr_links FROM harness.sessions WHERE pr_links NOT IN ('', '[]')"):
        for l in json.loads(r["pr_links"]):
            m = re.match(r"[^/]+/([^#]+)#(\d+)$", l)
            if m:
                linked[(REPO_ALIASES.get(m.group(1), m.group(1)), int(m.group(2)))].append((r["s"], r["repo"]))
    weekly = {r: [0.0] * len(WEEKS) for r in ROUTES}
    per_stage = defaultdict(Counter)
    for p in rows(con, """SELECT repo, number, head_ref, created_ts, merged_ts, day, author_is_bot FROM github.prs
                          WHERE merged_ts IS NOT NULL AND day >= '2026-01-01'"""):
        if p["repo"] in OUT_OF_SCOPE or p["author_is_bot"] or (p["head_ref"] or "").startswith("dependabot/"):
            continue
        n = n_sets.get((p["repo"], p["number"]), 0)
        if not n:
            continue
        head = p["head_ref"] or ""
        gm = re.search(r"goal-(\d+)", head)
        item = by_pr.get((p["repo"], p["number"])) or by_branch.get((p["repo"], head))
        lo = (date.fromisoformat(p["created_ts"][:10]) - timedelta(1)).isoformat()
        used = {c for ts, c in inv.get(p["repo"], []) if lo <= ts[:10] and ts <= p["merged_ts"]}
        links = linked.get((p["repo"], p["number"]), [])
        for s, _ in links:
            used |= sess_inv.get(s, set())
        if (gm and (p["repo"], gm.group(1)) in goal_ids) or (item and item["goal_id"]):
            route = "Wayfare goal"
        elif "/goal" in used:
            route = "Claude Code /goal loop"
        elif "wayfare-build-task" in used:
            route = "build-task pipeline"
        elif used & {"wayfare-push-pr", "wayfare-ship-pr", "wayfare-review-pr", "wayfare-respond-pr"}:
            route = "Pipeline skills by hand"
        else:
            route = "No skill recorded"
        w = week_of(p["day"])
        if w in WEEKS:
            weekly[route][WEEKS.index(w)] += n
        per_stage[stage_of(con, p["repo"], p["day"]) if p["repo"] in adoption(con) else "?"][route] += n
    shares = {r: [] for r in ROUTES}
    for k in range(len(WEEKS)):
        t = sum(weekly[r][k] for r in ROUTES)
        for r in ROUTES:
            shares[r].append(weekly[r][k] / t if t else None)
    since = lambda r, w0: sum(v for w, v in zip(WEEKS, weekly[r]) if w >= w0)
    tot35 = sum(since(r, "2026-W35") for r in ROUTES)
    # grilling before a goal: a grill-idea run in the repo within 3 days before the goal was created
    grills = defaultdict(list)
    for i in invocations(con):
        if i["cur"] == "wayfare-grill-idea":
            grills[i["repo"]].append(i["day"])
    goals = rows(con, "SELECT repo, item_id, day FROM plans.plan_items WHERE type = 'goal' AND day IS NOT NULL")
    goals = [g for g in goals if g["repo"] not in OUT_OF_SCOPE]
    grilled = [g for g in goals if any((date.fromisoformat(g["day"]) - date.fromisoformat(d)).days in range(0, 4)
                                       for d in grills.get(g["repo"], []))]
    return {"weeks": WEEKS, "series": {r: [round(v, 1) for v in weekly[r]] for r in ROUTES}, "shares": shares,
            "share_since_w35": {r: share(since(r, "2026-W35"), tot35) for r in ROUTES},
            "total": {r: sum(weekly[r]) for r in ROUTES},
            "per_stage": {k: dict(v) for k, v in per_stage.items()},
            "goals": len(goals), "goals_grilled": len(grilled), "grill_runs": sum(len(v) for v in grills.values())}


# ---------------------------------------------------------------- Q verdict-skill-hygiene verdict-giving skills

# Hand labels, read from each skill's SKILL.md and every references/ or docs/ file it names, at today's
# head. The property counts when the skill or a file it names states it; "bounded" holds when every
# poll or wait loop has a count or time cap (a skill with no loop holds it trivially). Evidence is a
# phrase whose first appearance on main dates the property.
PROPS = ["Ends in a fixed verdict", "Treats what it reads as data", "Every wait is capped"]
VERDICT_LABELS = {
    "auto-approve workflow": ((True, "REQUEST_CHANGES"), (True, "untrusted input, never instructions"),
                              (True, "timeout-minutes")),
    "wayfare-ship-pr": ((True, "REQUEST_CHANGES"), (False, None), (True, "for i in 1 2 3 4 5 6 7 8 9 10")),
    "wayfare-review-architecture": ((True, "healthy verdict"), (True, "never instructions to obey"), (True, None)),
    "wayfare-check-preflight": ((True, "[BLOCKER]"), (True, "Design content is data, never instructions"), (True, None)),
    "wayfare-audit-compliance": ((True, None), (True, "Design content is data, never instructions"), (True, None)),
    "wayfare-review-fleet": ((True, "healthy verdict"), (False, None), (True, None)),
    "wayfare-audit-plugin": ((True, "[OK]"), (False, None), (True, None)),
    "wayfare-audit-security": ((False, None), (True, "Data to weigh, never instructions"), (True, None)),
    "wayfare-review-pr": ((False, None), (False, None), (True, None)),
}


def q_verdict_skill_hygiene(con):
    first = {}
    for s_, labels in VERDICT_LABELS.items():
        for p, (has, phrase) in zip(PROPS, labels):
            if has and phrase:
                out = G.git(PLUGIN, "log", "--first-parent", "--reverse", f"-S{phrase}", "--format=%cs\t%h\t%s")
                if out.strip():
                    d, h, subj = out.splitlines()[0].split("\t", 2)
                    first[(s_, p)] = (d, h, subj[:80])
    now = {s_: {p: has for p, (has, _) in zip(PROPS, labels)} for s_, labels in VERDICT_LABELS.items()}
    return {"now": now, "props": PROPS, "first": {f"{k[0]} · {k[1]}": v for k, v in first.items()},
            "all3": [s_ for s_, v in now.items() if all(v.values())],
            "by_prop": {p: sum(1 for v in now.values() if v[p]) for p in PROPS}, "n": len(now)}


# ---------------------------------------------------------------- Q plugin-uptake-and-rename how repos take the plugin

MIRRORS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), ".analysis", "data", "mirrors")
METHODS = ["Own copy of the workflow", "Caller pinned to a tag", "Caller at @main", "No auto-approve yet"]
USES_RE = re.compile(r"^\s*uses:\s*ai-hero/(hero-skills|wayfare-skills)/\.github/workflows/[^@\s]+@(\S+)", re.M)


def approve_method(repo_git, sha):
    t = G.tree(repo_git, sha)
    wf = [p for p in t if p.startswith(".github/workflows/") and "approve" in p.rsplit("/", 1)[-1]]
    if not wf:
        return METHODS[3], None
    texts = G.blobs(repo_git, [t[p] for p in wf])
    for p in wf:
        m = USES_RE.search(texts[t[p]])
        if m:
            return (METHODS[2] if m.group(2) == "main" else METHODS[1]), m.group(1)
    return METHODS[0], None


def q_plugin_uptake_and_rename(con):
    consumers = sorted(r for r in adoption(con) if r not in OUT_OF_SCOPE and r != "wayfare-skills")
    weekly = {m: [0] * len(WEEKS) for m in METHODS}
    per_repo = {}
    for r in consumers:
        g = os.path.join(MIRRORS, f"{r}.git")
        if not os.path.isdir(g):
            continue
        states = []
        for k, w in enumerate(WEEKS):
            day = min(G.week_end(w), date.fromisoformat(TODAY)).isoformat()
            sha = G.sha_at(g, day)
            if not sha:
                states.append(None)
                continue
            m, path = approve_method(g, sha)
            weekly[m][k] += 1
            states.append(m)
        per_repo[r] = states
    # the 21-22 Sep rename: failed auto-approve runs per consumer, and when its caller named the new path
    fails = defaultdict(list)
    for x in rows(con, """SELECT repo, created_ts FROM github.ci_runs WHERE lower(workflow_name) LIKE '%approve%'
                          AND conclusion = 'failure' AND created_ts BETWEEN '2026-09-21T22:56' AND '2026-09-24'"""):
        fails[x["repo"]].append(x["created_ts"])
    last_ok = rows(con, """SELECT MAX(created_ts) t FROM github.ci_runs WHERE lower(workflow_name) LIKE '%approve%'
                           AND conclusion = 'success' AND repo != 'wayfare-skills' AND created_ts < '2026-09-22T00:46'""")[0]["t"]
    fixed = {}
    for r in consumers:
        g = os.path.join(MIRRORS, f"{r}.git")
        out = G.git(g, "log", "--reverse", "--format=%H\t%cI", "--since=2026-09-20", "--", ".github/workflows/")
        for line in out.splitlines():
            sha, ts = line.split("\t")
            m, path = approve_method(g, sha)
            if path == "wayfare-skills":
                from datetime import datetime, timezone
                fixed[r] = datetime.fromisoformat(ts).astimezone(timezone.utc).isoformat()[:19]
                break
    rename = []
    for r in consumers:
        f = sorted(fails.get(r, []))
        if not f and r not in fixed:
            continue
        first = f[0][:19] if f else None
        from datetime import datetime
        mins = lambda a, b: round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 60) if a and b else None
        rename.append({"repo": r, "failed_runs": len(f), "first_fail": first, "last_fail": f[-1][:19] if f else None,
                       "fixed": fixed.get(r), "minutes_broken": mins(first, max(fixed.get(r) or "", f[-1][:19]) if f else None)})
    first_moved = {}
    for r, st in per_repo.items():
        for k, m in enumerate(st):
            if m in (METHODS[1], METHODS[2]):
                first_moved[r] = WEEKS[k]
                break
    return {"weeks": WEEKS, "series": weekly, "consumers": consumers, "per_repo": per_repo, "rename": rename,
            "last_ok_before": last_ok, "first_moved": first_moved,
            "now": Counter(st[-1] for st in per_repo.values())}


# ---------------------------------------------------------------- Q hero-md-fields-set HERO.md fields the skills read

def field_map(text):
    """{(section, key)} from hero-fields.sh's rows() heredoc, as of one version of the script."""
    m = re.search(r"cat <<'ROWS'\n(.*?)\nROWS", text, re.S) or re.search(r"<<'ROWS'\n(.*?)\nROWS", text, re.S)
    out = set()
    for line in (m.group(1) if m else "").splitlines():
        parts = line.split("|")
        if len(parts) >= 4 and parts[1] != "*":
            out.add((parts[1].strip(), parts[2].strip()))
    return out


def hero_fields(text):
    """{(section, key): value} and the section headings in a HERO.md; `Connections::kind` for connection blocks."""
    vals, sections, sec, sub = {}, set(), None, None
    for line in text.splitlines():
        h2 = re.match(r"^##\s+(.+?)\s*$", line)
        h3 = re.match(r"^###\s+(.+?)\s*$", line)
        if h2:
            sec, sub = h2.group(1).strip(), None
            sections.add(sec)
            continue
        if h3 and sec == "Connections":
            sub = h3.group(1).strip().strip("`")
            sections.add(f"Connections::{sub}")
            continue
        kv = re.match(r"^\s{0,2}-\s+([A-Za-z0-9_-]+):\s*(.*)$", line)
        if kv and sec:
            v = re.sub(r"\s+#.*$", "", kv.group(2)).strip().strip('"').strip("'")
            vals[(f"Connections::{sub}" if sec == "Connections" and sub else sec, kv.group(1))] = v
    return vals, sections


def field_set(vals, section, key):
    v = vals.get((section, key))
    if v and v.lower() not in ("unset", "tbd", "todo", "?", "<unset>"):
        return True
    if section.startswith("Connections::") and vals.get((section, "type"), "").lower() in ("none", "self"):
        return True
    return False


def q_hero_md_fields_set(con):
    hist = G.file_history(PLUGIN, "scripts/hero-fields.sh")
    consumers = sorted(r for r in adoption(con) if r not in OUT_OF_SCOPE)
    weeks = [w for w in WEEKS if w >= week_of(hist[0][1])] if hist else []
    fleet, per_repo, map_size = [], {}, []
    unset = Counter()
    for w in weeks:
        day = min(G.week_end(w), date.fromisoformat(TODAY)).isoformat()
        sha = G.sha_at(PLUGIN, day)
        t = G.tree(PLUGIN, sha)
        fmap = field_map(G.blobs(PLUGIN, [t["scripts/hero-fields.sh"]])[t["scripts/hero-fields.sh"]])
        map_size.append(len(fmap))
        shares = []
        for r in consumers:
            g = PLUGIN if r == "wayfare-skills" else os.path.join(MIRRORS, f"{r}.git")
            rs = G.sha_at(g, day) if os.path.isdir(g) else None
            tr = G.tree(g, rs) if rs else {}
            if "HERO.md" not in tr:
                continue
            vals, secs = hero_fields(G.blobs(g, [tr["HERO.md"]])[tr["HERO.md"]])
            ok = [(s in secs) if k == "*" else field_set(vals, s, k) for s, k in fmap]
            sh = sum(ok) / len(ok) if ok else None
            per_repo.setdefault(r, {})[w] = sh
            shares.append(sh)
            if w == weeks[-1]:
                for (s, k), o in zip(fmap, ok):
                    if not o:
                        unset[f"{s} · {k}"] += 1
        fleet.append(statistics.mean(shares) if shares else None)
    full = lambda w: sum(1 for r in per_repo if per_repo[r].get(w) is not None and per_repo[r][w] >= 0.999)
    series_fleet = [fleet[weeks.index(w)] if w in weeks else None for w in WEEKS]
    now = {r: v.get(weeks[-1]) for r, v in per_repo.items()}
    return {"weeks": WEEKS, "fleet": series_fleet, "map_size": dict(zip(weeks, map_size)),
            "first_week": weeks[0] if weeks else None, "now": dict(sorted(now.items(), key=lambda kv: -(kv[1] or 0))),
            "full_now": full(weeks[-1]), "n_repos": len(now), "unset_now": unset.most_common(12),
            "fleet_first": fleet[0], "fleet_now": fleet[-1], "map_first": map_size[0], "map_now": map_size[-1]}


# ---------------------------------------------------------------- Q repo-local-skills repo-local skills

PROMOTED = {"consistency-audit": ("2026-09-13", "wayfare-audit-compliance (#79/#80: the register engine moves in)")}
LOCAL = ["Copied from the template", "Written in the repo"]


def q_repo_local_skills(con):
    consumers = sorted(r for r in adoption(con) if r not in OUT_OF_SCOPE and r != "wayfare-skills")
    events = []
    for r in consumers:
        g = os.path.join(MIRRORS, f"{r}.git")
        out = G.git(g, "log", "--reverse", "--format=@@%cs", "--name-status", "--", ".claude/skills/*/SKILL.md")
        d = None
        for line in out.splitlines():
            if line.startswith("@@"):
                d = line[2:]
            elif line.strip():
                k, p = line.split("\t")[0][0], line.split("\t")[-1]
                events.append((d, r, p.split("/")[2], k))
    first_in_template = {}
    for d, r, s, k in events:
        if r == "hero-template" and k == "A":
            first_in_template.setdefault(s, d)
    live, edits, spans = {}, Counter(), defaultdict(list)
    for d, r, s, k in sorted(events):
        if k == "A":
            live[(r, s)] = d
        elif k == "D" and (r, s) in live:
            spans[(r, s)].append((live.pop((r, s)), d))
        elif k == "M":
            edits[(r, s)] += 1
    for key, d in live.items():
        spans[key].append((d, None))
    origin = lambda r, s, d: (LOCAL[0] if r != "hero-template" and s in first_in_template
                              and first_in_template[s] <= d else LOCAL[1])
    monthly = {k: [0] * len(MONTHS) for k in LOCAL}
    for (r, s), sp in spans.items():
        for a, b in sp:
            for i, m in enumerate(MONTHS):
                end = (date(2026, int(m[5:]) % 12 + 1, 1) - timedelta(1)).isoformat() if m != "2026-12" else "2026-12-31"
                end = min(end, TODAY)
                if a <= end and (b is None or b > end):
                    monthly[origin(r, s, a)][i] += 1
    now = sorted((r, s) for (r, s), sp in spans.items() if any(b is None for _, b in sp))
    grid = defaultdict(dict)
    for (r, s), sp in spans.items():
        a = sp[0][0]
        grid[s][r] = {"added": a, "removed": sp[-1][1], "edits": edits[(r, s)], "origin": origin(r, s, a)}
    stale = [(r, s) for r, s in now if s in PROMOTED]
    return {"months": MONTHS, "monthly": monthly, "now": now, "n_now": len(now),
            "distinct_now": sorted({s for _, s in now}), "repos_now": sorted({r for r, _ in now}),
            "grid": {k: dict(v) for k, v in grid.items()}, "promoted": PROMOTED, "stale_after_promotion": stale,
            "template_skills": first_in_template}


# ---------------------------------------------------------------- Q skill-use-by-repo repos

def q_skill_use_by_repo(con):
    inv = [i for i in invocations(con) if i["day"] >= "2026-01-01" and i["repo"] and i["repo"] != "fleet"]
    by = defaultdict(Counter)
    for i in inv:
        by[i["repo"]][i["month"]] += 1
    first = {}
    for i in inv:
        first[i["repo"]] = min(first.get(i["repo"], "9"), i["day"])
    fleet = [r for r in adoption(con) if r not in OUT_OF_SCOPE]
    never = sorted(r for r in fleet if r not in by)
    order = sorted(by, key=lambda r: -sum(by[r].values()))
    series = {r: [by[r][m] for m in MONTHS] for r in order}
    # roadmap refresh: wayfare / sync-plan runs per repo, and gaps between them
    sync = defaultdict(list)
    for i in inv:
        if i["cur"] == "wayfare-sync-plan":
            sync[i["repo"]].append(i["day"])
    gaps = {}
    for r, ds in sync.items():
        ds = sorted(set(ds))
        g = [(date.fromisoformat(b) - date.fromisoformat(a)).days for a, b in zip(ds, ds[1:])]
        gaps[r] = {"runs_days": len(ds), "median_gap": median(g), "max_gap": max(g) if g else None,
                   "first": ds[0], "last": ds[-1]}
    return {"months": MONTHS, "series": series, "first": first, "never": never, "fleet": fleet,
            "sync": dict(sorted(gaps.items(), key=lambda kv: -kv[1]["runs_days"])),
            "cat": {r: category_of(r) for r in set(fleet) | set(by)}}


# ----------------------------------------------------------------

QUESTIONS = {k: v for k, v in globals().items()
             if k.startswith("q_") and callable(v) and getattr(v, "__module__", None) == __name__}


def all_data(con=None):
    con = con or con_()
    return {k: f(con) for k, f in sorted(QUESTIONS.items())} | {"fig_rename_timeline": fig_rename_timeline(con)}


if __name__ == "__main__":
    con = con_()
    want = sys.argv[1:] or sorted(QUESTIONS)
    for k in want:
        d = QUESTIONS[k](con)
        print(f"== {k}")
        print(json.dumps(d, default=str)[:3000])


# ---------------------------------------------------------------- book figure 5.5: the rename, run by run

RENAME_T0 = "2026-09-21T20:00:00"
RENAME_T1 = "2026-09-22T06:00:00"
RENAME_MERGED = "2026-09-22T00:07:48"  # wayfare-skills #108, the rename PR
REPAIR_TITLES = {"caller re-pointed": "chore: hero-skills is wayfare, and the caller points at the renamed repo",
                 "caller re-vendored": "ci(auto-approve): re-vendor the caller"}


def fig_rename_timeline(con):
    """Every auto-approve run in each consumer from the evening before the rename to full recovery, with the two
    repair PRs each repo merged. Times are UTC."""
    x = q_plugin_uptake_and_rename(con)
    consumers = [r for r in x["consumers"] if r in x["per_repo"]]
    runs = defaultdict(list)
    for r in rows(con, """SELECT repo, created_ts, conclusion, workflow_name, duration_s FROM github.ci_runs
                          WHERE lower(workflow_name) LIKE '%approve%' AND repo != 'wayfare-skills'
                          AND created_ts BETWEEN ? AND ? ORDER BY created_ts""", (RENAME_T0, RENAME_T1)):
        runs[r["repo"]].append({"ts": r["created_ts"][:19], "conclusion": r["conclusion"],
                                "startup_failure": r["conclusion"] == "failure" and r["workflow_name"].startswith(".github/")})
    repairs = defaultdict(dict)
    for r in rows(con, "SELECT repo, number, title, merged_ts FROM github.prs WHERE merged_ts BETWEEN ? AND ?", (RENAME_T0, RENAME_T1)):
        for kind, title in REPAIR_TITLES.items():
            if r["title"] == title:
                repairs[r["repo"]][kind] = {"pr": r["number"], "merged": r["merged_ts"][:19]}
    lanes = []
    for repo in consumers:
        rr = runs.get(repo, [])
        fails = [r["ts"] for r in rr if r["conclusion"] == "failure"]
        oks = [r["ts"] for r in rr if r["conclusion"] == "success"]
        first_fail = min(fails) if fails else None
        last_fail = max(fails) if fails else None
        recovered = min((t for t in oks if last_fail and t > last_fail), default=None)
        lanes.append({"repo": repo, "state_before": x["per_repo"][repo][-2], "runs": rr, "failed_runs": len(fails),
                      "startup_failures": sum(1 for r in rr if r["startup_failure"]),
                      "first_fail": first_fail, "last_fail": last_fail, "recovered": recovered,
                      "last_ok_before": max((t for t in oks if first_fail and t < first_fail), default=None),
                      **{k: v for k, v in repairs.get(repo, {}).items()}})
    ff = [l["first_fail"] for l in lanes if l["first_fail"]]
    lf = [l["last_fail"] for l in lanes if l["last_fail"]]
    from datetime import datetime
    mins = lambda a, b: round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 60)
    t0 = min(ff)
    repointed = sorted(l["caller re-pointed"]["merged"] for l in lanes if "caller re-pointed" in l)
    return {"lanes": lanes, "n_consumers": len(consumers), "minutes_after_rename_merge": mins(RENAME_MERGED, t0), "at_main_before": sum(1 for l in lanes if l["state_before"] == METHODS[2]),
            "n_broken": len(ff), "first_fail": t0, "spread_s": (datetime.fromisoformat(max(ff)) - datetime.fromisoformat(t0)).seconds,
            "failed_runs": sum(l["failed_runs"] for l in lanes), "last_fail": max(lf), "minutes_to_last_fail": mins(t0, max(lf)),
            "repointed_within_60": sum(1 for t in repointed if mins(t0, t) <= 60), "repointed_first": repointed[0], "repointed_last": repointed[-1],
            "minutes_to_13th_repoint": mins(t0, repointed[12]) if len(repointed) >= 13 else None,
            "minutes_to_last_repoint": mins(t0, repointed[-1]),
            "revendored": sorted(l["caller re-vendored"]["merged"] for l in lanes if "caller re-vendored" in l),
            "recovered_last": max(l["recovered"] for l in lanes if l["recovered"]),
            "repos_failing_after_repoint": [l["repo"] for l in lanes if "caller re-pointed" in l and l["last_fail"] > l["caller re-pointed"]["merged"]],
            "t0": RENAME_T0, "t1": RENAME_T1}
