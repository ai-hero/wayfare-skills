---
name: wayfare-humanize-prose
# prettier-ignore
description: "Rewrite text with the maintained rules from Wikipedia's \"Signs of AI writing\". Preserve meaning and remove AI writing patterns. Use when editing prose or applying the pipeline's prose filter to text."
argument-hint: "[TEXT | PATH | nothing, to use the text in context]"
compatibility: "Requires the complete Wayfare plugin because its maintained prose rules live in docs/HUMANIZING.md."
---

# Humanizer: strip the AI tells out of prose

Apply [docs/HUMANIZING.md](../../docs/HUMANIZING.md) to the text you were given
and return the rewrite.

**Read that file first.** It defines the writing patterns, replacements, and
constraints on changes. Four pipeline steps read it directly: `wayfare-push-pr`,
`wayfare-review-pr`, `wayfare-respond-pr`, and wayfare's review step. Thus, the
shared rules live in `docs/`.

## Instructions

1. Read `docs/HUMANIZING.md` in full.
2. Resolve the input in this order. First, try `$ARGUMENTS` as literal text.
   Next, try a path in `$ARGUMENTS` that names an existing file. Otherwise, use
   the conversation text the user identifies. If no input resolves, ask which
   text to rewrite. Never guess the input.
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
