---
name: wayfare-humanize-prose
# prettier-ignore
description: Remove signs of AI-generated writing from text so it reads as human-written; based on Wikipedia's "Signs of AI writing". Use when editing or reviewing prose, or on any text you want to pass through the same filter the pipeline applies.
argument-hint: "[TEXT | PATH | nothing, to use the text in context]"
compatibility: "Requires the complete Wayfare plugin because its maintained prose rules live in docs/HUMANIZING.md."
---

# Humanizer: strip the AI tells out of prose

Apply [docs/HUMANIZING.md](../../docs/HUMANIZING.md) to the text you were given
and return the rewrite.

**Read that file first.** It is the whole substance of this skill: the tells,
the rewrites, the words to watch, and the rules about what not to change. It
lives in `docs/` rather than here because four pipeline steps read it too
(`wayfare-push-pr`, `wayfare-review-pr`, `wayfare-respond-pr`, and wayfare's
review step), and they read it directly rather than invoking this skill.

## Instructions

1. Read `docs/HUMANIZING.md` in full.
2. Resolve what to humanize, in this order: `$ARGUMENTS` as literal text; a path
   in `$ARGUMENTS`, if it names a file that exists; otherwise the text already
   in the conversation the user is pointing at. If none of the three resolves,
   ask which text. Never guess and rewrite something the user did not mean.
3. Apply the file's rules. **Rewrite, never delete**: cover everything the
   original covers. Five paragraphs in, five paragraphs out.
4. Return the rewrite. For a file, show the diff and ask before writing.

## What this skill does not do

- **It does not change meaning.** A tell that is load-carrying stays. If
  removing an AI-ism would drop a claim, keep the claim and rewrite around it.
- **It does not touch code**, only the prose in and around it: comments,
  docstrings, docs, messages a person reads.
- **It is not a style opinion.** Every rule in the file is a documented pattern
  from Wikipedia's "Signs of AI writing", not a preference.
