# Format: book chapter or long manuscript

This is the default when nothing else is specified. The reference is Rahul's
software factory book: a practitioner explaining the system he built, how it
works, and what he learned, to a peer who might build one too. If the manuscript
is reachable (look for a `chapters/` or `manuscript/` folder, or `.md` files
with chapter numbers, in the working folder or the repo), read one chapter
before writing. Chapter Four was his approved calibration for examples; Chapter
One for the overall voice. The live text beats anything in this file.

## Who reads it and what they get

An engineering leader, a senior engineer, or a founder who is deciding whether
and how to let agents do real software work. They are smart and skeptical. They
want to know what he actually did, what happened, what broke, and what he would
do differently. They do not want a methodology paper.

## Shape

Chapters open with the argument or the situation, not with context-setting. The
lead-then-roadmap move from his blog applies at chapter scale: say what the
chapter argues and what the sections will cover, then deliver it. Sections are
headed in Title Case with headings that say what the section is about (see
Titles in `voice.md`). Figures, tables and diagrams carry the supporting
evidence so the prose can stay focused on the point.

Within a section: the practical situation first (who does what, what happens
next), then the mechanism in plain words, then the example or evidence, then the
lesson or his opinion on it. Technical tables and figures stay as they are; the
narrative around them gets simplified.

## Examples make one point

This was his explicit instruction on 18 October 2026, and he approved Chapter
Four as the model. An example in the book is there to make one point. Keep the
concrete situation, the behavior or decision that matters, and the lesson. Use a
number when it helps make that point. Leave out pull request numbers, UTC times,
commit hashes, and the intermediate steps that only prove something happened.
Supporting detail stays available in the figures and evidence; it does not go in
the narrative.

Before: "At 14:32 UTC the agent opened PR #412, which failed the conformance
check on the second run after the first run passed; the reviewer flagged this in
a comment at 15:07 and the agent pushed a fix in commit 3fa9c..."

After: "The agent's change passed the checks the first time and failed the
second. Nothing in the code had changed between runs. That is how we found out
one of the checks depended on the order the tests ran in, and it is why every
check now runs in isolation."

The "In This Factory" boxes follow the same rule.

## Terminology

The book has settled vocabulary: factory, fleet, agents, guides, sensors, work
items, goals, conformance, the five flows. These are his terms with precise
meanings, not AI jargon. Keep them consistent. Do not rename them, and do not
replace them with vaguer words to avoid repetition. The first use in a chapter
gets a short plain-language explanation.

The distinction he drew between "records" (the material used in the analysis)
and "account" (the narrative) stays where the analysis paragraph uses it. But do
not compress ordinary actions into abstractions about "the record"; say what the
person or agent does.

## Limits, opinions, and first person

The book is his informed opinion, and he says so. State limits in his words: "I
do not claim this as scientific proof", "Treat this as an informed opinion",
"I'm going from memory here." Not "this is not a causal before-and-after result"
and not "one contribution of the case is therefore methodological." Keep his
confident engineering observations and his humor ("After all, how many factories
does one need to build?"), and when writing new book text, give each section at
least one dry line drawn from the material, usually the moment the system did
something a bit absurd or the moment he admits what he got wrong. Do not add
first-person recollections he did not supply.

## Marks

Title Case headings. Parentheses for "(e.g. ...)" and caveats. No emoji. Em
dashes rare; a spaced one at most once or twice a chapter. Bold only on a term
being defined the first time, if at all. No bullet lists with bold labels in the
narrative; lists of steps or options are fine when the content is actually a
list.

## When editing existing chapters

Follow the "before changing a sentence he wrote" rules in `voice.md` strictly.
The book went through a sentence-by-sentence voice restoration in October 2026
and he has approved large parts of it. Treat approved text as settled. Apply
changes to new framing and transitions; do not rewrite working passages for
consistency. Flag unusual-but-clear sentences instead of changing them.
