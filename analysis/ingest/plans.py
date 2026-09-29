"""Reads each fleet repo's .plans/ work-item store -> data/plans.sqlite.

The store is untracked local state (not in git), so this reads straight from
disk. Two schema eras exist in the fleet, discovered by inspection rather than
documented anywhere:

  - old: flat files directly under .plans/ (NNN-slug.md), frontmatter key
    `kind`, a free-text `## Comments` log.
  - new: PLAN.md (the plan object) + items/NNN-slug.md, frontmatter key
    `type`, goals as type: goal, a `## Log` section with dated entries.

Both eras share the same shape enough to normalise into one set of tables.
Frontmatter is YAML-*like* but simple (flat key: value, key: [list], one
level of key:\\n  nested: map) - a hand-written parser covers it without
pulling in a YAML dependency, per the project's own "no new dependency
without asking" rule.
"""
import os, re, sys, sqlite3, time, json, glob, hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest.fleet import ALL_REPOS, path_of, dims
from ingest.redact import redact

OUT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".analysis", "data", "plans.sqlite")

FAMILY = re.compile(r"^([a-zA-Z][a-zA-Z0-9._-]*):(\d+)$")  # cross-repo "repo:item" reference

# ---------------------------------------------------------------------------
# tiny frontmatter parser: flat key: value, key: [a, b, c] (possibly wrapped
# across lines), and one level of nested `key:\n  sub: val` maps (only
# `anchors` and PLAN.md's `source` use this in the corpus inspected).
# ---------------------------------------------------------------------------

_TRAILING_COMMENT_RE = re.compile(r"\s+#.*$")


def _scalar(s):
    s = s.strip()
    if s == "": return None
    if s == "[]": return []
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"': return s[1:-1]
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'": return s[1:-1]
    # An unquoted scalar's trailing " # ..." is a YAML comment, not part of
    # the value -- unstripped, it corrupted ready_ts/done_ts into unparsable
    # date strings and turned `one_way_door: true # why` into neither True
    # nor a real string. A quoted scalar already returned above, so `#`
    # reaching here is always a comment, never literal content.
    s = _TRAILING_COMMENT_RE.sub("", s).strip()
    if s.lower() == "null" or s == "~": return None
    if s.lower() == "true": return True
    if s.lower() == "false": return False
    if re.fullmatch(r"-?\d+", s): return int(s)
    return s

def _split_flow_list(s):
    """s is the inside-brackets text of a [a, b, c] flow list, comma-split
    respecting simple quoting (no nested brackets appear in the corpus)."""
    items, cur, depth, inq = [], "", 0, None
    for ch in s:
        if inq:
            cur += ch
            if ch == inq: inq = None
            continue
        if ch in "\"'":
            inq = ch; cur += ch; continue
        if ch == ",":
            items.append(cur); cur = ""; continue
        cur += ch
    if cur.strip(): items.append(cur)
    return [_scalar(i) for i in items if i.strip() != ""]

def parse_frontmatter(text):
    """text is everything between the two `---` lines. Returns a dict."""
    # join a flow list ("key: [" ... "]") that wraps across several physical
    # lines into one logical line before the per-line pass
    raw_lines = text.split("\n")
    joined = []
    buf, depth = None, 0
    for line in raw_lines:
        if buf is None:
            depth = line.count("[") - line.count("]")
            if depth > 0:
                buf = line
                continue
            joined.append(line)
        else:
            buf += " " + line.strip()
            depth += line.count("[") - line.count("]")
            if depth <= 0:
                joined.append(buf)
                buf = None
    if buf is not None: joined.append(buf)

    data = {}
    i = 0
    while i < len(joined):
        line = joined[i]
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if not m:
            i += 1; continue
        key, rest = m.group(1), m.group(2)
        if rest == "":
            # either a nested map (next lines indented "  sub: val") or an
            # empty scalar
            sub = {}
            j = i + 1
            while j < len(joined) and re.match(r"^  [A-Za-z_]", joined[j]):
                sm = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", joined[j])
                if sm: sub[sm.group(1)] = _scalar(sm.group(2))
                j += 1
            if sub:
                data[key] = sub
                i = j
                continue
            data[key] = None
            i += 1
            continue
        if rest.startswith("["):
            inner = rest[1:rest.rfind("]")] if "]" in rest else rest[1:]
            data[key] = _split_flow_list(inner)
        else:
            data[key] = _scalar(rest)
        i += 1
    return data

def split_doc(text):
    """Returns (frontmatter_dict, body_text) for a file with a leading
    `---\\n ... \\n---` block, or ({}, text) if there is none."""
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    parts = text.split("---\n", 2) if "\r\n" not in text[:200] else text.split("---\r\n", 2)
    if len(parts) < 3:
        return {}, text
    return parse_frontmatter(parts[1]), parts[2]

# ---------------------------------------------------------------------------
# dates: old and new era logs share `- YYYY-MM-DD (source[, extra]) [kind:] text`
# ---------------------------------------------------------------------------

LOG_LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) \(([^)]*)\)(?:\s+([a-z][a-z-]*):)?\s*(.*)$")

def parse_log_section(body, heading="## Log"):
    """Returns a list of (date, source, kind, text). Falls back to
    `## Comments` (the old era's heading) when `heading` is absent."""
    for h in (heading, "## Comments"):
        m = re.search(re.escape(h) + r"\s*\n(.*)$", body, re.S)
        if not m: continue
        section = m.group(1)
        # stop at the next top-level heading, if any follows (there is none
        # in the corpus - Log/Comments is always last - but be defensive)
        section = re.split(r"\n## ", section)[0]
        entries = []
        cur = None
        for line in section.split("\n"):
            lm = LOG_LINE.match(line)
            if lm:
                if cur: entries.append(cur)
                date, source, kind, text = lm.groups()
                cur = [date, source.strip(), kind or "note", text.strip()]
            elif cur is not None and line.strip():
                cur[3] += " " + line.strip()
        if cur: entries.append(cur)
        if entries: return entries
    return []

def to_ts(date_str):
    return date_str + "T00:00:00+00:00" if date_str else None

# ---------------------------------------------------------------------------
# type / kind normalisation
# ---------------------------------------------------------------------------

def normalise_type(schema_era, raw_type, shape, channel):
    if schema_era == "old":
        return {
            "feature": "feature", "hardening": "security", "polish": "chore",
            "architecture": "research", "architecture-feedback": "research",
            "design-feedback": "feedback", "design-system-feedback": "feedback",
            "goal": "goal",
        }.get(raw_type, raw_type or "unknown")
    # new era
    if raw_type == "goal": return "goal"
    if raw_type == "idea": return "research"
    if raw_type == "signal": return "feedback"
    if raw_type == "task":
        return {
            "defect": "bug", "dependency": "chore", "docs": "docs",
            "story": "feature", "structural": "chore", "visual": "polish",
        }.get(shape, "task")
    return raw_type or "unknown"

# ---------------------------------------------------------------------------
# per-item parse
# ---------------------------------------------------------------------------

def parse_item(repo, path, schema_era):
    text = open(path, encoding="utf-8", errors="replace").read()
    fm, body = split_doc(text)
    if not fm or "id" not in fm:
        return None, f"{path}: no frontmatter id"

    item_id = str(fm["id"])
    raw_type = fm.get("type") if schema_era == "new" else fm.get("kind")
    shape = fm.get("shape")
    channel = fm.get("channel")
    ntype = normalise_type(schema_era, raw_type, shape, channel)

    logs = parse_log_section(body)
    dates = [e[0] for e in logs]
    ready_marked = fm.get("ready_marked")
    ready_ts = to_ts(ready_marked) if isinstance(ready_marked, str) else None

    # A schema migration rewrites the log, so its line is the earliest one on every migrated item; taking it
    # as the creation date makes the whole backlog look new on migration day. Skip it; the real date is lost.
    born = [e[0] for e in logs if e[2] != "migrate" and "migrated to schema" not in (e[3] or "")]
    created_ts = to_ts(min(born)) if born else None
    updated_ts = to_ts(max(dates)) if dates else created_ts

    done_ts = None
    status = fm.get("status")
    if status == "done" and dates:
        # last log entry that mentions "done"/"shipped"/"merged"/"closed",
        # else fall back to the last entry overall
        for date, source, kind, txt in reversed(logs):
            if re.search(r"\bdone\b|shipped|merged|closed|DONE", txt):
                done_ts = to_ts(date); break
        if done_ts is None:
            done_ts = to_ts(dates[-1])

    depends_on = fm.get("depends_on") or []
    if not isinstance(depends_on, list): depends_on = [depends_on]

    parent = fm.get("parent")
    goal_id = str(parent) if parent not in (None, "") else None

    priority = fm.get("rank")

    row = dict(
        repo=repo, item_id=item_id, title=fm.get("title"),
        type=ntype, type_raw=raw_type or "", status=status,
        origin=fm.get("origin"), priority=priority, goal_id=goal_id,
        created_ts=created_ts, updated_ts=updated_ts, ready_ts=ready_ts, done_ts=done_ts,
        schema_era=schema_era, file_path=path, body_chars=len(body),
        raw_frontmatter_json=json.dumps(fm, default=str, sort_keys=True),
    )
    edges = []
    for dep in depends_on:
        dep = str(dep)
        m = FAMILY.match(dep)
        if m: edges.append((repo, item_id, m.group(1), m.group(2), "depends_on"))
        else: edges.append((repo, item_id, repo, dep, "depends_on"))
    if goal_id is not None:
        edges.append((repo, item_id, repo, goal_id, "parent"))
    discovered_from = fm.get("discovered_from")
    if isinstance(discovered_from, (int, str)) and str(discovered_from).strip():
        d = str(discovered_from)
        m = FAMILY.match(d)
        if m:
            edges.append((repo, item_id, m.group(1), m.group(2), "discovered_from"))
        elif re.fullmatch(r"\d+", d):
            edges.append((repo, item_id, repo, d, "discovered_from"))
        # else: free-text provenance (e.g. "harden audit 2026-08-25") - not an edge
    for kind in ("blocks", "supersedes"):
        val = fm.get(kind)
        if not val: continue
        vals = val if isinstance(val, list) else [val]
        for v in vals:
            v = str(v)
            m = FAMILY.match(v)
            if m: edges.append((repo, item_id, m.group(1), m.group(2), kind))
            elif re.fullmatch(r"\d+", v): edges.append((repo, item_id, repo, v, kind))

    log_rows = [(repo, item_id, to_ts(d), k, redact(t)) for d, s, k, t in logs]
    return (row, edges, log_rows), None

# ---------------------------------------------------------------------------
# goals: type/kind == goal items become goals table rows too, membership from
# the reverse of item_edges kind='parent'
# ---------------------------------------------------------------------------

def is_goal(schema_era, fm):
    raw = fm.get("type") if schema_era == "new" else fm.get("kind")
    return raw == "goal"

# ---------------------------------------------------------------------------
# messages: structured mailbox files (inbox/, outbox/, .outbox/) with
# msg_id/from/to frontmatter, plus free-form "Signal to X" outbox files
# (no frontmatter to/from - parsed from the title/From line instead).
# ---------------------------------------------------------------------------

MAILBOX_DIRS = ("inbox", "outbox", ".outbox")

def parse_mailbox_file(repo, path):
    text = open(path, encoding="utf-8", errors="replace").read()
    fm, body = split_doc(text)
    if fm and "msg_id" in fm:
        heading_m = re.search(r"^## .+$", body, re.M)
        first_line = ""
        if heading_m:
            after = body[heading_m.end():].lstrip("\n")
            first_line = after.split("\n", 1)[0].strip()
        subject = f"[{fm.get('type')}] {first_line}"[:200] if first_line else str(fm.get("type"))
        return dict(
            from_repo=fm.get("from") or repo, to_repo=fm.get("to"),
            direction=None, message_id=fm.get("msg_id"),
            created_ts=to_ts(fm.get("sent")) if isinstance(fm.get("sent"), str) else None,
            status=fm.get("status"), subject=redact(subject),
            body_redacted=redact(body.strip()), file_path=path,
        ), None
    # free-form "# Signal to <repo>: <title>" + "From: <repo> · <date> · ..."
    title_m = re.search(r"^#\s*Signal to ([a-zA-Z0-9._-]+):\s*(.+)$", text, re.M)
    from_m = re.search(r"^From:\s*([a-zA-Z0-9._-]+)\s*·\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    if title_m:
        return dict(
            from_repo=(from_m.group(1) if from_m else repo), to_repo=title_m.group(1),
            direction=None, message_id=os.path.basename(path),
            created_ts=to_ts(from_m.group(2)) if from_m else None,
            status="sent", subject=title_m.group(2).strip(),
            body_redacted=redact(text.strip()), file_path=path,
        ), None
    return None, f"{path}: unrecognised message format"

def message_direction(from_repo, to_repo, role_of_map):
    upstream_roles = {"template repo", "shared service", "design system", "process plugin"}
    fr, tr = role_of_map.get(from_repo), role_of_map.get(to_repo)
    if fr in upstream_roles and tr not in upstream_roles: return "downstream"
    if tr in upstream_roles and fr not in upstream_roles: return "upstream"
    return "unknown"

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    os.makedirs(os.path.dirname(OUT_DB), exist_ok=True)
    if os.path.exists(OUT_DB): os.remove(OUT_DB)
    con = sqlite3.connect(OUT_DB)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE plan_items(
        repo TEXT, item_id TEXT, title TEXT, type TEXT, type_raw TEXT,
        status TEXT, origin TEXT, priority TEXT, goal_id TEXT,
        created_ts TEXT, updated_ts TEXT, ready_ts TEXT, done_ts TEXT,
        day TEXT, week TEXT, month TEXT,
        schema_era TEXT, file_path TEXT, body_chars INTEGER, raw_frontmatter_json TEXT,
        PRIMARY KEY (repo, item_id)
    );
    CREATE TABLE item_edges(repo TEXT, src_item TEXT, dst_repo TEXT, dst_item TEXT, kind TEXT);
    CREATE TABLE item_logs(repo TEXT, item_id TEXT, ts TEXT, kind TEXT, text_redacted TEXT);
    CREATE TABLE goals(repo TEXT, goal_id TEXT, title TEXT, status TEXT, created_ts TEXT, members TEXT, PRIMARY KEY (repo, goal_id));
    CREATE TABLE messages(from_repo TEXT, to_repo TEXT, direction TEXT, message_id TEXT,
        created_ts TEXT, status TEXT, subject TEXT, body_redacted TEXT, file_path TEXT);
    CREATE TABLE plan_docs(repo TEXT, file TEXT, chars INTEGER, updated_ts TEXT);
    CREATE TABLE meta(source TEXT, path TEXT, rows INTEGER, extracted_at TEXT);
    """)

    role_of_map = {}
    for r in ALL_REPOS:
        try:
            from ingest.fleet import role_of
            role_of_map[r] = role_of(r)
        except Exception:
            role_of_map[r] = "unknown"

    failures = []
    per_repo_counts = {}
    per_repo_era = {}
    goal_rows_pending = []  # (repo, item_id, fm-ish row) to build goals table after all items parsed

    for repo in ALL_REPOS:
        base = os.path.join(path_of(repo), ".plans")
        if not os.path.isdir(base):
            continue
        items_dir = os.path.join(base, "items")
        schema_era = "new" if os.path.isdir(items_dir) else "old"
        per_repo_era[repo] = schema_era

        if schema_era == "new":
            item_files = sorted(glob.glob(os.path.join(items_dir, "*.md")))
        else:
            item_files = sorted(f for f in glob.glob(os.path.join(base, "*.md")))

        count = 0
        for path in item_files:
            result, err = parse_item(repo, path, schema_era)
            if err:
                failures.append(err); continue
            row, edges, log_rows = result
            d = dims(row["created_ts"]) if row["created_ts"] else {"day": None, "week": None, "month": None}
            cur.execute(
                "INSERT INTO plan_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row["repo"], row["item_id"], row["title"], row["type"], row["type_raw"],
                 row["status"], row["origin"], row["priority"], row["goal_id"],
                 row["created_ts"], row["updated_ts"], row["ready_ts"], row["done_ts"],
                 d["day"], d["week"], d["month"],
                 row["schema_era"], row["file_path"], row["body_chars"], row["raw_frontmatter_json"]),
            )
            for e in edges:
                cur.execute("INSERT INTO item_edges VALUES (?,?,?,?,?)", e)
            for lr in log_rows:
                cur.execute("INSERT INTO item_logs VALUES (?,?,?,?,?)", lr)
            fm = json.loads(row["raw_frontmatter_json"])
            if is_goal(schema_era, fm):
                goal_rows_pending.append((repo, row["item_id"], row["title"], row["status"], row["created_ts"]))
            count += 1
        per_repo_counts[repo] = count

        # plan_docs: PLAN.md, docs/*.md, notes/*.md - top-level docs, not items
        doc_candidates = [os.path.join(base, "PLAN.md")]
        doc_candidates += glob.glob(os.path.join(base, "docs", "*.md"))
        doc_candidates += glob.glob(os.path.join(base, "notes", "*.md"))
        for dpath in doc_candidates:
            if not os.path.isfile(dpath): continue
            dtext = open(dpath, encoding="utf-8", errors="replace").read()
            dfm, dbody = split_doc(dtext)
            logs = parse_log_section(dbody)
            updated = to_ts(max(e[0] for e in logs)) if logs else None
            cur.execute("INSERT INTO plan_docs VALUES (?,?,?,?)",
                        (repo, os.path.relpath(dpath, base), len(dtext), updated))

        # messages: mailbox dirs
        for mdir in MAILBOX_DIRS:
            mpath = os.path.join(base, mdir)
            if not os.path.isdir(mpath): continue
            for mf in sorted(glob.glob(os.path.join(mpath, "*.md"))):
                msg, err = parse_mailbox_file(repo, mf)
                if err:
                    failures.append(err); continue
                direction = message_direction(msg["from_repo"], msg["to_repo"], role_of_map)
                cur.execute(
                    "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
                    (msg["from_repo"], msg["to_repo"], direction, msg["message_id"],
                     msg["created_ts"], msg["status"], msg["subject"], msg["body_redacted"], msg["file_path"]),
                )

    # goals table + membership (reverse of item_edges kind='parent')
    for repo, goal_id, title, status, created_ts in goal_rows_pending:
        members = [r[0] for r in cur.execute(
            "SELECT src_item FROM item_edges WHERE kind='parent' AND repo=? AND dst_repo=? AND dst_item=?",
            (repo, repo, goal_id)).fetchall()]
        cur.execute("INSERT INTO goals VALUES (?,?,?,?,?,?)",
                    (repo, goal_id, title, status, created_ts, json.dumps(members)))

    tables = ["plan_items", "item_edges", "item_logs", "goals", "messages", "plan_docs"]
    total_rows = 0
    for t in tables:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        total_rows += n
        cur.execute("INSERT INTO meta VALUES (?,?,?,?)",
                    ("plans", OUT_DB, n, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))

    con.commit()

    # ---- verification prints ----
    print("\n=== per-repo item counts / schema era ===")
    for repo in ALL_REPOS:
        if repo in per_repo_counts:
            print(f"{repo:32} {per_repo_era[repo]:4} {per_repo_counts[repo]:4} items")

    print("\n=== type/status distribution per repo ===")
    for repo in ALL_REPOS:
        if repo not in per_repo_counts: continue
        rows = cur.execute(
            "SELECT type, status, COUNT(*) FROM plan_items WHERE repo=? GROUP BY type, status ORDER BY type, status",
            (repo,)).fetchall()
        print(f"-- {repo} --")
        for ty, st, n in rows:
            print(f"   {ty:12} {st or '(none)':12} {n}")

    print("\n=== ls-count spot checks (3 repos) ===")
    for repo in ALL_REPOS[:3]:
        base = os.path.join(path_of(repo), ".plans")
        items_dir = os.path.join(base, "items")
        if os.path.isdir(items_dir):
            ls_n = len(glob.glob(os.path.join(items_dir, "*.md")))
        else:
            ls_n = len(glob.glob(os.path.join(base, "*.md")))
        db_n = cur.execute("SELECT COUNT(*) FROM plan_items WHERE repo=?", (repo,)).fetchone()[0]
        print(f"{repo}: ls={ls_n} db={db_n} {'OK' if ls_n == db_n else 'MISMATCH'}")

    print("\n=== message count by direction ===")
    for d, n in cur.execute("SELECT direction, COUNT(*) FROM messages GROUP BY direction").fetchall():
        print(f"   {d}: {n}")

    if failures:
        print("\n=== parse failures ===")
        for f in failures: print(f"   {f}")
    else:
        print("\n=== parse failures: none ===")

    elapsed = time.time() - t0
    print(f"\ntables={tables} total_rows={total_rows} elapsed={elapsed:.2f}s -> {OUT_DB}")

if __name__ == "__main__":
    main()
