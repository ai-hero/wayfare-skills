"""Q12.xx / RQ-h1-014 -- Measured in change sets rather than lines or
commits, does each repo's output rank the same way? D1-backed comparison
of three units.
"""
RQ_ID = "RQ-h1-014"
QUESTION = "Measured in change sets rather than lines or commits, does each repo's output rank the same way?"

SQL = """
SELECT c.repo, COUNT(*) AS commits, SUM(c.insertions + c.deletions) AS lines,
       SUM(COALESCE(u.n_sets, 1)) AS change_sets
FROM git.commits c
LEFT JOIN detectors.changesets_by_commit lk ON lk.repo = c.repo AND lk.sha = c.sha
LEFT JOIN detectors.cs_units u ON u.repo = lk.repo AND u.unit_kind = lk.unit_kind AND u.unit_id = lk.unit_id
GROUP BY c.repo
"""


def answer(con):
    rows = con.execute("SELECT repo, sha FROM git.commits").fetchall()
    sets_by_commit = {(r["repo"], r["sha"]): r["n_sets"] for r in con.execute(
        "SELECT lk.repo, lk.sha, u.n_sets FROM detectors.changesets_by_commit lk "
        "JOIN detectors.cs_units u USING (repo, unit_kind, unit_id)").fetchall()}

    by_repo = {}
    for repo, sha in rows:
        by_repo.setdefault(repo, {"commits": 0, "sets": 0})
        by_repo[repo]["commits"] += 1
        by_repo[repo]["sets"] += sets_by_commit.get((repo, sha), 1)

    lines_by_repo = {r["repo"]: r["lines"] or 0 for r in con.execute(
        "SELECT repo, SUM(insertions + deletions) AS lines FROM git.commits GROUP BY repo"
    ).fetchall()}

    ranked_commits = sorted(by_repo, key=lambda r: -by_repo[r]["commits"])
    ranked_sets = sorted(by_repo, key=lambda r: -by_repo[r]["sets"])
    ranked_lines = sorted(lines_by_repo, key=lambda r: -lines_by_repo[r])

    return [{"repo": r, "commits": by_repo[r]["commits"], "change_sets": by_repo[r]["sets"],
             "lines": lines_by_repo.get(r, 0),
             "rank_by_commits": ranked_commits.index(r) + 1, "rank_by_change_sets": ranked_sets.index(r) + 1,
             "rank_by_lines": ranked_lines.index(r) + 1 if r in ranked_lines else None}
            for r in by_repo]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
