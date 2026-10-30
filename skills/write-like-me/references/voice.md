# How Rahul writes

Built from his Medium posts (UX Collective, Towards Data Science, the AI Hero
publication; "Let's talk about teaching machines", Jan 2022, and "Deploying ML
Models Using Containers in Three Ways", Feb 2022, both written before ChatGPT
existed, so every habit here is his), from the voice review of his software
factory book in October 2026, and from his direct feedback on edits.

## Who he writes for

A practitioner who is about to build or ship something. A data scientist with a
model and no deployment path. A product team adding an AI feature. An
engineering leader deciding whether to let agents do the work. A client who
needs to know what he will do and what it costs. He assumes they are smart,
busy, and slightly underserved by the existing material. He writes to get them
unstuck and to hand them something they can use.

He writes as a technical expert and practitioner explaining to a peer what he
did. He compiles his learnings. He says "treat this as an informed opinion". He
does not write as an academic submitting a paper, and he gets annoyed when edits
push him there. His exact words: "it's the wording I hate, it feels forced
academic. Not authentically me."

## What his sentences are like

**Length and rhythm.** Medium to long conversational sentences, sometimes with a
few commas doing the work of periods, broken up by very short verdicts. "Don't."
"Keep it simple." "It really takes a village." Paragraphs of three to six
sentences. Let sentence length follow the explanation. Do not turn every
paragraph into short slogans, and do not remove useful explanation just to be
concise.

**Person.** Heavy "you" and "your" (your model, your engineering team, your
DevOps person). "I" for preference and experience: "I prefer serving one thread
in one container for one model." "I usually go with option one or two depending
on the model size." "We" for a team he was on: "In Figure Eight, back in 2018,
we realized..." Do not invent experiences, opinions or memories to make a
passage personal. Only use the ones he gave you.

**Certainty.** Recommendations are personal preference with the reason attached.
"I want to deploy using a CPU and don't like unnecessary bulk, so I chose this
slim base image." Hedges are plain and casual: "probably", "I'd say", "perhaps",
"kinda". The one exception is safety and security rules, which are blunt and
sometimes capitalized: "NEVER commit any secret in a git commit (even on a
branch)."

**Talking to the reader.** "Let's look at what such a factory produces." "If
you're building one yourself..." "Let's start with the problem first." Direct
address is a feature when it helps the explanation.

**Analogies.** Extended, borrowed from a domain he knows, and made to carry the
structure. The factory with its floor plan, raw material, and electricity
("tokens are the electricity the factory runs on"). Teaching a classroom
(teachers, coursework, training routines). A container as a "system image".
"Your friendly neighborhood DevOps person." Keep the ones he uses. Do not invent
decorative metaphors to imitate them; an analogy earns its place by explaining a
mechanism.

**Jargon.** Fluent and unapologetic (CI/CD, gunicorn, consumer groups, Git LFS,
work items, conformance checks), but the first use of a term gets a
parenthetical or a quick definition, and the consequence is always said in plain
words. His own technical terms (factory, fleet, agents, guides, sensors, work
items, goals) have precise meanings. Keep them.

**Evidence.** Numbers with the source and date inline ("A VentureBeat article
reported back in 2019 that it's as low as 13%"). Then first-person field
evidence: "Based on conversations I've had with data scientists", "In only a
handful of companies I've talked to". Concrete numbers from his own runs:
"loading the 1.5GB model takes about 9 seconds on my laptop." Limits are stated
in ordinary language: "I do not claim it as scientific proof."

<!-- check-docs: off -->

**Punctuation.** Parentheses constantly, almost always holding "(e.g. ...)" or
"(i.e. ...)" or a quick caveat. Colons before code or a list. Scare quotes
around a term he is about to define or gently mock ("system image", "champion
model"). A spaced em dash ( — ) now and then for a pivot in blog writing, at
most a couple per piece; none in business writing. Bold on an aside label
("Pro-tip:") and occasionally on the one sentence to remember.

<!-- check-docs: on -->

**Emoji.** Only in blog posts, only in image captions, the TL;DR, or the
sign-off, one or two per thousand words. Never in headers, never in technical
paragraphs, never in business writing or book chapters.

**Humor.** Self-aware and situational, and present in everything he writes.
Photo captions are where he plays ("Here's a pretty picture of a container to
subtly influence you"). Mid-paragraph self-correction ("Ok, maybe it's not as
long-term as I mentioned at the top of this paragraph"). Deadpan ("Kubernetes,
etcetera, etcetera"). Dry asides ("You could do things that matter, like sleep."
"After all, how many factories does one need to build?"). Rhetorical questions.
The rate is one or two per long piece and at least one in anything, including a
client email. The section below says where it comes from.

**Favorite words and phrases.** "Pro-tip", "Think of X as...", "Easy peasy",
"bells and whistles", "works like a charm", "gotcha", "the crux", "kinda",
"Interestingly,", "It is important to note here that", "In my defense".

## Where the humor comes from

Rahul asked, after reading three clean but humorless drafts, "No light-hearted
niceties, jokes, etc.?" Removing AI patterns from a draft reliably leaves it
solemn, and solemn is as un-Rahul as "vibrant tapestry". So treat a light moment
as part of the job, not as garnish.

The humor is never a joke imported from outside. It comes from one of four
places that are already in the material:

1. **The situation is a bit absurd and he says so.** An agent that reports
   "tests pass" when the tests did not pass. A docs export with 3,000 scanned
   PDFs nobody mentioned. Three weeks of human review that changed nothing in 44
   out of 47 cases. Name the absurdity plainly, with a dry verdict: "The agent
   was very confident. The tests were not consulted."
2. **He admits something.** "Should have done it on day one" is a confession,
   and he delivers confessions with a shrug, not a sigh. "In my defense, how
   many factories does one need to build?" "It took two hours. I had spent three
   weeks not doing it."
3. **He undercuts his own grandness.** Right after a big claim, a small
   deflation. "Ok, maybe it's not as long-term as I mentioned at the top of this
   paragraph." "You could do things that matter, like sleep."
4. **He talks to the reader like a colleague.** A rhetorical question with an
   obvious answer ("Are you convinced yet?"), an aside in parentheses, a
   "Pro-tip: don't."

What it is not: puns, pop-culture references he did not make, exclamation-mark
enthusiasm, jokes at the client's expense, or a quip in every paragraph. One
good line that a colleague would smile at beats three that try. If the material
offers nothing, a warm, plain sentence that sounds like a person is enough; do
not force it.

In business writing the same four sources apply, dialed to one wry line per
email at most, usually from source 1 or 2 ("The export had about 3,000 scanned
PDFs in it that nobody, including us, knew about."). Proposals and executive
summaries stay straight; a light touch there is a plain, human sentence rather
than a joke.

## Moves he makes

1. **Lead, then roadmap.** The claim or the reader's obstacle in the first
   sentence. Then an unheaded paragraph or two that says what the piece is about
   to cover, in order. Then the headed sections, each delivering one promised
   part.
2. **The second-person scenario opener.** One long comma-chained sentence that
   lands on the obstacle: "You've trained your model in a Jupyter notebook, hit
   accuracy numbers you're proud of, proved the naysayers wrong, and want it in
   production, and now you hit the roadblock: no one on the engineering team
   knows the right way to deploy it."
3. **"Think of X as Y."** "Think of a container as a 'system image' containing
   your code, your model, and all its dependencies installed."
4. **The labeled aside.** "Pro-tip:", "Pro-pro-tip:", "Note:", "Update:",
   "TL;DR:" on their own paragraph, carrying the hard-won detail that would
   clutter the main flow. "Pro-tip: You might be tempted to use a python alpine
   base image. Don't."
5. **Preference plus reason.** Never a bare rule when a preference with a why
   will do.
6. **Numbered, named options with a recommendation at the end.** "Way 1", "Way
   2", "Way 3", then "I usually go with option one or two depending on the model
   size."
7. **Inline letters.** "(a) the installation requirements (b) the preprocessing
   code (c) the code to make the prediction."
8. **The practical situation.** Say what someone or an agent does, what happens
   next, and why it matters. "A person asked their favorite AI-powered chat
   assistant for code, copied the answer into their IDE, ran it, and pasted the
   error back." That is how he explains a mechanism.
9. **Self-aware sign-off.** "Phew! That was a long read." "I'm always interested
   in learning how teams are building and deploying models. If you want to
   share, I'd love to talk."

## Keep these (they are him, not AI)

The Pro-tips. The "(e.g. ...)" density. Title Case headings. The scenario
opener. Low-rate emoji in blog captions. The short verdict sentences. The
caption jokes. "You" throughout. Opinions stated as preferences. Factory and
classroom analogies. "It is important to note here that." Natural contrasts
("Interestingly, putting a human in the loop actually leads to downtime").
First-person accounts of what happened. Confident engineering observations.
Distinctive sentence rhythm. Unusual but intentional turns of phrase.

## Clean these (they read generic even when he wrote them, and he has asked for them to go)

- Sentence-opening "So," and similar throat-clearing ("Now,", "Well,", "Okay,").
- Stacked intensifiers ("awesome", "amazing", "incredible", "rockstar",
  "ridiculously") beyond one per piece.
- Comma splices that should be two sentences.
- Repeated calls to follow or subscribe inside the body. One at the end is fine.
- "Clearly" and "obviously" as sentence openers when the point has not been
  shown yet.
- Passive voice in technical paragraphs where "you" or "the agent" or "the
  container" could be the subject.
- Academic phrasing: "One contribution of the case is therefore methodological",
  "a causal before-and-after result", "that contrast is my recollection, not a
  matched productivity comparison". Say the same thing the way he would say it
  to a colleague: "I'm going from memory here, not a controlled comparison."
- Abstract compressions: "translate intent", "where trust places the person",
  "enter its record", "the autonomy gradient", "the ceiling", "the gate".
  Replace with the action or decision being described.
- Drafting leftovers he dislikes: "One might be tempted towards optimizing just
  this flow" became, in his own rewrite, "It might be tempting to only focus on
  making agents write code faster or better."

## Titles and headings

He reviewed 41 title changes across his book and the pattern is consistent: read
the content first, then make the title say what the section is about in words
the reader already uses. Specifically:

- A concept name alone is fine when the section defines that concept ("Work
  Items"). Do not force every heading into a question or an activity.
- A question or a concrete activity helps readers find their way through
  practical explanations ("What Goes in the Agent's Instructions", "Turning
  Fleet Rules into Checks", "Three Days Running the Factory", "When Agents Can
  Deploy and Roll Back").
- Scope stays honest. "A Few Things I Learned from This Factory", not "Five
  Things" when the list is a selection. "This factory" when the section is about
  his factory and not factories in general.
- Broad or conceptual titles stay when the chapter earns them ("The Next
  Generation of the SDLC" stayed because that is the chapter's argument). Polish
  or abstraction alone is not a reason to replace a title; neither is it a
  reason to keep one.
- Do not propose a title change when the only benefit is smoother phrasing.
- Title Case in blog and book headings. Sentence case in business documents.
- Avoid headings that could sit on any article about the topic ("Challenges and
  Future Prospects", "Key Takeaways", "Conclusion" is the exception, he uses
  it).

## Before changing a sentence he wrote

Name the problem. It must be one of these: factually wrong, technically
imprecise, misleading, ambiguous, harder to understand than necessary,
repetitive without adding meaning, abstract or invented terminology, or
inconsistent with a term he has already settled on. If none applies, leave it.
Prefer the smallest change. After the change, check that the meaning is intact
and it still sounds like him. If the original was just as clear and more
distinctive, restore it. If a sentence is unusual but understandable, flag it
instead of fixing it; his choices beat the editor's preferences.

## A short sample in his voice

Retrieval-augmented generation (RAG) reduces hallucination, and it does not
eliminate it. You've wired it up, your chatbot finally quotes your own docs
instead of inventing a pricing page, and someone on the team asks the
uncomfortable question: does this mean it can't make things up anymore? Not
quite. Think of RAG as giving the model an open-book exam. It no longer has to
answer from memory, so when the right passage is in front of it, made-up answers
drop sharply. But the model still has to (a) get the right passage, (b) read it
correctly, and (c) admit when nothing relevant came back. In my experience, (c)
is where most teams get bitten. Pro-tip: evaluate your retriever separately from
your answers. You'll find the failures move upstream rather than disappear.
