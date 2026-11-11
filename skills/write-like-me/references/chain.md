# The chain: what the piece says, in order

A piece can keep every fact, sound like him, and still not say what he meant to
say. That happens when it is written outward from the facts. The fix is to agree
three things with him before drafting, write from them, and hold the draft to
them afterwards.

## Three things to agree before drafting

**The main point.** One sentence: what he wants the reader to leave with. It is
often a way of thinking about a problem, and not a finding.

**The outline.** The parts in order, nested when the piece has sections inside
sections.

**The chain.** One sentence for each lowest-level part of the outline, in
reading order, where each sentence follows from the one before it. That includes
the places where the next part sits under a different heading. Read top to
bottom, the chain is the story. The outline says which parts exist. The chain
says what each part tells the reader and why the next part comes next.

If he gave a brief, an outline or notes on the order, those are his. Restate
them as a chain; do not replace them. Where the material does not answer, ask
the question open instead of guessing. Show him all three and ask whether this
is his story, every time, before drafting. A short piece has a short chain
(three sentences for an email is normal), and you still show it.

Do not read the main point off where the words went, and do not read the outline
off the headings of an existing draft. Both tell you where the draft ended up,
not what he meant.

## The usual path

The same path tends to repeat at every level of a piece:

1. the background,
2. the problem,
3. how it is done today, and what is wrong with that,
4. how he thinks about solving it,
5. the solution,
6. what the reader takes away.

An example inside the piece follows it too: the job to be done, how it is done
today, how each step was matched to a solution, and the solution. This is a
check and not a template. If a level skips a step, ask him whether he meant to.

## Place the facts on the chain

Go through the facts list and put each fact under the sentence of the chain it
supports. A fact that supports no sentence stays out of the piece. Name it in
the closing note as left out, so nothing disappears without him knowing, and
nothing is squeezed in just because it was in the notes.

When many facts pile up under one sentence, that part is about to take over the
piece. Keep the ones the sentence needs. The others go to a table, a link, or
the left-out list.

## Writing from the chain

- Each part picks up where the last one ended, delivers its sentence early, and
  ends ready for the next part.
- Length follows the job the part has in the chain, not how much material there
  is for it.
- A side trip (rules, setup, caveats) that runs longer than a paragraph either
  has its own sentence in the chain or moves to a link or a note.
- A heading names the job its part has in the chain, in the reader's words. It
  does not name a detail of the solution.
- The format file gives the shape inside the chain. Where the two disagree, the
  chain wins.

## Check the draft against the chain

Do this from the draft alone, without looking at the chain:

1. Write one sentence for each section, saying what that section tells the
   reader.
2. Read those sentences in order.
3. Compare them with the chain he agreed.

Where they differ, the draft drifted. Fix the draft, not the chain. If you now
think the chain was wrong, ask him.

Other signs of drift:

- The part with the most words is not the part the chain says matters most.
- The headings, read on their own, tell a different story from the chain.
- A section ends on a caveat or a detail instead of leading to the next one.
- The piece stops without the last sentence of the chain.

## An example of drift

He asked for a blog post on small models in healthcare. His chain:

1. A lot of healthcare work is paperwork jobs.
2. People do those jobs today by reading page by page, and that is slow.
3. Other teams are already using open models on jobs like these.
4. Here is how to think about it: take a job, break it into steps, decide
   whether it should run as a fixed workflow, an agent loop or a mix of the two,
   and work out which steps that code can do and which need a model trained for
   that one task.
5. First example: the job, how it runs today, whether it runs as a workflow, an
   agent loop or a mix, which steps went to a small model, and the result.
6. Second example, told the same way.
7. So you can think about your own workflows this way.

The draft kept every fact and had most of the parts. Read section by section
from the draft alone, it told a narrower story: how the code checks what the
model read, and how patient data stays inside your network. Those were details
of the solution, and they had taken over. The signs were all there. Sentence 2
had two lines and the compliance rules had half a section. Sentence 4 was told
as "does this need a model at all" and never as a way to split the steps. Both
examples gave the split as a table and spent their words on how strong each
check was. The post ended on run instructions, without sentence 7.

The first chain he gave left out most of sentence 4 (the split between code and
model, and the choice between a workflow and an agent loop), and he added both
when he saw the chain written down. That is what showing it to him is for.

## Re-chaining a draft

Two common cases. An agent writes something in the conversation and he says
"don't forget to write-like-me". Or he hands over a draft, pasted or as a link,
and says "write this blog like me" or "rewrite this in my voice". Either way the
draft gets re-chained, not only cleaned up.

- The draft is AI output, not his text. The smallest-change rules do not protect
  it.
- Take the chain from him, not from the draft. Look back through the
  conversation for what he asked for: the brief, the order he gave, every
  correction since. Write the chain from those, in his words where you can.
- Show him that chain with the main point and the outline, and mark each
  sentence you had to work out yourself because he never said it. Those are the
  ones he needs to look at.
- Then check the draft against the chain, section by section, and rewrite from
  the chain. A part the chain needs and the draft lacks is written from the
  facts if they are there; if they are not, it becomes a question to him, never
  a guess.
- A part the draft has and the chain does not is left out and named in the
  closing note.

If there is no brief, as when he only hands over a draft, propose a chain. Lay
the draft's material onto the usual path above, write the chain that path gives,
and say plainly that it is your proposal and not his words. Name the steps of
the path the draft has nothing for, because those are usually what the draft is
missing. Do not take the story the draft happens to tell and present it as his.
Then ask, and rewrite once he has corrected it.

## Text that already exists

This is for text he wrote or has approved. Agree the same three things first.
Then compare the text against the chain and tell him where it leaves it. Fix the
smallest thing that restores the chain: a connecting sentence, a heading, a
paragraph cut back to what its part needs. Anything larger (moving a section,
rewriting a part) is a proposal, and it waits for his answer.
