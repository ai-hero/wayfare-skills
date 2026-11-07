"""Q12.xx / NEW-A-08 -- Does the factory keep a fleet map naming every repo
and its role? FLEET.md lives in the register checkout at .fleet/FLEET.md
(ingest.fleet.FLEET_MAP), not per-repo, so this is a straight filesystem check
plus the role vocabulary git.repos already has.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest.fleet import FLEET_MAP, FLEET_REPOS

RQ_ID = "NEW-A-08"
QUESTION = "Does the factory keep a fleet map naming every repo and its role?"


def answer(con):
    fleet_md = FLEET_MAP
    roles = con.execute("SELECT repo, role FROM git.repos").fetchall()
    return [{
        "fleet_md_exists": os.path.exists(fleet_md),
        "fleet_md_path": fleet_md,
        "repos_in_fleet_md_group": len(FLEET_REPOS),
        "repos_with_a_role_in_git_repos": len(roles),
    }]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
