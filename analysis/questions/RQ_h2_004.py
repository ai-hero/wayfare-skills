"""Q16.xx / RQ-h2-004 -- For a defect inherited from the template by
every clone, what does fixing it independently in each clone cost versus
fixing it once upstream? Combines RQ-h2-011's repeat count with the
fleet's overall spend-per-change-set rate as a cost estimate per repeat.
"""
RQ_ID = "RQ-h2-004"
QUESTION = "For a defect inherited by every clone, what does fixing it independently cost versus fixing it once upstream?"


def answer(con):
    from questions.RQ_h2_011 import answer as repeat_answer
    repeats = repeat_answer(con)[0]
    avg_spend_per_set = con.execute(
        "SELECT SUM(s.cost_usd) * 1.0 / SUM(u.n_sets) FROM detectors.session_spend s "
        "JOIN detectors.changesets_by_commit lk ON lk.repo = s.repo "
        "JOIN detectors.cs_units u ON u.repo = lk.repo AND u.unit_kind = lk.unit_kind AND u.unit_id = lk.unit_id "
        "WHERE lk.sha IS NOT NULL"
    ).fetchone()[0]
    if not repeats.get("median_repos_repeating_independently") or not avg_spend_per_set:
        return [repeats]
    return [{**repeats, "fleet_avg_spend_per_change_set": round(avg_spend_per_set, 2),
             "estimated_cost_of_independent_repeats": round(
                 repeats["median_repos_repeating_independently"] * avg_spend_per_set, 2)}]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
