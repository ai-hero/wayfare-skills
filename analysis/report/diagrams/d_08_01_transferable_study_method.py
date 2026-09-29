"""Diagram 8.1: what another factory can reuse from the study, and what it must replace.

Top group is factory-specific (sources and their adapters); bottom group is portable (event model,
dictionary, detectors, question bank, figures). Question counts are the evidence tiers of
Q git-only-measurability, recomputed from analysis/bank/questions.csv with the tier maps in
analysis/report/field/data.py: 55 + 52 + 88 + 155 + 26 = 376.
"""
import svg_lib as S

c = S.Canvas(1400, 900)
W = 290
xs = [76, 396, 716, 1036]

c.group(40, 40, 1320, 290, "Factory-specific: replace these per factory")
git = c.node(xs[0], 85, W, 110, "record", "Git, pull requests, CI", "answers 55 of 376 questions alone")
logs = c.node(xs[1], 85, W, 110, "record", "Harness session logs", "52 more need these")
own = c.node(xs[2], 85, W, 110, "record", "Factory-owned records", "88 more need work items and goals; 155 the rest")
human = c.node(xs[3], 85, W, 110, "evidence", "Live system or a person", "26 rest on the owner's judgement")
ad = [c.node(x, 240, W, 60, "policy", "Adapter", None) for x in xs[:3]]

c.group(40, 410, 1320, 370, "Portable: reuse unchanged")
PW = 240
px = [76, 412, 748, 1084]
events = c.node(px[0], 455, PW, 110, "record", "Canonical event model", "one time-stamped event per change")
detectors = c.node(px[1], 455, PW, 110, "check", "Shared detectors", "ten: change sets, drift, lag, chains")
bank = c.node(px[2], 455, PW, 110, "record", "Question bank", "376 questions, each named")
figures = c.node(px[3], 455, PW, 110, "evidence", "Figures", "each cited to its question")
dictionary = c.node(362, 610, 340, 140, "policy", "Measurement dictionary",
                    "unit, population, interval, human-involvement rule, cost basis, quality proxy")

for src, a in zip((git, logs, own), ad):
    c.arrow(src, a, "flow")
c.arrow(ad[0], (221, 455), "flow", "events", ports=("bottom", "top"), label_at=0.5)
c.arrow(ad[1], (265, 455), "flow", via=((541, 350), (265, 350)), ports=("bottom", "top"))
c.arrow(ad[2], (305, 455), "flow", via=((861, 370), (305, 370)), ports=("bottom", "top"))
c.arrow(human, (900, 455), "flow", "answers", via=((1181, 390), (900, 390)), ports=("bottom", "top"), label_at=0.55)
c.arrow(events, detectors, "flow", "events")
c.arrow(detectors, bank, "flow", "measures")
c.arrow(bank, figures, "flow", "answers")
c.arrow(dictionary, detectors, "dependency", "defines", label_at=0.35, label_dy=0)

c.legend(40, 810, kinds=("record", "policy", "check", "evidence"), arrows=("flow", "dependency"), cols=6, cell=215)

S.finish(
    c, id="8.1", name="diagram-08-01-transferable-study-method",
    caption="Another factory swaps the four sources and their adapters and keeps everything below the line: the "
            "event model, the detectors, the dictionary that fixes each number's definition, and the questions.",
    alt="Two groups. The factory-specific group holds four sources: Git, pull requests and CI; harness session "
        "logs; factory-owned records; and live-system or human evidence, with an adapter under each of the first "
        "three. They feed the portable group: a canonical event model, shared detectors, the question bank and "
        "figures, with a measurement dictionary defining the detectors. Labels give how many of the 376 questions "
        "each source tier answers.",
    source="Replaces D09 WHAT ANOTHER FACTORY WOULD REUSE. Counts from Q git-only-measurability (376 questions: 55 "
           "git and GitHub, 52 plus transcripts, 88 plus work items and goals, 155 plus the factory's other "
           "records, 26 owner's judgement only), recomputed from analysis/bank/questions.csv with the tier maps in "
           "analysis/report/field/data.py; ten detectors D1 to D10 from the same file. Dictionary fields from "
           "Chapter 8, 'What to study next'.",
)
