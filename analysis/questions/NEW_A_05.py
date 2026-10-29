"""Q2.18 / NEW-A-05 -- Before the factory, how large and how focused were
PRs, in change sets per PR? D1-backed, split by fleet.BASELINE_CUTOFF.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest.fleet import BASELINE_CUTOFF

RQ_ID = "NEW-A-05"
QUESTION = "Before the factory, how large and how focused were PRs, in change sets per PR?"

SQL = """
SELECT p.repo, p.number, p.additions, p.deletions, p.changed_files,
       COALESCE(u.n_sets, 1) AS n_sets
FROM github.prs p
JOIN git.commits c ON c.repo = p.repo AND c.pr_number = p.number
JOIN detectors.changesets_by_commit lk ON lk.repo = c.repo AND lk.sha = c.sha
LEFT JOIN detectors.cs_units u ON u.repo = lk.repo AND u.unit_kind = lk.unit_kind AND u.unit_id = lk.unit_id
WHERE p.day < ?
"""


def answer(con):
    rows = con.execute(SQL, (BASELINE_CUTOFF,)).fetchall()
    pr_sets = {}
    pr_size = {}
    for r in rows:
        key = (r["repo"], r["number"])
        pr_sets.setdefault(key, 0)
        pr_sets[key] += r["n_sets"]
        pr_size[key] = (r["additions"] or 0) + (r["deletions"] or 0)

    if not pr_sets:
        return [{"note": "no pre-factory PRs with commit-level change-set data"}]
    sets_vals = sorted(pr_sets.values())
    n = len(sets_vals)
    return [{
        "pre_factory_prs": n,
        "avg_change_sets_per_pr": round(sum(sets_vals) / n, 2),
        "p50_change_sets_per_pr": sets_vals[n // 2],
        "avg_lines_per_pr": round(sum(pr_size.values()) / n, 1),
    }]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
