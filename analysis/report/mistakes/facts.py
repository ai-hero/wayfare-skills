"""Mistakes and rework building blocks shared by szz.py and data.py."""
import os
import re
import sqlite3
import sys
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]
from record import changeset_facts, commit_facts  # noqa: E402

FIX_RE = re.compile(r"^fix(\(|!|:)", re.I)


def has_table(con, db, table):
    try:
        return bool(con.execute(f"SELECT 1 FROM {db}.sqlite_master WHERE name=?", (table,)).fetchone())
    except sqlite3.OperationalError:
        return False


@lru_cache(maxsize=None)
def fix_method(con):
    return "cs_worktype" if has_table(con, "detectors", "cs_worktype") else "first commit is fix:"


@lru_cache(maxsize=None)
def fix_changesets(con):
    """Change sets whose work is a fix, Dependabot excluded.

    The lead's shared detectors.cs_worktype label is used when it exists; until then a change
    set is a fix when its first original commit has a conventional `fix` subject. The rule
    misses fixes filed under other types and counts the rare `fix:` that is really a feature."""
    cs = [f for f in changeset_facts(con) if not f["dependabot"]]
    if fix_method(con) == "cs_worktype":
        cols = {r[1] for r in con.execute("PRAGMA detectors.table_info(cs_worktype)")}
        typ = "work_type" if "work_type" in cols else "type"
        lab = {(r["repo"], r["unit_kind"], r["unit_id"], r["set_idx"]): r[typ]
               for r in con.execute(f"SELECT * FROM detectors.cs_worktype")}
        return [f for f in cs if lab.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"])) == "fix"]
    subj = {(c["repo"], c["sha"]): c["subject"] or "" for c in commit_facts(con)}
    return [f for f in cs if FIX_RE.match(subj.get((f["repo"], f["shas"][0]), ""))]
