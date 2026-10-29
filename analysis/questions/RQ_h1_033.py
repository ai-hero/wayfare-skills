"""Q9.xx / RQ-h1-033 -- Can a change set's complexity be scored from
measurable properties (files touched, lines changed, repos touched)?
Correlates D1's n_sets with commit-level files/lines -- a coarse check of
whether "more change sets" tracks "bigger diff," not a validated model.
"""
RQ_ID = "RQ-h1-033"
QUESTION = "Can a change set's complexity be scored from measurable properties (files, lines)?"

SQL = """
SELECT u.n_sets, c.changed_files, c.additions, c.deletions
FROM detectors.changesets_by_commit lk
JOIN detectors.cs_units u ON u.repo = lk.repo AND u.unit_kind = lk.unit_kind AND u.unit_id = lk.unit_id
JOIN github.prs c ON c.repo = lk.repo AND c.number = (
    SELECT pr_number FROM git.commits gc WHERE gc.repo = lk.repo AND gc.sha = lk.sha
)
"""


def answer(con):
    rows = con.execute(SQL).fetchall()
    by_sets = {}
    for r in rows:
        b = by_sets.setdefault(r["n_sets"], {"files": [], "lines": []})
        b["files"].append(r["changed_files"] or 0)
        b["lines"].append((r["additions"] or 0) + (r["deletions"] or 0))
    out = []
    for n_sets, v in sorted(by_sets.items()):
        m = len(v["files"])
        out.append({"n_sets": n_sets, "prs": m,
                    "avg_files_changed": round(sum(v["files"]) / m, 1),
                    "avg_lines_changed": round(sum(v["lines"]) / m, 1)})
    return out


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
