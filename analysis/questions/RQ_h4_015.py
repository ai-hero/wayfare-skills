"""Q13.xx / RQ-h4-015 -- How do the size and shape of shipped changes
(change sets per PR, PR size) trend over the study? D1-backed monthly trend.
"""
RQ_ID = "RQ-h4-015"
QUESTION = "How do the size and shape of shipped changes trend over the study?"

SQL = """
SELECT p.month, p.repo, p.number, p.additions, p.deletions, c.sha
FROM github.prs p
JOIN git.commits c ON c.repo = p.repo AND c.pr_number = p.number
WHERE p.merged_ts IS NOT NULL
"""


def answer(con):
    rows = con.execute(SQL).fetchall()
    sets_by_commit = {(r["repo"], r["sha"]): r["n_sets"] for r in con.execute(
        "SELECT lk.repo, lk.sha, u.n_sets FROM detectors.changesets_by_commit lk "
        "JOIN detectors.cs_units u USING (repo, unit_kind, unit_id)").fetchall()}

    pr_sets, pr_size, pr_month = {}, {}, {}
    for r in rows:
        pr_key = (r["repo"], r["number"])
        pr_sets[pr_key] = pr_sets.get(pr_key, 0) + sets_by_commit.get((r["repo"], r["sha"]), 1)
        pr_size[pr_key] = (r["additions"] or 0) + (r["deletions"] or 0)
        pr_month[pr_key] = r["month"]

    by_month = {}
    for pr_key, sets in pr_sets.items():
        month = pr_month[pr_key]
        b = by_month.setdefault(month, {"prs": 0, "total_sets": 0, "total_lines": 0})
        b["prs"] += 1
        b["total_sets"] += sets
        b["total_lines"] += pr_size[pr_key]

    return [{"month": m, "prs": v["prs"], "avg_change_sets_per_pr": round(v["total_sets"] / v["prs"], 2),
             "avg_lines_per_pr": round(v["total_lines"] / v["prs"], 1)}
            for m, v in sorted(by_month.items())]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
