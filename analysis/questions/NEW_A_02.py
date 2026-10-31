"""Q2.17 / NEW-A-02 -- How many change sets does a typical commit, PR, work
item and goal contain? D1-backed (detectors.cs_units via changesets_by_commit).
"""
RQ_ID = "NEW-A-02"
QUESTION = "How many change sets does a typical commit, PR, work item and goal contain?"

SQL = """
SELECT lk.repo, lk.sha, u.n_sets
FROM detectors.changesets_by_commit lk
JOIN detectors.cs_units u USING (repo, unit_kind, unit_id)
WHERE lk.sha IS NOT NULL
"""


def _dist(values):
    if not values:
        return {}
    values = sorted(values)
    n = len(values)
    return {
        "n": n, "mean": round(sum(values) / n, 3),
        "p50": values[n // 2], "p90": values[int(n * 0.9)], "max": values[-1],
    }


def answer(con):
    commit_sets = con.execute(SQL).fetchall()
    by_commit = {r["sha"]: r["n_sets"] for r in commit_sets}
    commit_dist = _dist(list(by_commit.values()))

    pr_sql = "SELECT c.repo, c.pr_number, c.sha FROM git.commits c WHERE c.pr_number IS NOT NULL"
    pr_totals = {}
    for repo, pr_number, sha in con.execute(pr_sql).fetchall():
        pr_totals.setdefault((repo, pr_number), 0)
        pr_totals[(repo, pr_number)] += by_commit.get(sha, 1)
    pr_dist = _dist(list(pr_totals.values()))

    return [{"unit": "commit", **commit_dist}, {"unit": "pr", **pr_dist}]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
