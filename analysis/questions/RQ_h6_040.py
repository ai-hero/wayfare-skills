"""Q5.xx / RQ-h6-040 -- What is the review/CI cost of shipping many small
units vs one consolidated unit? D1+D8-backed: PRs bucketed by change-set
count (from D1, via their commits) against review count and CI run count.
"""
from cube.db import commit_sets

RQ_ID = "RQ-h6-040"
QUESTION = "What is the review and CI cost of shipping many small units versus one consolidated unit?"

SQL = """
SELECT p.repo, p.number, p.review_count,
       (SELECT COUNT(*) FROM github.ci_runs cr WHERE cr.repo = p.repo AND cr.head_branch = p.head_ref) AS ci_runs,
       c.sha
FROM github.prs p
JOIN git.commits c ON c.repo = p.repo AND c.pr_number = p.number
JOIN detectors.changesets_by_commit lk ON lk.repo = c.repo AND lk.sha = c.sha
"""


def _bucket(n):
    if n <= 1:
        return "1 change set"
    if n <= 3:
        return "2-3 change sets"
    return "4+ change sets"


def answer(con):
    rows = con.execute(SQL).fetchall()
    sets = commit_sets(con)
    pr_sets, pr_meta = {}, {}
    for r in rows:
        key = (r["repo"], r["number"])
        pr_sets.setdefault(key, 0)
        pr_sets[key] += sets[(r["repo"], r["sha"])]
        pr_meta[key] = (r["review_count"] or 0, r["ci_runs"] or 0)

    buckets = {}
    for key, sets in pr_sets.items():
        b = _bucket(sets)
        rc, cr = pr_meta[key]
        agg = buckets.setdefault(b, {"prs": 0, "reviews": 0, "ci_runs": 0})
        agg["prs"] += 1
        agg["reviews"] += rc
        agg["ci_runs"] += cr

    return [{"bucket": b, "prs": v["prs"], "avg_reviews_per_pr": round(v["reviews"] / v["prs"], 2),
              "avg_ci_runs_per_pr": round(v["ci_runs"] / v["prs"], 2)}
            for b, v in sorted(buckets.items())]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
