#!/usr/bin/env python3
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

"""Lint text before wayfare posts it: a PR title and body, a comment, a review.

    pr_text_lint.py --kind pr --title "feat: x" --body-file body.md
    pr_text_lint.py --kind pr-edit --title "feat: x" --body-file body.md
    pr_text_lint.py --kind comment --body-file body.md
    pr_text_lint.py --kind inline --body-file - <<<"$COMMENT_BODY"
    pr_text_lint.py --kind commit --body-file msg.txt

Exit 0 when clean; exit 1 and one line per finding otherwise. The skills run
this before every `gh pr create/edit/comment/review`, every inline comment or
thread reply, and every commit, so a rule the text breaks is caught here
rather than left for the model to notice.

    title        pr and pr-edit: at most 70 characters, no brand (A.I. Hero,
                 a standalone Hero, wayfare as a word), and the prose rules
    footer       pr, pr-edit, comment, review: the last line is exactly
                 `_Generated using wayfare._`, and it appears once
    placeholder  no template placeholder survived (DRAFTED_FULL_BODY_HERE,
                 NEW_TITLE_UNDER_70_CHARS, {file:line}, a `[slot]` line, ...)
    prose        every kind but pr-edit: no em or en dashes, ` -- `, curly
                 quotes, emoji, or banned phrases outside code
                 (docs/HUMANIZING.md)

pr-edit skips the prose rules on the body because an edited body keeps text
someone else wrote, and a person's em dash must not block the edit.
"""

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from check_docs import BANNED, PROSE_CHARS, prose_lines  # noqa: E402

FOOTER = "_Generated using wayfare._"

# The literal placeholders the skills' templates carry, and nothing broader: a
# generic `{word}` rule fires on `/users/{id}` and `{ok: true}` in real prose.
# A template that gains a new slot adds it here.
PLACEHOLDERS = re.compile(
    r"DRAFTED_FULL_BODY_HERE|NEW_TITLE_UNDER_70_CHARS|REVIEWER_FEEDBACK|"
    r"FIX_DESCRIPTION|TRIGGER_TEXT|TRIGGER_LABEL|\bFILE:LINE\b|"
    r"ANSWER_OR_RATIONALE|REASON_FOR_DECLINING|LIST_OR_NONE|"
    r"\bCommits: SHA1\b|(?<=: )(?:FINDING|QUESTION)\.|\bSkipped: REASON\b|"
    r"\{(?:[NWXYZ]|file:line|finding|agent|what's well-done|summary of fix \d+|"
    r"type|scope|description|body if needed|DECISION_FLAG|1-3 sentence summary|"
    r"most important issue|second most important|positive observations)\}")
# A template line that is nothing but a bracketed slot, bare or as a list
# item: `[1-3 sentence overview]`, `- [ ] [Test step 1]`. The slot needs two
# words or a digit range inside, so a bare `- [ ]` and a one-word shortcut
# reference `[ref]` are not slots. A Markdown link has a `(` after its `]`.
SLOT_LINE = re.compile(
    r"^\s*(?:[-*] (?:\[[ xX]\] )?)?"
    r"\[(?=[^\]]*[A-Za-z0-9])(?=[^\]]*(?:\S\s+\S|\d-\d))[^\]]+\]\s*$")
HTML_COMMENT = re.compile(r"<!--(?!\s*check-docs:)[\s\S]*?-->")
CODE_SPAN = re.compile(r"(`+).*?\1")
# Capitalized `Hero` is the brand; lowercase `hero` is the ordinary word
# ("hero section"), and `HERO.md` or `wayfare-push-pr` name a file or skill.
BRAND_CASED = re.compile(r"(?<![\w.-])(?:Hero|HERO)(?![\w-]|\.md)")
BRAND_ANYCASE = re.compile(r"\bA\.?I\.? Hero\b|(?<![\w-])wayfare(?![\w:.-])", re.I)


def prose_findings(where, text):
    found = [f"prose: {where}: {what}" for pat, what in PROSE_CHARS if pat.search(text)]
    m = BANNED.search(text)
    if m:
        found.append(f"prose: {where} uses the banned phrase {m.group(0)!r}")
    return found


def lint_title(title):
    found = []
    if len(title) > 70:
        found.append(f"title: {len(title)} characters, over 70")
    bare = CODE_SPAN.sub("", title)
    m = BRAND_ANYCASE.search(bare) or BRAND_CASED.search(bare)
    if m:
        found.append(f"title: keep it unbranded (drop {m.group(0)!r})")
    m = PLACEHOLDERS.search(title)
    if m:
        found.append(f"placeholder: title still holds {m.group(0)}")
    return found + prose_findings("title", bare)


def lint(kind, title, body):
    found = []
    if kind in ("pr", "pr-edit"):
        if title is None:
            found.append(f"title: --title is required for {kind}")
        else:
            found += lint_title(title)

    if kind in ("pr", "pr-edit", "comment", "review"):
        lines = body.rstrip().splitlines()
        if not lines or lines[-1].strip() != FOOTER:
            found.append(f"footer: the last line must be exactly {FOOTER}")
        elif sum(ln.strip() == FOOTER for ln in lines) > 1:
            found.append(f"footer: {FOOTER} appears more than once")

    visible = HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), body)
    for n, line in prose_lines(visible):
        m = PLACEHOLDERS.search(line)
        if m:
            found.append(f"placeholder: line {n} still holds {m.group(0)}")
        elif SLOT_LINE.match(line):
            found.append(f"placeholder: line {n} is an unfilled template slot: {line.strip()}")
        if kind != "pr-edit":
            found += prose_findings(f"line {n}", line)
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True,
                    choices=["pr", "pr-edit", "comment", "review", "inline", "commit"])
    ap.add_argument("--title")
    ap.add_argument("--body-file", required=True, help="path, or - for stdin")
    args = ap.parse_args()
    body = sys.stdin.read() if args.body_file == "-" else pathlib.Path(args.body_file).read_text()
    found = lint(args.kind, args.title, body)
    for f in found:
        print(f"pr_text_lint: {f}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
