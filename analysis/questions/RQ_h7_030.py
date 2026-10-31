"""Q19.xx / RQ-h7-030 -- When two independent passes count the same
history, where do totals disagree, and does the chosen fleet-wide
number hide that disagreement? sql half: compare the two passes this
repo actually has over the same events -- raw git commits vs D1's
Haiku-reclustered change sets -- per repo. The second pass is SUM(n_sets):
cs_units holds one row per unit, so counting its rows recounts units,
not change sets.
"""
RQ_ID = "RQ-h7-030"
QUESTION = "When two independent passes count the same history, where do totals disagree, and does the chosen number hide that?"


def answer(con):
    commits = {r["repo"]: r["n"] for r in con.execute(
        "SELECT repo, COUNT(*) AS n FROM git.commits GROUP BY repo"
    ).fetchall()}
    sets_by_repo = {r["repo"]: (r["n"], r["offmain"]) for r in con.execute(
        "SELECT bc.repo AS repo, SUM(CASE WHEN bc.sha IS NOT NULL THEN u.n_sets END) AS n, "
        "SUM(CASE WHEN bc.sha IS NULL THEN u.n_sets ELSE 0 END) AS offmain "
        "FROM detectors.changesets_by_commit bc "
        "JOIN detectors.cs_units u USING (repo, unit_kind, unit_id) "
        "GROUP BY bc.repo"
    ).fetchall()}
    out = []
    for repo, n_commits in commits.items():
        n_sets, offmain = sets_by_repo.get(repo, (None, 0))
        out.append({"repo": repo, "raw_commit_count": n_commits, "change_set_count": n_sets,
                    "commits_per_change_set": round(n_commits / n_sets, 2) if n_sets else None,
                    "offmain_change_sets_excluded": offmain})
    out.append({"answerable_by_code": "partial",
                "reason": "totals per pass are computable per repo above; whether the fleet-wide "
                          "single number (either pass) hides a repo that skews the average is a "
                          "human read of this table, not a further computation"})
    return out


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
