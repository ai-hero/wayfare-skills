"""Q16.xx / RQ-h2-010 -- How do spend and CI minutes per unit of work
change when the unit is counted at each level (commit, PR, item, goal)?
Reuses RQ-h2-020 (spend per change set) and adds per-PR/per-item spend
using the same D9 session_spend base.
"""
RQ_ID = "RQ-h2-010"
QUESTION = "How do spend and CI minutes per unit of work change when counted as commit, PR, item or goal?"


def answer(con):
    total_spend = con.execute("SELECT SUM(cost_usd) FROM detectors.session_spend").fetchone()[0] or 0
    commits = con.execute("SELECT COUNT(*) FROM git.commits").fetchone()[0]
    prs = con.execute("SELECT COUNT(*) FROM github.prs WHERE merged_ts IS NOT NULL").fetchone()[0]
    items = con.execute("SELECT COUNT(*) FROM plans.plan_items WHERE type != 'goal'").fetchone()[0]
    goals = con.execute("SELECT COUNT(*) FROM plans.goals").fetchone()[0]
    sets = con.execute(
        "SELECT SUM(u.n_sets) FROM detectors.changesets_by_commit lk "
        "JOIN detectors.cs_units u USING (repo, unit_kind, unit_id)"
    ).fetchone()[0] or 0
    return [
        {"unit": "change_set", "count": sets, "spend_per_unit": round(total_spend / sets, 2) if sets else None},
        {"unit": "commit", "count": commits, "spend_per_unit": round(total_spend / commits, 2) if commits else None},
        {"unit": "merged_pr", "count": prs, "spend_per_unit": round(total_spend / prs, 2) if prs else None},
        {"unit": "item", "count": items, "spend_per_unit": round(total_spend / items, 2) if items else None},
        {"unit": "goal", "count": goals, "spend_per_unit": round(total_spend / goals, 2) if goals else None},
    ]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
