"""Q19.xx / RQ-h7-021 -- How reproducible are the study's model-assigned
labels if a second classifier or rater runs the same prompts? Human/
methodology question: this repo's Haiku classifiers (d1_changesets,
d_prompt_kind) cache by content hash and log the raw model output, which
is what a second-rater re-run would diff against, but running that
second pass and scoring agreement is not done here.
"""
RQ_ID = "RQ-h7-021"
QUESTION = "How reproducible are the study's model-assigned labels if a second classifier or rater runs the same prompts?"


def answer(con):
    n_cached = con.execute("SELECT COUNT(*) AS n FROM detectors.prompt_kind").fetchone()["n"]
    n_changesets = con.execute("SELECT COUNT(*) AS n FROM detectors.cs_units").fetchone()["n"]
    return [{"haiku_labeled_prompts": n_cached, "haiku_labeled_changesets": n_changesets,
             "answerable_by_code": False,
             "reason": "labels are cached by content hash so a re-run and agreement score is "
                       "mechanically possible, but no second pass or inter-rater agreement metric "
                       "has been computed here; this needs a human to run and score it"}]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)
