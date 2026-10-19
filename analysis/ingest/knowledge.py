"""Knowledge sources: design docs, agent instructions, the compliance register,
and the wayfare-skills plugin's own history. One read of git history per
source repo, into data/knowledge.sqlite.

Standard library only. Read-only on the repos: every "current" fact and every
history walk reads a git ref (origin/main, or HEAD for the local-only .fleet
folder), never the working tree, so a repo checked out on a feature branch
still reports the same thing everyone else's fan-out sees.
"""
import os, sys, re, sqlite3, subprocess, hashlib, time, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest.fleet import ALL_REPOS, ROOT, FLEET_REGISTER, PLUGIN_REPO_NAME, path_of, dims

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".analysis", "data", "knowledge.sqlite")
MAX_VERSIONS = 200

DOCS = ["DESIGN.md", "AGENTS.md", "CLAUDE.md", "HERO.md", "README.md", "CONSISTENCY.md"]
RULE_GLOB = ".claude/rules/"


def ref_for(repo_path):
    """origin/main everywhere a remote exists; HEAD for a local-only folder repo (.fleet)."""
    r = run(repo_path, "rev-parse", "--verify", "origin/main")
    return "origin/main" if r is not None else "HEAD"


def run(cwd, *args, check=False):
    try:
        p = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=60)
    except Exception:
        return None
    if p.returncode != 0:
        if check:
            raise RuntimeError(p.stderr)
        return None
    return p.stdout


def show(repo_path, ref, path):
    """Content of path at ref, or None if it doesn't exist there."""
    p = subprocess.run(["git", "-C", repo_path, "show", f"{ref}:{path}"], capture_output=True, timeout=30)
    if p.returncode != 0:
        return None
    try:
        return p.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def ls_tree(repo_path, ref, prefix=""):
    out = run(repo_path, "ls-tree", "-r", "--name-only", ref) or ""
    files = out.splitlines()
    return [f for f in files if f.startswith(prefix)] if prefix else files


def log_follow(repo_path, path, ref="HEAD"):
    """[(sha, iso_ts), ...] newest-first, capped at MAX_VERSIONS."""
    out = run(repo_path, "log", ref, "--follow", f"-n{MAX_VERSIONS}", "--format=%H\x09%aI", "--", path)
    if not out:
        return []
    rows = []
    for line in out.splitlines():
        sha, ts = line.split("\x09")
        rows.append((sha, ts))
    return rows


def count_sections(text):
    return len(re.findall(r"(?m)^## ", text))


def count_decisions(text):
    m = re.search(r"(?mi)^##\s+Decisions\s*$", text)
    if not m:
        return 0
    rest = text[m.end():]
    nxt = re.search(r"(?m)^## ", rest)
    body = rest[:nxt.start()] if nxt else rest
    return len(re.findall(r"(?m)^### ", body))


def parse_decisions(text):
    """[(date_in_text, heading, body_text), ...] from the current Decisions section."""
    m = re.search(r"(?mi)^##\s+Decisions\s*$", text)
    if not m:
        return []
    rest = text[m.end():]
    nxt = re.search(r"(?m)^## ", rest)
    body = rest[:nxt.start()] if nxt else rest
    entries = []
    for hm in re.finditer(r"(?m)^### (.+)$", body):
        heading = hm.group(1).strip()
        start = hm.end()
        following = re.search(r"(?m)^### ", body[start:])
        entry_body = body[start: start + following.start()] if following else body[start:]
        dm = re.match(r"([\d]{4}-[\d]{2}-[\d]{2})\s*—?\s*(.*)", heading)
        date_in_text = dm.group(1) if dm else ""
        entries.append((date_in_text, heading, entry_body.strip()))
    return entries


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def create_schema(con):
    con.executescript("""
    CREATE TABLE doc_versions(
        repo TEXT, doc TEXT, sha TEXT, ts TEXT, day TEXT, week TEXT, month TEXT,
        bytes INTEGER, lines INTEGER, sections INTEGER, decisions INTEGER
    );
    CREATE TABLE design_decisions(
        repo TEXT, heading TEXT, date_in_text TEXT,
        first_seen_sha TEXT, first_seen_ts TEXT, text_redacted TEXT
    );
    CREATE TABLE instruction_files(
        repo TEXT, path TEXT, bytes INTEGER, lines INTEGER, updated_ts TEXT, vendored_hash TEXT
    );
    CREATE TABLE controls(
        control_id TEXT, title TEXT, severity TEXT, category TEXT, created_ts TEXT, raw_json TEXT, repo TEXT
    );
    CREATE TABLE checks(
        check_id TEXT, control_id TEXT, title TEXT, kind TEXT, raw_json TEXT, repo TEXT
    );
    CREATE TABLE check_results(
        repo TEXT, check_id TEXT, result TEXT, as_of TEXT
    );
    CREATE TABLE register_history(
        file TEXT, sha TEXT, ts TEXT, controls INTEGER, checks INTEGER
    );
    CREATE TABLE skills(
        skill TEXT, path TEXT, bytes INTEGER, lines INTEGER, description TEXT
    );
    CREATE TABLE skill_versions(
        skill TEXT, sha TEXT, ts TEXT, day TEXT, week TEXT, month TEXT,
        bytes INTEGER, lines INTEGER, change_type TEXT, subject TEXT, old_path TEXT
    );
    CREATE TABLE plugin_versions(
        sha TEXT, ts TEXT, version TEXT
    );
    CREATE TABLE meta(source TEXT, path TEXT, rows INTEGER, extracted_at TEXT);
    """)


# ---------------------------------------------------------------- doc_versions

def ingest_docs(con):
    dv_rows = 0
    dd_rows = 0
    unparsed = []
    for repo in ALL_REPOS:
        rp = path_of(repo)
        if not os.path.isdir(rp):
            continue
        ref = ref_for(rp)
        current_rules = [f for f in ls_tree(rp, ref) if f.startswith(RULE_GLOB) and f.endswith(".md")]
        ever_rules_out = run(rp, "log", ref, "--format=", "--name-only", "--diff-filter=ACMR",
                              "--", f"{RULE_GLOB}*.md") or ""
        ever_rules = set(l for l in ever_rules_out.splitlines() if l.strip())
        doc_paths = list(DOCS) + sorted(set(current_rules) | ever_rules)

        for doc in doc_paths:
            versions = log_follow(rp, doc, ref)
            for sha, ts in versions:
                content = show(rp, sha, doc)
                if content is None:
                    continue
                d = dims(ts)
                b = len(content.encode("utf-8"))
                lines = content.count("\n") + (0 if content.endswith("\n") or content == "" else 1)
                dv_rows += 1
                con.execute(
                    "INSERT INTO doc_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (repo, doc, sha, d["ts"], d["day"], d["week"], d["month"],
                     b, lines, count_sections(content), count_decisions(content)),
                )

        # design_decisions: from the current DESIGN.md only
        head_design = show(rp, ref, "DESIGN.md")
        if head_design:
            versions = log_follow(rp, "DESIGN.md", ref)  # newest-first
            oldest_first = list(reversed(versions))
            for date_in_text, heading, body in parse_decisions(head_design):
                first_sha, first_ts = versions[0] if versions else (None, None)
                for sha, ts in oldest_first:
                    c = show(rp, sha, "DESIGN.md")
                    if c and heading in c:
                        first_sha, first_ts = sha, ts
                        break
                from ingest.redact import redact
                dd_rows += 1
                con.execute(
                    "INSERT INTO design_decisions VALUES (?,?,?,?,?,?)",
                    (repo, heading, date_in_text, first_sha, first_ts, redact(body)[:1500]),
                )
    return dv_rows, dd_rows, unparsed


# ------------------------------------------------------------ instruction_files

def ingest_instruction_files(con):
    rows = 0
    for repo in ALL_REPOS:
        rp = path_of(repo)
        if not os.path.isdir(rp):
            continue
        ref = ref_for(rp)
        all_files = ls_tree(rp, ref)
        wanted = [f for f in all_files if (
            f.startswith(".claude/rules/") or
            f == ".claude/settings.json" or f == ".claude/settings.local.json" or
            (f.startswith(".claude/skills/") and f.endswith("/SKILL.md")) or
            f.startswith(".claude/hooks/")
        )]
        for f in wanted:
            content = show(rp, ref, f)
            if content is None:
                continue
            updated = run(rp, "log", ref, "-1", "--format=%aI", "--", f)
            updated_ts = updated.strip() if updated else None
            b = len(content.encode("utf-8"))
            lines = content.count("\n") + (0 if content.endswith("\n") or content == "" else 1)
            rows += 1
            con.execute(
                "INSERT INTO instruction_files VALUES (?,?,?,?,?,?)",
                (repo, f, b, lines, updated_ts, sha256_text(content)),
            )
    return rows


# --------------------------------------------------------- controls / checks

def _blocks(text):
    """Split a YAML list of '- id: ...' mapping entries at the top-level
    'controls:'/'checks:' key into raw blocks, hand-rolled because the file
    mixes prose (>) blocks and nested maps that a strict YAML parser chokes
    less on than a naive line splitter, but we only need a handful of scalar
    fields."""
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if re.match(r"^- id:\s*\S+", l)]
    blocks = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(lines)
        blocks.append("\n".join(lines[s:e]))
    return blocks


def _field(block, name):
    # Every field but `id` is indented under its "- id: ..." line; anchoring at
    # column 0 silently returns None for all of them.
    m = re.search(rf"(?m)^\s*-?\s*{name}:\s*(.+)$", block)
    return m.group(1).strip() if m else None


def parse_controls(text):
    out = []
    for b in _blocks(text):
        cid = _field(b, "id")
        if not cid:
            continue
        out.append({
            "id": cid, "title": _field(b, "title") or "",
            "severity": _field(b, "severity") or "", "raw": b,
        })
    return out


def parse_checks(text):
    out = []
    for b in _blocks(text):
        cid = _field(b, "id")
        if not cid:
            continue
        out.append({
            "id": cid, "control": _field(b, "control") or "",
            "title": _field(b, "title") or "", "kind": _field(b, "layer") or _field(b, "scope") or "",
            "raw": b,
        })
    return out


def _register_sources():
    """(label, path, ref) for the fleet-level register (if FLEET.md declares
    one) plus any repo that ALSO carries its own CONTROLS.yaml/CHECKS.yaml --
    probed dynamically across every fleet repo, not a fixed allowlist, since
    which repos (if any) carry a local overlay is fleet-specific and changes
    over time (this fleet's own overlay moved out of hero-template on
    2026-09-13, per .fleet/README.md)."""
    sources = [("fleet", FLEET_REGISTER, "HEAD")] if FLEET_REGISTER else []
    for repo in ALL_REPOS:
        rp = path_of(repo)
        if not os.path.isdir(rp):
            continue
        ref = ref_for(rp)
        if show(rp, ref, "CONTROLS.yaml") or show(rp, ref, "CHECKS.yaml"):
            sources.append((repo, rp, ref))
    return sources


def ingest_controls_checks(con):
    sources = _register_sources()

    n_controls = n_checks = 0
    for repo, rp, ref in sources:
        ctext = show(rp, ref, "CONTROLS.yaml")
        ktext = show(rp, ref, "CHECKS.yaml")
        if ctext:
            for c in parse_controls(ctext):
                created = None
                out = run(rp, "log", ref, f"-S id: {c['id']}", "--format=%aI", "--", "CONTROLS.yaml")
                if out and out.strip():
                    created = out.strip().splitlines()[-1]
                n_controls += 1
                con.execute(
                    "INSERT INTO controls VALUES (?,?,?,?,?,?,?)",
                    (c["id"], c["title"], c["severity"], None, created, c["raw"], repo),
                )
        if ktext:
            for c in parse_checks(ktext):
                n_checks += 1
                con.execute(
                    "INSERT INTO checks VALUES (?,?,?,?,?,?)",
                    (c["id"], c["control"], c["title"], c["kind"], c["raw"], repo),
                )
    return n_controls, n_checks


# --------------------------------------------------------------- check_results

def parse_consistency_md(text):
    """[(check_id, repo, result), ...] from the current generated table."""
    lines = text.splitlines()
    results = []
    header = None
    for i, line in enumerate(lines):
        if line.startswith("| Check |"):
            header = [c.strip() for c in line.strip("|").split("|")]
            continue
        if header and re.match(r"^\|\s*-", line):
            continue
        if header and line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) != len(header):
                continue
            m = re.match(r"\*\*([A-Z0-9-]+)\*\*", cells[0])
            if not m:
                header = None
                continue
            check_id = m.group(1)
            for repo_col, val in zip(header[1:-1], cells[1:-1]):
                results.append((check_id, repo_col, val))
        elif header and not line.startswith("|"):
            header = None
    return results


def ingest_check_results(con):
    rows = 0
    text = show(FLEET_REGISTER, "HEAD", "CONSISTENCY.md") if FLEET_REGISTER else None
    if text:
        as_of = run(FLEET_REGISTER, "log", "-1", "--format=%aI", "--", "CONSISTENCY.md")
        as_of = as_of.strip() if as_of else dt.datetime.now(dt.timezone.utc).isoformat()
        for check_id, repo, result in parse_consistency_md(text):
            rows += 1
            con.execute("INSERT INTO check_results VALUES (?,?,?,?)", (repo, check_id, result, as_of))
    return rows


# ------------------------------------------------------------- register_history

def ingest_register_history(con):
    rows = 0
    for label, rp, ref in _register_sources():
        for fname in ("CONTROLS.yaml", "CHECKS.yaml", "CONSISTENCY.md"):
            for sha, ts in log_follow(rp, fname, ref):
                content = show(rp, sha, fname)
                if content is None:
                    continue
                if fname == "CONTROLS.yaml":
                    n_ctrl, n_chk = len(parse_controls(content)), None
                elif fname == "CHECKS.yaml":
                    n_ctrl, n_chk = None, len(parse_checks(content))
                else:
                    res = parse_consistency_md(content)
                    n_ctrl, n_chk = None, len(set(r[0] for r in res))
                rows += 1
                con.execute(
                    "INSERT INTO register_history VALUES (?,?,?,?,?)",
                    (f"{label}:{fname}", sha, ts, n_ctrl, n_chk),
                )
    return rows


# --------------------------------------------------------------------- skills

def parse_name_status_log(out):
    """Yields (sha, ts, subject, change_type, commit_path, old_path) from
    `git log --name-status --format=%x01%H\\x09%aI\\x09%s` output for a single
    pathspec. Reads the FULL name-status block per commit (not just its first
    line): a commit's record is [commit header][blank line][status line(s)],
    and taking only the first line after the header used to grab the blank
    separator instead of the status, so every row came out "modify"."""
    for chunk in out.split("\x01"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        lines = chunk.splitlines()
        sha, ts, subject = lines[0].split("\x09", 2)
        change_type, commit_path, old_path = "modify", None, None
        for l in lines[1:]:
            if not l.strip():
                continue
            parts = l.split("\t")
            code = parts[0]
            if code[:1] in ("R", "C"):
                old_path, commit_path = parts[1], parts[2]
                change_type = "rename"
            else:
                commit_path = parts[1] if len(parts) > 1 else None
                change_type = {"A": "add", "D": "delete", "M": "modify"}.get(code[:1], "modify")
            break  # one pathspec -> at most one status line per commit
        yield sha, ts, subject, change_type, commit_path, old_path


def skill_size(rp, rev, skill_md, content):
    """Bytes and lines of a skill: SKILL.md plus the WORKFLOW.md beside it.

    #142 moved the five pipeline skills' bodies into WORKFLOW.md; counting SKILL.md alone reads that as the
    skills losing most of their length overnight.
    """
    parts = [content, show(rp, rev, skill_md[:-len("SKILL.md")] + "WORKFLOW.md") or ""]
    b = sum(len(p.encode("utf-8")) for p in parts)
    lines = sum(p.count("\n") + (0 if p.endswith("\n") or p == "" else 1) for p in parts)
    return b, lines


def ingest_skills(con):
    rp = path_of(PLUGIN_REPO_NAME)
    ref = ref_for(rp)
    current = [f for f in ls_tree(rp, ref) if re.match(r"^skills/[^/]+/SKILL\.md$", f)]

    n_skills = 0
    for f in current:
        content = show(rp, ref, f)
        if content is None:
            continue
        skill = f.split("/")[1]
        b, lines = skill_size(rp, ref, f, content)
        m = re.search(r"(?m)^description:\s*(.+)$", content)
        desc = m.group(1).strip() if m else ""
        n_skills += 1
        con.execute("INSERT INTO skills VALUES (?,?,?,?,?)", (skill, f, b, lines, desc))

    # Every path a SKILL.md ever lived at, add through delete, so a skill
    # renamed or removed before HEAD (and not reachable by --follow from any
    # currently-existing path) still gets its own walk below.
    ever_out = run(rp, "log", ref, "--format=", "--name-only", "--diff-filter=ACMRD",
                   "--", "skills/*/SKILL.md") or ""
    ever = set(l for l in ever_out.splitlines() if re.match(r"^skills/[^/]+/SKILL\.md$", l))
    walk_order = current + [p for p in sorted(ever) if p not in current]

    n_versions = 0
    seen = set()  # (sha, commit_path) — a dead lineage's own walk overlaps a live one's tail
    for start_path in walk_order:
        skill = start_path.split("/")[1]
        out = run(rp, "log", ref, "--follow", f"-n{MAX_VERSIONS}",
                  "--name-status", "--format=%x01%H\x09%aI\x09%s", "--", start_path)
        if not out:
            continue
        for sha, ts, subject, change_type, commit_path, old_path in parse_name_status_log(out):
            path_at_commit = commit_path or start_path
            key = (sha, path_at_commit)
            if key in seen:
                continue
            seen.add(key)
            content = None if change_type == "delete" else show(rp, sha, path_at_commit)
            b, lines = skill_size(rp, sha, path_at_commit, content) if content else (0, 0)
            d = dims(ts)
            n_versions += 1
            con.execute(
                "INSERT INTO skill_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (skill, sha, d["ts"], d["day"], d["week"], d["month"], b, lines, change_type, subject, old_path),
            )

    # A commit that edits only WORKFLOW.md changes the skill's size but not its SKILL.md, so the walk above
    # never sees it.
    wf_out = run(rp, "log", ref, "--format=%x01%H\x09%aI\x09%s", "--name-status", "--diff-filter=ACMR",
                 "--", "skills/*/WORKFLOW.md") or ""
    for chunk in wf_out.split("\x01"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        head, *changes = chunk.splitlines()
        sha, ts, subject = head.split("\x09", 2)
        for l in changes:
            parts = l.split("\t")
            if len(parts) < 2:
                continue
            skill_md = parts[-1].rsplit("/", 1)[0] + "/SKILL.md"
            if (sha, skill_md) in seen:
                continue
            seen.add((sha, skill_md))
            content = show(rp, sha, skill_md)
            if content is None:
                continue
            b, lines = skill_size(rp, sha, skill_md, content)
            d = dims(ts)
            n_versions += 1
            con.execute(
                "INSERT INTO skill_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (skill_md.split("/")[1], sha, d["ts"], d["day"], d["week"], d["month"], b, lines, "modify", subject, None),
            )
    return n_skills, n_versions


def ingest_plugin_versions(con):
    rp = path_of(PLUGIN_REPO_NAME)
    ref = ref_for(rp)
    rows = 0
    for sha, ts in log_follow(rp, ".claude-plugin/plugin.json", ref):
        content = show(rp, sha, ".claude-plugin/plugin.json")
        if not content:
            continue
        m = re.search(r'"version"\s*:\s*"([^"]+)"', content)
        rows += 1
        con.execute("INSERT INTO plugin_versions VALUES (?,?,?)", (sha, ts, m.group(1) if m else None))
    return rows


# ------------------------------------------------------------------------- main

def main():
    t0 = time.time()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    con = sqlite3.connect(OUT)
    create_schema(con)

    dv, dd, _ = ingest_docs(con)
    inst = ingest_instruction_files(con)
    n_ctrl, n_chk = ingest_controls_checks(con)
    n_res = ingest_check_results(con)
    n_reg = ingest_register_history(con)
    n_skills, n_skillver = ingest_skills(con)
    n_plugver = ingest_plugin_versions(con)

    extracted_at = dt.datetime.now(dt.timezone.utc).isoformat()
    counts = {
        "doc_versions": dv, "design_decisions": dd, "instruction_files": inst,
        "controls": n_ctrl, "checks": n_chk, "check_results": n_res,
        "register_history": n_reg, "skills": n_skills, "skill_versions": n_skillver,
        "plugin_versions": n_plugver,
    }
    for table, n in counts.items():
        con.execute("INSERT INTO meta VALUES (?,?,?,?)", ("knowledge", table, n, extracted_at))
    con.commit()
    con.close()

    elapsed = time.time() - t0
    print(f"knowledge.sqlite: {sum(counts.values())} rows across {len(counts)} tables in {elapsed:.1f}s")
    for table, n in counts.items():
        print(f"  {table:20} {n}")


if __name__ == "__main__":
    main()
