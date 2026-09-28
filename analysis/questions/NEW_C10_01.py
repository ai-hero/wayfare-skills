"""Skills preflight / NEW-C10-01 -- Does the factory package its
procedures as versioned skills?

Yes/no + inventory: skill_versions has one row per commit that touched a
skill (ingest/knowledge.py walks wayfare-skills' own history), so its mere
existence answers "yes", and count-distinct-skill gives the inventory size.
"""
RQ_ID = "NEW-C10-01"
QUESTION = "Does the factory package its procedures as versioned skills?"

SQL = """
SELECT COUNT(DISTINCT skill) AS distinct_skills,
       COUNT(*) AS skill_version_events,
       MIN(day) AS first_seen,
       MAX(day) AS last_seen
FROM knowledge.skill_versions
"""


def answer(con):
    row = dict(con.execute(SQL).fetchone())
    row["packaged_as_versioned_skills"] = row["distinct_skills"] > 0
    return [row]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
