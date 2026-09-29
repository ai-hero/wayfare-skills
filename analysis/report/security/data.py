"""Security series: one function per question, each returning what its slides plot.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/security/data.py     # prints every answer's numbers

Reads the shared databases plus .analysis/data/security.sqlite, which report/security/scan.py (weekly
mirror snapshots, lockfile CVE scans, credential scan of full history) and report/security/label.py
(Haiku labels on reviews and work items) fill. Weeks are ISO weeks of 2026, W01 to W39.
"""
import json
import os
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(REPORT))
sys.path.insert(0, REPORT)
from cube.db import connect  # noqa: E402
from record import adoption, changeset_facts, rows, stage_of, week_of  # noqa: E402
from ingest.fleet import category_of  # noqa: E402

WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
MIRRORS = os.path.join(os.path.dirname(os.path.dirname(REPORT)), ".analysis", "data", "mirrors")
APPS = ("app", "app, no features yet")

# Security milestones from wayfare-skills' history (drawn in pink where a chart is about them).
SEC_EVENTS = [
    ("2026-05-05", "scan-vulns skill"),
    ("2026-07-18", "auto-approve: write-access trigger"),
    ("2026-07-19", "harden skill"),
    ("2026-09-13", "Compliance register"),
    ("2026-09-22", "audit-security stage"),
]
JUDGE_EVENTS = [
    ("2026-07-18", "Write-access trigger, secret files skipped"),
    ("2026-08-29", "Scripted gates before model (#65)"),
    ("2026-09-10", "Bot lane spoofable (#75)"),
    ("2026-09-18", "Who posted (#99-#102)"),
    ("2026-09-23", "PR text can't argue (#118)"),
]


def median(v):
    return round(statistics.median(v), 1) if v else None


def wk(day):
    return week_of(day[:10])


def ddays(a, b):
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def in_scope(con):
    return set(adoption(con))


@lru_cache(maxsize=None)
def snaps(con):
    """{repo: {week: row}} from the weekly mirror snapshots (in-scope repos only)."""
    scope = in_scope(con)
    out = defaultdict(dict)
    for r in rows(con, "SELECT * FROM security.snap"):
        if r["repo"] in scope:
            out[r["repo"]][r["week"]] = r
    return out


def first_week(weeks_map, pred):
    for w in WEEKS:
        r = weeks_map.get(w)
        if r and pred(r):
            return w
    return None


# ---------------------------------------------------------------- Q scanner-coverage scanning gates

GATES = [("Secret scanning", lambda r: r["secret_local"] or r["secret_ci"]),
         ("Secret scanning in CI", lambda r: r["secret_ci"]),
         ("Dependabot", lambda r: r["dep_update"]),
         ("Dependency scan in CI", lambda r: r["dep_scan_ci"]),
         ("Image scan in CI", lambda r: r["image_ci"])]


def q_scanner_coverage_gates(con):
    S = snaps(con)
    series = {name: [sum(1 for r in S if w in S[r] and f(S[r][w])) for w in WEEKS] for name, f in GATES}
    series = {"Repos with history": [sum(1 for r in S if w in S[r]) for w in WEEKS], **series}
    last = {r: S[r][WEEKS[-1]] for r in S if WEEKS[-1] in S[r]}
    docker = [r for r in last if last[r]["has_docker"]]
    table = []
    for r in sorted(S, key=lambda r: (category_of(r) not in APPS, r)):
        table.append({"repo": r, "category": category_of(r),
                      **{name: first_week(S[r], f) for name, f in GATES},
                      "local_only": bool(last[r]["secret_local"] and not last[r]["secret_ci"]),
                      "has_docker": bool(last[r]["has_docker"])})
    reg = {r["repo"]: r["result"] for r in rows(con, "SELECT repo, result FROM knowledge.check_results WHERE check_id='STRUCT-04'")}
    scan_runs = rows(con, """SELECT repo, workflow_name, MIN(SUBSTR(created_ts,1,10)) first, COUNT(*) n FROM github.ci_runs
                             WHERE LOWER(workflow_name) GLOB '*scan*' OR LOWER(workflow_name) GLOB '*vuln*'
                                OR LOWER(workflow_name) GLOB '*secur*' GROUP BY 1, 2""")
    return dict(series=series, n=len(last), table=table, register=reg, scan_runs=scan_runs,
                secret_any=sum(1 for r in last.values() if r["secret_local"] or r["secret_ci"]),
                secret_ci=sum(1 for r in last.values() if r["secret_ci"]),
                local_only=[r for r in last if last[r]["secret_local"] and not last[r]["secret_ci"]],
                none=[r for r in last if not (last[r]["secret_local"] or last[r]["secret_ci"])],
                dep_update=sum(1 for r in last.values() if r["dep_update"]),
                dep_scan_ci=sum(1 for r in last.values() if r["dep_scan_ci"]),
                image_ci=sum(1 for r in docker if last[r]["image_ci"]), docker=len(docker),
                image_missing=[r for r in docker if not last[r]["image_ci"]],
                first_ci_secret=min((t["Secret scanning in CI"] for t in table if t["Secret scanning in CI"]), default=None))


# ---------------------------------------------------------------- Q supply-chain-pins supply-chain pins

def q_supply_chain_pins_pins(con):
    S = snaps(con)
    act, dig, eco = [], [], []
    for w in WEEKS:
        rs = [S[r][w] for r in S if w in S[r]]
        ut, up = sum(r["uses_total"] for r in rs), sum(r["uses_pinned"] for r in rs)
        ft, fd = sum(r["from_total"] for r in rs), sum(r["from_digest"] for r in rs)
        ep = sum(len(json.loads(r["ecos_present"])) for r in rs)
        ec = sum(len(set(json.loads(r["ecos_present"])) & set(json.loads(r["ecos_covered"]))) for r in rs)
        act.append(up / ut if ut else None)
        dig.append(fd / ft if ft else None)
        eco.append(ec / ep if ep else None)
    last = {r: S[r][WEEKS[-1]] for r in S if WEEKS[-1] in S[r]}
    by_repo = []
    for r, x in sorted(last.items()):
        pres, cov = set(json.loads(x["ecos_present"])), set(json.loads(x["ecos_covered"]))
        by_repo.append({"repo": r, "actions": x["uses_pinned"] / x["uses_total"] if x["uses_total"] else None,
                        "uses": (x["uses_pinned"], x["uses_total"]),
                        "digest": x["from_digest"] / x["from_total"] if x["from_total"] else None,
                        "froms": (x["from_digest"], x["from_total"]),
                        "eco_missing": sorted(pres - cov)})
    supply = [r["check_id"] for r in rows(con, "SELECT check_id FROM knowledge.checks WHERE repo='fleet' AND control_id='C-SUPPLY'")]
    reg = defaultdict(Counter)
    for r in rows(con, "SELECT repo, check_id, result FROM knowledge.check_results"):
        if r["check_id"] in supply:
            reg[r["repo"]][r["result"]] += 1
    unpinned = []
    for r, x in last.items():
        for f in git(r, "ls-tree", "-r", "--name-only", x["sha"]).split():
            if re.match(r"^\.github/workflows/[^/]+\.ya?ml$", f):
                for line in git(r, "show", f"{x['sha']}:{f}").splitlines():
                    m = re.match(r"^\s*-?\s*uses:\s*([^\s#]+)", line)
                    if m and not line.lstrip().startswith("#") and not m.group(1).startswith("./") \
                            and "docker://" not in m.group(1) and not re.search(r"@[0-9a-f]{40}$", m.group(1)):
                        unpinned.append((r, m.group(1)))
    wk_first_full = next((w for w, v in zip(WEEKS, act) if v is not None and v >= 0.9), None)
    return dict(actions=act, digest=dig, eco=eco, by_repo=by_repo, register={k: dict(v) for k, v in reg.items()},
                supply_checks=supply, first_90=wk_first_full,
                unpinned_workflow_calls=sum(1 for _, u in unpinned if "/.github/workflows/" in u),
                unpinned_other=Counter(r for r, u in unpinned if "/.github/workflows/" not in u),
                last=dict(actions=act[-1], digest=dig[-1], eco=eco[-1]),
                unpinned_actions=sum(r["uses"][1] - r["uses"][0] for r in by_repo),
                uses_total=sum(r["uses"][1] for r in by_repo),
                a_start=next((v for v in act if v is not None), None), d_start=next((v for v in dig if v is not None), None))


# ---------------------------------------------------------------- Q security-work-share volume of security work

KINDS = [("Dependency CVE", r"cve|advisor|vulnerab|openssl|audit|lockfile|patch .*(for|to clear)|go dependency|stdlib|"
                            r"x/crypto|x/net|npm|bump|transitive|image"),
         ("Auth and sessions", r"auth|session|token|cookie|oauth|oidc|login|csrf|cors|origin|jwt|revoc|password|otp|"
                               r"azp|pkce|tenant|realm|suspend|permission|access|consent|bearer|redirect"),
         ("Secrets and data exposure", r"secret|credential|scrub|redact|pii|leak|logging|sentry|exposure|api.?key"),
         ("Headers and browser", r"header|csp|hsts|frame|xss|sanitiz|beacon|samesite"),
         ("CI and supply chain", r"pin|workflow|action|\bci\b|digest|dependabot|zizmor|least.privilege|gate|scan|"
                                 r"semgrep|approve|supply|trivy|scout")]


def kind_of(label):
    l = (label or "").lower()
    for k, rx in KINDS:
        if re.search(rx, l):
            return k
    return "Other hardening"


@lru_cache(maxsize=None)
def sec_sets(con):
    """Change sets the shared cs_worktype labels security, with their facts."""
    wt = {(r["repo"], r["unit_kind"], r["unit_id"], r["set_idx"]): r["work_type"]
          for r in rows(con, "SELECT * FROM detectors.cs_worktype")}
    facts = changeset_facts(con)
    out_all = []
    for f in facts:
        t = wt.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"]))
        out_all.append({**f, "work_type": t, "kind": kind_of(f["label"])})
    return out_all


KEYWORD_MISSES = r"secur|cve|vulnerab|secret scan|detect-secrets|csrf|xss|injection|harden|digest-pin|security header"


def q_security_work_share_volume(con):
    facts = [f for f in sec_sets(con) if f["day"] >= "2026-01-01"]
    sec = [f for f in facts if f["work_type"] == "security"]
    nondep = [f for f in facts if not f["dependabot"]]
    series = {"App": [0] * len(WEEKS), "Allied": [0] * len(WEEKS)}
    tot = Counter(f["week"] for f in nondep)
    for f in sec:
        if f["week"] in WEEKS:
            series["App" if f["category"] in APPS else "Allied"][WEEKS.index(f["week"])] += 1
    share = [(series["App"][i] + series["Allied"][i]) / tot[w] if tot[w] else None for i, w in enumerate(WEEKS)]
    per = lambda lo, hi: (sum(1 for f in sec if lo <= f["week"] <= hi), sum(1 for f in nondep if lo <= f["week"] <= hi))
    before, after = per("2026-W01", "2026-W29"), per("2026-W30", "2026-W39")
    kinds = [k for k, _ in KINDS] + ["Other hardening"]
    by_kind = {k: [sum(1 for f in sec if f["month"] == m and f["kind"] == k) for m in MONTHS] for k in kinds}
    by_repo = defaultdict(lambda: [0] * len(MONTHS))
    for f in sec:
        by_repo[f["repo"]][MONTHS.index(f["month"])] += 1
    misses = [f for f in facts if f["work_type"] not in ("security", "dependency") and re.search(KEYWORD_MISSES, (f["label"] or "").lower())]
    peak = max(range(len(WEEKS)), key=lambda i: series["App"][i] + series["Allied"][i])
    return dict(series=series, share=share, n=len(sec), n_all=len(nondep), before=before, after=after,
                by_kind=by_kind, kind_total=Counter(f["kind"] for f in sec), by_repo=dict(by_repo),
                repo_total=Counter(f["repo"] for f in sec), keyword_misses=len(misses),
                peak_week=WEEKS[peak], peak_n=series["App"][peak] + series["Allied"][peak],
                dependabot_sets=sum(1 for f in facts if f["dependabot"]))


# ---------------------------------------------------------------- links: change set -> PR -> item

@lru_cache(maxsize=None)
def items(con):
    out = {}
    for r in rows(con, """SELECT i.repo, i.item_id, i.title, i.type, i.origin, i.status, i.created_ts, i.done_ts, i.updated_ts,
                                 i.goal_id, i.raw_frontmatter_json j, s.security, s.finder, s.sec_criterion, s.infra_risk,
                                 s.scanner_wrong, i.file_path
                          FROM plans.plan_items i LEFT JOIN security.item_sec s ON s.repo=i.repo AND s.item_id=i.item_id
                          WHERE i.type != 'goal'"""):
        fm = json.loads(r["j"] or "{}")
        prs = set()
        for key in ("pr", "merged_pr", "merged_prs"):
            v = fm.get(key)
            for x in (v if isinstance(v, list) else [v]):
                m = re.search(r"(\d+)$", str(x)) if x is not None else None
                if m:
                    prs.add(int(m.group(1)))
        disc = str(fm.get("discovered_from") or "")
        out[(r["repo"], r["item_id"])] = {**r, "branch": fm.get("branch"), "prs": prs, "discovered_from": disc,
                                          "finder_final": final_finder(r, disc)}
    return out


FINDERS = ["Scanner or alert", "Review", "Audit", "Owner", "Agent, in passing", "Production", "Not recorded"]


def final_finder(r, disc):
    """Deterministic evidence first (origin, discovered_from, a Dependabot title), then the Haiku label."""
    d, o, t = disc.lower(), (r["origin"] or "").lower(), (r["title"] or "").lower()
    if o == "harden" or re.search(r"harden|audit|register|compliance", d):
        return "Audit"
    if re.search(r"dependabot|alert|trivy|scout|govulncheck|npm audit|scan", d) or re.match(r"bump |clear the .*advisory", t):
        return "Scanner or alert"
    if re.search(r"review|copilot", d):
        return "Review"
    if o in ("one-shot", "rahul", "user", "conversation", "think-it-through"):
        return "Owner"
    return {"scanner": "Scanner or alert", "review": "Review", "audit": "Audit", "owner": "Owner",
            "agent": "Agent, in passing", "incident": "Production"}.get(r["finder"] or "", "Not recorded")


@lru_cache(maxsize=None)
def pr_item(con):
    it = items(con)
    by_pr = {(i["repo"], n): i for i in it.values() for n in i["prs"]}
    by_branch = {(i["repo"], i["branch"]): i for i in it.values() if i["branch"]}
    heads = {(r["repo"], r["number"]): r["head_ref"] for r in rows(con, "SELECT repo, number, head_ref FROM github.prs")}
    out = {}
    for (repo, n), h in heads.items():
        out[(repo, n)] = by_pr.get((repo, n)) or by_branch.get((repo, h))
    return out


REVIEW_NOISE = ("Copilot was unable to review", "Changes requested — see Claude's verification comment above.",
                "Changes requested — see the verification comment above.")


@lru_cache(maxsize=None)
def review_rows(con):
    body = {(r["repo"], r["number"], r["reviewer"], r["state"], r["submitted_ts"]): r["body_redacted"] or ""
            for r in rows(con, "SELECT repo, number, reviewer, state, submitted_ts, body_redacted FROM github.pr_reviews")}
    out = []
    for r in rows(con, "SELECT * FROM security.review_sec"):
        b = body.get((r["repo"], r["number"], r["reviewer"], r["state"], r["ts"]), "")
        if any(b.strip().lstrip("❌ ").startswith(n) or n in b[:120] for n in REVIEW_NOISE):
            continue
        out.append({**r, "body_len": len(b)})
    return out


# ---------------------------------------------------------------- Q security-finders who finds security problems

def q_security_finders_finders(con):
    pri = pr_item(con)
    rev_prs = {(r["repo"], r["number"]) for r in review_rows(con) if r["finding"]}
    sec = [f for f in sec_sets(con) if f["work_type"] == "security" and f["day"] >= "2026-01-01"]
    out = []
    for f in sec:
        it = pri.get((f["repo"], f["pr"])) if f["pr"] else None
        if it and it["finder_final"] != "Not recorded":
            who = it["finder_final"]
        elif f["pr"] and (f["repo"], f["pr"]) in rev_prs:
            who = "Review"
        elif re.search(r"cve|advisor|alert|vulnerab|ghsa", (f["label"] or "").lower()):
            who = "Scanner or alert"
        else:
            who = "Not recorded"
        out.append({**f, "finder": who, "has_item": bool(it)})
    series = {k: [sum(1 for f in out if f["week"] == w and f["finder"] == k) for w in WEEKS] for k in FINDERS}
    series = {k: v for k, v in series.items() if sum(v)}
    tot = Counter(f["finder"] for f in out)
    since = [f for f in out if f["week"] >= "2026-W30"]
    kinds = [k for k, _ in KINDS] + ["Other hardening"]
    grid = {k: [sum(1 for f in out if f["finder"] == fd and f["kind"] == k) for fd in FINDERS if tot[fd]] for k in kinds}
    it_sec = [i for i in items(con).values() if i["security"] == 1 or i["type"] == "security"]
    return dict(series=series, total=dict(tot), n=len(out), since=Counter(f["finder"] for f in since), n_since=len(since),
                grid=grid, grid_finders=[fd for fd in FINDERS if tot[fd]],
                items=Counter(i["finder_final"] for i in it_sec), n_items=len(it_sec))


# ---------------------------------------------------------------- Q review-security-flags review findings

def reviewer_kind(r):
    return {"copilot-pull-request-reviewer": "Copilot", "github-actions": "Auto-approve judge"}.get(r, "Agent self-review")


def q_review_security_flags_reviews(con):
    rv = [r for r in review_rows(con) if r["ts"]]
    per_pr = defaultdict(lambda: {"finding": 0, "high": 0, "ts": "9", "kinds": set()})
    for r in rv:
        p = per_pr[(r["repo"], r["number"])]
        p["ts"] = min(p["ts"], r["ts"])
        if r["finding"]:
            p["finding"] = 1
            p["kinds"].add(reviewer_kind(r["reviewer"]))
            if r["severity"] in ("high", "critical"):
                p["high"] = 1
    weeks = defaultdict(lambda: [0, 0, 0])
    for (repo, n), p in per_pr.items():
        w = wk(p["ts"])
        weeks[w][0] += 1
        weeks[w][1] += p["finding"]
        weeks[w][2] += p["high"]
    reviewed = [weeks[w][0] for w in WEEKS]
    found = [weeks[w][1] for w in WEEKS]
    high = [weeks[w][2] for w in WEEKS]
    share = [f / n if n >= 5 else None for f, n in zip(found, reviewed)]
    by_repo = defaultdict(lambda: [0, 0])
    for (repo, n), p in per_pr.items():
        by_repo[repo][0] += 1
        by_repo[repo][1] += p["finding"]
    by_kind = Counter(reviewer_kind(r["reviewer"]) for r in rv if r["finding"])
    kind_n = Counter(reviewer_kind(r["reviewer"]) for r in rv)
    cls = Counter(r["cls"] for r in rv if r["finding"])
    old = {(r["repo"], r["number"]) for r in rows(con, "SELECT repo, number FROM detectors.review_topics WHERE security=1")}
    first_rev = {}
    for r in rows(con, "SELECT repo, number, MIN(submitted_ts) ts FROM github.pr_reviews WHERE submitted_ts IS NOT NULL GROUP BY 1, 2"):
        first_rev[(r["repo"], r["number"])] = r["ts"]
    topic = [sum(1 for k in old if k in first_rev and wk(first_rev[k]) == w) for w in WEEKS]
    all_reviewed = [sum(1 for k, t in first_rev.items() if wk(t) == w) for w in WEEKS]
    n_prs = len(per_pr)
    n_find = sum(p["finding"] for p in per_pr.values())
    half = lambda lo, hi: (sum(found[i] for i, w in enumerate(WEEKS) if lo <= w <= hi),
                           sum(reviewed[i] for i, w in enumerate(WEEKS) if lo <= w <= hi))
    return dict(reviewed=reviewed, found=found, high=high, share=share, topic=topic, all_reviewed=all_reviewed,
                n_all_reviewed=len(first_rev), n_prs=n_prs, n_find=n_find,
                n_high=sum(p["high"] for p in per_pr.values()), n_reviews=len(rv),
                by_repo={k: v for k, v in by_repo.items()}, by_kind=dict(by_kind), kind_n=dict(kind_n), cls=dict(cls),
                topic_prs=len(old), early=half("2026-W01", "2026-W33"), late=half("2026-W34", "2026-W39"))


# ---------------------------------------------------------------- Q agent-security-defects exposure of agent-introduced defects

# Exit 1 (git grep: no match) and 128 (path absent at that revision) read as empty; a missing mirror or
# ref must not, or a broken checkout reports as a repo with nothing in it.
GIT_BROKEN = ("not a git repository", "cannot change to", "unknown revision", "bad object")


def git(repo, *args):
    p = subprocess.run(["git", "-C", os.path.join(MIRRORS, repo + ".git"), *args], capture_output=True, text=True,
                       errors="replace")
    if p.returncode not in (0, 1, 128) or any(s in p.stderr for s in GIT_BROKEN):
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {p.stderr.strip()}")
    return p.stdout if p.returncode == 0 else ""


CODE_FILE = re.compile(r"\.(go|ts|tsx|js|mjs|py|sh|ya?ml|tf|toml|conf|json)$|Dockerfile|justfile|Justfile")
LOCKS = re.compile(r"(package-lock\.json|pnpm-lock|yarn\.lock|go\.sum|go\.mod|uv\.lock|\.trivyignore)")


@lru_cache(maxsize=None)
def q_agent_security_defects_exposure(con):
    """Blame the lines each post-merge security fix removed or rewrote, to find the commit that introduced them."""
    main = {(r["repo"], r["pr_number"]): r for r in rows(con, "SELECT repo, sha, day, pr_number, claude_trailer FROM git.commits "
                                                                "WHERE pr_number IS NOT NULL")}
    by_sha = {(r["repo"], r["sha"]): r for r in rows(con, "SELECT repo, sha, day, pr_number, claude_trailer, is_bot FROM git.commits")}
    pr_files = defaultdict(set)
    for r in rows(con, "SELECT repo, pr_number, sha, files_json FROM pr_commits.pr_commits"):
        for f in json.loads(r["files_json"] or "[]"):
            pr_files[(r["repo"], r["sha"])].add(f if isinstance(f, str) else f.get("path", ""))
    agent_pr = {(r["repo"], r["pr_number"]) for r in rows(con, "SELECT DISTINCT repo, pr_number FROM pr_commits.pr_commits "
                                                                 "WHERE claude_trailer = 1")}
    deploys = defaultdict(list)
    for r in rows(con, """SELECT repo, created_ts FROM github.ci_runs WHERE head_branch IN ('main','master')
                          AND conclusion='success' AND (LOWER(workflow_name) GLOB '*deploy*' OR workflow_name IN ('Build',
                          'Build and Push Website', 'CI')) AND event IN ('push','workflow_run','workflow_dispatch')"""):
        deploys[r["repo"]].append(r["created_ts"][:10])
    ci_from = {r["repo"]: r["d"] for r in rows(con, "SELECT repo, MIN(SUBSTR(created_ts,1,10)) d FROM github.ci_runs GROUP BY 1")}
    out = []
    for f in sec_sets(con):
        if f["work_type"] != "security" or not f["pr"] or f["kind"] == "Dependency CVE" or f["day"] < "2026-01-01":
            continue
        m = main.get((f["repo"], f["pr"]))
        if not m:
            continue
        files = set()
        for s in f["shas"]:
            files |= pr_files.get((f["repo"], s), set())
        files = {p for p in files if p and CODE_FILE.search(p) and not LOCKS.search(p)}
        tally = Counter()
        for p in sorted(files)[:25]:
            diff = git(f["repo"], "diff", "-U0", f"{m['sha']}^", m["sha"], "--", p)
            for a, b in re.findall(r"^@@ -(\d+)(?:,(\d+))? \+", diff, re.M):
                n = int(b) if b != "" else 1
                if n == 0:
                    continue
                bl = git(f["repo"], "blame", "--porcelain", "-L", f"{a},+{n}", f"{m['sha']}^", "--", p)
                for sha in re.findall(r"^([0-9a-f]{40}) \d+ \d+", bl, re.M):
                    tally[sha] += 1
        rec = {**f, "fix_day": m["day"], "traced": bool(tally)}
        if tally:
            sha = tally.most_common(1)[0][0]
            intro = by_sha.get((f["repo"], sha))
            iday = intro["day"] if intro else git(f["repo"], "log", "-1", "--format=%cs", sha).strip()
            rec.update(intro_day=iday, intro_pr=intro["pr_number"] if intro else None,
                       inherited=bool(intro and intro["pr_number"] is None and iday == adoption(con)[f["repo"]]["first"]),
                       agent=bool(intro and ((f["repo"], intro["pr_number"]) in agent_pr or intro["claude_trailer"])),
                       days=ddays(iday, m["day"]))
            shipped = [d for d in deploys[f["repo"]] if iday <= d < m["day"]]
            rec["ci_tracked"] = iday >= ci_from.get(f["repo"], "9999")
            # The plugin ships on merge: every consumer calls it at @main.
            rec["shipped"] = bool(shipped) or f["repo"] == "wayfare-skills"
        out.append(rec)
    traced = [r for r in out if r["traced"]]
    status = lambda r: ("Not traceable (fix only adds lines)" if not r["traced"] else
                        "Shipped from main before the fix" if r.get("shipped") else
                        "On main, no deploy seen" if r.get("ci_tracked") else "On main, deploys not tracked")
    cats = ["Shipped from main before the fix", "On main, no deploy seen", "On main, deploys not tracked",
            "Not traceable (fix only adds lines)"]
    series = {c: [sum(1 for r in out if r["week"] == w and status(r) == c) for w in WEEKS] for c in cats}
    agent = [r for r in traced if r["agent"]]
    by_repo = defaultdict(list)
    for r in traced:
        by_repo[r["repo"]].append(r["days"])
    return dict(series=series, n=len(out), traced=len(traced), agent=len(agent),
                inherited=sum(1 for r in traced if r.get("inherited")),
                agent_shipped=sum(1 for r in agent if r["shipped"]), shipped=sum(1 for r in traced if r["shipped"]),
                median_days=median([r["days"] for r in traced]), median_days_agent=median([r["days"] for r in agent]),
                by_repo={k: (median(v), len(v)) for k, v in by_repo.items()}, cats=cats,
                over30=sum(1 for r in traced if r["days"] > 30), rows=out)


# ---------------------------------------------------------------- Q security-fix-time time to fix, open backlog

DONE = ("done", "delivered", "committed", "accepted")
CLOSED = DONE + ("dropped",)


def q_security_fix_time_backlog(con):
    it = [i for i in items(con).values() if (i["security"] == 1 or i["type"] == "security") and i["created_ts"]]
    for i in it:
        i["closed_day"] = (i["done_ts"] or i["updated_ts"] or "")[:10] if i["status"] in CLOSED else None
    open_, closed_med, opened = [], [], []
    for w in WEEKS:
        end = date.fromisocalendar(2026, int(w[6:]), 7).isoformat()
        open_.append(sum(1 for i in it if i["created_ts"][:10] <= end and not (i["closed_day"] and i["closed_day"] <= end)))
        opened.append(sum(1 for i in it if wk(i["created_ts"]) == w))
        ds = [ddays(i["created_ts"], i["closed_day"]) for i in it if i["closed_day"] and wk(i["closed_day"]) == w
              and i["status"] in DONE]
        closed_med.append(median(ds))
    days = [ddays(i["created_ts"], i["closed_day"]) for i in it if i["closed_day"] and i["status"] in DONE]
    still = [i for i in it if not i["closed_day"]]
    by_finder = defaultdict(list)
    for i in it:
        if i["closed_day"] and i["status"] in DONE:
            by_finder[i["finder_final"]].append(ddays(i["created_ts"], i["closed_day"]))
    same_day = sum(1 for d in days if d <= 0)
    buckets = ["Same day", "1-3 days", "4-14 days", "Over 14 days", "Still open"]
    def bucket(i):
        if not i["closed_day"]:
            return "Still open"
        if i["status"] not in DONE:
            return None
        dd = ddays(i["created_ts"], i["closed_day"])
        return buckets[0] if dd <= 0 else buckets[1] if dd <= 3 else buckets[2] if dd <= 14 else buckets[3]
    fb = defaultdict(Counter)
    for i in it:
        b = bucket(i)
        if b:
            fb[i["finder_final"]][b] += 1
    return dict(open=open_, opened=opened, closed_median=closed_med, n=len(it), n_done=len(days), median=median(days),
                p90=sorted(days)[int(0.9 * (len(days) - 1))] if days else None, same_day=same_day,
                still_open=len(still), still_by_status=Counter(i["status"] for i in still),
                oldest_open=max((ddays(i["created_ts"], "2026-09-25") for i in still), default=None),
                by_finder={k: (median(v), len(v)) for k, v in by_finder.items()},
                open_by_finder=Counter(i["finder_final"] for i in still), buckets=buckets,
                finder_buckets={k: dict(v) for k, v in fb.items()}, first=min(i["created_ts"][:10] for i in it))


# ---------------------------------------------------------------- Q dependency-fix-lag known-vulnerable dependencies

@lru_cache(maxsize=None)
def vuln_presence(con):
    """{(repo, vuln, pkg): {"weeks": [...], "severity", "published"}} over weekly heads, HIGH and CRITICAL only."""
    sha_weeks = defaultdict(list)
    for r in rows(con, "SELECT repo, week, sha FROM security.snap"):
        sha_weeks[(r["repo"], r["sha"])].append(r["week"])
    pres = {}
    for r in rows(con, "SELECT DISTINCT repo, sha, vuln_id, pkg, severity, published FROM security.vulns "
                       "WHERE severity IN ('HIGH','CRITICAL')"):
        k = (r["repo"], r["vuln_id"], r["pkg"])
        e = pres.setdefault(k, {"weeks": set(), "severity": r["severity"], "published": r["published"]})
        e["weeks"] |= set(sha_weeks[(r["repo"], r["sha"])])
    return pres


def q_dependency_fix_lag_deps(con):
    scope = in_scope(con)
    S = snaps(con)
    pres = {k: v for k, v in vuln_presence(con).items() if k[0] in scope}
    crit, high = [0] * len(WEEKS), [0] * len(WEEKS)
    lags, open_ages, removed_by = [], [], defaultdict(set)
    per_repo = defaultdict(lambda: {"removed": [], "open": 0})
    for (repo, vid, pkg), e in pres.items():
        pub = e["published"] or "2000-01-01"
        pub_w = wk(pub) if pub >= "2026-01-01" else WEEKS[0]
        live = sorted(w for w in e["weeks"] if w >= pub_w)
        for w in live:
            (crit if e["severity"] == "CRITICAL" else high)[WEEKS.index(w)] += 1
        if not live:
            continue
        start = max(live[0], pub_w)
        last_seen = live[-1]
        if last_seen < WEEKS[-1] and WEEKS[-1] in S.get(repo, {}):
            nxt = WEEKS[WEEKS.index(last_seen) + 1]
            d = (WEEKS.index(nxt) - WEEKS.index(start)) * 7
            lags.append(d)
            per_repo[repo]["removed"].append(d)
            removed_by[vid].add(repo)
        elif last_seen == WEEKS[-1]:
            open_ages.append((WEEKS.index(last_seen) - WEEKS.index(start)) * 7)
            per_repo[repo]["open"] += 1
    multi = {v: r for v, r in removed_by.items() if len(r) > 1}
    rx = re.compile(r"(CVE-\d{4}-\d{4,}|GHSA(?:-[23456789cfghjmpqrvwx]{4}){3})", re.I)
    named = defaultdict(dict)
    for r in rows(con, "SELECT repo, day, subject, body_redacted b FROM git.commits WHERE is_bot = 0"):
        if r["repo"] not in scope:
            continue
        for a in {x.upper() for x in rx.findall((r["subject"] or "") + " " + (r["b"] or ""))}:
            if r["repo"] not in named[a] or r["day"] < named[a][r["repo"]]:
                named[a][r["repo"]] = r["day"]
    named_multi = {a: v for a, v in named.items() if len(v) > 1}
    spreads = [ddays(min(v.values()), max(v.values())) for v in named_multi.values()]
    peak = max(range(len(WEEKS)), key=lambda i: crit[i] + high[i])
    return dict(crit=crit, high=high, n_pairs=len(pres), median_lag=median(lags), n_removed=len(lags),
                p75=sorted(lags)[int(0.75 * (len(lags) - 1))] if lags else None, open_now=len(open_ages),
                median_open_age=median(open_ages), fixed_in_several=len(multi), n_vulns_removed=len(removed_by),
                repeat_repos=sum(len(v) for v in multi.values()),
                named=len(named), named_multi=len(named_multi), named_spread_median=median(spreads),
                per_repo={k: (median(v["removed"]), len(v["removed"]), v["open"]) for k, v in per_repo.items()},
                peak_week=WEEKS[peak], peak=crit[peak] + high[peak], now=crit[-1] + high[-1])


# ---------------------------------------------------------------- Q sibling-hardening-lag the same hardening fix across siblings

def q_sibling_hardening_lag_siblings(con):
    sec_main = {}
    for f in sec_sets(con):
        if f["work_type"] == "security" and f["pr"]:
            sec_main[(f["repo"], f["pr"])] = f
    main_pr = {(r["repo"], r["sha"]): r["pr_number"] for r in rows(con, "SELECT repo, sha, pr_number FROM git.commits")}
    files = defaultdict(set)
    for r in rows(con, "SELECT repo, sha, path FROM git.commit_files"):
        files[(r["repo"], r["sha"])].add(r["path"])
    clusters = defaultdict(list)
    for r in rows(con, "SELECT * FROM detectors.duplicate_fixes"):
        clusters[r["cluster_id"]].append(r)
    out = []
    for cid, mem in clusters.items():
        sec = [m for m in mem if (m["repo"], main_pr.get((m["repo"], m["sha"]))) in sec_main]
        if 2 * len(sec) < len(mem) or len({m["repo"] for m in mem}) < 2:
            continue
        mem = sorted(mem, key=lambda m: m["ts"])
        first_by_repo = {}
        for m in mem:
            first_by_repo.setdefault(m["repo"], m)
        repos = list(first_by_repo)
        paths = [{re.sub(r"^(ui|lib|service)/", "", p) for p in files[(m["repo"], m["sha"])]} for m in first_by_repo.values()]
        jac = []
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                u = paths[i] | paths[j]
                jac.append(len(paths[i] & paths[j]) / len(u) if u else 0)
        out.append({"cluster": cid, "subject": mem[0]["subject"], "repos": repos, "n": len(repos),
                    "first": mem[0]["ts"][:10], "last": max(m["ts"] for m in first_by_repo.values())[:10],
                    "span": ddays(mem[0]["ts"], max(m["ts"] for m in first_by_repo.values())),
                    "upstream_first": repos[0] in ("hero-template", "wayfare-skills"),
                    "same_files": median(jac) if jac else None})
    by_month = {"Template or plugin first": [0] * len(MONTHS), "Repo by repo": [0] * len(MONTHS)}
    for c in out:
        by_month["Template or plugin first" if c["upstream_first"] else "Repo by repo"][MONTHS.index(c["first"][:7])] += 1
    return dict(clusters=sorted(out, key=lambda c: -c["n"]), n=len(out), by_month=by_month,
                median_span=median([c["span"] for c in out]), same_day=sum(1 for c in out if c["span"] == 0),
                upstream=sum(1 for c in out if c["upstream_first"]),
                same_way=sum(1 for c in out if (c["same_files"] or 0) >= 0.5), repo_fixes=sum(c["n"] for c in out))


# ---------------------------------------------------------------- Q dependency-bump-upkeep Dependabot upkeep

GROUPED = re.compile(r"group|across \d+ director|bump the ", re.I)


def q_dependency_bump_upkeep_dependabot(con):
    scope = in_scope(con)
    prs = [r for r in rows(con, "SELECT repo, number, title, state, created_ts, merged_ts, closed_ts FROM github.prs "
                                "WHERE author = 'app/dependabot'") if r["repo"] in scope]
    outcome = lambda p: "Merged" if p["merged_ts"] else "Closed unmerged" if p["state"] == "CLOSED" else "Open"
    cats = ["Merged", "Closed unmerged", "Open"]
    series = {c: [sum(1 for p in prs if wk(p["created_ts"]) == w and outcome(p) == c) for w in WEEKS] for c in cats}
    grouped = [[sum(1 for p in prs if p["created_ts"][:7] == m and GROUPED.search(p["title"])),
                sum(1 for p in prs if p["created_ts"][:7] == m)] for m in MONTHS]
    by_repo = defaultdict(lambda: [0] * len(MONTHS))
    for p in prs:
        if p["created_ts"][:7] in MONTHS:
            by_repo[p["repo"]][MONTHS.index(p["created_ts"][:7])] += 1
    hours = [(datetime.fromisoformat(p["merged_ts"].replace("Z", "+00:00")) -
              datetime.fromisoformat(p["created_ts"].replace("Z", "+00:00"))).total_seconds() / 3600
             for p in prs if p["merged_ts"]]
    c = Counter(outcome(p) for p in prs)
    per_repo_active = {}
    for repo, v in by_repo.items():
        months = [x for x in v if x]
        per_repo_active[repo] = round(sum(v) / len(months), 1) if months else 0
    return dict(series=series, n=len(prs), outcome=dict(c), grouped=grouped, by_repo=dict(by_repo),
                median_hours=median(hours), per_repo_active=per_repo_active,
                grouped_share_by_month=[g / n if n else None for g, n in grouped],
                since_jul=sum(1 for p in prs if p["created_ts"] >= "2026-07-01"))


# ---------------------------------------------------------------- Q scanner-mistakes scanners and suppressions

SCAN_WF = re.compile(r"scan|vuln|secur|trivy|scout|cve", re.I)


def q_scanner_mistakes_scanners(con):
    S = snaps(con)
    live, expiring, dead = [0] * len(WEEKS), [0] * len(WEEKS), [0] * len(WEEKS)
    for repo, wmap in S.items():
        for w, r in wmap.items():
            ids = json.loads(r["ignore_ids"] or "{}")
            i = WEEKS.index(w)
            live[i] += len(ids)
            expiring[i] += sum(1 for v in ids.values() if v)
            end = date.fromisocalendar(2026, int(w[6:]), 7).isoformat()
            dead[i] += sum(1 for v in ids.values() if v and v < end)
    runs = rows(con, """SELECT repo, workflow_name wf, COUNT(*) n, SUM(conclusion='failure') fail, SUM(conclusion='success') ok,
                               MIN(SUBSTR(created_ts,1,10)) first FROM github.ci_runs GROUP BY 1, 2""")
    scans = [r for r in runs if SCAN_WF.search(r["wf"]) and r["n"] >= 3 and r["repo"] in S]
    never_fail = [r for r in scans if not r["fail"]]
    always_fail = [r for r in scans if not r["ok"]]
    mostly_fail = [r for r in scans if r["fail"] / r["n"] >= 0.5]
    wrong = [i for i in items(con).values() if i["scanner_wrong"] == 1 and i["created_ts"]]
    events = sorted({(i["created_ts"][:10], "") for i in wrong})
    sched = [r for r in rows(con, """SELECT repo, workflow_name wf, conclusion, created_ts FROM github.ci_runs
                                     WHERE event='schedule'""") if SCAN_WF.search(r["wf"])]
    red_weeks = defaultdict(lambda: [0, 0])
    for r in sched:
        w = wk(r["created_ts"])
        red_weeks[w][0] += 1
        red_weeks[w][1] += r["conclusion"] == "failure"
    return dict(live=live, expiring=expiring, dead_listed=dead, scans=scans, never_fail=never_fail,
                always_fail=always_fail, mostly_fail=mostly_fail, wrong=len(wrong),
                wrong_by_repo=Counter(i["repo"] for i in wrong), wrong_weeks=[sum(1 for i in wrong if wk(i["created_ts"]) == w) for w in WEEKS],
                sched_runs=[red_weeks[w][0] for w in WEEKS], sched_red=[red_weeks[w][1] for w in WEEKS],
                sched_total=len(sched), sched_failed=sum(1 for r in sched if r["conclusion"] == "failure"),
                peak_live=max(live), now_live=live[-1])


# ---------------------------------------------------------------- Q judge-attack-tests the auto-approve judge

TEST_FILE = "scripts/auto-approve-logic.test.sh"
ATTACKS = [("PR text argues for approval", ("untag", "claims", "model-write")),
           ("Commenter without write access", ("prior-review", "threads-paginate")),
           ("Bot impersonation", ("bot-lane",)),
           ("Secret files sent to the model", ("classify", "diff-filter")),
           ("A PR that edits the gate", ("fleet-workflow",)),
           ("Fail closed on errors", ("crash-notice", "verdict", "submit-verdict", "contents-fetch", "files-list",
                                      "tree-guard", "ci"))]


def q_judge_attack_tests_judge(con):
    repo = os.path.dirname(os.path.dirname(REPORT))
    log = subprocess.run(["git", "-C", repo, "log", "--format=%H %cs", "--", TEST_FILE], capture_output=True, text=True).stdout
    per_commit = []
    for line in log.splitlines():
        sha, day = line.split()
        text = subprocess.run(["git", "-C", repo, "show", f"{sha}:{TEST_FILE}"], capture_output=True, text=True).stdout
        prefixes = Counter(re.findall(r'check "([^:"]+)', text))
        per_commit.append((day, {a: sum(prefixes[p] for p in ps) for a, ps in ATTACKS}))
    per_commit.sort(key=lambda x: x[0])
    series = {a: [] for a, _ in ATTACKS}
    for w in WEEKS:
        end = date.fromisocalendar(2026, int(w[6:]), 7).isoformat()
        cur = [c for d, c in per_commit if d <= end]
        for a, _ in ATTACKS:
            series[a].append(cur[-1][a] if cur else 0)
    first = per_commit[0][0] if per_commit else None
    wf_log = subprocess.run(["git", "-C", repo, "log", "--format=%cs", "--", ".github/workflows/auto-approve.yaml",
                             ".github/workflows/auto-approve.yml"], capture_output=True, text=True).stdout.split()
    judge = rows(con, "SELECT state, submitted_ts FROM github.pr_reviews WHERE reviewer = 'github-actions' "
                      "AND state IN ('APPROVED', 'CHANGES_REQUESTED') AND submitted_ts IS NOT NULL")
    verdicts = Counter(r["state"] for r in judge)
    approve_rate = []
    for w in WEEKS:
        ws = [r for r in judge if wk(r["submitted_ts"]) == w]
        approve_rate.append(sum(r["state"] == "APPROVED" for r in ws) / len(ws) if len(ws) >= 5 else None)
    return dict(series=series, first=first, now={a: v[-1] for a, v in series.items()},
                total_now=sum(v[-1] for v in series.values()), workflow_changes=len(wf_log),
                workflow_changes_before_tests=sum(1 for d in wf_log if first and d < first), verdicts=dict(verdicts),
                approve_rate=approve_rate)


# ---------------------------------------------------------------- Q plugin-security-fixes the plugin's own security fixes

PLUGIN_FIXES = [
    # date, fix, vector, origin, how closed  (read from each commit and PR body; see notes)
    ("2026-07-18", "Secret-bearing file paths skipped before upload (e6155d3)", "Secrets sent to the model", "Own design", "Narrowed"),
    ("2026-07-18", "Trigger restricted to write-access commenters (a2ed6a8)", "Anyone could start an approval", "Own design", "Guarded"),
    ("2026-07-18", "Fail closed when the API key is missing (fee2005)", "Silent pass", "Own design", "Guarded"),
    ("2026-09-10", "Bot lane crashed, then spoofable once fixed (#75)", "Bot impersonation", "Consumer repo", "Guarded"),
    ("2026-09-18", "Every leg of the prior-review gate turns on who posted (#99)", "Any commenter satisfied the gate", "Own review", "Guarded"),
    ("2026-09-18", "Write access read from the roster the token can read (#100)", "Same gate, regression of #99", "Own review", "Guarded, then reverted (#102)"),
    ("2026-09-22", "Dependabot runs have no secrets; skip them (#115)", "Failing runs with no jobs", "Consumer repos", "Guarded"),
    ("2026-09-23", "Fail closed on unverified reads; PR text kept out of the instructions (#118)", "Prompt injection, fail-open reads", "Own audit (harden)", "Removed"),
    ("2026-09-25", "Permissions grant only to launches that reach a gate (#124, #125)", "Over-broad merge authority", "Owner design session", "Removed"),
]


ORIGIN_GROUP = {"Own design": "Plugin's own review or design", "Own review": "Plugin's own review or design",
                "Own audit (harden)": "Plugin's own audit", "Consumer repo": "A consumer repo", "Consumer repos": "A consumer repo",
                "Owner design session": "Owner's design session"}


def q_plugin_security_fixes_plugin(con):
    by_month_origin = defaultdict(lambda: [0] * len(MONTHS))
    for d, _, _, o, _ in PLUGIN_FIXES:
        by_month_origin[ORIGIN_GROUP[o]][MONTHS.index(d[:7])] += 1
    closed = Counter("Removed" if h == "Removed" else "Narrowed or guarded" for *_, h in PLUGIN_FIXES)
    origin = Counter(ORIGIN_GROUP[o] for _, _, _, o, _ in PLUGIN_FIXES)
    return dict(fixes=PLUGIN_FIXES, by_month=dict(by_month_origin), closed=dict(closed), origin=dict(origin), n=len(PLUGIN_FIXES))


# ---------------------------------------------------------------- Q unmet-security-criteria done with a security criterion unmet

def criteria_lines(text):
    """Acceptance-criterion lines: the frontmatter success: field and checkbox lines."""
    succ = re.findall(r"^success:\s*(.+)$", text, re.M)
    boxes = re.findall(r"^\s*[-*]\s*\[( |x|X)\]\s*(.+)$", text, re.M)
    return succ, boxes


SEC_WORDS = re.compile(r"secur|secret|auth|token|cve|advisor|vuln|csrf|xss|inject|pin|permission|access|cookie|session|"
                       r"credential|redact|scrub|header|csp|tls|encrypt|trivy|scout|govulncheck|alert", re.I)


DONE_CATS = ["Every criterion ticked", "A security criterion left unticked", "No box ticked (not tracked)",
             "Success line only, no checklist"]


def q_unmet_security_criteria_done(con):
    it = [i for i in items(con).values() if i["sec_criterion"] == 1 and (i["done_ts"] or i["updated_ts"] or i["created_ts"])]
    out = []
    for i in it:
        text = open(i["file_path"], errors="replace").read() if i["file_path"] and os.path.exists(i["file_path"]) else ""
        succ, boxes = criteria_lines(text)
        ticked = [t for st, t in boxes if st != " "]
        unticked_sec = [t for st, t in boxes if st == " " and SEC_WORDS.search(t)]
        cat = (DONE_CATS[3] if not boxes else DONE_CATS[2] if not ticked else
               DONE_CATS[1] if unticked_sec else DONE_CATS[0])
        out.append({"repo": i["repo"], "item": i["item_id"], "done": i["status"] in DONE, "cat": cat,
                    "week": wk(i["done_ts"] or i["updated_ts"] or i["created_ts"]), "unticked": len(unticked_sec)})
    done = [o for o in out if o["done"]]
    series = {c: [sum(1 for o in done if o["week"] == w and o["cat"] == c) for w in WEEKS] for c in DONE_CATS}
    by_repo = defaultdict(Counter)
    for o in done:
        by_repo[o["repo"]][o["cat"]] += 1
    flagged = [o for o in done if o["cat"] == DONE_CATS[1]]
    return dict(series=series, n=len(out), n_done=len(done), cats=Counter(o["cat"] for o in done),
                flagged=len(flagged), flagged_list=[(o["repo"], o["item"], o["unticked"]) for o in flagged],
                by_repo={k: dict(v) for k, v in by_repo.items()},
                tracked=sum(1 for o in done if o["cat"] in DONE_CATS[:2]))


# ---------------------------------------------------------------- Q false-security-claims documentation claims

CLAIM_GATE = {"secret_scan": lambda r: r["secret_local"] or r["secret_ci"],
              "image_scan": lambda r: r["image_ci"],
              "dep_scan": lambda r: r["dep_scan_ci"] or r["dep_scan_local"],
              "action_pins": lambda r: r["uses_total"] == 0 or r["uses_pinned"] / r["uses_total"] >= 0.9,
              "dependabot": lambda r: r["dep_update"]}
CLAIM_NAMES = {"secret_scan": "Secret scanning", "image_scan": "Image scanning", "dep_scan": "Dependency scanning",  # pragma: allowlist secret
               "action_pins": "Actions pinned to a SHA", "dependabot": "Dependabot"}


def q_false_security_claims_claims(con):
    S = snaps(con)
    tpl = S.get("hero-template", {})
    false_w = [0] * len(WEEKS)
    pairs = {}
    backed_w = [0] * len(WEEKS)
    for repo, wmap in S.items():
        if repo == "wayfare-skills":
            continue
        for w in WEEKS:
            r = wmap.get(w)
            if not r:
                continue
            for c in json.loads(r["doc_claims"] or "[]"):
                if CLAIM_GATE[c](r):
                    backed_w[WEEKS.index(w)] += 1
                else:
                    false_w[WEEKS.index(w)] += 1
                    pairs.setdefault((repo, c), []).append(w)
    out = []
    for (repo, c), ws in pairs.items():
        w0 = ws[0]
        claim_since = first_week(S[repo], lambda r: c in json.loads(r["doc_claims"] or "[]"))
        had_gate = any(CLAIM_GATE[c](S[repo][w]) for w in WEEKS if w in S[repo] and w < w0)
        t = tpl.get(claim_since) if claim_since else None
        tpl_claims = t and c in json.loads(t["doc_claims"] or "[]")
        origin = ("Regression (gate removed, claim stayed)" if had_gate else
                  "Template copy" if tpl_claims and repo != "hero-template" and claim_since == first_week(S[repo], lambda r: True) else
                  "Claim without the gate")
        still = WEEKS[-1] in ws
        out.append({"repo": repo, "claim": CLAIM_NAMES[c], "from": w0, "weeks": len(ws), "origin": origin, "still": still})
    return dict(false_weeks=false_w, backed_weeks=backed_w, pairs=sorted(out, key=lambda o: (not o["still"], o["repo"])), n=len(out),
                still=sum(1 for o in out if o["still"]), origin=Counter(o["origin"] for o in out),
                median_weeks=median([o["weeks"] for o in out]))


# ---------------------------------------------------------------- Q infra-security-risks infrastructure risks on record

RISKS = {"credential_scope": "Credential scope", "boot_secrets": "Secrets in boot config", "network_exposure": "Network exposure",  # pragma: allowlist secret
         "revocation": "Revocation latency", "other_infra": "Other infrastructure"}


def q_infra_security_risks_infra(con):
    it = [i for i in items(con).values() if i["infra_risk"] in RISKS and i["created_ts"]]
    rec, res = [], []
    for w in WEEKS:
        end = date.fromisocalendar(2026, int(w[6:]), 7).isoformat()
        rec.append(sum(1 for i in it if i["created_ts"][:10] <= end))
        res.append(sum(1 for i in it if i["status"] in DONE and (i["done_ts"] or i["updated_ts"] or "9")[:10] <= end))
    grid = defaultdict(Counter)
    for i in it:
        grid[RISKS[i["infra_risk"]]]["Fixed" if i["status"] in DONE else "Dropped" if i["status"] == "dropped" else "Open"] += 1
    return dict(recorded=rec, resolved=res, n=len(it), grid={k: dict(v) for k, v in grid.items()},
                by_repo=Counter(i["repo"] for i in it), open=sum(1 for i in it if i["status"] not in CLOSED),
                first=min((i["created_ts"][:10] for i in it), default=None),
                in_sep=sum(1 for i in it if i["created_ts"][:7] == "2026-09"))


# ---------------------------------------------------------------- Q committed-secrets committed secrets

EXPOSURE_FIX = re.compile(r"scrub|redact|unredacted|leak|credentials? logging|password logging|secret.*(log|report)|"
                          r"cookie.*(sentry|report)|pii", re.I)


def q_committed_secrets_secrets(con):
    scope = in_scope(con)
    hits = [r for r in rows(con, "SELECT * FROM security.secret_hits") if r["repo"] in scope]
    real = [h for h in hits if not h["fixture"]]
    commits = sum(int(subprocess.run(["git", "-C", os.path.join(MIRRORS, r + ".git"), "rev-list", "--all", "--count"],
                                     capture_output=True, text=True).stdout.strip() or 0) for r in scope
                  if os.path.isdir(os.path.join(MIRRORS, r + ".git")))
    fixes = [r for r in rows(con, "SELECT repo, day, subject FROM git.commits WHERE is_bot = 0 AND day >= '2026-01-01'")
             if r["repo"] in scope and EXPOSURE_FIX.search(r["subject"] or "")]
    series = {"Credential-exposure fixes (logs, error reports, URLs)": [sum(1 for f in fixes if wk(f["day"]) == w) for w in WEEKS]}
    S = snaps(con)
    cover = [sum(1 for r in S if w in S[r] and (S[r][w]["secret_local"] or S[r][w]["secret_ci"])) for w in WEEKS]
    return dict(series=series, n_hits=len(hits), real=len(real), fixture_repos=sorted({h["repo"] for h in hits if h["fixture"]}),
                fixture_findings=len({h["finding_id"] for h in hits if h["fixture"]}), commits=commits,
                repos_scanned=sum(1 for r in scope if os.path.isdir(os.path.join(MIRRORS, r + ".git"))),
                n_fixes=len(fixes), fix_repos=Counter(f["repo"] for f in fixes), cover=cover,
                fix_list=[(f["repo"], f["day"]) for f in fixes],
                peak_week=max(WEEKS, key=lambda w: series["Credential-exposure fixes (logs, error reports, URLs)"][WEEKS.index(w)]),
                peak_n=max(series["Credential-exposure fixes (logs, error reports, URLs)"]))


def all_data(con=None):
    con = con or connect("security")
    return {name: fn(con) for name, fn in [
        ("q_scanner_coverage", q_scanner_coverage_gates), ("q_supply_chain_pins", q_supply_chain_pins_pins), ("q_security_work_share", q_security_work_share_volume), ("q_security_finders", q_security_finders_finders), ("q_review_security_flags", q_review_security_flags_reviews),
        ("q_agent_security_defects", q_agent_security_defects_exposure), ("q_security_fix_time", q_security_fix_time_backlog), ("q_dependency_fix_lag", q_dependency_fix_lag_deps), ("q_sibling_hardening_lag", q_sibling_hardening_lag_siblings), ("q_dependency_bump_upkeep", q_dependency_bump_upkeep_dependabot),
        ("q_scanner_mistakes", q_scanner_mistakes_scanners), ("q_judge_attack_tests", q_judge_attack_tests_judge), ("q_plugin_security_fixes", q_plugin_security_fixes_plugin), ("q_unmet_security_criteria", q_unmet_security_criteria_done), ("q_false_security_claims", q_false_security_claims_claims),
        ("q_infra_security_risks", q_infra_security_risks_infra), ("q_committed_secrets", q_committed_secrets_secrets),
        ("fig_flaw_lifetimes", fig_flaw_lifetimes), ("fig_item_closure", fig_item_closure)]}


if __name__ == "__main__":
    con = connect("security")
    fns = {name: fn for name, fn in globals().items() if name.startswith("q_") and callable(fn) and getattr(fn, "__module__", None) == __name__}
    names = sys.argv[1:] or list(fns)
    for n in names:
        fn = next(v for k, v in fns.items() if k.startswith(n))
        d = fn(con)
        print(f"== {n}")
        for k, v in d.items():
            if k in ("rows", "table", "clusters", "pairs", "fixes", "fix_list", "scans"):
                print(f"  {k}: {len(v)} rows; first: {v[:3]}")
            elif isinstance(v, list) and len(v) == len(WEEKS):
                print(f"  {k}: {v[-12:]}")
            else:
                s = str(v)
                print(f"  {k}: {s[:400]}")


# ---------------------------------------------------------------- book figures 5.3 and 5.4

END = "2026-09-24"  # last day the plan and CI ingests cover; open items are censored here
AUTHOR_GROUPS = ["Written by an agent in this repo", "Inherited with the clone's first commit", "Written by a person"]


def author_group(r):
    if r.get("inherited"):
        return AUTHOR_GROUPS[1]
    return AUTHOR_GROUPS[0] if r["agent"] else AUTHOR_GROUPS[2]


def fig_flaw_lifetimes(con):
    """5.3: days from the introducing commit to the merged fix for every traceable security flaw, by who wrote it,
    with production exposure and, where the fix's work item is linked, the detection date in between."""
    x = q_agent_security_defects_exposure(con)
    traced = [dict(r, group=author_group(r)) for r in x["rows"] if r["traced"]]
    pi = pr_item(con)
    for r in traced:
        i = pi.get((r["repo"], r["pr"]))
        r["detected"] = i["created_ts"][:10] if i else None
        r["finder"] = i["finder_final"] if i else None
        r["intro_to_detect"] = ddays(r["intro_day"], r["detected"]) if i else None
        r["detect_to_fix"] = ddays(r["detected"], r["fix_day"]) if i else None
    exposure = lambda r: ("Deployed from main before the fix" if r["shipped"] else
                          "On main, no deploy in between" if r["ci_tracked"] else "On main, deploys not tracked")
    EXPO = ["Deployed from main before the fix", "On main, no deploy in between", "On main, deploys not tracked"]
    groups = {g: sorted(r["days"] for r in traced if r["group"] == g) for g in AUTHOR_GROUPS}
    linked = [r for r in traced if r["detected"]]
    return {"rows": traced, "n_fixes": x["n"], "n_traced": len(traced), "untraceable": x["n"] - len(traced),
            "groups": groups, "median": {g: median(v) for g, v in groups.items()},
            "exposure": {g: {e: sum(1 for r in traced if r["group"] == g and exposure(r) == e) for e in EXPO} for g in AUTHOR_GROUPS},
            "expo_names": EXPO, "shipped": sum(1 for r in traced if r["shipped"]),
            "over30": sum(1 for r in traced if r["days"] > 30), "max_days": max(r["days"] for r in traced),
            "linked": len(linked), "intro_to_detect": sorted(r["intro_to_detect"] for r in linked),
            "detect_to_fix": sorted(r["detect_to_fix"] for r in linked),
            "severity_recorded": 0, "fix_window": (min(r["fix_day"] for r in traced), max(r["fix_day"] for r in traced))}


def fig_item_closure(con):
    """5.4: days from a security work item's creation to its close, open items censored at END, dropped ones apart."""
    it = [i for i in items(con).values() if (i["security"] == 1 or i["type"] == "security") and i["created_ts"]]
    done, open_, dropped = [], [], []
    for i in it:
        closed = (i["done_ts"] or i["updated_ts"] or "")[:10] if i["status"] in CLOSED else None
        rec = {"repo": i["repo"], "item": i["item_id"], "status": i["status"], "created": i["created_ts"][:10],
               "closed": closed, "finder": i["finder_final"], "title": (i["title"] or "")[:80]}
        if i["status"] == "dropped":
            dropped.append(rec)
        elif closed:
            rec["days"] = ddays(i["created_ts"], closed)
            done.append(rec)
        else:
            rec["age"] = ddays(i["created_ts"], END)
            open_.append(rec)
    days = sorted(r["days"] for r in done)
    q = lambda p: days[min(len(days) - 1, int(p * len(days)))]
    return {"done": done, "open": open_, "dropped": dropped, "n": len(it), "n_done": len(done), "n_open": len(open_),
            "n_dropped": len(dropped), "days": days, "same_day": sum(1 for d in days if d <= 0),
            "within_3": sum(1 for d in days if d <= 3), "median": median(days), "p90": q(0.9), "max": max(days),
            "open_ages": sorted(r["age"] for r in open_), "open_by_status": Counter(r["status"] for r in open_),
            "accepted": sum(1 for r in done if r["status"] == "accepted"), "duplicates_marked": 0,
            "first": min(r["created"] for r in done + open_ + dropped), "end": END}
