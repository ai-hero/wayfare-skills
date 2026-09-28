"""Security mirror scans, read-only, into .analysis/data/security.sqlite.

    WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/security/scan.py [snap|secrets|vulns|all]

snap:    each repo's default branch at the end of every 2026 ISO week: which security gates
         exist (secret, dependency, container scanning; local hook vs CI), how many workflow
         `uses:` refs and Dockerfile `FROM` lines are pinned, which package ecosystems
         Dependabot covers, and how many scanner suppressions the repo carries.
secrets: every added line in every commit reachable in the mirror, matched against
         high-confidence credential patterns. Only repo, path, short sha, date and rule are
         stored; the matched value never leaves this process
         (repeat sightings of one value share a per-run finding_id, not a hash of it).
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
DATA = os.path.join(ROOT, ".analysis", "data")
MIRRORS = os.path.join(DATA, "mirrors")
DB = os.path.join(DATA, "security.sqlite")
WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]

SECRET_TOOLS = re.compile(r"\b(gitleaks|detect-secrets|trufflehog|ggshield|secretlint)\b")
DEP_SCAN = re.compile(r"\b(govulncheck|npm audit|pnpm audit|yarn audit|bun audit|osv-scanner|pip-audit|trivy fs|"
                      r"scanners: vuln|audit-ci|npm-audit|safety check)\b")
IMAGE_SCAN = re.compile(r"(trivy-action|trivy image|docker/scout-action|scout cves|grype|anchore/scan-action)")
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.M)
FROM = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", re.M | re.I)
JUST_CALL = re.compile(r"\bjust\s+([A-Za-z0-9_-]+)")
MANIFESTS = {"npm": re.compile(r"(^|/)package\.json$"), "gomod": re.compile(r"(^|/)go\.mod$"),
             "docker": re.compile(r"(^|/)Dockerfile[^/]*$"), "github-actions": re.compile(r"^\.github/workflows/.+\.ya?ml$"),
             "pip": re.compile(r"(^|/)(requirements[^/]*\.txt|pyproject\.toml)$"), "terraform": re.compile(r"\.tf$")}
DOC_FILES = ("AGENTS.md", "CLAUDE.md", "HERO.md", "README.md", "SECURITY.md")
DOC_CLAIMS = {"secret_scan": re.compile(r"gitleaks|detect-secrets|trufflehog|secret scann", re.I),
              "image_scan": re.compile(r"\btrivy\b|docker scout|\bscout\b|image scan|container scan", re.I),
              "dep_scan": re.compile(r"govulncheck|npm audit|osv-scanner|pip-audit", re.I),
              "action_pins": re.compile(r"(pinned|pin) (to|by) (a |the |full |commit )*sha|sha-pinned", re.I),
              "dependabot": re.compile(r"dependabot", re.I)}


# Exit 1 (git grep: no match) and 128 (path absent at that revision) read as empty; a missing mirror or
# ref must not, or a broken checkout reports as a repo with nothing in it.
GIT_BROKEN = ("not a git repository", "cannot change to", "unknown revision", "bad object")


def git(repo, *args):
    p = subprocess.run(["git", "-C", os.path.join(MIRRORS, repo + ".git"), *args], capture_output=True, text=True,
                       errors="replace")
    if p.returncode not in (0, 1, 128) or any(s in p.stderr for s in GIT_BROKEN):
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {p.stderr.strip()}")
    return p.stdout if p.returncode == 0 else ""


def strip_comments(text):
    out = []
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("#"):
            continue
        out.append(re.sub(r"\s+#.*$", "", line))
    return "\n".join(out)


def just_recipes(text):
    """{recipe: body} from a justfile; bodies are the indented lines under each header."""
    recipes, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^@?([A-Za-z0-9_-]+)(?:\s+[^:=]*)?:(?!=)(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            cur = m.group(1)
            recipes[cur] = m.group(2) + "\n"
        elif cur and line.startswith((" ", "\t")):
            recipes[cur] += line + "\n"
        elif line.strip() and not line.startswith((" ", "\t")):
            cur = None
    return recipes


def expand_just(text, recipes, depth=2):
    """Workflow text plus the bodies of the just recipes it calls (and their dependencies)."""
    seen, frontier, out = set(), set(JUST_CALL.findall(text)), text
    for _ in range(depth):
        nxt = set()
        for r in frontier - seen:
            seen.add(r)
            body = recipes.get(r, "")
            out += "\n" + body
            head = body.splitlines()[0] if body else ""
            nxt |= set(JUST_CALL.findall(body)) | set(re.findall(r"[A-Za-z0-9_-]+", head))
        frontier = nxt
    return out


def week_end(w):
    d = date.fromisocalendar(int(w[:4]), int(w[6:]), 7)
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()


def snapshot(repo, sha):
    files = git(repo, "ls-tree", "-r", "--name-only", sha).splitlines()
    show = lambda p: git(repo, "show", f"{sha}:{p}")
    pc_path = next((f for f in files if f in (".pre-commit-config.yaml", ".pre-commit-config.yml")), None)
    pc = strip_comments(show(pc_path)) if pc_path else ""
    jf = next((f for f in files if f in ("justfile", "Justfile", ".justfile")), None)
    recipes = just_recipes(show(jf)) if jf else {}
    wf_files = [f for f in files if re.match(r"^\.github/workflows/[^/]+\.ya?ml$", f)]
    wfs = {f: strip_comments(show(f)) for f in wf_files}
    ci_all = "\n".join(expand_just(t, recipes) for t in wfs.values())
    ci_runs_precommit = bool(re.search(r"pre-commit(/action|\s+run)|\bprek\s+run", ci_all))
    secret_local = bool(SECRET_TOOLS.search(pc))
    secret_ci = bool(SECRET_TOOLS.search(ci_all)) or (ci_runs_precommit and secret_local)
    dep_scan_ci = bool(DEP_SCAN.search(ci_all)) or (ci_runs_precommit and bool(DEP_SCAN.search(pc)))
    dep_scan_local = bool(DEP_SCAN.search(pc))
    image_ci = bool(IMAGE_SCAN.search(ci_all))
    dockerfiles = [f for f in files if re.search(r"(^|/)Dockerfile[^/]*$", f) and "node_modules" not in f]
    uses = [u for t in wfs.values() for u in USES.findall(t) if not u.startswith("./") and "docker://" not in u]
    pinned = [u for u in uses if re.search(r"@[0-9a-f]{40}$", u)]
    froms = []
    for f in dockerfiles:
        for img in FROM.findall(show(f)):
            if img.lower() == "scratch" or "$" in img:
                continue
            froms.append(img)
    stages = set()
    for f in dockerfiles:
        stages |= {m.lower() for m in re.findall(r"^\s*FROM\s+\S+\s+AS\s+(\S+)", show(f), re.M | re.I)}
    froms = [i for i in froms if i.lower() not in stages]
    digest = [i for i in froms if "@sha256:" in i]
    dep_path = next((f for f in files if f in (".github/dependabot.yml", ".github/dependabot.yaml")), None)
    dep = strip_comments(show(dep_path)) if dep_path else ""
    renovate = any(f in ("renovate.json", ".github/renovate.json", "renovate.json5") for f in files)
    covered = sorted(set(re.findall(r"package-ecosystem:\s*[\"']?([\w-]+)", dep)))
    covered = sorted({"docker" if c == "docker-compose" else c for c in covered})
    present = sorted(e for e, rx in MANIFESTS.items() if any(rx.search(f) and "node_modules" not in f for f in files))
    ignore_ids = {}
    for f in files:
        if re.search(r"(^|/)\.trivyignore(\.yaml|\.yml)?$", f) or re.search(r"(^|/)\.grype\.ya?ml$", f):
            t = strip_comments(show(f))
            if f.endswith(("yaml", "yml")):
                for block in re.split(r"\n\s*-\s+id:\s*", "\n" + t)[1:]:
                    vid = re.match(r"[\"']?([\w-]+)", block)
                    exp = re.search(r"expired_at:\s*[\"']?([\d-]{10})", block)
                    if vid:
                        ignore_ids[vid.group(1)] = exp.group(1) if exp else ""
            else:
                for line in t.splitlines():
                    m = re.match(r"\s*(CVE-\d{4}-\d+|GHSA-[\w-]+)(?:.*exp:([\d-]{10}))?", line)
                    if m:
                        ignore_ids[m.group(1)] = m.group(2) or ""
    ig, ig_exp = len(ignore_ids), sum(1 for v in ignore_ids.values() if v)
    docs = "\n".join(show(f) for f in files if f in DOC_FILES)
    doc_claims = sorted(k for k, rx in DOC_CLAIMS.items() if rx.search(docs))
    return dict(secret_local=secret_local, secret_ci=secret_ci, dep_update=bool(dep_path) or renovate,
                dep_scan_ci=dep_scan_ci, dep_scan_local=dep_scan_local, image_ci=image_ci,
                has_docker=bool(dockerfiles), uses_total=len(uses), uses_pinned=len(pinned), from_total=len(froms),
                from_digest=len(digest), ecos_present=json.dumps(present), ecos_covered=json.dumps(covered),
                ignores=ig, ignores_expiring=ig_exp, cooldown="cooldown:" in dep,
                groups="groups:" in dep, ci_precommit=ci_runs_precommit, ignore_ids=json.dumps(ignore_ids),
                doc_claims=json.dumps(doc_claims))


def repos():
    return sorted(d[:-4] for d in os.listdir(MIRRORS) if d.endswith(".git"))


def run_snap(con):
    con.execute("DROP TABLE IF EXISTS snap")
    cols = ("secret_local secret_ci dep_update dep_scan_ci dep_scan_local image_ci has_docker uses_total uses_pinned "
            "from_total from_digest ecos_present ecos_covered ignores ignores_expiring cooldown groups ci_precommit ignore_ids "
            "doc_claims").split()
    con.execute(f"CREATE TABLE snap (repo TEXT, week TEXT, sha TEXT, ts TEXT, {', '.join(cols)}, PRIMARY KEY (repo, week))")
    for repo in repos():
        cache = {}
        for w in WEEKS:
            sha = git(repo, "rev-list", "-1", "--first-parent", f"--before={week_end(w)}", "HEAD").strip()
            if not sha:
                continue
            if sha not in cache:
                cache[sha] = snapshot(repo, sha)
            ts = git(repo, "log", "-1", "--format=%cI", sha).strip()
            s = cache[sha]
            con.execute(f"INSERT INTO snap VALUES (?,?,?,?,{','.join('?' * len(cols))})",
                        (repo, w, sha, ts, *[s[c] for c in cols]))
        con.commit()
        print(f"snap {repo}: {len(cache)} distinct heads", file=sys.stderr)


# High-confidence rules (the same families trivy's and gitleaks' default rule sets carry).
RULES = [
    ("aws-access-key-id", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{60,}")),
    ("private-key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY( BLOCK)?-----")),
    ("slack-token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}")),
    ("stripe-live-key", re.compile(r"\b[sr]k_live_[0-9A-Za-z]{20,}")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai-key", re.compile(r"\bsk-(proj-)?[A-Za-z0-9]{32,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("digitalocean-token", re.compile(r"\bdo[po]_v1_[a-f0-9]{64}\b")),
    ("cloudflare-tunnel-token", re.compile(r"\beyJhIjoi[A-Za-z0-9+/=_-]{40,}")),
    ("docker-hub-pat", re.compile(r"\bdckr_pat_[A-Za-z0-9_-]{20,}")),
    ("sendgrid-key", re.compile(r"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("url-with-password", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@'\"]+:([^\s@/'\"$<{]{6,})@[^\s/'\"]+")),
]
PLACEHOLDER = re.compile(r"(example|placeholder|changeme|dummy|fake|xxxx|your[_-]|<|\$\{|test|localhost|password@|"
                         r"user:pass|postgres:postgres|redis:|secret@|EXAMPLE)", re.I)
FIXTURE_PATH = re.compile(r"(test|spec|fixture|mock|example|\.md$|\.secrets\.baseline|testdata|__snapshots__|"
                          r"package-lock\.json|pnpm-lock|yarn\.lock|go\.sum)", re.I)


def run_secrets(con):
    con.execute("DROP TABLE IF EXISTS secret_hits")
    con.execute("CREATE TABLE secret_hits (repo TEXT, sha TEXT, ts TEXT, path TEXT, rule TEXT, fixture INTEGER, "
                "finding_id INTEGER, on_main INTEGER)")
    ids = {}
    for repo in repos():
        main = set(git(repo, "rev-list", "--first-parent", "HEAD").split())
        p = subprocess.Popen(["git", "-C", os.path.join(MIRRORS, repo + ".git"), "log", "--all", "-p", "--no-color",
                              "--no-merges", "--format=@@COMMIT %H %cI", "--unified=0", "--no-ext-diff"],
                             stdout=subprocess.PIPE, text=True, errors="replace")
        sha = ts = path = None
        n = 0
        for line in p.stdout:
            if line.startswith("@@COMMIT "):
                _, sha, ts = line.split()
            elif line.startswith("+++ "):
                path = line[6:].strip() if line.startswith("+++ b/") else None
            elif line.startswith("+") and path and len(line) < 4000:
                for rule, rx in RULES:
                    m = rx.search(line)
                    if not m:
                        continue
                    val = m.group(0)
                    if rule == "url-with-password":
                        if PLACEHOLDER.search(val):
                            continue
                    elif PLACEHOLDER.search(line) and rule in ("jwt", "openai-key"):
                        continue
                    fid = ids.setdefault((rule, val), len(ids) + 1)
                    del val
                    con.execute("INSERT INTO secret_hits VALUES (?,?,?,?,?,?,?,?)",
                                (repo, sha[:10], ts, path, rule, int(bool(FIXTURE_PATH.search(path))), fid,
                                 int(sha in main)))
                    n += 1
        p.wait()
        con.commit()
        print(f"secrets {repo}: {n} hits", file=sys.stderr)


LOCKFILES = re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lock|go\.mod|go\.sum|uv\.lock|"
                       r"poetry\.lock|requirements[^/]*\.txt|Cargo\.lock)$")
SCRATCH = os.environ.get("CH11_SCRATCH", os.path.join(ROOT, ".analysis", "scratch", "security"))


def trivy_head(repo, sha):
    """Known-vulnerable dependencies in one commit's lockfiles, judged by today's trivy DB (offline)."""
    import shutil
    import tempfile
    files = [f for f in git(repo, "ls-tree", "-r", "--name-only", sha).splitlines()
             if LOCKFILES.search(f) and "node_modules" not in f and "testdata" not in f]
    if not files:
        return []
    os.makedirs(SCRATCH, exist_ok=True)
    d = tempfile.mkdtemp(dir=SCRATCH)
    try:
        for f in files:
            os.makedirs(os.path.join(d, os.path.dirname(f)), exist_ok=True)
            with open(os.path.join(d, f), "w") as fh:
                fh.write(git(repo, "show", f"{sha}:{f}"))
        out = os.path.join(d, "_out.json")
        subprocess.run(["trivy", "fs", "--quiet", "--scanners", "vuln", "--skip-db-update", "--offline-scan",
                        "--format", "json", "--output", out, d], capture_output=True, timeout=600)
        if not os.path.exists(out):
            return []
        res = json.load(open(out))
        rows = []
        for r in res.get("Results") or []:
            for v in r.get("Vulnerabilities") or []:
                rows.append((r.get("Target", "").replace(d + "/", ""), v.get("VulnerabilityID"), v.get("PkgName"),
                             v.get("InstalledVersion"), v.get("FixedVersion") or "", v.get("Severity"),
                             (v.get("PublishedDate") or "")[:10]))
        return rows
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run_vulns(con):
    from concurrent.futures import ThreadPoolExecutor
    con.execute("CREATE TABLE IF NOT EXISTS vulns (repo TEXT, sha TEXT, target TEXT, vuln_id TEXT, pkg TEXT, "
                "installed TEXT, fixed TEXT, severity TEXT, published TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS vulns_done (repo TEXT, sha TEXT, PRIMARY KEY (repo, sha))")
    done = {(r, s) for r, s in con.execute("SELECT repo, sha FROM vulns_done")}
    todo = sorted({(r, s) for r, s in con.execute("SELECT DISTINCT repo, sha FROM snap")} - done)
    print(f"vulns: {len(todo)} heads to scan", file=sys.stderr)
    with ThreadPoolExecutor(4) as ex:
        for (repo, sha), rows in zip(todo, ex.map(lambda t: trivy_head(*t), todo)):
            con.executemany("INSERT INTO vulns VALUES (?,?,?,?,?,?,?,?,?)", [(repo, sha, *r) for r in rows])
            con.execute("INSERT INTO vulns_done VALUES (?,?)", (repo, sha))
            con.commit()
            print(f"  {repo} {sha[:8]}: {len(rows)}", file=sys.stderr)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    con = sqlite3.connect(DB)
    if what in ("snap", "all"):
        run_snap(con)
    if what in ("secrets", "all"):
        run_secrets(con)
    if what in ("vulns", "all"):
        run_vulns(con)
