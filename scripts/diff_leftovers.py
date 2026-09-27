#!/usr/bin/env python3
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

"""Find debug code and untracked TODOs on the lines a change adds.

    diff_leftovers.py                 # working tree and untracked vs HEAD
    diff_leftovers.py --base main     # the same, vs the merge base with main

Exit 0 when clean, 1 and `file:line: finding` per hit, 2 when git cannot
answer (not a repo, an unknown base). Only added lines are read, so debt that
was already there is not this change's. Both modes read the working tree, not
just commits, because the skills run this before they commit.

    debug  console.log, debugger, breakpoint(), pdb/ipdb.set_trace,   leftovers: ok
           binding.pry, dbg!                                          leftovers: ok
    todo   TODO/FIXME/XXX with no issue reference (#123, ABC-123, or a URL)

A line that means it (a fixture, the pattern list itself) carries the marker
`leftovers: ok` anywhere on it, ideally with a reason.

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
TODO_MARK = re.compile(r"\b(TODO|FIXME|XXX)\b")  # leftovers: ok
TRACKED = re.compile(r"#\d+|\b[A-Z][A-Z0-9]+-\d+\b|https?://")
PROSE = re.compile(r"\.(md|mdx|rst|txt|adoc)$")
ALLOW = "leftovers: ok"
# Explicit prefixes and flags override the diff.noprefix, diff.mnemonicPrefix
# and color configs, any of which silently changes the headers this parser
# reads. core.quotePath=false keeps non-ASCII paths unescaped.
DIFF = ["git", "-c", "core.quotePath=false", "diff", "--unified=0", "--no-color",
        "--no-ext-diff", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/"]


class GitError(Exception):
    pass


def git(args, cwd, check=True):
    p = subprocess.run(args, cwd=cwd, capture_output=True)
    if check and p.returncode != 0:
        raise GitError(p.stderr.decode("utf-8", "replace").strip() or " ".join(args))
    return p.returncode, p.stdout.decode("utf-8", "replace")


def unquote(path):
    # Git C-quotes a path holding `"`, `\` or a control character even with
    # quotePath off; the octal escapes are the path's UTF-8 bytes.
    if not (path.startswith('"') and path.endswith('"')):
        return path
    raw = re.sub(rb"\\([0-7]{3}|.)",
                 lambda m: bytes([int(m.group(1), 8)]) if len(m.group(1)) == 3
                 else {b"n": b"\n", b"t": b"\t"}.get(m.group(1), m.group(1)),
                 path[1:-1].encode("utf-8"))
    return raw.decode("utf-8", "replace")


def added_lines(diff):
    path, n, header = None, 0, False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path, header = None, True
        elif header and line.startswith("+++ "):
            # Git ends the name with a tab when it holds a space.
            name = unquote(line[4:].rstrip("\t"))
            path = name[2:] if name.startswith("b/") else None
        elif line.startswith("@@"):
            header = False
            n = int(re.search(r"\+(\d+)", line).group(1))
        elif not header and line.startswith("+") and path:
            # Inside a hunk, so an added line that starts `++ ` is content.
            yield path, n, line[1:]
            n += 1


def untracked_lines(top):
    _, out = git(["git", "ls-files", "--others", "--exclude-standard", "-z"], top)
    for path in filter(None, out.split("\0")):
        try:
            with open(f"{top}/{path}", "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        if b"\0" in data:
            continue
        for n, text in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            yield path, n, text


def scan(base):
    _, top = git(["git", "rev-parse", "--show-toplevel"], None)
    top = top.strip()
    has_head = git(["git", "rev-parse", "--verify", "-q", "HEAD"], top, check=False)[0] == 0
    if base and has_head:
        _, since = git(["git", "merge-base", base, "HEAD"], top)
    elif has_head:
        since = "HEAD"
    else:
        _, since = git(["git", "hash-object", "-t", "tree", "/dev/null"], top)
    _, diff = git(DIFF + [since.strip()], top)
    yield from added_lines(diff)
    yield from untracked_lines(top)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="diff against the merge base of this ref and HEAD")
    args = ap.parse_args()
    hits = []
    try:
        for path, n, text in scan(args.base):
            if PROSE.search(path) or ALLOW in text:
                continue
            if DEBUG.search(text):
                hits.append(f"{path}:{n}: debug: {text.strip()[:80]}")
            if TODO_MARK.search(text) and not TRACKED.search(text):
                hits.append(f"{path}:{n}: todo without an issue reference: {text.strip()[:80]}")
    except GitError as e:
        print(f"diff_leftovers: {e}", file=sys.stderr)
        return 2
    for h in hits:
        print(h)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
