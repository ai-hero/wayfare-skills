"""Fleet scope and apps series: fleet scope and apps.

    cd analysis && WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/fleet/data.py

One function per question, each returning what its answer slide (and breakdown slide)
plots. Trees over time come from the bare mirrors in .analysis/data/mirrors, read with
`git ls-tree` / `git cat-file` at the last main commit of each week or month; nothing
there is written, fetched or checked out.
"""
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]
from cube.db import connect as _connect  # noqa: E402
from record import adoption, changeset_facts, rows, week_of  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE, category_of  # noqa: E402

FLEET = os.path.expanduser(os.environ.get("WAYFARE_FLEET_ROOT", "~/workspaces/aihero"))
PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MIRRORS = os.path.join(PLUGIN, ".analysis", "data", "mirrors")
LATEST = "2026-09-24"
WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
CATS = ["app", "app, no features yet", "allied", "out of scope"]
TEMPLATE = "hero-template"
CLONES = ["elevate-commons", "aihero-wayfare", "ah-cozy", "aihero-dokyu", "aihero-mehr", "aihero-steadfast"]
APPS = ["auth", "design-system", "website", "hiro", "saga", "elevate-commons", "aihero-wayfare", "aihero-steadfast",
        "ah-cozy", "aihero-dokyu", "aihero-mehr"]
IN_SCOPE = APPS + [TEMPLATE, "wayfare-skills", "infrastructure-root", "infrastructure-environments"]
DESIGN_REMOVED = "2026-08-16"


def week_end(w):
    return date.fromisocalendar(int(w[:4]), int(w[6:]), 7).isoformat()


def month_end(m):
    y, mo = int(m[:4]), int(m[5:])
    return (date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(1)).isoformat()


def clamp(day):
    return min(day, LATEST)


# ------------------------------------------------------------------ mirrors

# Exit 1 (git grep: no match) and 128 (path absent at that revision) read as empty; a missing mirror or
# ref must not, or a broken checkout reports as a repo with nothing in it.
GIT_BROKEN = ("not a git repository", "cannot change to", "unknown revision", "bad object")


def git(repo, *args, inp=None, binary=False):
    p = subprocess.run(["git", f"--git-dir={os.path.join(MIRRORS, repo + '.git')}", *args],
                       input=inp, capture_output=True, text=not binary)
    err = p.stderr.decode(errors="replace") if binary else p.stderr
    if p.returncode not in (0, 1, 128) or any(s in err for s in GIT_BROKEN):
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {err.strip()}")
    return p.stdout


def has_mirror(repo):
    return os.path.isdir(os.path.join(MIRRORS, repo + ".git"))


@lru_cache(maxsize=None)
def main_log(repo):
    """[(committer day, sha)] on main's first-parent line, oldest first."""
    out = git(repo, "log", "--first-parent", "--reverse", "--format=%cI %H", "main")
    return [(l[:10], l.split()[1]) for l in out.splitlines() if l.strip()]


def sha_at(repo, day):
    last = None
    for d, sha in main_log(repo):
        if d <= day:
            last = sha
        else:
            break
    return last


@lru_cache(maxsize=None)
def tree(repo, sha):
    """{path: (blob, bytes)} for a commit."""
    out = {}
    for line in git(repo, "ls-tree", "-r", "-l", sha).splitlines():
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if parts[1] != "blob":
            continue
        out[path] = (parts[2], int(parts[3]) if parts[3] != "-" else 0)
    return out


_LINES = {}


def blob_lines(repo, blobs):
    """{blob: line count}; binary blobs count 0. Cached by blob id."""
    need = [b for b in set(blobs) if b not in _LINES]
    if need:
        data = git(repo, "cat-file", "--batch", inp=("\n".join(need) + "\n").encode(), binary=True)
        i = 0
        while i < len(data):
            nl = data.index(b"\n", i)
            head = data[i:nl].split()
            size = int(head[2])
            body = data[nl + 1: nl + 1 + size]
            _LINES[head[0].decode()] = 0 if b"\0" in body[:8000] else body.count(b"\n")
            i = nl + 1 + size + 1
    return {b: _LINES[b] for b in blobs}


def show(repo, sha, path):
    return git(repo, "show", f"{sha}:{path}")


# ------------------------------------------------------------------ Q fleet-size-over-time repos in the fleet

@lru_cache(maxsize=None)
def first_day(repo):
    """The repo's first authored commit (committer dates move when history is rebased)."""
    if has_mirror(repo):
        return min(l[:10] for l in git(repo, "log", "--format=%aI", "main").split())
    return rows(CON, "SELECT MIN(day) d FROM git.commits WHERE repo=?", (repo,))[0]["d"]


def join_mode(repo):
    if repo in OUT_OF_SCOPE:
        return "design export"
    if repo in CLONES:
        return "copy of the template"
    return "started on its own"


def q_fleet_size_over_time(con):
    repos = IN_SCOPE + sorted(OUT_OF_SCOPE)
    first = {r: first_day(r) for r in repos}
    left = {r: DESIGN_REMOVED for r in OUT_OF_SCOPE}
    series = {c: [] for c in CATS}
    for m in MONTHS:
        end = clamp(month_end(m))
        cnt = Counter(category_of(r) for r in repos if first[r] <= end and not (r in left and left[r] <= end))
        for c in CATS:
            series[c].append(cnt.get(c, 0))
    joins = sorted(({"repo": r, "day": first[r], "category": category_of(r), "mode": join_mode(r)} for r in repos),
                   key=lambda j: j["day"])
    before = [j for j in joins if j["day"] < "2026-01-01"]
    modes = ["started on its own", "copy of the template", "design export"]
    join_by_month = {mo: [sum(1 for j in joins if j["mode"] == mo and j["day"][:7] == m) for m in MONTHS] for mo in modes}
    return {"series": series, "joins": joins, "before_2026": before, "join_by_month": join_by_month,
            "left": [{"repo": r, "day": d} for r, d in sorted(left.items())],
            "now": {c: series[c][-1] for c in CATS}, "peak": max(sum(v[i] for v in series.values()) for i in range(len(MONTHS)))}


# ------------------------------------------------------------------ Q fleet-map-accuracy the fleet map

MAP_EVENTS = [
    ("2026-07-14", "Port registry in workspace README"),
    ("2026-08-29", "FLEET.md standard (#67)"),
    ("2026-09-22", "review-fleet skill (#106)"),
]


def fleet_rows():
    rows_, name = {}, None
    for line in open(os.path.join(FLEET, "FLEET.md")):
        m = re.match(r"### (\S+)", line)
        if m:
            name = m.group(1)
            rows_[name] = {}
            continue
        m = re.match(r"- (group|port|what): (.*)", line)
        if m and name:
            rows_[name][m.group(1)] = m.group(2).strip()
    return rows_


def q_fleet_map_accuracy(con):
    mp = fleet_rows()
    dirs = sorted(d for d in os.listdir(FLEET) if not d.startswith(".") and os.path.isdir(os.path.join(FLEET, d, ".git")))
    mp = {("wayfare-skills" if r == "hero-skills" else r): v for r, v in mp.items()}
    study = set(IN_SCOPE) - {"wayfare-skills"}
    out = []
    for r in sorted(set(mp) | set(dirs) | study | {"wayfare-skills"}):
        in_map, checked = r in mp, r in dirs or r == "wayfare-skills"
        group = mp.get(r, {}).get("group")
        if r == "wayfare-skills":
            status = "in the study, row under old name"
            group = "infra (as hero-skills)"
        elif r in study and in_map and checked:
            status = "in the study and the map"
        elif r in study and not in_map:
            status = "in the study, no row"
        elif in_map and not checked:
            status = "row, no checkout"
        elif r in OUT_OF_SCOPE:
            status = "left the factory, row kept"
        elif in_map:
            status = "row, not fleet (group none)"
        else:
            status = "checkout, no row"
        out.append({"repo": r, "group": group, "in_map": in_map, "checked_out": checked, "status": status})
    order = ["in the study and the map", "in the study, row under old name", "in the study, no row",
             "left the factory, row kept", "row, not fleet (group none)", "row, no checkout", "checkout, no row"]
    counts = {s: sum(1 for o in out if o["status"] == s) for s in order}
    # Chapter 15's NEW-C07-F: does each row's group agree with what the repo is?
    expected = {"app": "apps", "app, no features yet": "apps", "allied": None}
    misclass = []
    for r in study:
        g = mp.get(r, {}).get("group")
        cat = category_of(r)
        want = "template" if r == TEMPLATE else "infra" if r.startswith("infrastructure-") else "apps"
        if g and g != want:
            misclass.append((r, g, want))
    # weekly: repos in the study fleet, and how many had a row once the map existed
    first = {r: first_day(r) for r in study}
    weekly_fleet = [sum(1 for r in study if first[r] <= week_end(w)) for w in WEEKS]
    return {"rows": out, "counts": counts, "order": order, "misclass": misclass, "n_rows": len(mp),
            "n_dirs": len(dirs), "weekly_fleet": weekly_fleet, "map_mtime": datetime.fromtimestamp(
                os.path.getmtime(os.path.join(FLEET, "FLEET.md"))).date().isoformat(),
            "study_rows": sum(1 for r in study if r in mp), "study_n": len(study)}


# ------------------------------------------------------------------ Q dev-port-claims ports

PORT_RE = re.compile(r"HOST_PORT:-(\d{4,5})|[\"'\s-](\d{5}):\d{2,5}")


def ports_at(repo, sha):
    t = tree(repo, sha)
    found = set()
    for p in t:
        base = os.path.basename(p)
        if "/" in p or not re.match(r"(docker-)?compose.*\.ya?ml$", base):
            continue
        for m in PORT_RE.finditer(show(repo, sha, p)):
            v = m.group(1) or m.group(2)
            # 33000 is auth's port; other repos map it for a local auth sidecar, not as their own stack
            if v.startswith("33") and not (v == "33000" and repo != "auth"):
                found.add(int(v))
    return found


def q_dev_port_claims(con):
    repos = [r for r in APPS + [TEMPLATE] if has_mirror(r)]
    weekly = {}
    for r in repos:
        weekly[r] = []
        for w in WEEKS:
            sha = sha_at(r, week_end(w))
            weekly[r].append(sorted(ports_at(r, sha)) if sha else None)
    statuses = ["own port", "template's port (33099)", "shares a port", "no dev stack yet"]
    series = {s: [0] * len(WEEKS) for s in statuses}
    for i in range(len(WEEKS)):
        owner = defaultdict(set)
        for r in repos:
            for p in (weekly[r][i] or []):
                owner[p].add(r)
        for r in repos:
            ps = weekly[r][i]
            if ps is None:
                continue
            if not ps:
                series["no dev stack yet"][i] += 1
            elif r != TEMPLATE and 33099 in ps:
                series["template's port (33099)"][i] += 1
            elif any(len(owner[p]) > 1 for p in ps if p != 33099):
                series["shares a port"][i] += 1
            else:
                series["own port"][i] += 1
    # days from a clone's first commit to its own port, walking every main commit
    claim = {}
    for r in CLONES:
        born = main_log(r)[0][0]
        for d, sha in main_log(r):
            ps = ports_at(r, sha)
            if ps and 33099 not in ps:
                claim[r] = {"born": born, "claimed": d, "days": (date.fromisoformat(d) - date.fromisoformat(born)).days,
                            "port": sorted(ps)[0]}
                break
        else:
            claim[r] = {"born": born, "claimed": None, "days": None, "port": None}
    now = {r: weekly[r][-1] for r in repos}
    return {"series": series, "statuses": statuses, "weekly": weekly, "claim": claim, "now": now}


# ------------------------------------------------------------------ Q repo-kind-requirements what each kind of repo carries

ARTIFACTS = [
    ("AGENTS.md", lambda t: "AGENTS.md" in t),
    ("HERO.md", lambda t: "HERO.md" in t),
    ("DESIGN.md", lambda t: "DESIGN.md" in t),
    ("pre-commit", lambda t: ".pre-commit-config.yaml" in t or ".pre-commit-config.yml" in t),
    ("CI workflow", lambda t: any(p.startswith(".github/workflows/") for p in t)),
    ("auto-approve caller", lambda t: any(re.match(r"\.github/workflows/auto-approve\.ya?ml$", p) for p in t)),
    (".gitignore", lambda t: ".gitignore" in t),
    (".env.example", lambda t: any(os.path.basename(p) == ".env.example" for p in t)),
    ("Dependabot", lambda t: any(re.match(r"\.github/dependabot\.ya?ml$", p) for p in t)),
]


def q_repo_kind_requirements(con):
    repos = [r for r in IN_SCOPE if has_mirror(r)]
    grid = {}
    by_cat = defaultdict(lambda: [[] for _ in MONTHS])
    for r in repos:
        cat = category_of(r)
        for i, m in enumerate(MONTHS):
            sha = sha_at(r, clamp(month_end(m)))
            if not sha:
                continue
            t = tree(r, sha)
            have = [a for a, f in ARTIFACTS if f(t)]
            by_cat[cat][i].append(len(have) / len(ARTIFACTS))
            if i == len(MONTHS) - 1:
                grid[r] = have
    series = {c: [round(sum(v) / len(v), 3) if v else None for v in by_cat[c]] for c in ["app", "app, no features yet", "allied"]}
    missing = {a: [r for r in repos if a not in grid.get(r, [])] for a, _ in ARTIFACTS}
    n_controls = rows(con, "SELECT COUNT(DISTINCT control_id) n FROM knowledge.controls")[0]["n"]
    scopes = Counter(r["repo"] for r in rows(con, "SELECT DISTINCT control_id, repo FROM knowledge.controls"))
    role_words = rows(con, """SELECT COUNT(DISTINCT control_id) n FROM knowledge.controls
                              WHERE raw_json LIKE '%template repo%' OR raw_json LIKE '%role%' OR raw_json LIKE '%group:%'""")[0]["n"]
    return {"series": series, "grid": grid, "missing": missing, "artifacts": [a for a, _ in ARTIFACTS],
            "n_controls": n_controls, "control_scopes": dict(scopes), "role_words": role_words}


# ------------------------------------------------------------------ Q template-shape the template's shape

def layer_of(path):
    top = path.split("/")[0]
    if top in ("lib", "service"):
        return "Go backend (lib/, service/)"
    if top == "schema":
        return "API schema (schema/)"
    if top == "ui":
        return "UI (ui/)"
    if top == "cli":
        return "CLI (cli/)"
    if top in ("scripts", "CHECKS.yaml", "CONTROLS.yaml"):
        return "Register and scripts"
    if top in (".github",) or path in (".pre-commit-config.yaml", "Justfile", "Makefile", ".golangci.yaml",
                                       ".golangci.yml", ".hadolint.yaml") or top.startswith("Dockerfile") \
            or top.startswith("docker-compose") or top in ("dev.sh", "supervisor.mjs", "go.work", "go.work.sum"):
        return "Build, CI and dev stack"
    if top in (".claude", ".plans") or path in ("AGENTS.md", "CLAUDE.md", "HERO.md"):
        return "Agent files"
    if path.endswith(".md") or top == "docs":
        return "Docs"
    return "Other"


LAYERS = ["Go backend (lib/, service/)", "UI (ui/)", "CLI (cli/)", "API schema (schema/)", "Build, CI and dev stack",
          "Register and scripts", "Agent files", "Docs", "Other"]
GENERATED = re.compile(r"(^|/)(gen|generated)/|\.pb\.go$|_pb\.ts$|connect\.go$|routeTree\.gen\.ts$|"
                       r"(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|go\.sum|go\.work\.sum)$")


def q_template_shape_template(con):
    weeks = [w for w in WEEKS if week_end(w) >= main_log(TEMPLATE)[0][0]]
    series = {l: [] for l in LAYERS}
    for w in WEEKS:
        sha = sha_at(TEMPLATE, clamp(week_end(w)))
        acc = Counter()
        if sha:
            t = {p: v for p, v in tree(TEMPLATE, sha).items() if not GENERATED.search(p)}
            ln = blob_lines(TEMPLATE, [b for b, _ in t.values()])
            for p, (b, _) in t.items():
                acc[layer_of(p)] += ln[b]
        for l in LAYERS:
            series[l].append(acc.get(l, 0))
    first_clone = min(main_log(c)[0][0] for c in CLONES)
    i_clone = next(i for i, w in enumerate(WEEKS) if week_end(w) >= first_clone)
    head = sha_at(TEMPLATE, LATEST)
    t = tree(TEMPLATE, head)
    tops = Counter(p.split("/")[0] for p in t)
    return {"series": series, "first_clone": first_clone, "at_first_clone": {l: series[l][i_clone] for l in LAYERS},
            "now": {l: series[l][-1] for l in LAYERS}, "files_now": len(t), "tops": tops.most_common(12),
            "go_work": "go.work" in t, "has_ui": any(p.startswith("ui/") for p in t),
            "has_cli": any(re.match(r"(cmd|cli)/", p) for p in t),
            "commits": len(main_log(TEMPLATE)), "first": main_log(TEMPLATE)[0][0]}


# ------------------------------------------------------------------ Q clone-template-share clone origin and drift

SKIP_DRIFT = re.compile(r"^(\.plans/|README\.md$|HERO\.md$|DESIGN\.md$|AGENTS\.md$|CLAUDE\.md$)")


def ids(t):
    return {p: b for p, (b, _) in t.items()}


def q_clone_template_share(con):
    tlog = main_log(TEMPLATE)
    ttrees = [(d, sha, ids(tree(TEMPLATE, sha))) for d, sha in tlog]
    origin = {}
    for c in CLONES:
        d0, sha0 = main_log(c)[0]
        ct = ids(tree(c, sha0))
        best = None
        for i, (d, sha, tt) in enumerate(ttrees):
            if d > d0:
                break
            same = sum(1 for p, b in ct.items() if tt.get(p) == b)
            score = same / max(len(ct), len(tt))
            if best is None or score >= best["score"]:
                best = {"index": i + 1, "day": d, "sha": sha[:7], "same": same, "score": score, "clone_files": len(ct),
                        "template_files": len(tt)}
        best["born"] = d0
        best["template_commits_then"] = best["index"]
        best["inventory"] = {a: f(tree(c, sha0)) for a, f in ARTIFACTS}
        origin[c] = best
    # weekly: share of the template's files (that week) byte-identical in the clone
    drift = {}
    for c in CLONES:
        born = main_log(c)[0][0]
        vals = []
        for w in WEEKS:
            end = clamp(week_end(w))
            if end < born:
                vals.append(None)
                continue
            tt = {p: b for p, b in ids(tree(TEMPLATE, sha_at(TEMPLATE, end))).items() if not SKIP_DRIFT.search(p)}
            ct = ids(tree(c, sha_at(c, end)))
            vals.append(round(sum(1 for p, b in tt.items() if ct.get(p) == b) / len(tt), 3))
        drift[c] = vals
    return {"origin": origin, "drift": drift, "template_commits_now": len(tlog)}


# ------------------------------------------------------------------ Q stack-convergence stack homogeneity

def _pkg(repo, sha, path):
    try:
        return json.loads(show(repo, sha, path) or "{}")
    except ValueError:
        return {}


def markers(repo, sha):
    t = tree(repo, sha)
    ui_pkg = _pkg(repo, sha, "ui/package.json") if "ui/package.json" in t else {}
    deps = {**ui_pkg.get("dependencies", {}), **ui_pkg.get("devDependencies", {})}
    comp = show(repo, sha, "ui/components.json") if "ui/components.json" in t else ""
    return {
        "go.work": "go.work" in t,
        "lib/ + service/": any(p.startswith("lib/") for p in t) and any(p.startswith("service/") for p in t),
        "TanStack Start ui/": any(k.startswith("@tanstack/react-start") or k.startswith("@tanstack/start") for k in deps),
        "@aihero registry": "@aihero" in comp,
        "Dockerfile.dev": "Dockerfile.dev" in t,
        "Justfile": "Justfile" in t or "justfile" in t,
        "pre-commit": ".pre-commit-config.yaml" in t or ".pre-commit-config.yml" in t,
        "supervisor.mjs": "supervisor.mjs" in t,
    }


MARKERS = ["go.work", "lib/ + service/", "TanStack Start ui/", "@aihero registry", "Dockerfile.dev", "Justfile",
           "pre-commit", "supervisor.mjs"]
FAMILIES = ["full template stack (7–8 of 8)", "partial (3–6)", "different (0–2)"]


def family(score):
    return FAMILIES[0] if score >= 7 else FAMILIES[1] if score >= 3 else FAMILIES[2]


def q_stack_convergence(con):
    repos = [r for r in IN_SCOPE if has_mirror(r)]
    series = {f: [0] * len(MONTHS) for f in FAMILIES}
    per_repo = {}
    for r in repos:
        per_repo[r] = []
        for i, m in enumerate(MONTHS):
            sha = sha_at(r, clamp(month_end(m)))
            if not sha:
                per_repo[r].append(None)
                continue
            mk = markers(r, sha)
            s = sum(mk.values())
            per_repo[r].append(s)
            series[family(s)][i] += 1
    grid = {r: markers(r, sha_at(r, LATEST)) for r in repos}
    return {"series": series, "per_repo": per_repo, "grid": grid}


# ------------------------------------------------------------------ Q shared-service-deps shared-service dependencies

INFRA_NAME = {"auth": "auth", "design-system": "design", "website": "website", "hiro": "hiro", "saga": "saga",
              "elevate-commons": "commons", "aihero-wayfare": "wayfare", "aihero-steadfast": "steadfast",
              "ah-cozy": "cozy", "aihero-dokyu": "dokyu", "aihero-mehr": "mehr"}
IE = "infrastructure-environments"


def grep_count(repo, sha, pattern, paths=()):
    out = git(repo, "grep", "-I", "-l", "-E", pattern, sha, "--", *paths)
    return [l.split(":", 1)[1] for l in out.splitlines() if ":" in l]


def uses_identity(repo, sha, day):
    return bool(grep_count(repo, sha, r"auth\.aihero\.studio|AUTH_ISSUER|OIDC_ISSUER",
                           [":(exclude)*.md", ":(exclude).plans/*", ":(exclude)docs/*", ":(exclude).claude/*"]))


def uses_registry(repo, sha, day):
    t = tree(repo, sha)
    return "ui/components.json" in t and bool(re.search(r"@aihero|design\.aihero\.studio", show(repo, sha, "ui/components.json")))


def has_infra(repo, sha, day):
    ie = sha_at(IE, day)
    return bool(ie) and any(re.search(rf"/app_{INFRA_NAME[repo]}\.tf$", p) for p in tree(IE, ie))


SERVICES = {
    "identity (auth)": (uses_identity, r"auth\.aihero\.studio|\bauth\b service|identity provider|OIDC|OAuth|sign[- ]in"),
    "design-system registry": (uses_registry, r"@aihero|design system|design-system|design\.aihero\.studio"),
    "infrastructure": (has_infra, r"infrastructure-(environments|root)|OpenTofu|Terraform|EKS|Kubernetes|k8s"),
}


def q_shared_service_deps(con):
    apps = [r for r in APPS if has_mirror(r)]
    series, grid = {}, {}
    for svc, (uses, doc_re) in SERVICES.items():
        code_n, rec_n = [0] * len(MONTHS), [0] * len(MONTHS)
        for r in apps:
            if (svc.startswith("design") and r == "design-system") or (svc.startswith("identity") and r == "auth"):
                continue
            for i, m in enumerate(MONTHS):
                day = clamp(month_end(m))
                sha = sha_at(r, day)
                if not sha:
                    continue
                code = uses(r, sha, day)
                has_md = "DESIGN.md" in tree(r, sha)
                rec = has_md and bool(grep_count(r, sha, doc_re, ["DESIGN.md"]))
                code_n[i] += code
                rec_n[i] += code and rec
                if i == len(MONTHS) - 1:
                    grid.setdefault(r, {})[svc] = {"code": code, "record": rec, "has_design_md": has_md}
        series[svc] = {"code": code_n, "code and record": rec_n}
    return {"series": series, "grid": grid, "apps": apps}


# ------------------------------------------------------------------ Q design-system-scaffolding the design system

DS = "design-system"


def ds_kind(path):
    if GENERATED.search(path) or path.startswith("public/r/") or path.startswith("design-cache/") \
            or path == "registry.json":
        return None
    if re.search(r"(\.test\.|\.spec\.|/__tests__/|^e2e/|^tests?/)", path):
        return "tests"
    if path.startswith("src/components/examples/"):
        return "examples and docs site"
    if re.match(r"src/components/(ui|atoms|molecules|organisms|templates|blocks)/", path) or path.startswith("registry/"):
        return "registry components"
    if re.match(r"(src/(app|routes|pages|demo|docs)|handbook|docs|content|mockup|claude-design)/", path) or path.endswith(".mdx"):
        return "examples and docs site"
    if re.match(r"(scripts|\.github|\.claude)/", path) or "/" not in path:
        return "tooling, CI and agent files"
    return "shared lib and app shell"


DS_KINDS = ["registry components", "examples and docs site", "tests", "shared lib and app shell", "tooling, CI and agent files"]
ITEM_KINDS = {"registry:ui": "components", "registry:block": "components", "registry:example": "examples"}


def registry_items(sha):
    try:
        items = json.loads(show(DS, sha, "registry.json")).get("items", [])
    except ValueError:
        return Counter()
    return Counter(ITEM_KINDS.get(i.get("type"), "other") for i in items)


def q_design_system_scaffolding_design_system(con):
    items, kinds = {k: [] for k in ("components", "examples", "other")}, {k: [] for k in DS_KINDS}
    for w in WEEKS:
        sha = sha_at(DS, clamp(week_end(w)))
        if not sha:
            for k in items:
                items[k].append(None)
            for k in DS_KINDS:
                kinds[k].append(None)
            continue
        t = tree(DS, sha)
        c = registry_items(sha) if "registry.json" in t else Counter()
        for k in items:
            items[k].append(c.get(k, 0))
        ln = blob_lines(DS, [b for b, _ in t.values()])
        acc = Counter()
        for p, (b, _) in t.items():
            k = ds_kind(p)
            if k:
                acc[k] += ln[b]
        for k in DS_KINDS:
            kinds[k].append(acc.get(k, 0))
    # consumption: registry components vendored in each app's ui/src/components/ui
    consumed = {}
    names = set()
    try:
        names = {i["name"] for i in json.loads(show(DS, sha_at(DS, LATEST), "registry.json")).get("items", [])}
    except ValueError:
        pass
    for r in APPS:
        if r == DS or not has_mirror(r):
            continue
        consumed[r] = []
        for m in MONTHS:
            sha = sha_at(r, clamp(month_end(m)))
            if not sha:
                consumed[r].append(None)
                continue
            comp = show(r, sha, "ui/components.json") if "ui/components.json" in tree(r, sha) else ""
            consumed[r].append(sum(1 for p in tree(r, sha) if p.startswith("ui/src/components/")
                                   and os.path.splitext(os.path.basename(p))[0] in names) if "@aihero" in comp else 0)
    return {"items": items, "kinds": kinds, "consumed": consumed, "n_items_now": {k: v[-1] for k, v in items.items()}}


# ------------------------------------------------------------------ Q app-lifetime-work work per app, by age

def q_app_lifetime_work_work(con):
    facts = [f for f in changeset_facts(con) if not f["dependabot"] and f["repo"] in APPS]
    by = defaultdict(Counter)
    for f in facts:
        by[f["repo"]][f["month"]] += 1
    order = sorted(by, key=lambda r: -sum(by[r].values()))
    monthly = {r: [by[r].get(m, 0) for m in MONTHS] for r in order}
    born = {r: first_day(r) for r in order}
    aged = defaultdict(Counter)
    for f in facts:
        age = (date.fromisoformat(f["day"]) - date.fromisoformat(born[f["repo"]])).days // 28
        aged[f["repo"]][age] += 1
    horizon = 9
    by_age = {r: [aged[r].get(a, 0) if (date.fromisoformat(LATEST) - date.fromisoformat(born[r])).days >= a * 28 else None
                  for a in range(horizon)] for r in order}
    totals = {r: sum(by[r].values()) for r in order}
    stages = Counter((f["repo"], f["stage"]) for f in facts)
    return {"monthly": monthly, "by_age": by_age, "totals": totals, "born": born, "stages": dict(stages), "n": len(facts)}


# ------------------------------------------------------------------ Q features-vs-structure work mix per app

MIX = ["customer-facing feature", "platform feature", "fix", "upkeep (chore, deps, CI, docs, tests, refactor)", "security"]


def mix_of(work_type, theme):
    if work_type in ("feature", "feat", "design_ui"):
        return MIX[0] if theme in ("product", "design_ui") else MIX[1]
    if work_type == "fix":
        return MIX[2]
    if work_type == "security":
        return MIX[4]
    return MIX[3]


def model_family(m):
    if not m:
        return None
    for fam in ("Opus", "Sonnet", "Fable", "Haiku"):
        if fam in m:
            return fam
    return None


def q_features_vs_structure_mix(con):
    wt = {(r["repo"], r["unit_kind"], r["unit_id"], r["set_idx"]): (r["work_type"], r["theme"])
          for r in rows(con, "SELECT * FROM detectors.cs_worktype")}
    model = {(r["repo"], r["pr_number"]): r["trailer_model"] for r in rows(
        con, "SELECT repo, pr_number, trailer_model FROM git.commits WHERE pr_number IS NOT NULL")}
    facts = []
    for f in changeset_facts(con):
        if f["repo"] not in APPS or f["dependabot"]:
            continue
        t = wt.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"]))
        if not t:
            continue
        facts.append({**f, "mix": mix_of(*t), "work_type": t[0], "theme": t[1],
                      "model": model_family(model.get((f["repo"], f["pr"])))})
    weekly = {m: [0] * len(WEEKS) for m in MIX}
    for f in facts:
        if f["week"] in WEEKS:
            weekly[f["mix"]][WEEKS.index(f["week"])] += 1
    share = []
    for i in range(len(WEEKS)):
        n = sum(weekly[m][i] for m in MIX)
        share.append(round(weekly[MIX[0]][i] / n, 3) if n >= 10 else None)
    per_repo = {}
    for r in APPS:
        rf = [f for f in facts if f["repo"] == r]
        if len(rf) < 20:
            continue
        per_repo[r] = []
        for m in MONTHS:
            mf = [f for f in rf if f["month"] == m]
            per_repo[r].append(round(sum(1 for f in mf if f["mix"] == MIX[0]) / len(mf), 3) if len(mf) >= 8 else None)
    totals = {r: Counter(f["mix"] for f in facts if f["repo"] == r) for r in APPS}
    by_model = {}
    for fam in ("Opus", "Sonnet", "Fable"):
        mf = [f for f in facts if f["model"] == fam]
        by_model[fam] = {"n": len(mf), "feature": round(sum(1 for f in mf if f["mix"] == MIX[0]) / len(mf), 3) if mf else None}
    # same months, Opus vs the rest, to take calendar time out of the model comparison
    paired = {}
    for m in MONTHS:
        mf = [f for f in facts if f["month"] == m and f["model"]]
        o = [f for f in mf if f["model"] == "Opus"]
        x = [f for f in mf if f["model"] != "Opus"]
        if len(o) >= 20 and len(x) >= 20:
            fs = lambda v: round(sum(1 for f in v if f["mix"] == MIX[0]) / len(v), 3)
            paired[m] = {"opus": fs(o), "other": fs(x), "n_opus": len(o), "n_other": len(x)}
    halves = {}
    for label, lo, hi in (("before Opus 5 (to 23 Jul)", "2026-01-01", "2026-07-23"),
                          ("after Opus 5 (from 24 Jul)", "2026-07-24", "2026-12-31")):
        v = [f for f in facts if lo <= f["day"] <= hi]
        halves[label] = {"n": len(v), "feature": round(sum(1 for f in v if f["mix"] == MIX[0]) / len(v), 3)}
    all_sets = [f for f in changeset_facts(con) if f["repo"] in APPS and not f["dependabot"]]
    return {"weekly": weekly, "share": share, "per_repo": per_repo, "totals": {r: dict(c) for r, c in totals.items()},
            "by_model": by_model, "paired": paired, "halves": halves, "n": len(facts), "n_all": len(all_sets),
            "overall": round(sum(1 for f in facts if f["mix"] == MIX[0]) / len(facts), 3)}


# ------------------------------------------------------------------ Q feature-scope-progress features shipped vs open

def q_feature_scope_progress_features(con):
    items = rows(con, """SELECT repo, item_id, status, created_ts, done_ts, updated_ts FROM plans.plan_items
                         WHERE type='feature'""")
    items = [i for i in items if i["repo"] in APPS]
    weeks = [w for w in WEEKS if w >= "2026-W30"]
    DONE, DROPPED = {"done", "committed", "accepted"}, {"dropped", "rejected", "superseded"}

    def state(i, end):
        if not i["created_ts"] or i["created_ts"][:10] > end:
            return None
        if i["status"] in DONE and (i["done_ts"] or i["updated_ts"] or "")[:10] <= end:
            return "shipped"
        if i["status"] in DROPPED and (i["updated_ts"] or "")[:10] <= end:
            return "dropped"
        return "open"
    series = {s: [] for s in ("shipped", "open", "dropped")}
    per_repo = defaultdict(list)
    intake = []
    for w in weeks:
        end = week_end(w)
        c = Counter(state(i, end) for i in items)
        for s in series:
            series[s].append(c.get(s, 0))
        intake.append(sum(1 for i in items if i["created_ts"] and week_of(i["created_ts"][:10]) == w))
    repos = sorted({i["repo"] for i in items}, key=lambda r: -sum(1 for i in items if i["repo"] == r))
    for r in repos:
        ri = [i for i in items if i["repo"] == r]
        for m in MONTHS[6:]:
            c = Counter(state(i, clamp(month_end(m))) for i in ri)
            n = c["shipped"] + c["open"]
            per_repo[r].append(round(c["shipped"] / n, 3) if n else None)
    no_done_ts = sum(1 for i in items if i["status"] in DONE and not i["done_ts"])
    ship_days = sorted((date.fromisoformat(i["done_ts"][:10]) - date.fromisoformat(i["created_ts"][:10])).days
                       for i in items if i["status"] in DONE and i["done_ts"] and i["created_ts"])
    median_ship = ship_days[len(ship_days) // 2] if ship_days else None
    within_week = round(sum(1 for d in ship_days if d <= 7) / len(ship_days), 3) if ship_days else None
    now = Counter(state(i, LATEST) for i in items)
    return {"weeks": weeks, "series": series, "intake": intake, "per_repo": dict(per_repo), "now": dict(now),
            "n": len(items), "no_done_ts": no_done_ts, "repos": repos, "median_ship": median_ship,
            "within_week": within_week, "n_ship": len(ship_days),
            "by_repo_now": {r: dict(Counter(state(i, LATEST) for i in items if i["repo"] == r)) for r in repos},
            "no_features": [r for r in APPS if r not in repos]}


# ------------------------------------------------------------------ Q code-origin-split code volume

VENDORED = re.compile(r"^(\.claude/(skills|rules|hooks)/|\.github/workflows/auto-approve\.ya?ml$|ui/src/components/ui/|"
                      r"vendor/|third_party/)")


def code_class(path):
    if GENERATED.search(path):
        return "generated"
    if VENDORED.search(path):
        return "vendored"
    if path.startswith(".plans/") or path.endswith(".md"):
        return None
    return "written for the app"


def q_code_origin_split_volume(con):
    repos = [r for r in APPS if has_mirror(r)]
    monthly, split = {}, {}
    for r in repos:
        monthly[r] = []
        for m in MONTHS:
            sha = sha_at(r, clamp(month_end(m)))
            if not sha:
                monthly[r].append(None)
                continue
            t = tree(r, sha)
            ln = blob_lines(r, [b for b, _ in t.values()])
            acc = Counter()
            for p, (b, _) in t.items():
                k = code_class(p)
                if k:
                    acc[k] += ln[b]
            monthly[r].append(acc["written for the app"])
            if m == MONTHS[-1]:
                split[r] = dict(acc)
    return {"monthly": monthly, "split": split}


# ------------------------------------------------------------------ Q app-to-first-feature time to first feature and deploy

def q_app_to_first_feature(con):
    feat = {}
    wt = {(r["repo"], r["unit_kind"], r["unit_id"], r["set_idx"]): mix_of(r["work_type"], r["theme"])
          for r in rows(con, "SELECT * FROM detectors.cs_worktype")}
    for f in sorted(changeset_facts(con), key=lambda f: f["day"]):
        if f["repo"] in APPS and not f["dependabot"] and wt.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"])) == MIX[0]:
            feat.setdefault(f["repo"], (f["day"], f["label"]))
    deploy = {}
    for r in rows(con, """SELECT repo, MIN(created_ts) d FROM github.ci_runs
                          WHERE conclusion='success' AND LOWER(workflow_name) LIKE 'deploy%' GROUP BY repo"""):
        deploy[r["repo"]] = r["d"][:10]
    infra = {}
    for r in APPS:
        out = git(IE, "log", "--reverse", "--format=%as", "main", "--", f"customers/*/*/app_{INFRA_NAME[r]}.tf")
        if out.strip():
            infra[r] = out.split()[0]
    out = []
    for r in APPS:
        born = first_day(r)
        days = lambda x: (date.fromisoformat(x) - date.fromisoformat(born)).days if x else None
        f = feat.get(r)
        out.append({"repo": r, "born": born, "first_feature": f[0] if f else None, "feature_label": f[1] if f else None,
                    "infra_defined": infra.get(r), "first_deploy": deploy.get(r),
                    "to_feature": days(f[0] if f else None), "to_infra": days(infra.get(r)),
                    "to_deploy": days(deploy.get(r)), "clone": r in CLONES})
    return {"apps": out}


# ------------------------------------------------------------------ Q route-allowlist-pairs the route / proxy contract

GO_FILE, TS_FILE = "lib/server/server.go", "ui/src/server/api-prefixes.ts"
GO_PATH = re.compile(r"\b(?:Get|Post|Put|Patch|Delete|Handle|HandleFunc|Mount|Route)\(\s*\"(/[^\"]*)\"|"
                     r"\breg\(\s*http\.Method\w+,\s*\"(/[^\"]*)\"")
TS_PATH = re.compile(r"[\"'`](/[A-Za-z0-9_.\-/]*)[\"'`]")


def top(p):
    seg = p.strip("/").split("/")[0]
    return "/" + seg


CONNECT_GO = re.compile(r"(\w+?)v\d+connect\.New\w+Handler")
ROUTE_OPEN = re.compile(r"\.Route\(\s*\"(/[^\"]*)\"")


def go_prefixes(src):
    """Top-level paths the Go router serves. Routes nested in r.Route("/api", ...) count as /api, and a
    ConnectRPC mount (whose path comes from generated code, not a literal) counts by its service package."""
    out, stack, depth = set(), [], 0
    for line in src.splitlines():
        code = line.split("//", 1)[0]
        for m in CONNECT_GO.finditer(code):
            out.add("connect:" + m.group(1).lower())
        if "mcpserver.MetadataPath" in code:
            out.add("/.well-known")
        ro = ROUTE_OPEN.search(code)
        for m in GO_PATH.finditer(code):
            out.add(stack[0][0] if stack else top(m.group(1) or m.group(2)))
        if ro and "func(" in code:
            stack.append((top(ro.group(1)) if not stack else stack[0][0], depth))
        depth += code.count("{") - code.count("}")
        while stack and depth <= stack[-1][1]:
            stack.pop()
    return out


def ts_prefixes(src):
    body = "\n".join(l.split("//", 1)[0] for l in src.splitlines())
    out = set()
    for p in TS_PATH.findall(body):
        if len(p) <= 1:
            continue
        m = re.match(r"/([\w.]+?)\.v\d+\.?$", p)
        out.add("connect:" + m.group(1).split(".")[-1].lower() if m else top(p))
    return out


def go_side(repo, sha, t):
    files = [p for p in t if re.match(r"lib/(server|route)/[^/]+\.go$", p) and not p.endswith("_test.go")]
    out = set()
    for p in files:
        out |= go_prefixes(show(repo, sha, p))
    return out, tuple(sorted(t[p][0] for p in files))


def q_route_allowlist_pairs_contract(con):
    events, out_of_sync = [], {}
    repos = [r for r in APPS + [TEMPLATE] if has_mirror(r)]
    for r in repos:
        prev_go = prev_ts = None
        prev_blobs = None
        state = []
        for d, sha in main_log(r):
            t = tree(r, sha)
            if TS_FILE not in t or not any(p.startswith("lib/server/") for p in t):
                prev_go = prev_ts = None
                continue
            blobs = (tuple(sorted(t[p][0] for p in t if re.match(r"lib/(server|route)/", p))), t[TS_FILE][0])
            if blobs == prev_blobs:
                continue
            prev_blobs = blobs
            g, _ = go_side(r, sha, t)
            s_ = ts_prefixes(show(r, sha, TS_FILE))
            state.append((d, len(g - s_) + len(s_ - g), sorted(g - s_), sorted(s_ - g)))
            if prev_go is not None:
                dg, ds = g != prev_go, s_ != prev_ts
                if dg or ds:
                    events.append({"repo": r, "day": d, "sha": sha[:7], "go": dg, "ts": ds,
                                   "go_added": sorted(g - prev_go), "ts_added": sorted(s_ - prev_ts),
                                   "go_removed": sorted(prev_go - g), "ts_removed": sorted(prev_ts - s_)})
            prev_go, prev_ts = g, s_
        out_of_sync[r] = state
    for e in events:
        e["kind"] = "both in one PR" if e["go"] and e["ts"] else "Go side only" if e["go"] else "proxy side only"
    # a one-sided change is closed when the two sides agree again; how many days did that take?
    for e in events:
        if e["kind"] == "both in one PR":
            e["closed_days"] = 0
            continue
        later = [s for s in out_of_sync[e["repo"]] if s[0] >= e["day"]]
        agree = next((s for s in later if s[1] == 0), None)
        e["closed_days"] = (date.fromisoformat(agree[0]) - date.fromisoformat(e["day"])).days if agree else None
    kinds = ["both in one PR", "Go side only", "proxy side only"]
    monthly = {k: [sum(1 for e in events if e["kind"] == k and e["day"][:7] == m) for m in MONTHS] for k in kinds}
    per_repo = {r: dict(Counter(e["kind"] for e in events if e["repo"] == r)) for r in sorted({e["repo"] for e in events})}
    now = {r: (v[-1][1], v[-1][2], v[-1][3]) for r, v in out_of_sync.items() if v}
    # weekly count of repos whose two lists disagree
    weekly = []
    for w in WEEKS:
        end = week_end(w)
        n = 0
        for r, v in out_of_sync.items():
            last = [s for s in v if s[0] <= end]
            if last and last[-1][1] > 0:
                n += 1
        weekly.append(n)
    weekly_have = [sum(1 for r, v in out_of_sync.items() if v and v[0][0] <= week_end(w)) for w in WEEKS]
    return {"events": events, "monthly": monthly, "per_repo": per_repo, "kinds": kinds, "now": now,
            "weekly_out_of_sync": weekly, "weekly_have": weekly_have}


CON = None


def all_data(which=None):
    global CON
    CON = _connect()
    fns = {"fleet-size-over-time": q_fleet_size_over_time, "fleet-map-accuracy": q_fleet_map_accuracy, "dev-port-claims": q_dev_port_claims, "repo-kind-requirements": q_repo_kind_requirements, "template-shape": q_template_shape_template, "clone-template-share": q_clone_template_share,
           "stack-convergence": q_stack_convergence, "shared-service-deps": q_shared_service_deps, "design-system-scaffolding": q_design_system_scaffolding_design_system, "app-lifetime-work": q_app_lifetime_work_work, "features-vs-structure": q_features_vs_structure_mix,
           "feature-scope-progress": q_feature_scope_progress_features, "code-origin-split": q_code_origin_split_volume, "app-to-first-feature": q_app_to_first_feature, "route-allowlist-pairs": q_route_allowlist_pairs_contract}
    return {k: f(CON) for k, f in fns.items() if not which or k in which}


if __name__ == "__main__":
    import pprint
    which = sys.argv[1:] or None
    for k, v in all_data(which).items():
        print(f"===== 12.{k}")
        pprint.pprint(v, width=160, compact=True)
