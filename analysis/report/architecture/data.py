"""Architecture records series: architecture and design records.

    cd analysis && WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/architecture/data.py

One function per question (q_design_record_adoption … q_design_guardrails_fired); each returns what its answer slide (and, where
there is one, its by-repo slide) plots. The design records themselves are re-read from the
git mirrors by records.py, because knowledge.doc_versions has no hiro rows.
"""
import hashlib
import json
import os
import re
import sqlite3
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from difflib import SequenceMatcher
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import records as R  # noqa: E402
from record import adoption, changeset_facts, rows, stage_of, week_of  # noqa: E402
from evolution import WEEKS, MONTHS, APPS  # noqa: E402

CH_DB = os.path.join(HERE, "..", "..", "..", ".analysis", "data", "architecture.sqlite")
FLEET_ROOT = os.path.expanduser(os.environ.get("WAYFARE_FLEET_ROOT", "~/workspaces/aihero"))
FLEET_REGISTER = os.path.join(FLEET_ROOT, ".fleet")
TEMPLATE = "hero-template"

# Chapter events from wayfare-skills' history, drawn in pink.
RECORD_EVENTS = [("2026-07-23", "ARCHITECTURE.md skill (#44)"), ("2026-07-30", "DESIGN.md replaces it (#47)")]
CORE_SECTIONS = ["Overview", "Tech stack", "Codemap", "Boundaries", "Invariants", "Decisions"]
PRODUCT_SECTIONS = ["Users", "Flows", "Interaction standards"]
DOC_FILES = ("DESIGN.md", "AGENTS.md", "HERO.md", "CLAUDE.md", "README.md")


def week_end(w):
    return date.fromisocalendar(int(w[:4]), int(w[6:]), 7).isoformat()


def month_end(m):
    d = date(int(m[:4]), int(m[5:]), 1)
    return (date(d.year + (d.month == 12), d.month % 12 + 1, 1) - timedelta(days=1)).isoformat()


def median(v):
    return round(statistics.median(v), 1) if v else None


def share(a, b):
    return round(a / b, 3) if b else None


def in_scope(con):
    """Repos the study covers (adoption() already drops the five deleted -design repos)."""
    ad = adoption(con)
    return [r for r in R.mirror_repos() if r in ad]


def first_commit(repo):
    mc = R.main_commits(repo)
    return mc[0][1] if mc else None


def record_at(repo, day):
    """The latest version of the record on or before `day` (None if none yet or deleted)."""
    v = [x for x in R.versions(repo) if x["day"] <= day]
    return v[-1] if v and v[-1]["parsed"] else None


@lru_cache(maxsize=None)
def work_sets(con):
    return [f for f in changeset_facts(con) if not f["dependabot"]]


# ---------------------------------------------------------------- decisions: identity, copies

@lru_cache(maxsize=None)
def decision_index(con):
    """Every decision entry ever seen: {(repo, key): {first_day, date, heading, body, first_sha, bootstrap}}."""
    out = {}
    for r in in_scope(con):
        vs = R.versions(r)
        for i, v in enumerate(vs):
            if not v["parsed"]:
                continue
            fresh = i == 0 or not vs[i - 1]["parsed"]
            for d in v["parsed"]["decisions"]:
                if (r, d["key"]) not in out:
                    out[(r, d["key"])] = {"repo": r, "key": d["key"], "first_day": v["day"], "date": d["date"],
                                          "heading": d["heading"], "body": d["body"], "norm": d["norm"],
                                          "first_sha": v["sha"], "bootstrap": fresh}
    return out


def ch_db():
    db = sqlite3.connect(CH_DB)
    db.execute("CREATE TABLE IF NOT EXISTS copy_labels (h TEXT PRIMARY KEY, repo TEXT, heading TEXT, same_as TEXT, "
               "model TEXT, cost REAL)")
    db.execute("CREATE TABLE IF NOT EXISTS spend_log (ts TEXT, what TEXT, cost REAL)")
    return db


COPY_PROMPT = """You compare architecture decision records across repos of one software fleet. Several repos were cloned
from a template repo and copy some of its decisions, sometimes reworded or adapted.

REFERENCE decisions (id | repo | heading):
{refs}

For each CANDIDATE below, answer whether it records the SAME decision as one REFERENCE decision from a DIFFERENT repo
(the same architectural choice, possibly reworded or adapted to this repo). A decision that is merely related, or
that makes a different choice about the same topic, is NOT the same. Reply with JSON only: a list of
{{"n": <candidate number>, "same_as": <reference id or null>}}.

CANDIDATES:
"""


# Model matches rejected on the hand spot-check: related decisions that make a different choice.
REJECTED = {
    ("auth", "the decision paths reads cache in redis "),
    ("auth", "the idp becomes a per request fleet depe"),
    ("auth", "two process single image runtime ssr"),
    ("website", "the token layer has one upstream"),
    ("design-system", "atomic component layers with mechanical "),
    ("design-system", "key the registry decision cache on a tok"),
}


def copy_labels(con, run_model=True):
    """(repo, key) -> origin (repo, key) for decisions restating another repo's decision.

    Exact heading match (date stripped) first; the unmatched remainder goes to Haiku once, cached in architecture.sqlite.
    The origin is the repo that carried the decision first."""
    idx = decision_index(con)
    by_key = defaultdict(list)
    for (r, k), d in idx.items():
        by_key[k].append(d)
    origin = {}
    for k, ds in by_key.items():
        if len(ds) > 1:
            first = min(ds, key=lambda d: (d["first_day"], d["repo"] != TEMPLATE))
            for d in ds:
                if d is not first:
                    origin[(d["repo"], k)] = (first["repo"], k)
    db = ch_db()
    rest = [d for (r, k), d in sorted(idx.items()) if (r, k) not in origin and len(by_key[k]) == 1]
    refs = sorted(idx.values(), key=lambda d: (d["repo"], d["first_day"]))
    ref_id = {(d["repo"], d["key"]): i + 1 for i, d in enumerate(refs)}
    ref_text = "\n".join(f"{ref_id[(d['repo'], d['key'])]} | {d['repo']} | {d['heading']}" for d in refs)
    h = lambda d: hashlib.sha256((d["repo"] + "\n" + d["heading"] + "\n" + d["norm"][:500] + "\n" + ref_text).encode()).hexdigest()
    cached = {row[0]: row[1] for row in db.execute("SELECT h, same_as FROM copy_labels")}
    todo = [d for d in rest if h(d) not in cached]
    if todo and run_model:
        from concurrent.futures import ThreadPoolExecutor
        from detectors.d1_changesets import call_haiku
        batches = [todo[i:i + 25] for i in range(0, len(todo), 25)]

        def one(batch):
            texts = [f"{n + 1}. [{d['repo']}] {d['heading']}\n{d['norm'][:400]}" for n, d in enumerate(batch)]
            res, cost = call_haiku(texts, model="haiku", header=COPY_PROMPT.format(refs=ref_text))
            return batch, res, cost
        with ThreadPoolExecutor(4) as ex:
            for batch, res, cost in ex.map(one, batches):
                db.execute("INSERT INTO spend_log VALUES (datetime('now'), 'copy_labels batch', ?)", (cost,))
                if not isinstance(res, list):
                    continue
                ans = {int(a.get("n", 0)): a.get("same_as") for a in res if isinstance(a, dict)}
                for n, d in enumerate(batch):
                    same = ans.get(n + 1)
                    db.execute("INSERT OR REPLACE INTO copy_labels VALUES (?,?,?,?,?,?)",
                               (h(d), d["repo"], d["heading"], str(same) if same else None, "haiku",
                                cost / len(batch)))
        db.commit()
        cached = {row[0]: row[1] for row in db.execute("SELECT h, same_as FROM copy_labels")}
    by_id = {v: k for k, v in ref_id.items()}
    for d in rest:
        same = cached.get(h(d))
        if same and same.isdigit() and int(same) in by_id:
            o = by_id[int(same)]
            o = origin.get(o, o)  # the reference may itself be a copy: point at the first carrier
            if (d["repo"], d["key"][:40]) in REJECTED or o[0] == d["repo"] or idx[o]["first_day"] > d["first_day"]:
                continue
            origin[(d["repo"], d["key"])] = o
    return origin


def model_spend():
    try:
        return round(ch_db().execute("SELECT COALESCE(SUM(cost), 0) FROM spend_log").fetchone()[0], 3)
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e):
            raise
        print(f"architecture: {e}; model spend unavailable", file=sys.stderr)
        return None


# ---------------------------------------------------------------- Q design-record-adoption

def q_design_record_adoption_exists(con):
    ad = adoption(con)
    repos = in_scope(con)
    first = {r: (R.versions(r)[0]["day"] if R.versions(r) else None) for r in repos}
    born = {r: first_commit(r) for r in repos}
    label = {"app": "Apps", "app, no features yet": "Apps, no features yet", "allied": "Allied repos"}
    cats = ["Apps", "Apps, no features yet", "Allied repos", "No design record"]
    series = {c: [0] * len(WEEKS) for c in cats}
    for i, w in enumerate(WEEKS):
        end = week_end(w)
        for r in repos:
            if not born[r] or born[r] > end:
                continue
            has = record_at(r, end) is not None
            series[label[ad[r]["category"]] if has else "No design record"][i] += 1
    rows_ = []
    for r in repos:
        rows_.append({"repo": r, "category": ad[r]["category"], "born": born[r], "record": first[r],
                      "path": R.versions(r)[0]["path"] if R.versions(r) else None,
                      "days": (date.fromisoformat(first[r]) - date.fromisoformat(max(born[r], "2026-01-01"))).days
                      if first[r] else None,
                      "stage": stage_of(con, r, first[r]) if first[r] else None})
    none = [x["repo"] for x in rows_ if not x["record"]]
    return {"weeks": WEEKS, "series": series, "repos": sorted(rows_, key=lambda x: (x["record"] or "9999", x["repo"])),
            "none": none, "hiro_in_doc_versions": con.execute(
                "SELECT COUNT(*) FROM knowledge.doc_versions WHERE repo='hiro' AND doc='DESIGN.md'").fetchone()[0],
            "infra_env_doc": R.git("infrastructure-environments", "log", "--diff-filter=A", "--format=%cs", "--",
                                   "docs/architecture.md")}


# ---------------------------------------------------------------- Q design-record-growth

def q_design_record_growth_growth(con):
    ad = adoption(con)
    repos = [r for r in in_scope(con) if R.versions(r)]
    label = {"app": "Apps", "app, no features yet": "Apps, no features yet", "allied": "Allied repos"}
    cats = ["Apps", "Apps, no features yet", "Allied repos"]
    edits = {c: [0] * len(WEEKS) for c in cats}
    for r in repos:
        for v in R.versions(r):
            w = week_of(v["day"])
            if w in WEEKS:
                edits[label[ad[r]["category"]]][WEEKS.index(w)] += 1
    lines = {r: [(lambda v: v["parsed"]["lines"] if v else None)(record_at(r, month_end(m))) for m in MONTHS]
             for r in repos}
    total_lines = [sum(filter(None, (lines[r][i] for r in repos))) for i in range(len(MONTHS))]
    sets = work_sets(con)
    last_set = {r: max((f["day"] for f in sets if f["repo"] == r), default=None) for r in repos}
    now = {r: {"last_edit": R.versions(r)[-1]["day"], "edits": len(R.versions(r)),
               "lines": R.versions(r)[-1]["parsed"]["lines"] if R.versions(r)[-1]["parsed"] else 0,
               "last_set": last_set[r],
               "sets_since": sum(1 for f in sets if f["repo"] == r and f["day"] > R.versions(r)[-1]["day"])}
           for r in repos}
    order = sorted(repos, key=lambda r: -(now[r]["lines"] or 0))

    def rho(a, b):
        keys = [k for k in a if a[k] is not None and b.get(k) is not None]
        ra = {k: i for i, k in enumerate(sorted(keys, key=lambda k: -a[k]))}
        rb = {k: i for i, k in enumerate(sorted(keys, key=lambda k: -b[k]))}
        n = len(keys)
        return round(1 - 6 * sum((ra[k] - rb[k]) ** 2 for k in keys) / (n * (n * n - 1)), 2) if n > 3 else None
    size = {r: now[r]["lines"] for r in repos}
    n_sets = {r: sum(1 for f in sets if f["repo"] == r) for r in repos}
    age = {r: (date(2026, 9, 25) - date.fromisoformat(first_commit(r))).days for r in repos}
    reviews = {r["repo"]: r["n"] for r in rows(con, "SELECT repo, COUNT(*) n FROM github.pr_reviews GROUP BY repo")}
    correlates = {"change sets merged": rho(size, n_sets), "repo age": rho(size, age),
                  "record edits": rho(size, {r: now[r]["edits"] for r in repos}),
                  "PR reviews received": rho(size, {r: reviews.get(r) for r in repos})}
    return {"correlates": correlates, "weeks": WEEKS, "edits": edits, "lines_by_repo": {r: lines[r] for r in order}, "total_lines": total_lines,
            "now": now, "total_edits": sum(len(R.versions(r)) for r in repos)}


# ---------------------------------------------------------------- Q decision-rate

def q_decision_rate_rate(con):
    idx = decision_index(con)
    origin = copy_labels(con)
    own = [d for k, d in idx.items() if k not in origin]
    copied = [d for k, d in idx.items() if k in origin]
    wk = lambda ds: [sum(1 for d in ds if week_of(d["first_day"]) == w) for w in WEEKS]
    series = {"Own decisions": wk(own), "Copied from another repo": wk(copied)}
    repos = sorted({d["repo"] for d in own}, key=lambda r: -sum(1 for d in own if d["repo"] == r))
    cum = {r: [sum(1 for d in own if d["repo"] == r and d["first_day"] <= month_end(m)) or None for m in MONTHS]
           for r in repos}
    sets = work_sets(con)
    since = "2026-07-30"
    rate = {}
    for r in repos:
        n_sets = sum(1 for f in sets if f["repo"] == r and f["day"] >= since)
        n_dec = sum(1 for d in own if d["repo"] == r and d["first_day"] >= since and not d["bootstrap"])
        rate[r] = {"sets": n_sets, "decisions": n_dec, "per100": round(100 * n_dec / n_sets, 1) if n_sets else None}
    fleet_sets = sum(1 for f in sets if f["day"] >= since and f["repo"] in repos)
    fleet_dec = sum(1 for d in own if d["first_day"] >= since and not d["bootstrap"])
    monthly = {}
    for m in MONTHS[6:]:
        s = sum(1 for f in sets if f["month"] == m and f["repo"] in repos)
        n = sum(1 for d in own if d["first_day"][:7] == m and not d["bootstrap"])
        monthly[m] = {"sets": s, "decisions": n, "per100": round(100 * n / s, 1) if s else None}
    by_pos = defaultdict(list)
    for d in own:
        vs = [v for v in R.versions(d["repo"]) if v["parsed"]]
        keys = [x["key"] for x in vs[-1]["parsed"]["decisions"]] if vs else []
        if d["key"] in keys:
            by_pos["first half" if keys.index(d["key"]) < len(keys) / 2 else "second half"].append(len(d["norm"]))
    return {"weeks": WEEKS, "series": series, "cum_by_repo": cum, "rate": rate, "n_own": len(own),
            "n_copied": len(copied), "fleet_per100": round(100 * fleet_dec / fleet_sets, 1) if fleet_sets else None,
            "fleet_dec_since": fleet_dec, "fleet_sets_since": fleet_sets, "monthly": monthly,
            "len_by_pos": {k: median(v) for k, v in by_pos.items()},
            "undated": sorted(f"{d['repo']}: {d['heading']}" for d in own if not d["date"])}


# ---------------------------------------------------------------- Q decision-timing

LAG_BUCKETS = ["Within 2 days", "3–14 days", "15+ days later", "No date in heading"]


def lag_bucket(d):
    if not d["date"]:
        return LAG_BUCKETS[3]
    lag = (date.fromisoformat(d["first_day"]) - date.fromisoformat(d["date"])).days
    return LAG_BUCKETS[0] if lag <= 2 else LAG_BUCKETS[1] if lag <= 14 else LAG_BUCKETS[2]


def q_decision_timing(con):
    idx = decision_index(con)
    origin = copy_labels(con)
    own = [d for k, d in idx.items() if k not in origin]
    for d in own:
        d["lag"] = (date.fromisoformat(d["first_day"]) - date.fromisoformat(d["date"])).days if d["date"] else None
    series = {b: [sum(1 for d in own if week_of(d["first_day"]) == w and lag_bucket(d) == b) for w in WEEKS]
              for b in LAG_BUCKETS}
    split = {}
    for name, ds in (("Written with the first version", [d for d in own if d["bootstrap"]]),
                     ("Added later", [d for d in own if not d["bootstrap"]])):
        split[name] = [sum(1 for d in ds if lag_bucket(d) == b) for b in LAG_BUCKETS]
    later = [d for d in own if not d["bootstrap"] and d["lag"] is not None]
    boot = [d for d in own if d["bootstrap"] and d["lag"] is not None]
    negative = [d for d in own if d["lag"] is not None and d["lag"] < 0]
    worst = sorted((d for d in own if d["lag"] is not None), key=lambda d: -d["lag"])[:5]
    return {"weeks": WEEKS, "series": series, "split": split, "buckets": LAG_BUCKETS,
            "median_later": median([d["lag"] for d in later]), "median_boot": median([d["lag"] for d in boot]),
            "n_later": len(later), "n_boot": len(boot),
            "later_within2": sum(1 for d in later if d["lag"] <= 2),
            "negative": [f"{d['repo']}: {d['heading']} (first seen {d['first_day']})" for d in negative],
            "worst": [f"{d['repo']}: {d['heading']} — in the record {d['first_day']}, lag {d['lag']} d" for d in worst]}


# ---------------------------------------------------------------- Q template-inheritance

def q_template_inheritance(con):
    idx = decision_index(con)
    origin = copy_labels(con)
    repos = [r for r in in_scope(con) if R.versions(r)]
    stock = {"Own decisions": [], "Copied from another repo": []}
    for w in WEEKS:
        end = week_end(w)
        own = cop = 0
        for r in repos:
            v = record_at(r, end)
            if not v:
                continue
            for d in v["parsed"]["decisions"]:
                if (r, d["key"]) in origin:
                    cop += 1
                else:
                    own += 1
        stock["Own decisions"].append(own)
        stock["Copied from another repo"].append(cop)
    now = {}
    for r in repos:
        v = R.versions(r)[-1]
        ds = v["parsed"]["decisions"] if v["parsed"] else []
        now[r] = {"own": sum(1 for d in ds if (r, d["key"]) not in origin),
                  "copied": sum(1 for d in ds if (r, d["key"]) in origin)}
    order = sorted(repos, key=lambda r: (-(now[r]["copied"] / max(1, now[r]["own"] + now[r]["copied"])), r))
    # Template decisions made after the clones existed: how long until each clone carried them.
    clones = [r for r in repos if r != TEMPLATE and any(o[0] == TEMPLATE for (rr, k), o in origin.items() if rr == r)]
    tmpl = [d for (r, k), d in idx.items() if r == TEMPLATE]
    prop = []
    for d in sorted(tmpl, key=lambda d: d["first_day"]):
        row = {"heading": d["heading"], "template_day": d["first_day"], "clones": {}}
        for c in clones:
            if first_commit(c) > d["first_day"]:
                row["clones"][c] = "born after"
                continue
            got = [x for (rr, k), o in origin.items() if rr == c and o == (TEMPLATE, d["key"])
                   for x in [idx[(rr, k)]]]
            # the same decision can reach a clone first and the template second
            got += [idx[(c, d["key"])]] if (c, d["key"]) in idx and (c, d["key"]) not in origin else []
            row["clones"][c] = (date.fromisoformat(got[0]["first_day"]) - date.fromisoformat(d["first_day"])).days if got else None
        prop.append(row)
    reworded = [(r, idx[(r, k)]["heading"], o[0], idx[o]["heading"]) for (r, k), o in origin.items() if k != o[1]]
    return {"weeks": WEEKS, "stock": stock, "now": {r: now[r] for r in order}, "clones": clones,
            "propagation": prop, "reworded": reworded,
            "copied_now": sum(v["copied"] for v in now.values()), "all_now": sum(v["own"] + v["copied"] for v in now.values()),
            "n_exact": sum(1 for (r, k), o in origin.items() if k == o[1]), "n_model": len(reworded)}


# ---------------------------------------------------------------- Q fleet-architecture-home

FLEET_FACTS = [
    ("Port range 33000–33099", r"33000[-–]33099|port[- ]range"),
    ("hero-template is the template", r"hero-template"),
    ("Register lives in the fleet (.fleet/)", r"\.fleet/|fleet register|fleet-level register|family register"),
    ("Shared stack: TanStack Start UI", r"TanStack Start"),
    ("Shared stack: vendored @aihero registry", r"@aihero"),
    ("Sibling repos are mapped in FLEET.md", r"FLEET\.md"),
]


def q_fleet_architecture_home(con):
    repos = in_scope(con)
    fleet_section = lambda t: bool(t and re.search(r"^## Fleet\b", t, re.M))
    carry = {"`## Fleet` section in AGENTS.md": [], "A copy of the register (CONSISTENCY.md)": [],
             "DESIGN.md shares a decision with another repo": []}
    origin = copy_labels(con)
    agents = {r: R.file_versions(r, "AGENTS.md") for r in repos}
    cons = {r: R.file_versions(r, "CONSISTENCY.md") for r in repos}
    at = lambda vs, end: next((t for s, d, t in reversed(vs) if d <= end), None)
    for w in WEEKS:
        end = week_end(w)
        carry["`## Fleet` section in AGENTS.md"].append(sum(1 for r in repos if fleet_section(at(agents[r], end))))
        carry["A copy of the register (CONSISTENCY.md)"].append(sum(1 for r in repos if at(cons[r], end)))
        n = 0
        for r in repos:
            v = record_at(r, end)
            if v and any((r, d["key"]) in origin for d in v["parsed"]["decisions"]):
                n += 1
        carry["DESIGN.md shares a decision with another repo"].append(n)
    facts = []
    for name, pat in FLEET_FACTS:
        hits = defaultdict(list)
        for r in repos:
            for f in DOC_FILES:
                t = R.head_text(r, f)
                if t and re.search(pat, t, re.I):
                    hits[r].append(f)
        facts.append({"fact": name, "repos": len(hits), "files": sum(len(v) for v in hits.values()),
                      "where": {r: v for r, v in sorted(hits.items())}})
    fleet_md = os.path.join(FLEET_ROOT, "FLEET.md")
    fm = open(fleet_md).read() if os.path.exists(fleet_md) else ""
    reg_log = subprocess.run(["git", "-C", FLEET_REGISTER, "log", "--reverse", "--format=%cs"], capture_output=True,
                             text=True).stdout.split()
    return {"weeks": WEEKS, "carry": carry, "facts": facts, "fleet_md_lines": len(fm.splitlines()),
            "fleet_md_sections": re.findall(r"^## (.+)$", fm, re.M), "register_first": reg_log[0] if reg_log else None,
            "register_commits": len(reg_log), "n_repos": len(repos),
            "wayfare_design_mentions_fleet": bool(re.search(r"fleet", R.head_text("wayfare-skills", "DESIGN.md") or "", re.I))}


# ---------------------------------------------------------------- Q append-only-decisions

def q_append_only_decisions(con):
    """Follow each decision entry across versions: kept, edited in place, removed; superseding entries separately."""
    events = []
    per_repo = defaultdict(lambda: defaultdict(int))
    examples = defaultdict(list)
    for r in in_scope(con):
        vs = [v for v in R.versions(r)]
        prev = None
        for v in vs:
            if not v["parsed"]:
                for k in prev or {}:
                    events.append((v["day"], "Removed", r))
                    per_repo[r]["removed"] += 1
                    per_repo[r]["deleted_with_record"] += 1
                if prev:
                    examples["record deleted"].append(f"{r} {v['day']}: record deleted with {len(prev)} decisions")
                prev = {} if prev is not None else None
                continue
            cur = {d["key"]: d for d in v["parsed"]["decisions"]}
            if not prev:
                for k in cur:
                    events.append((v["day"], "Added", r))
                prev = cur
                continue
            new = [k for k in cur if k not in prev]
            gone = [k for k in prev if k not in cur]
            renamed = set()
            for g in gone:
                match = max(new, key=lambda k: SequenceMatcher(None, prev[g]["norm"][:800], cur[k]["norm"][:800]).ratio(),
                            default=None)
                if match and SequenceMatcher(None, prev[g]["norm"][:800], cur[match]["norm"][:800]).ratio() > 0.6:
                    renamed.add(match)
                    events.append((v["day"], "Edited in place", r))
                    per_repo[r]["heading"] += 1
                    examples["heading"].append(f"{r} {v['day']}: '{prev[g]['heading']}' -> '{cur[match]['heading']}'")
                else:
                    events.append((v["day"], "Removed", r))
                    per_repo[r]["removed"] += 1
                    examples["removed"].append(f"{r} {v['day']}: {prev[g]['heading']}")
            for k in new:
                if k not in renamed:
                    events.append((v["day"], "Added", r))
            for k in cur:
                if k in prev and cur[k]["norm"] != prev[k]["norm"]:
                    ratio = SequenceMatcher(None, prev[k]["norm"], cur[k]["norm"]).ratio()
                    kind = "Edited in place" if ratio < 0.97 else "Touched up (under 3% changed)"
                    events.append((v["day"], kind, r))
                    per_repo[r]["edited" if ratio < 0.97 else "touched"] += 1
                    if ratio < 0.97:
                        examples["edited"].append(f"{r} {v['day']}: {cur[k]['heading']} (similarity {ratio:.2f})")
            prev = cur
    cats = ["Added", "Edited in place", "Touched up (under 3% changed)", "Removed"]
    series = {c: [sum(1 for d, k, r in events if k == c and week_of(d) == w) for w in WEEKS] for c in cats}
    idx = decision_index(con)
    supersede = [d for d in idx.values() if re.search(r"supersed", d["heading"], re.I)]
    now = {}
    for r in in_scope(con):
        if not R.versions(r):
            continue
        n_ever = sum(1 for (rr, k) in idx if rr == r)
        now[r] = {"ever": n_ever, **{k: per_repo[r][k] for k in ("edited", "touched", "heading", "removed", "deleted_with_record")}}
    tot = {c: sum(series[c]) for c in cats}
    return {"weeks": WEEKS, "series": series, "totals": tot, "by_repo": now, "examples": examples,
            "supersede_entries": [f"{d['repo']}: {d['heading']}" for d in supersede],
            "n_decisions": len(idx)}


# ---------------------------------------------------------------- Q design-record-writers

@lru_cache(maxsize=None)
def files_of(con):
    out = defaultdict(set)
    for r in rows(con, "SELECT repo, sha, files_json FROM pr_commits.pr_commits WHERE files_json IS NOT NULL"):
        for f in json.loads(r["files_json"] or "[]"):
            out[(r["repo"], r["sha"])].add(f["path"] if isinstance(f, dict) else f)
    for r in rows(con, "SELECT repo, sha, path FROM git.commit_files"):
        if (r["repo"], r["sha"]) not in out or r["path"]:
            out.setdefault((r["repo"], r["sha"]), set()).add(r["path"])
    return out


def is_doc(path):
    return path.endswith(".md") or path.startswith("docs/")


@lru_cache(maxsize=None)
def arch_skill_prs(con):
    """PRs linked from a session that ran the architecture skill (sessions start 9 Aug)."""
    sess = {r["session_id_hash"] for r in rows(con, "SELECT DISTINCT session_id_hash FROM harness.tool_calls "
                                                   "WHERE skill_name LIKE '%architecture%'")}
    asked = {r["session_id_hash"] for r in rows(con, "SELECT DISTINCT session_id_hash FROM harness.asks")}
    prs, prs_asked = set(), set()
    for s in rows(con, "SELECT session_id_hash, repo, pr_links FROM harness.sessions WHERE pr_links NOT IN ('', '[]')"):
        if s["session_id_hash"] not in sess:
            continue
        for link in json.loads(s["pr_links"]):
            m = re.match(r"[^/]+/([^#]+)#(\d+)$", link)
            if m:
                k = (m.group(1).replace("hero-skills", "wayfare-skills"), int(m.group(2)))
                prs.add(k)
                if s["session_id_hash"] in asked:
                    prs_asked.add(k)
    return prs, prs_asked, len(sess), len(sess & asked)


def q_design_record_writers_writes(con):
    fo = files_of(con)
    prs, prs_asked, n_sess, n_sess_asked = arch_skill_prs(con)
    cats = ["Record edited with code", "Record-only change, architecture skill", "Record-only change, other"]
    touched = []
    for f in work_sets(con):
        files = set().union(*(fo.get((f["repo"], s), set()) for s in f["shas"])) if f["shas"] else set()
        if not files & set(R.RECORD_PATHS):
            continue
        only_docs = all(is_doc(p) for p in files)
        c = cats[0] if not only_docs else cats[1] if (f["repo"], f["pr"]) in prs else cats[2]
        touched.append(dict(f, cls=c))
    series = {c: [sum(1 for t in touched if t["cls"] == c and t["week"] == w) for w in WEEKS] for c in cats}
    all_wk = defaultdict(int)
    for f in work_sets(con):
        all_wk[f["week"]] += 1
    since = [f for f in work_sets(con) if f["day"] >= "2026-07-30"]
    t_since = [t for t in touched if t["day"] >= "2026-07-30"]
    by_repo = defaultdict(lambda: defaultdict(int))
    for t in touched:
        by_repo[t["repo"]][t["cls"]] += 1
    order = sorted(by_repo, key=lambda r: -sum(by_repo[r].values()))
    heads = {(r["repo"], r["number"]): r["head_ref"] or "" for r in rows(con, "SELECT repo, number, head_ref FROM github.prs")}
    recent = [t for t in touched if t["week"] >= "2026-W38"]
    return {"recent": len(recent), "recent_goal": sum(1 for t in recent if "goal-" in heads.get((t["repo"], t["pr"]), "")),
            "weeks": WEEKS, "series": series, "n": len(touched), "share_since": share(len(t_since), len(since)),
            "n_since": len(t_since), "sets_since": len(since),
            "cls_totals": {c: sum(1 for t in touched if t["cls"] == c) for c in cats},
            "by_repo": {r: [by_repo[r][c] for c in cats] for r in order}, "cats": cats,
            "skill_sessions": n_sess, "skill_sessions_asked": n_sess_asked,
            "skill_prs_touching": sum(1 for t in touched if (t["repo"], t["pr"]) in prs),
            "skill_prs_asked_touching": sum(1 for t in touched if (t["repo"], t["pr"]) in prs_asked)}


# ---------------------------------------------------------------- Q design-record-lag

ANCHOR_CATS = ["Current (0–3 behind)", "Stale (4–20)", "Very stale (20+)", "Anchor not in this repo", "No design record"]


@lru_cache(maxsize=None)
def main_sha_of_sets(con):
    out = defaultdict(list)
    units = {(r["repo"], r["unit_kind"], r["unit_id"]): r["main_sha"] for r in rows(con, "SELECT * FROM detectors.cs_units")}
    for f in work_sets(con):
        out[f["repo"]].append((units.get((f["repo"], f["unit_kind"], f["unit_id"])), f["day"]))
    return out


def anchor_lag(con, repo, end):
    """(category, change sets merged after the anchor up to `end`) for the record as it stood on `end`."""
    v = record_at(repo, end)
    if not v:
        return ANCHOR_CATS[4], None
    a = v["parsed"]["anchor"]
    mc = R.main_commits(repo)
    pos = {s: i for i, (s, d) in enumerate(mc)}
    full = None
    if a:
        full = next((s for s in pos if s.startswith(a)), None)
        if not full:
            day = R.commit_day(repo, a)
            if day is None:
                return ANCHOR_CATS[3], None
            # an anchor off the first-parent line (a PR-branch commit): count from its day
            n = sum(1 for s, d in main_sha_of_sets(con)[repo] if day < d <= end)
            return (ANCHOR_CATS[0] if n <= 3 else ANCHOR_CATS[1] if n <= 20 else ANCHOR_CATS[2]), n
    if not a:
        return ANCHOR_CATS[3], None
    i = pos[full]
    n = sum(1 for s, d in main_sha_of_sets(con)[repo] if s in pos and pos[s] > i and d <= end)
    return (ANCHOR_CATS[0] if n <= 3 else ANCHOR_CATS[1] if n <= 20 else ANCHOR_CATS[2]), n


def q_design_record_lag_anchor(con):
    ad = adoption(con)
    repos = [r for r in in_scope(con) if ad[r]["category"] in APPS]
    series = {c: [0] * len(WEEKS) for c in ANCHOR_CATS}
    lag = {r: [None] * len(WEEKS) for r in repos}
    for i, w in enumerate(WEEKS):
        end = week_end(w)
        for r in repos:
            if first_commit(r) > end:
                continue
            c, n = anchor_lag(con, r, end)
            series[c][i] += 1
            lag[r][i] = n
    monthly = {r: [anchor_lag(con, r, min(month_end(m), "2026-10-01"))[1] for m in MONTHS] for r in repos}
    now = {r: anchor_lag(con, r, "2026-10-01") for r in repos}
    from evolution import q_design_md_staleness_design
    q_design_md_staleness = q_design_md_staleness_design(con)["now"]
    # Each change of anchor is a check of the record against the code: how much had built up by then.
    refresh = []
    for r in repos:
        prev = None
        for v in R.versions(r):
            a = v["parsed"]["anchor"] if v["parsed"] else None
            if a and prev and a != prev and R.commit_day(r, prev):
                before = anchor_lag(con, r, (date.fromisoformat(v["day"]) - timedelta(days=1)).isoformat())[1]
                refresh.append({"repo": r, "day": v["day"], "behind_before": before})
            prev = a or prev
    gaps = []
    for r in repos:
        days = sorted({x["day"] for x in refresh if x["repo"] == r})
        gaps += [(date.fromisoformat(b) - date.fromisoformat(a)).days for a, b in zip(days, days[1:])]
    order = sorted(repos, key=lambda r: -(now[r][1] or 0))
    return {"refresh": refresh, "refresh_n": len(refresh),
            "refresh_median_behind": median([x["behind_before"] for x in refresh if x["behind_before"] is not None]),
            "refresh_median_gap_days": median(gaps),
            "weeks": WEEKS, "series": series, "by_repo_month": {r: monthly[r] for r in order if any(monthly[r])},
            "now": now, "q_design_md_staleness_now": q_design_md_staleness}


# ---------------------------------------------------------------- Q design-record-sections

@lru_cache(maxsize=None)
def has_ui(repo):
    tree = R.git(repo, "ls-tree", "-d", "--name-only", "HEAD", "ui", "src/routes") or ""
    return bool(tree.strip())


def missing_sections(repo, sections):
    need = CORE_SECTIONS + (PRODUCT_SECTIONS if has_ui(repo) else [])
    have = [s.lower() for s in sections]
    miss = [n for n in need if not any(h.startswith(n.lower()) for h in have)]
    extra = [s for s in sections if not any(s.lower().startswith(n.lower()) for n in CORE_SECTIONS + PRODUCT_SECTIONS)]
    wrong = [n for n in PRODUCT_SECTIONS if not has_ui(repo) and any(h.startswith(n.lower()) for h in have)]
    return miss, extra, wrong


def q_design_record_sections(con):
    repos = [r for r in in_scope(con) if R.versions(r)]
    cats = ["Every required section", "Missing 1–2", "Missing 3 or more"]
    series = {c: [0] * len(WEEKS) for c in cats}
    for i, w in enumerate(WEEKS):
        for r in repos:
            v = record_at(r, week_end(w))
            if not v:
                continue
            miss = missing_sections(r, v["parsed"]["sections"])[0]
            series[cats[0] if not miss else cats[1] if len(miss) <= 2 else cats[2]][i] += 1
    now = {}
    for r in repos:
        v = R.versions(r)[-1]
        miss, extra, wrong = missing_sections(r, v["parsed"]["sections"])
        now[r] = {"missing": miss, "extra": extra, "wrong": wrong, "ui": has_ui(r)}
    first_full = {}
    for r in repos:
        for v in R.versions(r):
            if v["parsed"] and not missing_sections(r, v["parsed"]["sections"])[0]:
                first_full[r] = v["day"]
                break
    groups = {"Architecture": ["Overview", "Tech stack", "Codemap", "Boundaries", "Invariants"],
              "Product (users, flows, interaction)": PRODUCT_SECTIONS, "Decisions": ["Decisions"]}
    content = {}
    topics = {"a data store": r"\b(Mongo|Redis|Postgres|SQLite|MySQL)", "design tokens": r"\btokens?\b",
              "a tech stack": r"^## Tech stack", "dated decisions": r"^### \d{4}-\d{2}-\d{2}"}
    for r in repos:
        text = R.versions(r)[-1]["text"]
        per = defaultdict(int)
        cur = None
        for line in text.splitlines():
            if line.startswith("## "):
                name = line[3:].strip()
                cur = next((g for g, secs in groups.items() if any(name.lower().startswith(s.lower()) for s in secs)),
                           "Other sections")
            elif cur:
                per[cur] += 1
        content[r] = {"lines": dict(per), "topics": {t: bool(re.search(p, text, re.M | re.I)) for t, p in topics.items()}}
    order = sorted(repos, key=lambda r: -sum(content[r]["lines"].values()))
    return {"weeks": WEEKS, "series": series, "now": {r: now[r] for r in order}, "first_full": first_full,
            "content": {r: content[r] for r in order}, "groups": list(groups) + ["Other sections"]}


# ---------------------------------------------------------------- Q decision-in-same-change

TRACE_CATS = ["Written with the record's first version", "Same change set as the code", "Same PR, its own change set",
              "Record-only PR", "Pushed to main"]


def q_decision_in_same_change_trace(con):
    idx = decision_index(con)
    origin = copy_labels(con)
    own = [d for k, d in idx.items() if k not in origin]
    pr_of = {(r["repo"], r["sha"]): r["pr_number"] for r in rows(con, "SELECT repo, sha, pr_number FROM git.commits")}
    fo = files_of(con)
    sets_by_pr = defaultdict(list)
    for f in changeset_facts(con):
        if f["pr"]:
            sets_by_pr[(f["repo"], f["pr"])].append(f)
    pr_commits = defaultdict(list)
    for r in rows(con, "SELECT repo, pr_number, sha, idx FROM pr_commits.pr_commits WHERE is_merge=0 ORDER BY idx"):
        pr_commits[(r["repo"], r["pr_number"])].append(r["sha"])
    out = []
    for d in own:
        if d["bootstrap"]:
            out.append(dict(d, cls=TRACE_CATS[0]))
            continue
        pr = pr_of.get((d["repo"], d["first_sha"]))
        if not pr:
            out.append(dict(d, cls=TRACE_CATS[4]))
            continue
        sets = sets_by_pr.get((d["repo"], pr), [])
        # the original commit that first carries the heading in the record
        adder = None
        for sha in pr_commits.get((d["repo"], pr), []):
            if not fo.get((d["repo"], sha), set()) & set(R.RECORD_PATHS):
                continue
            txt = R.git(d["repo"], "show", f"{sha}:DESIGN.md") or R.git(d["repo"], "show", f"{sha}:ARCHITECTURE.md") or ""
            if d["heading"] in txt:
                adder = sha
                break
        pr_files = set().union(*(fo.get((d["repo"], s), set()) for s in pr_commits.get((d["repo"], pr), [d["first_sha"]])))
        pr_code = any(not is_doc(p) for p in pr_files)
        if not pr_code:
            cls = TRACE_CATS[3]
        else:
            home = next((s for s in sets if adder and adder in s["shas"]), None)
            if home is None and len(sets) == 1:
                home = sets[0]
            if home is None:
                cls = TRACE_CATS[2]
            else:
                set_files = set().union(*(fo.get((d["repo"], s), set()) for s in home["shas"]))
                cls = TRACE_CATS[1] if any(not is_doc(p) for p in set_files) else TRACE_CATS[2]
        out.append(dict(d, cls=cls, pr=pr))
    series = {c: [sum(1 for d in out if d["cls"] == c and week_of(d["first_day"]) == w) for w in WEEKS]
              for c in TRACE_CATS}
    by_repo = defaultdict(lambda: defaultdict(int))
    for d in out:
        by_repo[d["repo"]][d["cls"]] += 1
    order = sorted(by_repo, key=lambda r: -sum(by_repo[r].values()))
    later = [d for d in out if d["cls"] != TRACE_CATS[0]]
    return {"weeks": WEEKS, "series": series, "cats": TRACE_CATS,
            "totals": {c: sum(1 for d in out if d["cls"] == c) for c in TRACE_CATS},
            "by_repo": {r: [by_repo[r][c] for c in TRACE_CATS] for r in order}, "n_later": len(later),
            "examples": {c: [f"{d['repo']} #{d.get('pr')}: {d['heading']}" for d in out if d["cls"] == c][:4]
                         for c in TRACE_CATS}}



# ---------------------------------------------------------------- Q decision-in-same-change, timing

TIMING = ["With the code", "Record-only change", "Before the code", "Unknown"]
DOOR = ["One-way door (item says so)", "Not a one-way door (item says so)", "Item without the flag", "No linked item"]
LINK_RE = re.compile(r"\.plans/items?/(\d+)|\bitem (\d+)\b|#(\d+)\b")


def _items_by_pr(con):
    """{(repo, pr): [items]} from each item's `pr` ledger or its `branch` (the PR's head), plus {(repo, id): item}."""
    by_pr, by_branch, by_id = defaultdict(list), defaultdict(list), {}
    for it in rows(con, "SELECT repo, item_id, title, done_ts, raw_frontmatter_json j FROM plans.plan_items WHERE type != 'goal'"):
        fm = json.loads(it["j"] or "{}")
        rec = dict(it, one_way=fm.get("one_way_door"), shape=fm.get("shape"))
        by_id[(it["repo"], str(it["item_id"]).lstrip("0"))] = rec
        prs = fm.get("pr") or []
        for u in ([prs] if isinstance(prs, str) else prs):
            m = re.search(r"/pull/(\d+)", str(u))
            if m:
                by_pr[(it["repo"], int(m.group(1)))].append(rec)
        if isinstance(fm.get("branch"), str):
            by_branch[(it["repo"], fm["branch"])].append(rec)
    for r in rows(con, "SELECT repo, number, head_ref FROM github.prs WHERE head_ref IS NOT NULL"):
        for rec in by_branch.get((r["repo"], r["head_ref"]), []):
            if rec not in by_pr[(r["repo"], r["number"])]:
                by_pr[(r["repo"], r["number"])].append(rec)
    return by_pr, by_id


def q_decision_in_same_change_timing(con):
    """Every own decision with its PR, files and timing class; the one-way-door flag comes from the work item that
    ledgers the PR, or the decision text itself."""
    idx = decision_index(con)
    origin = copy_labels(con)
    own = [d for k, d in idx.items() if k not in origin]
    pr_of = {(r["repo"], r["sha"]): r["pr_number"] for r in rows(con, "SELECT repo, sha, pr_number FROM git.commits")}
    merged = {(r["repo"], r["pr_number"]): r["day"] for r in rows(con, "SELECT repo, pr_number, day FROM git.commits WHERE pr_number IS NOT NULL")}
    fo = files_of(con)
    sets_by_pr = defaultdict(list)
    for f in changeset_facts(con):
        if f["pr"]:
            sets_by_pr[(f["repo"], f["pr"])].append(f)
    pr_commits = defaultdict(list)
    for r in rows(con, "SELECT repo, pr_number, sha, idx FROM pr_commits.pr_commits WHERE is_merge=0 ORDER BY idx"):
        pr_commits[(r["repo"], r["pr_number"])].append(r["sha"])
    by_pr, by_id = _items_by_pr(con)
    out = []
    for d in own:
        row = dict(repo=d["repo"], heading=d["heading"], first_day=d["first_day"], dated=d["date"], pr=None, trace=None,
                   timing=None, door=DOOR[3], item=None, names=None, named_merged=None,
                   backfilled=bool(d["date"]) and d["date"] < d["first_day"])
        if d["bootstrap"]:
            row.update(trace=TRACE_CATS[0], timing=TIMING[3])
            out.append(row)
            continue
        pr = pr_of.get((d["repo"], d["first_sha"]))
        if not pr:
            row.update(trace=TRACE_CATS[4], timing=TIMING[3])
            out.append(row)
            continue
        row["pr"] = pr
        sets = sets_by_pr.get((d["repo"], pr), [])
        adder = None
        for sha in pr_commits.get((d["repo"], pr), []):
            if not fo.get((d["repo"], sha), set()) & set(R.RECORD_PATHS):
                continue
            txt = R.git(d["repo"], "show", f"{sha}:DESIGN.md") or R.git(d["repo"], "show", f"{sha}:ARCHITECTURE.md") or ""
            if d["heading"] in txt:
                adder = sha
                break
        pr_files = set().union(*(fo.get((d["repo"], s), set()) for s in pr_commits.get((d["repo"], pr), [d["first_sha"]])))
        if not any(not is_doc(p) for p in pr_files):
            row["trace"] = TRACE_CATS[3]
            # a record-only decision that names a PR or item: before the code if that landed after the record
            names = [next(g for g in m.groups() if g) for m in LINK_RE.finditer(d["heading"] + " " + d["body"])]
            later = []
            for n in names:
                day = merged.get((d["repo"], int(n)))
                it = by_id.get((d["repo"], n.lstrip("0")))
                if day is None and it and it["done_ts"]:
                    day = it["done_ts"][:10]
                if day:
                    later.append(day > d["first_day"])
            row.update(names=names, named_merged=later,
                       timing=TIMING[2] if later and any(later) else TIMING[1])
        else:
            home = next((s for s in sets if adder and adder in s["shas"]), None)
            if home is None and len(sets) == 1:
                home = sets[0]
            if home is None:
                row["trace"] = TRACE_CATS[2]
            else:
                set_files = set().union(*(fo.get((d["repo"], s), set()) for s in home["shas"]))
                row["trace"] = TRACE_CATS[1] if any(not is_doc(p) for p in set_files) else TRACE_CATS[2]
            row["timing"] = TIMING[0]
        items = by_pr.get((d["repo"], pr), [])
        if items:
            row["item"] = ", ".join(str(i["item_id"]) for i in items)
            flags = [i["one_way"] for i in items]
            row["door"] = DOOR[0] if any(f is True for f in flags) else DOOR[1] if any(f is False for f in flags) else DOOR[2]
        if re.search(r"one-way door|one way door", d["body"], re.I):
            row["door"] = DOOR[0]
        out.append(row)
    later = [r for r in out if r["timing"] != TIMING[3]]
    def shares(rs):
        n = len(rs)
        return {t: sum(1 for r in rs if r["timing"] == t) for t in TIMING} | {"n": n}
    groups = {"All own decisions": out} | {g: [r for r in out if r["door"] == g] for g in DOOR}
    by_repo = defaultdict(lambda: Counter())
    for r in out:
        by_repo[r["repo"]][r["timing"]] += 1
    order = sorted(by_repo, key=lambda k: -sum(by_repo[k].values()))
    record_only = [r for r in out if r["timing"] == TIMING[1]]
    return {"rows": out, "timing": TIMING, "door": DOOR, "n": len(out), "n_known": len(later),
            "totals": shares(out), "known": shares(later), "groups": {g: shares(rs) for g, rs in groups.items()},
            "trace": Counter(r["trace"] for r in out), "n_record_only": len(record_only),
            "backfilled": sum(1 for r in record_only if r["backfilled"]),
            "record_only_prs": Counter((r["repo"], r["pr"]) for r in record_only).most_common(3),
            "n_linked": sum(1 for r in out if r["item"]),
            "by_repo": {k: [by_repo[k][t] for t in TIMING] for k in order},
            "examples": {t: [f"{r['repo']} #{r['pr']}: {r['heading']}" for r in out if r["timing"] == t][:4] for t in TIMING}}

# ---------------------------------------------------------------- Q work-items-cite-design

CITE_RE = re.compile(r"DESIGN\.md|ARCHITECTURE\.md|design record|architecture record", re.I)


def q_work_items_cite_design(con):
    idx = decision_index(con)
    heads = defaultdict(list)
    for (r, k), d in idx.items():
        if len(k) >= 20:
            heads[r].append(k)
    items = rows(con, "SELECT repo, item_id, title, created_ts, day, file_path, raw_frontmatter_json j FROM plans.plan_items "
                      "WHERE type != 'goal' AND day IS NOT NULL")
    arch = []
    for it in items:
        if it["repo"] not in adoption(con):
            continue
        fm = json.loads(it["j"] or "{}")
        is_arch = fm.get("one_way_door") is True or fm.get("shape") == "structural"
        if not is_arch:
            continue
        try:
            text = open(it["file_path"]).read()
        except OSError:
            text = ""
        norm = re.sub(r"[^a-z0-9]+", " ", text.lower())
        cites_file = bool(CITE_RE.search(text))
        cites_dec = any(k in norm for k in heads[it["repo"]])
        arch.append(dict(it, why="one-way door" if fm.get("one_way_door") is True else "structural",
                         cites=cites_file or cites_dec, cites_dec=cites_dec, readable=bool(text)))
    wk = defaultdict(list)
    for a in arch:
        wk[week_of(a["day"])].append(a["cites"])
    cited = [sum(wk[w]) for w in WEEKS]
    not_cited = [len(wk[w]) - sum(wk[w]) for w in WEEKS]
    ow = [a for a in arch if a["why"] == "one-way door"]
    # the reverse link: a decision added after items existed that names an item or a PR
    dec_links = [d for d in idx.values() if not d["bootstrap"] and d["first_day"] >= "2026-07-23"]
    dec_named = sum(1 for d in dec_links if re.search(r"\.plans/|item \d+|#\d+|PR ", d["body"]))
    return {"weeks": WEEKS, "series": {"Cites the design record": cited, "Doesn't cite it": not_cited},
            "n": len(arch), "cited": sum(a["cites"] for a in arch), "cites_dec": sum(a["cites_dec"] for a in arch),
            "one_way": len(ow), "one_way_cited": sum(a["cites"] for a in ow), "unreadable": sum(1 for a in arch if not a["readable"]),
            "structural": sum(1 for a in arch if a["why"] == "structural"),
            "structural_cited": sum(1 for a in arch if a["why"] == "structural" and a["cites"]),
            "dec_later": len(dec_links), "dec_named": dec_named,
            "by_repo": {r: (sum(1 for a in arch if a["repo"] == r), sum(1 for a in arch if a["repo"] == r and a["cites"]))
                        for r in sorted({a["repo"] for a in arch})}}


# ---------------------------------------------------------------- Q repeated-facts-agree

FACTS = {
    "Go version": {"code": [(lambda b: b == "go.mod", r"^go (1\.\d+)")], "doc": r"\bGo (1\.\d{2})\b"},
    "Node major": {"code": [(lambda b: b.startswith("Dockerfile"), r"(?:node:|nodejs)(\d{2})"),
                            (lambda b: b == ".nvmrc", r"^v?(\d{2})")],
                   "doc": r"(?:\bNode(?:\.js)?\s+v?|\bnodejs|\bnode:\s?\"?)(\d{2})\b"},
    "Debian release of the base image": {"code": [(lambda b: b.startswith("Dockerfile"), r"nodejs\d{2}-debian(\d{2})")],
                                         "doc": r"nodejs\d{2}-debian(\d{2})"},
}
CHECK_OF = {"Go version": "CTR-02", "Node major": "CTR-01", "Debian release of the base image": "CTR-04"}


def grep_at(repo, sha, pattern, paths):
    out = R.git(repo, "grep", "-h", "-o", "-i", "-P", pattern, sha, "--", *paths) or ""
    vals = set()
    rx = re.compile(pattern, re.I | re.M)
    for line in out.splitlines():
        m = rx.search(line)
        if m:
            vals.add(m.group(1))
    return vals


def q_repeated_facts_agree(con):
    repos = [r for r in in_scope(con) if R.versions(r)]
    months = [m for m in MONTHS if m >= "2026-07"]
    cats = ["Docs agree with the code", "Docs state another value"]
    per_month = {c: [0] * len(months) for c in cats}
    detail = {}
    for j, m in enumerate(months):
        end = min(month_end(m), "2026-10-01")
        for r in repos:
            mc = [s for s, d in R.main_commits(r) if d <= end]
            if not mc:
                continue
            sha = mc[-1]
            for fact, spec in FACTS.items():
                tree = [p for p in (R.git(r, "ls-tree", "-r", "--name-only", sha) or "").splitlines()
                        if "node_modules" not in p]
                code = set()
                for pred, pat in spec["code"]:
                    paths = [p for p in tree if pred(os.path.basename(p))]
                    code |= grep_at(r, sha, pat, paths) if paths else set()
                if not code:
                    continue
                docs = grep_at(r, sha, spec["doc"], list(DOC_FILES))
                if not docs:
                    continue
                if fact == "Go version":
                    code = {c.split(".")[0] + "." + c.split(".")[1] for c in code}
                agree = docs <= code
                per_month[cats[0] if agree else cats[1]][j] += 1
                if m == months[-1]:
                    stale_in = [f for f in DOC_FILES if grep_at(r, sha, spec["doc"], [f]) - code]
                    detail[(r, fact)] = {"code": sorted(code), "docs": sorted(docs), "agree": agree,
                                         "stale_in": stale_in}
    checks = {f: rows(con, "SELECT repo, result FROM knowledge.check_results WHERE check_id=?", (c,))
              for f, c in CHECK_OF.items()}
    check_pass = {f: (sum(1 for x in v if x["result"] == "✅"), sum(1 for x in v if x["result"] in ("✅", "❌")))
                  for f, v in checks.items()}
    doc_checks = rows(con, "SELECT check_id, title FROM knowledge.checks WHERE repo='fleet' AND "
                           "(raw_json LIKE '%DESIGN.md%' OR raw_json LIKE '%AGENTS.md%')")
    return {"months": months, "series": per_month, "detail": {f"{r} · {f}": v for (r, f), v in sorted(detail.items())},
            "now_disagree": sum(1 for v in detail.values() if not v["agree"]), "now_n": len(detail),
            "check_pass": check_pass, "doc_checks": [f"{c['check_id']} {c['title']}" for c in doc_checks]}


# ---------------------------------------------------------------- Q design-guardrails-fired

ARCH_CHECKS = ["ARCH-01", "ARCH-02", "ARCH-03"]


def consistency_versions():
    """(day, source, text) for every CONSISTENCY.md version: the template's (to 13 Sep), then the fleet register."""
    out = [(d, "hero-template", t) for s, d, t in R.file_versions(TEMPLATE, "CONSISTENCY.md") if t]
    log = subprocess.run(["git", "-C", FLEET_REGISTER, "log", "--format=%H %cI", "--", "CONSISTENCY.md"],
                         capture_output=True, text=True).stdout
    for line in log.splitlines():
        sha, ts = line.split()
        t = subprocess.run(["git", "-C", FLEET_REGISTER, "show", f"{sha}:CONSISTENCY.md"], capture_output=True,
                           text=True).stdout
        out.append((R.utc_day(ts), "fleet", t))
    return sorted(out, key=lambda x: x[0])


def arch_rows(text):
    """{check: {repo: result}} and {check: 'was broken in' list} for the ARCH rows of one CONSISTENCY.md."""
    res, broken = {}, {}
    header = None
    for line in text.splitlines():
        if line.startswith("| Check |"):
            header = [c.strip() for c in line.strip("|").split("|")]
            continue
        m = re.match(r"\|\s*\*\*(ARCH-0\d)\*\*", line)
        if header and m:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) != len(header):
                continue
            cols = header[1:-1]
            if cols and cols[0].lower().startswith("was broken"):
                broken[m.group(1)] = cells[1]
                cols, vals = cols[1:], cells[2:-1]
            else:
                vals = cells[1:-1]
            res[m.group(1)] = dict(zip(cols, vals))
    return res, broken


def q_design_guardrails_fired_guards(con):
    vs = consistency_versions()
    cats = ["Pass", "Fail", "Can't tell (manual)"]
    series = {c: [0] * len(WEEKS) for c in cats}
    first_seen, fired = {}, defaultdict(set)
    for d, src, t in vs:
        res, _ = arch_rows(t)
        for c, per in res.items():
            first_seen.setdefault(c, d)
            for repo, v in per.items():
                if "❌" in v:
                    fired[c].add((repo, d))
    for i, w in enumerate(WEEKS):
        end = week_end(w)
        cur = [x for x in vs if x[0] <= end]
        if not cur:
            continue
        res, _ = arch_rows(cur[-1][2])
        for c in ARCH_CHECKS:
            for repo, v in res.get(c, {}).items():
                if "✅" in v:
                    series["Pass"][i] += 1
                elif "❌" in v:
                    series["Fail"][i] += 1
                elif "?" in v:
                    series["Can't tell (manual)"][i] += 1
    last_res, last_broken = arch_rows(vs[-1][2]) if vs else ({}, {})
    now = {c: {k: v for k, v in last_res.get(c, {}).items()} for c in ARCH_CHECKS}
    fired_repos = {c: sorted({r for r, d in fired[c]}) for c in ARCH_CHECKS}
    first_fail = {c: min((d for r, d in fired[c]), default=None) for c in ARCH_CHECKS}
    return {"weeks": WEEKS, "series": series, "first_seen": first_seen, "fired_repos": fired_repos,
            "first_fail": first_fail, "now": now, "was_broken_in": last_broken, "n_versions": len(vs)}


def all_data(con=None):
    from cube.db import connect
    con = con or connect("architecture")
    out = {}
    for name, fn in list(globals().items()):
        if name.startswith("q_") and callable(fn) and getattr(fn, "__module__", None) == __name__:
            out[name] = fn(con)
    out["spend"] = model_spend()
    return out


if __name__ == "__main__":
    from cube.db import connect
    con = connect("architecture")
    for name in sys.argv[1:] or [n for n, fn in globals().items() if n.startswith("q_") and callable(fn) and getattr(fn, "__module__", None) == __name__]:
        print("=" * 20, name)
        r = globals()[name](con)
        print(json.dumps(r, default=str)[:3000])
