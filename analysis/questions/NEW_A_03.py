"""Q2.17 / NEW-A-03 -- What share of commits carry more than one change set,
and what share of change sets land as their own commit? D1-backed.
"""
RQ_ID = "NEW-A-03"
QUESTION = "What share of commits carry more than one change set?"


def answer(con):
    rows = con.execute(
        "SELECT u.n_sets FROM detectors.changesets_by_commit lk "
        "JOIN detectors.cs_units u USING (repo, unit_kind, unit_id)"
    ).fetchall()
    total = len(rows)
    multi = sum(1 for (n,) in rows if n > 1)
    return [{"commits": total, "commits_with_multiple_change_sets": multi,
             "multi_change_set_share": round(multi / total, 3) if total else None}]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
