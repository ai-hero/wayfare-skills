"""Q9.xx / RQ-h3-021 -- How are bug-fix change sets distributed by scope
(product code, tests, CI) and type (security or not)? sql: commits
whose subject starts with "fix" (a conventional-commit prefix already
present in this fleet's history, see cs_sets.label), grouped
by the top_dir of the files each one touches. "Security or not" is
flagged by a keyword match on the subject, which is a proxy, not a
classification.
"""
RQ_ID = "RQ-h3-021"
QUESTION = "How are bug-fix change sets distributed by scope (product code, tests, CI) and type (security or not)?"


def _scope(top_dir, ext):
    if top_dir in (".github",):
        return "ci"
    if top_dir and ("test" in top_dir.lower()):
        return "tests"
    return "product code"


def answer(con):
    fixes = con.execute(
        "SELECT repo, sha FROM git.commits WHERE conv_type = 'fix'"
    ).fetchall()
    fix_keys = {(r["repo"], r["sha"]) for r in fixes}
    scope_counts = {"ci": 0, "tests": 0, "product code": 0}
    security_count = 0
    seen = set()
    for r in fixes:
        subj = con.execute("SELECT subject FROM git.commits WHERE repo=? AND sha=?", (r["repo"], r["sha"])).fetchone()["subject"]
        if "secur" in subj.lower() or "cve" in subj.lower() or "vuln" in subj.lower():
            security_count += 1
        files = con.execute(
            "SELECT top_dir, ext FROM git.commit_files WHERE repo=? AND sha=?", (r["repo"], r["sha"])
        ).fetchall()
        scopes_touched = {_scope(f["top_dir"], f["ext"]) for f in files} or {"product code"}
        for s in scopes_touched:
            scope_counts[s] += 1
    return [{"bug_fix_commits": len(fix_keys), "scope_distribution": scope_counts,
             "security_flagged_by_keyword": security_count,
             "answerable_by_code": "partial",
             "reason": "'fix' prefix and file-path scoping are mechanical; security flagging is a "
                       "keyword proxy on the subject line, not a verified classification"}]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
