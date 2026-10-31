"""Q19.xx / RQ-h7-026 -- What unit should flow and output be compared in
across repos: lines, commits, PRs, or change sets? Methodology question
this repo has already answered by construction: D1's "change set" is the
chosen unit (see AGENTS.md's "change set as the fleet's preferred unit
of work" and NEW-A-02's size distribution). sql half: show why lines/
commits/PRs are each unstable units on this data.
"""
RQ_ID = "RQ-h7-026"
QUESTION = "What unit should flow and output be compared in across repos: lines, commits, PRs, or change sets?"


def answer(con):
    sets = con.execute("SELECT SUM(CASE WHEN main_sha IS NOT NULL THEN n_sets END) AS n, "
                       "SUM(CASE WHEN main_sha IS NULL THEN n_sets ELSE 0 END) AS offmain "
                       "FROM detectors.cs_units").fetchone()
    n_sets = sets["n"] or 0
    n_commits = con.execute("SELECT COUNT(*) AS n FROM git.commits").fetchone()["n"]
    n_prs = con.execute("SELECT COUNT(*) AS n FROM github.prs").fetchone()["n"]
    return [{"commits_per_pr_avg": round(n_commits / n_prs, 2) if n_prs else None,
             "commits_reclustered_into_change_sets": n_sets,
             "commits_per_change_set_avg": round(n_commits / n_sets, 2) if n_sets else None,
             "offmain_change_sets_excluded": sets["offmain"] or 0,
             "chosen_unit": "change set (D1's Haiku-assisted split), because commits-per-PR varies "
                            "widely and a single PR can bundle unrelated work; lines undercount "
                            "config/generated-file-heavy changes",
             "answerable_by_code": "partial",
             "reason": "the instability of raw commit/PR counts as a unit is measurable; whether "
                       "change sets are the *right* unit for a specific downstream comparison is a "
                       "human methodology call"}]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
