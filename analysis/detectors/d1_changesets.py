"""D1 change sets -> .analysis/data/detectors.sqlite.

A change set is the smallest coherent unit of work: one thing a reviewer
would accept or revert on its own, together with its tests and the fixes
review asked for. It is read from the commits the work was made in, not
from main: squash merges collapse a PR to one commit whose message cannot
say how the work divided. So the unit Haiku sees is a merged PR's original
commits (ingest/pr_commits.py), each with its message and the files it
touched, and it groups them:
  - several commits can be one change set (a feature, its test, a review fix);
  - one commit can hold several change sets (unrelated changes bundled) --
    that commit is listed under each.
Main commits with no PR (direct pushes), and PRs whose head ref is gone,
are units of their own one commit. Dependabot PRs and single commits with
no body are one change set without a model call.

Tables:
  cs_units   one row per unit (PR or pushed commit): n_commits, n_sets, method
  cs_sets    one row per change set: its label and the commit shas in it
  changesets / changesets_by_commit   the older per-main-commit shape the
             question modules read; n_sets there is now the unit's count.
             changesets.content_hash is the packed unit key ("repo#pr12"), not a
             hash: join changesets_by_commit to cs_units, cs_sets and cs_worktype
             on (repo, unit_kind, unit_id), never by parsing it.
The earlier message-only labels are kept as changesets_msg_v1 for comparison.

Cached by sha256(PROMPT_VERSION + unit text) in cs_cache: a re-run labels only
units it hasn't seen, and bumping PROMPT_VERSION relabels everything.
"""
import hashlib, json, os, re, sqlite3, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest.fleet import OUT

DB_PATH = os.path.join(OUT, "detectors.sqlite")
MODEL = "haiku"
NEUTRAL_CWD = "/tmp"  # outside any repo, so no CLAUDE.md/AGENTS.md is billed as context
PROMPT_VERSION = "v4-pr-commits"
BATCH_CHARS = 24000
BATCH_UNITS = 12
MAX_FILES = 8
WORKERS = 6

PROMPT_HEADER = """You group a pull request's commits into change sets.

A change set is the smallest coherent unit of work: one thing a reviewer would accept or
revert on its own, together with the commits that only exist to finish that thing.

Same change set:
- an implementation, its tests, its docs, and wiring it into config (feat + test + docs);
- review, self-review, lint or format fixes to something earlier in the PR.
Separate change sets:
- a problem found while building that has its own reason to exist, even if small (a
  secret leaking into logs, a different bug, an unrelated doc correction) -- with its test;
- unrelated changes bundled into one commit: list that commit under each change set.
Don't split one change by layer: UI + API + schema for one feature is one change set.
Every commit belongs to at least one change set.

Example. Commits: c1 feat(cache): read Mongo through Redis; c2 feat(cache): forward CACHE_TTL
into the stacks; c3 fix(cache): address self-review findings; c4 fix(cache): a malformed
REDIS_URL logged the Redis password; c5 test(cache): pin that scrubbing the URL keeps the reason.
Answer: [{"label": "read-through Redis cache", "commits": [1,2,3]},
         {"label": "stop logging the Redis password", "commits": [4,5]}]

Example of one commit holding several change sets. Commit: c1 feat(auth): OTP cooldown,
dev password login, and phone verification -- body: 1. 30s per-email OTP cooldown ... /
2. dev-mode password login ... / 3. phone verification ...
Answer: [{"label": "OTP cooldown", "commits": [1]}, {"label": "dev password login", "commits": [1]},
         {"label": "phone verification", "commits": [1]}]
Read each commit's body before grouping: a numbered or bulleted list of unrelated changes, or
a subject joining unrelated things with "and", is several change sets.

For each unit below reply with ONLY a JSON object, no prose, no markdown fence:
{"<unit id>": [{"label": "<short phrase>", "commits": [<commit numbers>]}, ...], ...}

Units:
"""


def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()


def files_line(files_json):
    files = sorted(json.loads(files_json or "[]"), key=lambda f: -(f["ins"] + f["del"]))
    shown = ", ".join(f"{f['path']} +{f['ins']}-{f['del']}" for f in files[:MAX_FILES])
    more = f", +{len(files) - MAX_FILES} more" if len(files) > MAX_FILES else ""
    return shown + more


def body_budget(n_commits):
    """How much of each message Haiku sees: whole bodies on small PRs, subjects only on huge ones."""
    return 1200 if n_commits <= 5 else 500 if n_commits <= 15 else 200 if n_commits <= 40 else 0


def unit_text(uid, header, commits):
    lines = [f"=== {uid}: {header} ({len(commits)} commits) ==="]
    budget = body_budget(len(commits))
    for i, c in enumerate(commits, 1):
        files = files_line(c["files_json"])
        lines.append(f"c{i} {c['subject']}  [files: {files if budget else files[:160]}]")
        body = " / ".join(l.strip() for l in (c["body"] or "").splitlines() if l.strip()
                          and not l.lower().startswith(("co-authored-by", "signed-off-by")))
        if body and budget:
            lines.append(f"   {body[:budget]}")
    return "\n".join(lines)


def call_haiku(texts, tries=3, model=MODEL, header=None):
    prompt = (header or PROMPT_HEADER) + "\n\n".join(texts)
    billed = 0.0  # every completed call is billed, including one whose reply won't parse
    for attempt in range(tries):
        try:
            # The labelled text is untrusted (anyone's PR or review), so the model gets no tools and no MCP.
            p = subprocess.run(["claude", "-p", "--model", model, "--effort", "low", "--output-format", "json",
                                "--tools", "", "--strict-mcp-config", "--permission-mode", "dontAsk"],
                               input=prompt, capture_output=True, text=True, cwd=NEUTRAL_CWD,
                               env={**os.environ, "MAX_THINKING_TOKENS": "0"},
                               timeout=240 + attempt * 120)
        except subprocess.TimeoutExpired:
            print(f"  ! claude -p timed out (try {attempt + 1}/{tries})", file=sys.stderr)
            continue
        if p.returncode != 0:
            print(f"  ! claude -p failed: {p.stderr[:300]}", file=sys.stderr)
            continue
        try:
            outer = json.loads(p.stdout)
        except json.JSONDecodeError:
            print(f"  ! unparsable reply: {p.stdout[:300]}", file=sys.stderr)
            continue
        billed += outer.get("total_cost_usd", 0.0) or 0.0
        text = outer.get("result", "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(text), billed
        except json.JSONDecodeError:
            print(f"  ! model didn't return clean JSON: {text[:300]}", file=sys.stderr)
    return {}, billed


def clean_sets(raw, n):
    """Model groups -> list of (label, [commit idx 0-based]); every commit covered once at least."""
    sets = []
    for s in raw if isinstance(raw, list) else []:
        # Model output: a group that is not a dict, or whose commits is not a list, is dropped. Iterating
        # a string "12" would read it as commits 1 and 2.
        commits = s.get("commits") if isinstance(s, dict) else None
        if not isinstance(commits, list):
            continue
        idx = sorted({int(x) - 1 for x in commits if str(x).isdigit() and 1 <= int(x) <= n})
        if idx:
            sets.append((str(s.get("label", ""))[:200], idx))
    covered = {i for _, idx in sets for i in idx}
    missing = [i for i in range(n) if i not in covered]
    if not sets:
        return None
    if missing:
        # An uncovered commit is almost always a small follow-up (review or lint fix):
        # fold it into the change set whose commits precede it most closely.
        for i in missing:
            best = max(sets, key=lambda s: max((j for j in s[1] if j < i), default=-1))
            best[1].append(i)
    return sets


BUMP_RES = [re.compile(r"^Updates `([^`]+)` from (\S+) to (\S+?)\.?$", re.M),
            re.compile(r"^Bumps \[([^\]]+)\]\([^)]*\) from (\S+) to (\S+?)\.?$", re.M),
            re.compile(r"\bbump (\S+) from (\S+) to (\S+?)(?: in |$)", re.I)]


def dependabot_sets(text):
    """All minor and patch bumps are one change set; each major bump is its own."""
    bumps = {}
    for rx in BUMP_RES:
        for pkg, old, new in rx.findall(text or ""):
            bumps.setdefault(pkg, (old, new))
    major = lambda a, b: re.match(r"v?(\d+)", a) and re.match(r"v?(\d+)", b) and \
        re.match(r"v?(\d+)", a).group(1) != re.match(r"v?(\d+)", b).group(1)
    majors = [f"{p} {o} → {n}" for p, (o, n) in bumps.items() if major(o, n)]
    minors = [p for p, (o, n) in bumps.items() if not major(o, n)]
    sets = ([f"minor/patch bumps: {', '.join(minors)}"[:200]] if minors or not majors else []) + \
           [f"major bump: {m}"[:200] for m in majors]
    return sets


def load_units(con):
    """(key, repo, kind, unit_id, main_sha, header, commits, rule) for every unit."""
    units = []
    prs = {(r[0], r[1]): r for r in con.execute(
        "SELECT repo, number, title, head_ref, author_is_bot, body_redacted FROM github.prs")}
    main_by_pr = {(r[0], r[1]): r[2] for r in con.execute(
        "SELECT repo, pr_number, sha FROM git.commits WHERE pr_number IS NOT NULL")}
    pr_commits = {}
    for r in con.execute("SELECT repo, pr_number, sha, subject, body_redacted, files_json, is_merge "
                         "FROM pr_commits.pr_commits ORDER BY repo, pr_number, idx"):
        if not r[6]:
            pr_commits.setdefault((r[0], r[1]), []).append(
                {"sha": r[2], "subject": r[3], "body": r[4], "files_json": r[5]})
    main_files = {}
    for repo, sha, path, ins, dele in con.execute("SELECT repo, sha, path, insertions, deletions FROM git.commit_files"):
        main_files.setdefault((repo, sha), []).append({"path": path, "ins": ins or 0, "del": dele or 0})
    for repo, sha, subject, body, pr_number, is_bot in con.execute(
            "SELECT repo, sha, subject, body_redacted, pr_number, is_bot FROM git.commits WHERE is_merge = 0"):
        pr = prs.get((repo, pr_number))
        dependabot = bool(is_bot) or bool(pr and ((pr[3] or "").startswith("dependabot/") or pr[4]))
        if pr_number and (repo, pr_number) in pr_commits and not dependabot:
            commits = pr_commits[(repo, pr_number)]
            units.append((f"{repo}#pr{pr_number}", repo, "pr", str(pr_number), sha,
                          f'PR #{pr_number} "{pr[2] if pr else subject}"', commits,
                          "single-line" if len(commits) == 1 and not (commits[0]["body"] or "").strip() else None))
        else:
            c = {"sha": sha, "subject": subject, "body": body,
                 "files_json": json.dumps(main_files.get((repo, sha), []))}
            kind = "pr-squash" if pr_number else "push"
            rule = "dependabot" if dependabot else ("single-line" if not (body or "").strip() else None)
            if dependabot:
                c["dependabot_sets"] = dependabot_sets(f"{pr[2]}\n{pr[5]}" if pr else f"{subject}\n{body}")
            units.append((f"{repo}#{kind}{pr_number or sha[:10]}", repo, kind, str(pr_number or sha), sha,
                          f"commit on main{f' for PR #{pr_number}' if pr_number else ''}", [c], rule))
    return units + offmain_units(con, units, pr_commits)


def offmain_units(con, units, pr_commits):
    """Merged PRs whose work never reached main's history: a branch rewritten after the merge
    (infrastructure-environments' main restarts on 17 Jul 2026) leaves GitHub and the PR head refs
    holding work no main commit carries. main_sha is NULL; record.changeset_facts dates them by the
    merge day. A PR is skipped when its squash commit is on main (it is already a push unit) or any
    of its commits is already in a unit, so nothing is counted twice."""
    default = dict(con.execute("SELECT repo, default_branch FROM git.repos").fetchall())
    on_main = {(r[0], r[1]) for r in con.execute("SELECT repo, sha FROM git.commits")}
    squash = {(r[0], r[1]): r[2] for r in con.execute("SELECT repo, pr_number, main_sha FROM pr_commits.pr_coverage")}
    have_pr = {(u[1], u[3]) for u in units if u[2] == "pr"}
    covered = {(u[1], c["sha"]) for u in units for c in u[6]}
    out = []
    for repo, num, title, base, head, bot in con.execute(
            "SELECT repo, number, title, base_ref, head_ref, author_is_bot FROM github.prs WHERE merged_ts IS NOT NULL"):
        commits = pr_commits.get((repo, num))
        if (not commits or bot or (head or "").startswith("dependabot/") or base != default.get(repo)
                or (repo, str(num)) in have_pr or (repo, squash.get((repo, num))) in on_main
                or any((repo, c["sha"]) in covered for c in commits)):
            continue
        out.append((f"{repo}#pr{num}", repo, "pr", str(num), None, f'PR #{num} "{title}"', commits,
                    "single-line" if len(commits) == 1 and not (commits[0]["body"] or "").strip() else None))
    return out


UNIT_KINDS = ("pr", "pr-squash", "push")
METHODS = ("dependabot", "single-line", "haiku", "unlabelled: one per commit")
_in = lambda values: ", ".join(f"'{v}'" for v in values)
UNIT_COLS = f"""repo TEXT NOT NULL CHECK (repo <> ''),
    unit_kind TEXT NOT NULL CHECK (unit_kind IN ({_in(UNIT_KINDS)})),
    unit_id TEXT NOT NULL CHECK (unit_id <> '')"""
# A table constraint, so it goes after the last column. pr and pr-squash ids are PR numbers; consumers key PRs
# by that number across both kinds, so "012" and "12" would be two PRs to SQL and one to them.
UNIT_ID_CHECK = """CHECK (unit_kind = 'push' OR (unit_id GLOB '[1-9]*' AND unit_id NOT GLOB '*[^0-9]*'))"""
# changesets_by_commit.sha stays nullable: an off-main unit (offmain_units) has no main commit, and SQLite lets
# NULLs repeat in a non-INTEGER primary key. NOT NULL or WITHOUT ROWID would reject those rows.
SCHEMA = f"""
    DROP TABLE IF EXISTS cs_units; DROP TABLE IF EXISTS cs_sets;
    DROP TABLE IF EXISTS changesets; DROP TABLE IF EXISTS changesets_by_commit;
    CREATE TABLE cs_units ({UNIT_COLS}, main_sha TEXT,
                           n_commits INTEGER NOT NULL CHECK (n_commits >= 1),
                           n_sets INTEGER NOT NULL CHECK (n_sets >= 1),
                           method TEXT NOT NULL CHECK (method IN ({_in(METHODS)})),
                           PRIMARY KEY (repo, unit_kind, unit_id), {UNIT_ID_CHECK});
    CREATE UNIQUE INDEX cs_units_one_pr ON cs_units (repo, unit_id) WHERE unit_kind IN ('pr', 'pr-squash');
    CREATE TABLE cs_sets ({UNIT_COLS}, set_idx INTEGER NOT NULL CHECK (set_idx >= 0), label TEXT, shas_json TEXT,
                          PRIMARY KEY (repo, unit_kind, unit_id, set_idx), {UNIT_ID_CHECK});
    CREATE TABLE changesets (content_hash TEXT PRIMARY KEY, n_sets INTEGER, labels_json TEXT, method TEXT);
    CREATE TABLE changesets_by_commit (repo TEXT NOT NULL, sha TEXT, content_hash TEXT,
                                       unit_kind TEXT NOT NULL CHECK (unit_kind IN ({_in(UNIT_KINDS)})),
                                       unit_id TEXT NOT NULL CHECK (unit_id <> ''), PRIMARY KEY (repo, sha),
                                       {UNIT_ID_CHECK});
"""


def check_unique(units):
    """Raise ValueError naming every unit load_units produced twice, with the main commits it came from.
    Two main commits naming one PR "(#N)" load as the same PR unit twice."""
    seen, dups = {}, {}
    for key, repo, kind, uid, main_sha, *_ in units:
        if (repo, kind, uid) in seen:
            dups.setdefault((repo, kind, uid), [seen[(repo, kind, uid)]]).append(main_sha)
        seen[(repo, kind, uid)] = main_sha
    if dups:
        raise ValueError("units loaded twice, nothing written: " + "; ".join(
            f"{repo} {kind} {uid} from main commits {', '.join(str(s) for s in shas)}"
            for (repo, kind, uid), shas in dups.items()))


def write_units(d, units, cache):
    """Replace cs_units, cs_sets, changesets and changesets_by_commit in one transaction."""
    check_unique(units)
    d.commit()
    # executescript() commits before it runs, and Python's sqlite3 does not open a transaction before DDL, so
    # the DROPs would land on their own and a failed insert would leave the tables empty. BEGIN is explicit.
    level, d.isolation_level = d.isolation_level, None
    try:
        d.execute("BEGIN")
        for stmt in SCHEMA.split(";"):
            if stmt.strip():
                d.execute(stmt)
        for key, repo, kind, uid, main_sha, header, commits, rule in units:
            if rule == "dependabot":
                sets, method = [(label, [0]) for label in commits[0]["dependabot_sets"]], rule
            elif rule:
                sets, method = [(commits[0]["subject"], list(range(len(commits))))], rule
            else:
                h = sha256(PROMPT_VERSION + unit_text(key, header, commits))
                sets, method = cache.get(h, ([(c["subject"], [i]) for i, c in enumerate(commits)],
                                             "unlabelled: one per commit"))
            d.execute("INSERT INTO cs_units VALUES (?,?,?,?,?,?,?)",
                      (repo, kind, uid, main_sha, len(commits), len(sets), method))
            for i, (label, idx) in enumerate(sets):
                d.execute("INSERT INTO cs_sets VALUES (?,?,?,?,?,?)",
                          (repo, kind, uid, i, label, json.dumps([commits[j]["sha"] for j in idx])))
            d.execute("INSERT OR REPLACE INTO changesets VALUES (?,?,?,?)",
                      (key, len(sets), json.dumps([l for l, _ in sets]), method))
            d.execute("INSERT INTO changesets_by_commit VALUES (?,?,?,?,?)", (repo, main_sha, key, kind, uid))
        d.execute("COMMIT")
    except BaseException:
        d.execute("ROLLBACK")
        raise
    finally:
        d.isolation_level = level


def build(limit=None, dry_run=False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cube.db import connect
    con = connect(check_changesets=False)
    d = sqlite3.connect(DB_PATH)
    names = {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "changesets" in names and "changesets_msg_v1" not in names:
        d.execute("ALTER TABLE changesets RENAME TO changesets_msg_v1")
        d.execute("ALTER TABLE changesets_by_commit RENAME TO changesets_by_commit_msg_v1")
    d.execute("CREATE TABLE IF NOT EXISTS cs_cache (unit_hash TEXT PRIMARY KEY, sets_json TEXT, method TEXT)")
    units = load_units(con)
    if limit:
        units = units[:limit]
    cache = {h: (json.loads(s), m) for h, s, m in d.execute("SELECT unit_hash, sets_json, method FROM cs_cache")}
    todo = []
    for u in units:
        key, repo, kind, uid, main_sha, header, commits, rule = u
        h = sha256(PROMPT_VERSION + unit_text(key, header, commits))
        if rule or h in cache:
            continue
        todo.append((h, unit_text(key, header, commits), u))
    print(f"{len(units)} units: {sum(1 for u in units if u[7])} by rule, {len(units) - len(todo) - sum(1 for u in units if u[7])} "
          f"cached, {len(todo)} need Haiku ({sum(len(t[1]) for t in todo):,} chars)", file=sys.stderr)
    if dry_run:
        return

    total = 0.0
    # A unit the model drops from its reply goes into the next round, smaller batches each time.
    for round_, per_batch in enumerate((BATCH_UNITS, 4, 1), 1):
        todo = [t for t in todo if t[0] not in cache]
        if not todo:
            break
        batches, batch, size = [], [], 0
        for t in todo:
            if batch and (size + len(t[1]) > BATCH_CHARS or len(batch) >= per_batch):
                batches.append(batch)
                batch, size = [], 0
            batch.append(t)
            size += len(t[1])
        if batch:
            batches.append(batch)
        # Calls run in parallel; sqlite is written from this thread only.
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(call_haiku, [t for _, t, _ in b]): b for b in batches}
            for n, fut in enumerate(as_completed(futures), 1):
                b = futures[fut]
                reply, cost = fut.result()
                total += cost
                for h, _, u in b:
                    sets = clean_sets(reply.get(u[0]), len(u[6]))
                    if sets:
                        d.execute("INSERT OR REPLACE INTO cs_cache VALUES (?,?,?)", (h, json.dumps(sets), "haiku"))
                        cache[h] = (sets, "haiku")
                d.commit()
                print(f"  round {round_} batch {n}/{len(batches)}: {len(b)} units, ${cost:.3f} (total ${total:.2f})",
                      file=sys.stderr)

    write_units(d, units, cache)
    print(f"detectors.sqlite: {len(units)} units, "
          f"{d.execute('SELECT SUM(n_sets) FROM cs_units').fetchone()[0]} change sets, ${total:.2f} spent")


if __name__ == "__main__":
    lim = next((int(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--limit=")), None)
    build(limit=lim, dry_run="--dry-run" in sys.argv)
