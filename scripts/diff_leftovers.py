#!/usr/bin/env python3
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

"""Find debug code and untracked TODOs on the lines a change adds.

    diff_leftovers.py                 # staged, unstaged and untracked vs HEAD
    diff_leftovers.py --base main     # everything the branch adds over main

Exit 0 when clean; exit 1 and `file:line: finding` per hit otherwise. Only
added lines are read, so debt that was already there is not this change's.

    debug  console.log, debugger, breakpoint(), pdb/ipdb.set_trace,
           binding.pry, dbg!
    todo   TODO/FIXME/XXX with no issue reference (#123, ABC-123, or a URL)

`print(` is deliberately not flagged: in a CLI it is the output, and a check
that fires on every command-line tool gets switched off.
"""

import argparse
import re
import subprocess
import sys

DEBUG = re.compile(
    r"\bconsole\.(log|debug)\s*\(|^\s*debugger\s*;?\s*$|\bbreakpoint\(\)|"
    r"\b[ip]db\.set_trace\(|\bbinding\.pry\b|\bdbg!\(")
TODO = re.compile(r"\b(TODO|FIXME|XXX)\b")
TRACKED = re.compile(r"#\d+|\b[A-Z][A-Z0-9]+-\d+\b|https?://")
PROSE = re.compile(r"\.(md|mdx|rst|txt|adoc)$")


def added_lines(base):
    cmd = ["git", "diff", "--unified=0", "--no-color", "--no-ext-diff"]
    cmd += [f"{base}...HEAD"] if base else ["HEAD"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    path, n = None, 0
    for line in out.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            n = int(re.search(r"\+(\d+)", line).group(1))
        elif line.startswith("+") and path:
            yield path, n, line[1:]
            n += 1


def untracked_lines():
    # `git diff HEAD` never shows a file that is not tracked yet, and a new
    # file is where debug code most often lands before the first commit.
    out = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"],
                         capture_output=True, text=True, check=True).stdout
    for path in filter(None, out.split("\0")):
        try:
            with open(path, encoding="utf-8") as fh:
                for n, text in enumerate(fh, 1):
                    yield path, n, text.rstrip("\n")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base")
    args = ap.parse_args()
    hits = []
    lines = added_lines(args.base)
    if not args.base:
        lines = list(lines) + list(untracked_lines())
    for path, n, text in lines:
        if PROSE.search(path):
            continue
        if DEBUG.search(text):
            hits.append(f"{path}:{n}: debug: {text.strip()[:80]}")
        if TODO.search(text) and not TRACKED.search(text):
            hits.append(f"{path}:{n}: todo without an issue reference: {text.strip()[:80]}")
    for h in hits:
        print(h)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
