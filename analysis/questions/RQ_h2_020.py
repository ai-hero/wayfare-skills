"""Q16.xx / RQ-h2-020 -- How much spend does the factory use per shipped
change set, and what share of spend goes to shipped versus abandoned work?
D9 repo-level spend divided by D1 change-set count per repo, as a coarse
per-repo rate (not a per-item rate -- see RQ-h7-020 for D9's item-level coverage).
"""
RQ_ID = "RQ-h2-020"
QUESTION = "How much spend does the factory use per shipped change set?"


def answer(con):
    spend_by_repo = {r["repo"]: r["cost_usd"] for r in con.execute(
        "SELECT repo, SUM(cost_usd) AS cost_usd FROM detectors.session_spend GROUP BY repo"
    ).fetchall()}
    sets_by_repo, offmain_by_repo = {}, {}
    for repo, sha in con.execute("SELECT repo, sha FROM git.commits").fetchall():
        sets_by_repo.setdefault(repo, 0)
    for r in con.execute(
        "SELECT lk.repo, lk.sha, u.n_sets FROM detectors.changesets_by_commit lk "
        "JOIN detectors.cs_units u USING (repo, unit_kind, unit_id)"
    ).fetchall():
        into = sets_by_repo if r["sha"] is not None else offmain_by_repo
        into[r["repo"]] = into.get(r["repo"], 0) + r["n_sets"]

    out = []
    for repo, spend in spend_by_repo.items():
        sets = sets_by_repo.get(repo, 0)
        if sets:
            out.append({"repo": repo, "spend": round(spend, 2), "change_sets": sets,
                        "spend_per_change_set": round(spend / sets, 2),
                        "offmain_change_sets_excluded": offmain_by_repo.get(repo, 0)})
    return sorted(out, key=lambda x: -x["spend_per_change_set"])


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
