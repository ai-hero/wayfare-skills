# What makes writing sound machine-made

Adapted from Wikipedia's "Signs of AI writing" (WikiProject AI Cleanup) and the
blader/humanizer project. The underlying reason for all of it: a language model
guesses the most statistically likely next thing, so the output drifts toward
what would fit the widest number of cases. The fix is always the same. Say the
specific thing this writer would say to this reader.

Look for clusters. One pattern alone is not a tell. Several together is.

## Made-up words and abstractions

This one comes first because it is the one Rahul hates most.

**Invented terminology.** A plain idea given a coined name so it sounds like a
framework: "the ceiling", "a gate", "the autonomy gradient", "the trust
surface", "the record", "records". Ask: would a colleague use this word at a
whiteboard? If not, say what it actually is.

**Abstract compressions.** A concrete action squeezed into a noun phrase:
"translate intent", "changes must enter its record", "the human layer". Unpack
it. Who does what, and then what happens.

**Formulaic sayings.** "X is the language of Y", "the currency of", "the
architecture of", "X becomes a trap", "X is not a tool but a mirror". Replace
with the plain claim underneath.

**Pretending to reveal a deeper truth.** "The real question is", "at its core",
"what really matters", "fundamentally", "the heart of the matter". The sentence
that follows is usually an ordinary point with extra ceremony. Make the point.

## Scenes and names the reader was never given

A draft written from notes refers to things the notes knew and the reader
doesn't. Each of these made Rahul stop and ask "what are you talking about?"

**A general situation told as a past event.** "The referring office had the
patient's name, date of birth and insurance in its own EHR; faxing turned it
into an image" reads like the middle of a story nobody started. A general
situation is present tense: "When a doctor's office refers a patient, it usually
has the patient's name, date of birth and insurance in its own EHR. Faxing turns
all of that into an image." A hypothetical starts as one: "Say your card
processor has a latency spike."

**"The" for something never introduced.** "The warehouse", "the register", "the
analyst", "the queue", "the check" on first mention. Introduce it with "a" and
say what it is, or name the system the reader knows ("the EHR").

**An example that doesn't say it's an example.** "The first job is in a
cardiology practice that gets new-patient referrals from primary-care offices it
doesn't share an EHR with" starts mid-scene and packs three ideas into the first
sentence. Open plainly and keep the first sentence short: "As an example,
consider a cardiology practice that gets referrals for new patients." The
details come next, one idea per sentence.

**Two names for one thing.** Once a worked case is "an example", it stays "the
referral example" or "both examples below", never "the first job" or "the first
one" three paragraphs later. Pick the name at the introduction and keep it.

**A figure of speech in place of what happens.** "Take the names out before it
leaves the building" (nothing leaves a building; the notes go to a research
team), "down the hall", "a patient on nobody's list". Say who gets what: "read
every note to hide the patient's personal details before the research team
analyzes them."

**Shorthand for steps the reader needs named.** "What's left after the lookups
is usually a narrow read" makes the reader reconstruct the steps. Name them:
"That leaves two things for a model to do: turning the fax pages into text, and
finding the personal details in a note so they can be hidden."

The test for all of these: could a reader who skipped every earlier paragraph
point at the thing the sentence means? If not, introduce it or name it.

## Inflation

**Importance inflation.** "stands as a testament", "a pivotal moment",
"underscores the significance", "reflects a broader shift", "setting the stage
for", "evolving landscape", "indelible mark". Ordinary facts dressed up as
historic. State the fact.

**Sales language.** "boasts", "vibrant", "rich" (figurative), "profound",
"groundbreaking", "seamless", "robust", "powerful", "commitment to excellence".
Reads like an ad.

**Trailing -ing phrases.** "..., highlighting the importance of", "..., ensuring
that", "..., fostering a culture of", "..., showcasing". A participle tacked on
to make a flat sentence sound deep. Cut it or make it a real sentence with a
subject.

**Vague sources.** "experts argue", "industry reports suggest", "observers have
noted", "some critics say". Name the source or drop the claim. Never invent one.

**Generic upbeat endings.** "The future looks bright." "Exciting times lie
ahead." "This is just the beginning." End on the last concrete thing, or on the
format's normal closing.

## Word-level habits

<!-- check-docs: off -->

**The overused list.** actually, additionally, align with, crucial, delve,
elevate, emphasize, enduring, enhance, foster, garner, highlight (verb),
interplay, intricate, key (adjective), landscape (abstract), leverage (verb),
load-bearing, navigate (figurative), pivotal, robust, seamless, showcase,
tapestry, testament, underscore (verb), unlock, utilize, valuable, vibrant. One
is fine. A cluster is the tell.

<!-- check-docs: on -->

**Avoiding "is".** "serves as", "stands as", "represents", "marks", "features",
"offers", "boasts" in place of is, has, does. Use the simple verb.

**"Not X but Y."** "It's not just about speed, it's about trust." "Not only...
but also..." And the clipped negative tail: "..., no guessing." Write the actual
clause. Watch for the same move reworded: "X matters less than Y", "X is a Y
decision, not a Z afterthought".

**Groups of three.** Ideas padded or trimmed to three for rhythm. Use the real
number.

**Synonym cycling.** The protagonist, the main character, the central figure,
the hero, all for one person. One clear name.

**Fake ranges.** "from the Big Bang to the cosmic web", "from startups to
enterprises" where the two ends are not on a scale. List the items.

**Hyphen everywhere.** Keep the hyphen before a noun ("a high-quality report");
drop it after ("the report is high quality").

**Passive voice with no actor.** "The results are preserved automatically." "No
configuration needed." Say who does it.

**Too many qualifiers.** "could potentially possibly be argued that it might
have some effect" is "may affect".

**Filler.** "In order to" is "to". "Due to the fact that" is "because". "At this
point in time" is "now". "Has the ability to" is "can". "It is important to note
that" is deleted, except when Rahul wrote "It is important to note here that",
which is his own phrase and stays.

## Structure habits

**Throat-clearing openers.** "So,", "Now,", "Well,", "Okay,", "Look," at the
start of a sentence or a piece. Cut the word; the sentence is more confident
without it.

**Announcing instead of doing.** "Let's dive in", "here's what you need to
know", "without further ado", "let's break this down". State the point.

**Fake-candid openers.** "Honestly?", "Here's the thing", "Real talk", "Let's be
honest" as a staged pause before a routine claim. A person being honest just
says the thing.

**Heading, then a sentence restating the heading.** Cut the sentence.

**Stock sections.** "Challenges and Future Outlook", "Key Takeaways", "Despite
these challenges, X continues to thrive." Replace with specific facts or cut.

**Bold-label bullet lists.** Every bullet starting with a bold phrase and a
colon. Merge into prose unless the labels are a real form (Rahul's Pro-tips are
a form; a generic feature list is not).

**Mechanical bold.** Bolding phrases for no reason. Bold goes on an aside label
or the one sentence to remember, if anywhere.

**Rows of short dramatic fragments.** "No aesthetic prior. No nostalgia. The old
rules were gone." One short sentence lands a point. A wall of them sounds
engineered.

**Answering objections nobody raised.** "This isn't about X", "To be clear",
"Don't get me wrong", "Some might say... but" when the objection appears nowhere
else. Remove the defense; keep the claim.

**Knocking down fake alternatives.** "A tempting approach would be...", "You
might think... but" introducing an option nobody would pick and dismissing it in
a clause. Usually a drafting leftover. State the real constraint. Keep real
alternatives a reader would weigh.

**Writing about the previous version.** "This replaces the old approach that..."
in documentation that should describe how the thing works now. Only change logs
and migration guides narrate changes.

**Logs posing as examples.** PR numbers, commit hashes, UTC timestamps, and
every intermediate step, included to prove that something happened. An example
keeps the situation, the decision that mattered, and the lesson. Supporting
detail goes in a figure or a footnote, not the narrative.

## Chatbot leftovers

<!-- check-docs: off -->

"I hope this helps." "Certainly!" "Great question!" "You're absolutely right."
"Would you like me to...?" "Let me know if..." "Here is a..." "As of my last
update." "While specific details are limited..." followed by a plausible guess.
Remove all of it. Where the source does not say something, say it is not known
or cut the sentence; never dress a guess up as fact.

<!-- check-docs: on -->

## Punctuation and marks

**Em and en dashes.** The most reliable single tell. Default for business
writing and LinkedIn: none. Replace with a period, a comma, a colon,
parentheses, or a rewrite. In blog posts, Rahul uses a spaced em dash
occasionally; a couple per piece is his rate, not one per paragraph.

**Title Case headings.** Rahul uses Title Case in blog and book headings as
house style, so it is not a tell in his work. Sentence case in business
documents.

**Emoji.** None, except Rahul's one or two per thousand words in blog captions
and sign-offs.

**Curly quotes.** Straight quotes unless the publishing tool curls them.

**Exclamation marks.** One in a blog sign-off is fine. None in business writing.

## What not to flag

None of these is evidence on its own:

- Perfect grammar and consistent style. Professionals get edited.
- Mixed casual and formal registers in one piece.
- Dry or plain prose without the specific tells above.
- Formal words that are not on the overused list. Do not flatten "ostensibly"
  because it sounds brainy.
- One transition word ("however", "additionally") on its own.
- A single em dash. A single short emphatic sentence.
- Deliberate repeated openings ("She came. She saw. She conquered.").
- "Honestly" or "look" in the middle of a sentence.
- Useful limits and scope statements, safety notices, named objections, FAQ
  answers.
- Real alternatives a reader would actually consider.
- A contrast or a "tempting" option in a sentence he already wrote or approved.
  He writes both naturally. "When editing something Rahul already wrote" in
  `SKILL.md` has the rule.
- Any phrase he has confirmed as his. His own examples beat this list.
- Unsourced claims. Most of the web is unsourced.
- Text inside quotations, titles, proper names, or phrases being discussed
  rather than used.
- Anything written before November 30, 2022.

## Human details to keep

These are what make writing sound like a person. Keep them unless they damage
the meaning.

- Specific, unusual, hard-to-fabricate details. "The lawyer who used to work
  upstairs from my dentist."
- Mixed feelings and unresolved tension. "I think this is mostly good, but it
  bothers me, and I can't fully explain why."
- Dated references: slang, memes, in-jokes that pin the writing to a year.
- First-person choices the writer could defend if asked.
- Variety in sentence length. Real writing alternates. Machine writing drifts to
  an even medium.
- Real asides, parentheticals, and self-corrections. "(I keep wanting to say
  'almost' here, but it really was certain.)"
- Confident observations from experience, even blunt ones.
- Humor that rests on something true in the material.
