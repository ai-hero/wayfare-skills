"""Q12.xx / NEW-A-11 -- Does the fleet map say what each repo role must
contain (pre-commit, CI workflows, etc)? Checked directly against FLEET.md
text: whether the `## Groups` section's prose names concrete file/artifact
requirements (vs just describing the group in general terms).
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest.fleet import FLEET_MAP

RQ_ID = "NEW-A-11"
QUESTION = "Does the fleet map say what each repo role must contain (pre-commit, CI workflows, etc)?"

ARTIFACT_WORDS = re.compile(r"pre-commit|workflow|CI|\.gitignore|dependabot|Dockerfile", re.I)


def answer(con=None):
    text = open(FLEET_MAP).read()
    m = re.search(r"## Groups\n(.*?)(\n## |\Z)", text, re.S)
    if not m:
        return [{"note": "no ## Groups section in FLEET.md"}]
    groups_text = m.group(1)
    return [{"names_concrete_artifacts": bool(ARTIFACT_WORDS.search(groups_text)),
             "groups_section_chars": len(groups_text)}]


if __name__ == "__main__":
    for row in answer():
        print(row)
