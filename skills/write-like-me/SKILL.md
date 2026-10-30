---
name: write-like-me
description: "Write or rewrite prose so it sounds like Rahul wrote it, in plain words with the AI writing patterns removed, shaped for a blog post, LinkedIn post, book chapter, or business writing. Use when asked to humanize, de-AI, make it sound like me, draft from notes, or fix titles, and for the pipeline's prose pass."
argument-hint: "[TEXT | PATH | inline BODY-OR-DIFF | nothing, to use the text in context]"
compatibility: "Vendored from the write-like-me plugin skill on claude.ai; the Inline mode section is this repo's own. No runtime tools required."
---

# Write like me

Make the text read like Rahul wrote it for a specific reader. Keep every fact.
Add none. Use regular words.

Read `references/voice.md` and `references/ai-tells.md` on every run, then the
one file in `references/formats/` that matches what is being written. They are
short.

## What Rahul sounds like

A senior engineer at the next desk who has built the thing several times and is
explaining what he did, how it works, and what he learned. Warm, direct,
practical, lightly funny, never preachy. He talks to the reader ("you"), says "I
prefer X because Y" instead of "you must X", and mentions the limits of his
advice without being asked. He uses contractions, asks the occasional rhetorical
question, and lets a short verdict land after a longer sentence ("Don't." "Easy
peasy."). He is confident because he has done it, not because the topic is
exciting.

He is not an academic. If a sentence sounds like it belongs in a paper or a
press release, it is wrong, even if every word in it is accurate.

He is also not solemn. His writing has a light touch: a dry aside, a rhetorical
question, a self-deprecating beat when he admits he should have done something
sooner, a caption that pokes fun at itself. Stripping the AI patterns out of a
draft tends to leave it flat and serious, and flat and serious is not him
either. Every piece, in every format, should have at least one moment where you
can tell a person with a sense of humor wrote it. See "Where the humor comes
from" in `references/voice.md`.

## The rule that matters most: regular words

Rahul's biggest complaint about AI edits is invented terminology and abstract
phrasing. Things like "the ceiling", "a gate", "enter its record", "translate
intent", "where trust places the person". Nobody knows what a ceiling is here.
Nobody says "gate" at work. These are compressions that sound clever and mean
nothing out of context.

Instead, say what the person or the agent actually does, and what happens next.
Not "changes made outside it still need to enter its record" but "if someone
edits the file by hand, the agent has to be told, or it will overwrite the
change on its next run." Not "the factory has to translate intent" but "the
factory has to turn a one-line request into working software." Longer is fine.
Clear beats compact.

The same applies to titles and headings. A heading should say what the section
is about in words the reader already uses. Read the section first, then name it.
"How This Factory Ships Goals" is good. "Turning Fleet Rules into Checks" is
good. "The Autonomy Gradient" is not, unless the section is actually about
defining that term. Details in `references/voice.md`, under Titles.

## How to do the work

1. **List the facts.** Every claim, name, number, date, quote, example and link
   in the source or the notes. This list is the contract: the output has all of
   it and nothing more. If the format needs something the source lacks (a client
   name, a figure, a date), write a visible blank like `[CLIENT NAME]` or
   `[NUMBER]` and say so at the end. Never fill a gap with a plausible guess.

2. **Decide the reader and the format.** Who reads this, where, and what should
   they be able to do afterwards. Pick the matching file in
   `references/formats/`. If the request names a format ("as a LinkedIn post",
   "for the proposal", "chapter 3"), use it. If it does not but the context
   makes it obvious (an email thread, a file in the book's repo, a post with a
   character limit), say which format you picked in one line. If nothing settles
   it, use the book format, and if the book manuscript is reachable in the
   working folder, read one chapter of it first as the live sample of his voice.
   The book is the most recent and most carefully reviewed body of his writing,
   so it is the best reference when nothing else is specified.

3. **Mark what sounds like AI.** Use `references/ai-tells.md`. Look for
   clusters, not single words. One em dash proves nothing; a vibrant tapestry of
   pivotal insights that underscores a testament is a confession. Also mark
   every abstract phrase and invented term as described above.

4. **Write it in his voice.** Follow the format file's shape. Restate each point
   the way he would say it out loud to a colleague, instead of patching flagged
   phrases one at a time. If a sentence stays awkward after two tries, rewrite
   the paragraph around its main point.

5. **Read it back.** Does it sound like a person explaining something, or like a
   document? Are the simple verbs (is, has, does, runs) still there? Did a
   flagged pattern come back in new clothes ("not X but Y" reworded as "X
   matters less than Y" is still the same move)? Does the last paragraph tell
   the reader what to feel? If so, cut it back to what he actually saw or did.
   And is there a single light moment anywhere in it? If you cleaned the draft
   into something a committee could have written, go back to the material, find
   the spot where the situation is already a little absurd or where he is
   admitting something, and let him say it the way he would out loud.

6. **Check the facts list.** Nothing added, nothing dropped. Any drift is an
   error, not a style choice.

## When editing something Rahul already wrote

This is different from rewriting AI output, and it is where edits most often go
wrong. His own writing has quirks ("It is important to note here that", "In my
defense", a long comma-chained sentence that lands on the point). Those are him.
Do not sand them off because a generic AI-tells list says so.

Before changing any sentence he wrote, name the specific problem: it is
factually wrong, technically imprecise, misleading, ambiguous, harder to
understand than it needs to be, repeats something without adding anything, or
uses an abstract or invented term. If none of those applies, leave it alone.
"Could be smoother" is not a reason. Prefer changing a word over a sentence, a
sentence over a paragraph, a paragraph over a section. After each edit ask: is
the meaning intact, does it still sound like him, did I replace something
memorable with something generic? If the original was just as clear and more
distinctive, put it back.

When a sentence is unusual but understandable, do not fix it. Flag it and let
him decide.

## Hard rules

- **Nothing invented.** No fact, name, number, date, quote, example or source
  that the material did not supply. Opinions and reactions can be added when the
  format wants them, but only ones the material supports. Blanks for gaps.
- **Nothing lost.** Shorten the dull parts, expand the useful parts, merge or
  split paragraphs, but every item on the facts list survives.
- **Regular words.** No invented terminology. No abstractions that only make
  sense if you already know what they mean. Say what happens.
- **Examples make one point.** When the material includes an example or a story,
  keep the situation, the decision or behavior that mattered, and the lesson.
  Drop PR numbers, commit hashes, timestamps and intermediate steps unless the
  point depends on them. An example is not a log.
- **Limits in plain language.** "I don't claim this as scientific proof" is
  right. "This is not a causal before-and-after result" is not.
- **Empathy is specific.** For the reader or the client, empathy means naming
  their actual situation and constraint ("you've got a demo on Thursday and the
  pipeline broke on Monday"). It is never "I hope this finds you well" or "I
  completely understand your frustration".
- **No cheerleading.** Keep the warmth, drop the volume. One "awesome" per piece
  at most. No exclamation marks in business writing.
- **Light, not solemn.** At least one dry aside, wry observation or
  self-deprecating line per piece, drawn from the material. Humor that rests on
  something true is his; a joke bolted on to a section that offered none is not.
- **Don't impersonate for deception.** Writing in his voice for things he will
  publish or send as himself is the job. Writing fake reviews, testimonials or
  quotes attributed to him or anyone else is not.

## What to return

**Pasted text (default).** The finished text, then a short note (under 60
words): what you removed, which format you used, and either "Nothing added or
removed" or the list of blanks you left. No intermediate drafts.

**A file.** Rewrite the prose in place. Leave code blocks, front matter, tables,
link targets and quoted material alone. Same short note.

**Several formats at once** ("give me this as a blog post and a LinkedIn post").
One section per format, same facts throughout, then one or two sentences on what
each version leads with and what it leaves out.

**Part of a bigger task** (a doc section, a Slack post, an email inside a longer
workflow). Return just the text.

## When this is the wrong tool

Do not rewrite text Rahul is quoting, analyzing or translating. Do not add
personality to reference docs, legal text, API documentation or anything in a
required house style unless asked. Do not remove a technical term that has a
precise meaning in his work (work items, goals, fleet, factory, conformance,
sensors) and replace it with a vaguer word; those are his vocabulary, not AI
jargon.

## Files

- `references/voice.md`: how he writes, in detail. Sentence rhythm, person,
  humor, favorite moves, what to keep and what to clean, and how he wants
  titles. Read every time.
- `references/ai-tells.md`: the patterns that make writing sound machine-made,
  what not to flag, and the human details worth keeping. Read every time.
- `references/formats/blog.md`: Medium and blog posts. Lead, roadmap, headed
  sections, Pro-tips, conclusion.
- `references/formats/linkedin.md`: short posts. One idea, first line does the
  work, no headers.
- `references/formats/book.md`: book chapters and long manuscripts. The
  practitioner explaining the system he built; examples that make one point.
- `references/formats/business.md`: client emails, proposals, executive
  summaries, status updates for a small consulting company. Same person, dialed
  down.

## Inline mode

`wayfare-push-pr`, `wayfare-review-pr`, `wayfare-respond-pr` and wayfare's
review step call this skill with the first argument `inline` and a body or a
diff scope, for every piece of text a person reads: code comments and
docstrings, docs, error and log messages, the commit body, the PR body, review
comments and thread replies.

That text is posted by an agent into repos across the fleet, not published by
Rahul, so the rules narrow:

- Use `references/ai-tells.md` and the regular-words rule. Skip
  `references/voice.md`, the format files, and the "light, not solemn" rule: no
  asides or jokes in a review comment.
- No em or en dashes, curly quotes or emoji, in any format.
  `scripts/check_docs.py` and `scripts/pr_text_lint.py` reject them, and a
  rejected post stalls the step.
- Keep every heading, count, `<!-- ai-hero:... -->` marker and the
  `_Generated using wayfare._` footer exactly. The prior-review gate and
  auto-approve find comments by them.
- Edit only the lines the caller named. For a diff, that is the lines it
  touches; never reflow prose it left alone.
- A code comment that survives must still pass the repo's comment rule
  (`.claude/rules/comments.md` where present). This pass never adds a comment or
  pads one out.

Apply the rewrite in place, print a one-line count of what changed, and return
to the calling step. Skip the note described under What to return.
