"""4.1 The logical unit of work: commits nest in change sets, change sets in pull requests and work items, and
related work items in a goal. Counts are from the final grouping (detectors.cs_units, cs_sets, cs_agreement)."""
import svg_lib as S

c = S.Canvas(1400, 700)

c.group(40, 40, 1320, 560, "Goal · a deployable unit of intent · median 3 work items, finished in a median 1 day",
        stroke=S.GREY_DARK)

# One pull request carrying two work items, each one change set.
c.group(70, 90, 830, 470, "Pull request · 78% hold one change set; 2.8 on skills alone, 1.3 with items, 1.2 in goals")
c.group(100, 140, 500, 390, "Work item · 2.04 change sets on average")
c.group(120, 190, 460, 320, "Change set · 1.70 commits on average", stroke=S.TEAL, fill=S.TEAL_TINT)
impl = c.node(150, 250, 160, 90, "record", "Commit", "the implementation")
test = c.node(340, 250, 160, 90, "record", "Commit", "its tests")
fix = c.node(245, 390, 160, 90, "record", "Commit", "a review correction")
c.arrow(impl, test, "flow")
c.arrow(test, fix, "flow", via=((420, 435),), ports=("bottom", "right"))
c.text(140, 480, "one coherent change, saved in several steps", size=S.SMALL, color=S.BODY)

c.group(640, 140, 230, 390, "Work item")
c.group(660, 190, 190, 320, "Change set", stroke=S.TEAL, fill=S.TEAL_TINT)
one = c.node(675, 300, 160, 90, "record", "Commit", "one save point")
c.text(670, 480, "1 commit, 1 change set", size=S.SMALL, color=S.BODY)

# A second pull request in the same goal.
c.group(940, 90, 390, 470, "Pull request · 22% hold several")
c.group(970, 140, 330, 390, "Work item")
c.group(990, 190, 290, 140, "Change set", stroke=S.TEAL, fill=S.TEAL_TINT)
a = c.node(1050, 230, 170, 80, "record", "Commit", "a thing")
c.group(990, 360, 290, 150, "Change set", stroke=S.TEAL, fill=S.TEAL_TINT)
b = c.node(1050, 410, 170, 80, "record", "Commit", "an unrelated thing")
c.text(990, 538, "several change sets: mixing, not size", size=S.SMALL, color=S.BODY)

c.text(40, 620, "On main after a squash merge: one commit per pull request. Since July, main shows 1,602 commits; "
       "the pull requests held 3,474 commits, grouped into 2,189 change sets.", size=S.SMALL, color=S.BODY, width=1320)

S.finish(
    c, id="4.1", name="diagram-04-01-logical-unit-of-work",
    caption="A commit is how the work was saved; a change set is what the work was, with its implementation, tests and "
            "review corrections together; pull requests and work items package change sets, and a goal groups the "
            "related items.",
    alt="Nested boxes. An outer box labelled goal holds two pull requests. The first holds two work items: one "
        "whose change set contains three commits (the implementation, its tests, a review correction) and one whose "
        "change set is a single commit. The second pull request holds one work item with two change sets, each one "
        "commit, labelled a thing and an unrelated thing. A note below says main after a squash merge shows one "
        "commit per pull request.",
    source="Replaces D26 THE UNIT OF WORK · 1 OF 3 · ANSWER. Commits per change set 1.70 (mean over 2,509 "
           "non-Dependabot change sets), 78% of 1,465 PRs hold one change set and 22% several: detectors.sqlite "
           "cs_units and cs_sets through record.changeset_facts, queried 28 Sep 2026 (the chapter's 1.64 predates "
           "the final grouping). Change sets per PR by stage 2.8, 1.3, 1.2: Q change-sets-per-pr. 2.04 change sets "
           "per work item: Q commits-per-change-set. Goal median 3 items, median 1 day: Q goal-duration-and-scope. "
           "1,602 / 3,474 / 2,189 since July: Q counting-units-compared. Rater agreement: a second rater matched "
           "the change-set count on 68% of 108 PRs and agreed on 87% of commit pairs (cs_agreement).",
)
