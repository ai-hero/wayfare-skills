"""Q2.08 / RQ-h1-045 -- How did churn per commit and per change set compare
before and after the factory in the same repo? D1-backed.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest.fleet import BASELINE_CUTOFF

RQ_ID = "RQ-h1-045"
QUESTION = "How did churn per commit and per change set compare before and after the factory?"

SQL = """
SELECT c.repo, CASE WHEN c.day < ? THEN 'before' ELSE 'after' END AS era,
       c.insertions, c.deletions, COALESCE(u.n_sets, 1) AS n_sets
FROM git.commits c
JOIN detectors.changesets_by_commit lk ON lk.repo = c.repo AND lk.sha = c.sha
LEFT JOIN detectors.cs_units u ON u.repo = lk.repo AND u.unit_kind = lk.unit_kind AND u.unit_id = lk.unit_id
"""


def answer(con):
    rows = con.execute(SQL, (BASELINE_CUTOFF,)).fetchall()
    agg = {}
    for r in rows:
        key = (r["repo"], r["era"])
        a = agg.setdefault(key, {"commits": 0, "churn": 0, "sets": 0})
        churn = (r["insertions"] or 0) + (r["deletions"] or 0)
        a["commits"] += 1
        a["churn"] += churn
        a["sets"] += r["n_sets"]

    out = []
    for (repo, era), a in sorted(agg.items()):
        out.append({
            "repo": repo, "era": era, "commits": a["commits"],
            "churn_per_commit": round(a["churn"] / a["commits"], 1),
            "churn_per_change_set": round(a["churn"] / a["sets"], 1) if a["sets"] else None,
        })
    return out


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
