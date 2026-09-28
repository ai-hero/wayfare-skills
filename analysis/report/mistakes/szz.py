"""SZZ over the mirrors: for each fix change set, the earlier PR whose lines it repaired.

    cd analysis && WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/mistakes/szz.py

For every commit in a fix change set, the lines it deletes or rewrites are blamed (`git blame -w`)
on the commit's parent in the read-only mirror. Each blamed commit is mapped to the PR (or pushed
commit) that put it on main; blame hits inside the fixing PR itself are in-PR fix-ups (Q in-pr-fix-share)
and are set aside. The introducing unit is the one owning the most blamed lines.
Writes mistakes.szz (one row per fix change set) and mistakes.szz_hits (every introducing candidate).
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]
from cube.db import connect as _connect  # noqa: E402
from facts import fix_changesets  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), ".analysis", "data")
DB = os.path.join(DATA, "mistakes.sqlite")
MIRRORS = os.path.join(DATA, "mirrors")
SKIP = re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|go\.sum|uv\.lock|poetry\.lock|Cargo\.lock|"
                  r"\.secrets\.baseline)$|\.(png|jpg|jpeg|gif|svg|ico|woff2?|pdf|snap)$")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


# Exit 1 (git grep: no match) and 128 (path absent at that revision) read as empty; a missing mirror or
# ref must not, or a broken checkout reports as a repo with nothing in it.
GIT_BROKEN = ("not a git repository", "cannot change to", "unknown revision", "bad object")


def git(repo, *args):
    p = subprocess.run(["git", "-C", os.path.join(MIRRORS, f"{repo}.git"), *args], capture_output=True, text=True)
    if p.returncode not in (0, 1, 128) or any(s in p.stderr for s in GIT_BROKEN):
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {p.stderr.strip()}")
    return p.stdout if p.returncode == 0 else ""


def old_ranges(repo, sha):
    """{old path: [(start, count)]} for lines the commit removes or rewrites."""
    out, path = defaultdict(list), None
    for line in git(repo, "show", "--format=", "--unified=0", "--no-renames", "--no-color", sha).splitlines():
        if line.startswith("--- "):
            path = None if line[4:] == "/dev/null" else line[6:]
        elif line.startswith("@@") and path and not SKIP.search(path):
            m = HUNK.match(line)
            if m and (int(m.group(2)) if m.group(2) is not None else 1) > 0:
                out[path].append((int(m.group(1)), int(m.group(2)) if m.group(2) is not None else 1))
    return out


def blame(repo, sha, path, ranges):
    args = ["blame", "-w", "--porcelain"]
    for a, n in ranges[:40]:
        args += ["-L", f"{a},+{n}"]
    hits = Counter()
    for line in git(repo, *args, f"{sha}^", "--", path).splitlines():
        m = re.match(r"^([0-9a-f]{40}) \d+ \d+", line)
        if m:
            hits[m.group(1)] += 1
    return hits


def owners(con):
    """blamed sha -> (repo, unit id, merged day): main commits, and original PR commits mapped to their PR."""
    own = {}
    main = {}
    for r in con.execute("SELECT repo, sha, pr_number, day, claude_trailer, is_bot FROM git.commits WHERE is_merge = 0"):
        unit = f"pr:{r['pr_number']}" if r["pr_number"] else f"push:{r['sha'][:12]}"
        main[(r["repo"], r["pr_number"])] = (r["day"], r["claude_trailer"], r["is_bot"])
        own[(r["repo"], r["sha"])] = (unit, r["day"], r["claude_trailer"], r["is_bot"])
    for r in con.execute("SELECT repo, sha, pr_number, claude_trailer FROM pr_commits.pr_commits"):
        m = main.get((r["repo"], r["pr_number"]))
        if m and (r["repo"], r["sha"]) not in own:
            own[(r["repo"], r["sha"])] = (f"pr:{r['pr_number']}", m[0], r["claude_trailer"], m[2])
    first = {r["repo"]: r["d"] for r in con.execute("SELECT repo, MIN(day) d FROM git.commits GROUP BY repo")}
    return own, first


def main():
    con = _connect()
    own, first = owners(con)
    fixes = fix_changesets(con)
    print(f"{len(fixes)} fix change sets", file=sys.stderr)

    def one(f):
        hits = Counter()
        for sha in f["shas"]:
            for path, ranges in old_ranges(f["repo"], sha).items():
                hits.update(blame(f["repo"], sha, path, ranges))
        return f, hits

    d = sqlite3.connect(DB, timeout=120)
    d.executescript("""
    DROP TABLE IF EXISTS szz; DROP TABLE IF EXISTS szz_hits;
    CREATE TABLE szz (repo TEXT, unit_kind TEXT, unit_id TEXT, set_idx INTEGER, fix_day TEXT, label TEXT,
        blamed_lines INTEGER, in_pr_lines INTEGER, intro_unit TEXT, intro_day TEXT, intro_lines INTEGER,
        intro_agent INTEGER, intro_is_first_commit INTEGER, lifetime_days REAL, outcome TEXT);
    CREATE TABLE szz_hits (repo TEXT, unit_id TEXT, set_idx INTEGER, intro_unit TEXT, intro_day TEXT, lines INTEGER);
    """)
    with ThreadPoolExecutor(8) as ex:
        for f, hits in ex.map(one, fixes):
            me = f"{'pr' if f['pr'] else 'push'}:{f['pr'] if f['pr'] else f['unit_id'][:12]}"
            by_unit, in_pr, unknown = Counter(), 0, 0
            meta = {}
            for sha, n in hits.items():
                o = own.get((f["repo"], sha))
                if not o:
                    unknown += n
                    continue
                if o[0] == me:
                    in_pr += n
                    continue
                by_unit[o[0]] += n
                meta[o[0]] = o
            for u, n in by_unit.items():
                d.execute("INSERT INTO szz_hits VALUES (?,?,?,?,?,?)", (f["repo"], f["unit_id"], f["set_idx"], u, meta[u][1], n))
            if by_unit:
                u, n = by_unit.most_common(1)[0]
                _, day, agent, _ = meta[u]
                life = (date.fromisoformat(f["day"]) - date.fromisoformat(day)).days
                outcome = "traced"
                row = (u, day, n, int(bool(agent)), int(day == first.get(f["repo"])), life, outcome)
            else:
                outcome = "only in-PR lines" if in_pr else "additive fix (nothing removed)" if not unknown else "blamed outside main"
                row = (None, None, 0, None, None, None, outcome)
            d.execute("INSERT INTO szz VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"], f["day"], f["label"],
                       sum(hits.values()), in_pr, *row))
    d.commit()
    for r in d.execute("SELECT outcome, COUNT(*) FROM szz GROUP BY 1"):
        print(*r)


if __name__ == "__main__":
    main()
