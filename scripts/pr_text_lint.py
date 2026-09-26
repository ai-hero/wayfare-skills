#!/usr/bin/env python3
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

"""Lint text before wayfare posts it: a PR title and body, a comment, a review.

    pr_text_lint.py --kind pr --title "feat: x" --body-file body.md
    pr_text_lint.py --kind comment --body-file body.md
    pr_text_lint.py --kind commit --body-file msg.txt

Exit 0 when clean; exit 1 and one line per finding otherwise. The skills run
this before every `gh pr create/edit/comment/review`, so a rule the text
breaks is caught here rather than left for the model to notice.

    title        pr only: at most 70 characters, no "Hero" or "wayfare"
    footer       every kind but commit: the last line is exactly
                 `_Generated using wayfare._`, and it appears once
    placeholder  no template placeholder survived (DRAFTED_FULL_BODY_HERE,
                 NEW_TITLE_UNDER_70_CHARS, {file:line}, a `[slot]` line, ...)
    prose        no em or en dashes, ` -- `, curly quotes, emoji, or banned
                 phrases outside code (docs/HUMANIZING.md)
"""

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from check_docs import BANNED, PROSE_CHARS, prose_lines  # noqa: E402

FOOTER = "_Generated using wayfare._"

# The literal placeholders the skills' templates carry. A body posted with one
# still in it overwrites a PR description with the placeholder's name.
PLACEHOLDERS = re.compile(
    r"DRAFTED_FULL_BODY_HERE|NEW_TITLE_UNDER_70_CHARS|REVIEWER_FEEDBACK|"
    r"FIX_DESCRIPTION|TRIGGER_TEXT|TRIGGER_LABEL|\bFILE:LINE\b|"
    r"ANSWER_OR_RATIONALE|REASON_FOR_DECLINING|LIST_OR_NONE|\bSHA[12]\b|"
    r"\{[A-Za-z][^{}\n]*\}")
# A template line that is nothing but a bracketed slot, bare or as a list
# item: `[1-3 sentence overview]`, `- [ ] [Test step 1]`. A Markdown link has
# a `(` after its `]`, so it never matches.
SLOT_LINE = re.compile(r"^\s*(?:[-*] (?:\[[ x]\] )?)?\[[^\]]+\]\s*$")


def lint(kind, title, body):
    found = []
    if kind == "pr":
        if title is None:
            found.append("title: --title is required for a pr")
        else:
            if len(title) > 70:
                found.append(f"title: {len(title)} characters, over 70")
            if re.search(r"\b(hero|wayfare)\b", title, re.I):
                found.append("title: keep it unbranded (no Hero or wayfare)")
            if PLACEHOLDERS.search(title):
                found.append(f"placeholder: title still holds {PLACEHOLDERS.search(title).group(0)}")

    if kind != "commit":
        lines = [ln for ln in body.rstrip().splitlines()]
        if not lines or lines[-1].strip() != FOOTER:
            found.append(f"footer: the last line must be exactly {FOOTER}")
        elif body.count(FOOTER) > 1:
            found.append(f"footer: {FOOTER} appears more than once")

    for n, line in prose_lines(body):
        m = PLACEHOLDERS.search(line)
        if m:
            found.append(f"placeholder: line {n} still holds {m.group(0)}")
        elif SLOT_LINE.match(line):
            found.append(f"placeholder: line {n} is an unfilled template slot: {line.strip()}")
        for pat, what in PROSE_CHARS:
            if pat.search(line):
                found.append(f"prose: line {n}: {what}")
        m = BANNED.search(line)
        if m:
            found.append(f"prose: line {n} uses the banned phrase {m.group(0)!r}")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=["pr", "comment", "review", "commit"])
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
