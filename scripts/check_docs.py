#!/usr/bin/env python3
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

"""Mechanical checks over this repo's Markdown, so no model has to make them.

    scripts/check_docs.py            # check the repo; exit 1 on any error
    scripts/check_docs.py --root DIR # check another checkout (the tests do)

Each check is a rule the docs used to state and an LLM used to enforce:

    frontmatter  every SKILL.md frontmatter parses as YAML, `name` then
                 `description`, description at most 1024 characters
    steps        `Step N` headings run without gaps; `Na` sub-steps belong
                 to step N and run a, b, c
    placeholder  no `<lowercase>` placeholders in skills (UPPER_CASE instead)
    todo         no TODO/FIXME/XXX left in skill prose
    prose        no em or en dashes, ` -- `, curly quotes, emoji, or the
                 banned phrases (docs/HUMANIZING.md, docs/AGENTS-MD.md R6)
    chain        a pipeline chain quoted anywhere matches docs/PIPELINES.md,
                 and a "N stages" beside it matches its length
    count        number words that claim a count match the count
    yml          no tracked `.yml` file (PLACE-06)
    link         relative Markdown links resolve

Fenced code, inline code, and regions between `<!-- check-docs: off -->` and
`<!-- check-docs: on -->` are exempt from placeholder, todo and prose: a
writing guide has to be able to show the pattern it bans.
"""

import argparse
import pathlib
import re
import subprocess
import sys

# docs/superpowers/ holds dated plans: a record of what was true then.
EXCLUDE_DIRS = ("analysis/", "memory/", "docs/superpowers/")

NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}

BANNED = re.compile(
    r"load[- ]bearing|honest take|belt and suspenders|that'?s the unlock|"
    r"you'?re absolutely right|\bdelve", re.I)
PROSE_CHARS = [
    (re.compile("—"), "em dash"),
    (re.compile("–"), "en dash"),
    # Between words only: a compact table's delimiter row is `| -- | -- |`.
    (re.compile(r"(?<=[\w.,;:)!?\"'])\s--\s(?=[\w(\"'])"), "double hyphen used as a dash"),
    (re.compile("[“”‘’]"), "curly quote"),
    (re.compile("[\U0001F300-\U0001FAFF☀-⛿✀-➿]"), "emoji"),
]

HTML_TAGS = {
    "a", "b", "br", "code", "details", "div", "em", "hr", "i", "img", "kbd",
    "li", "ol", "p", "pre", "span", "strong", "sub", "summary", "sup",
    "table", "td", "th", "tr", "ul",
}

# Links in these files point into the consumer repo the file scaffolds, not
# into this one, so they cannot resolve here.
LINK_EXEMPT = {"references/init.md", "references/scaffold.md"}

errors = []


def error(path, line, check, msg):
    errors.append(f"{path}:{line}: [{check}] {msg}")


def tracked(root, pattern):
    out = subprocess.run(["git", "-C", str(root), "ls-files", pattern],
                         capture_output=True, text=True, check=True).stdout
    # Mid-merge, ls-files lists a conflicted path once per stage.
    out = "\n".join(dict.fromkeys(out.splitlines()))
    # A symlink (CLAUDE.md -> AGENTS.md) would report every finding twice.
    return [p for p in out.splitlines()
            if not p.startswith(EXCLUDE_DIRS) and not (root / p).is_symlink()]


def prose_lines(text):
    """Yield (lineno, line) with code and exempt regions blanked out."""
    lines = text.splitlines()
    keep = [False] * len(lines)
    fence = None
    off = False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if "<!-- check-docs: off -->" in line:
            off = True
            continue
        if "<!-- check-docs: on -->" in line:
            off = False
            continue
        m = re.match(r"(`{3,}|~{3,})", stripped)
        if m:
            if fence is None:
                fence = m.group(1)
                continue
            # Only a bare run of the same character, at least as long, closes
            # a fence (CommonMark); a ```bash line inside one is content.
            if re.fullmatch(re.escape(fence[0]) + "{%d,}\\s*" % len(fence), stripped):
                fence = None
                continue
        keep[i] = fence is None and not off
    # Strip inline code over the whole text, not per line: the formatter wraps
    # paragraphs, so a code span routinely starts on one line and ends on the
    # next. Blanked lines are empty, so a span cannot reach across a fence.
    joined = "\n".join(ln if k else "" for ln, k in zip(lines, keep))
    joined = re.sub(r"(`+)(?:(?!\1)[^\n]|\n(?!\n))*?\1",
                    lambda m: "\n" * m.group(0).count("\n"), joined)
    for n, (line, k) in enumerate(zip(joined.split("\n"), keep), 1):
        if k:
            yield n, line


def frontmatter(text):
    if not text.startswith("---\n"):
        return None, 0
    end = text.find("\n---\n", 4)
    if end < 0:
        return None, 0
    return text[4:end], text[:end].count("\n") + 2


def check_frontmatter(rel, text):
    fm, _ = frontmatter(text)
    if fm is None:
        error(rel, 1, "frontmatter", "no frontmatter block")
        return
    # Imported here, not at the top: pr_text_lint.py imports this module for
    # its prose rules and runs in consumer repos that may not have pyyaml.
    import yaml
    try:
        data = yaml.safe_load(fm)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line = mark.line + 2 if mark else 1
        error(rel, line, "frontmatter",
              "does not parse as YAML (quote a value that contains ': ')")
        return
    if not isinstance(data, dict):
        error(rel, 2, "frontmatter", "is not a mapping of keys to values")
        return
    keys = list(data)
    if keys[:2] != ["name", "description"]:
        error(rel, 2, "frontmatter", f"keys must start name, description; got {keys[:2]}")
    desc = data.get("description")
    if not isinstance(desc, str) or not desc.strip():
        error(rel, 2, "frontmatter", "description missing")
    elif len(desc) > 1024:
        error(rel, 2, "frontmatter", f"description is {len(desc)} chars, over 1024")
    elif not 50 <= len(desc) <= 350:
        # Past about 350 a description is padding and dilutes skill matching;
        # under 50 it cannot carry a trigger (wayfare-audit-plugin 2e).
        error(rel, 2, "frontmatter", f"description is {len(desc)} chars; keep it within 50 to 350")
    # A chained stage is never matched against a user's request, so it needs
    # no trigger; everything else is picked by its description.
    if (isinstance(desc, str) and data.get("user-invocable") is not False
            and not re.search(r"\bUse (when|for|before|after|to|on|from)\b", desc)):
        error(rel, 2, "frontmatter", 'description says what, not when: add "Use when ..."')
    if "argument-hint" in keys and keys.index("argument-hint") != 2:
        error(rel, 2, "frontmatter", "argument-hint comes third, after name and description")


def check_yaml_only(rel, text):
    import yaml
    try:
        yaml.safe_load(frontmatter(text)[0])
    except yaml.YAMLError:
        error(rel, 2, "frontmatter", "does not parse as YAML (quote a value that contains ': ')")


def check_steps(rel, text):
    last_main = None
    letters = {}
    for n, line in prose_lines(text):
        # A skill with two modes numbers each mode's steps from 1 under its
        # own `##` heading, so a non-step section heading restarts the count.
        if re.match(r"## (?!Step )", line):
            last_main = None
            letters = {}
            continue
        m = re.match(r"#{2,4} Step (\d+)(\.\d+|[a-z])?\b", line)
        if m:
            main, suffix = int(m.group(1)), m.group(2) or ""
            if suffix.isalpha():
                want = chr(ord(letters.get(main, "`")) + 1)
                if suffix != want:
                    error(rel, n, "steps", f"Step {main}{suffix} should be Step {main}{want}")
                letters[main] = suffix
                continue
            if suffix:
                continue
            if last_main is not None and main not in (last_main, last_main + 1):
                error(rel, n, "steps", f"Step {main} follows Step {last_main}")
            last_main = main
            continue
        m = re.match(r"#{3,5} (\d+)([a-z]):", line)
        if m:
            main, letter = int(m.group(1)), m.group(2)
            if last_main is not None and main != last_main:
                error(rel, n, "steps", f"sub-step {main}{letter} sits under Step {last_main}")
            want = chr(ord(letters.get(main, "`")) + 1)
            if letter != want:
                error(rel, n, "steps", f"sub-step {main}{letter} should be {main}{want}")
            letters[main] = letter


def check_skill_prose(rel, text):
    for n, line in prose_lines(text):
        for tag in re.findall(r"</?([a-z][a-z0-9_-]*)(?![\w:-])[^>]*>", line):
            if tag not in HTML_TAGS:
                error(rel, n, "placeholder", f"<{tag}> placeholder; use UPPER_CASE")
        # Only a note left for later (`TODO:`, `FIXME(x)`); prose that names
        # TODO markers as a thing to look for is not one.
        if re.search(r"\b(TODO|FIXME|XXX)[:(]", line):
            error(rel, n, "todo", "TODO/FIXME/XXX note left in skill prose")


def check_markers(rel, text):
    # prose_lines honours these silently, so a missing `on` would exempt the
    # rest of the file without anyone seeing it.
    state, opened = "on", 0
    for n, line in enumerate(text.splitlines(), 1):
        if "<!-- check-docs: off -->" in line:
            if state == "off":
                error(rel, n, "marker", "check-docs: off inside an off region")
            state, opened = "off", n
        elif "<!-- check-docs: on -->" in line:
            if state == "on":
                error(rel, n, "marker", "check-docs: on with no off before it")
            state = "on"
    if state == "off":
        error(rel, opened, "marker", "check-docs: off is never turned back on")


def check_attribution(rel, text):
    # Read raw, fences included: the templates this guards live in code blocks.
    # A model name copied into a template is stale the next time a model ships.
    for n, line in enumerate(text.splitlines(), 1):
        if re.search(r"Co-Authored-By:\s*Claude\s+\w+\s+\d", line, re.I):
            error(rel, n, "attribution",
                  "model name in a Co-Authored-By template; say to use the harness's trailer")


def check_prose(rel, text):
    for n, line in prose_lines(text):
        for pat, what in PROSE_CHARS:
            if pat.search(line):
                error(rel, n, "prose", f"{what} (docs/HUMANIZING.md)")
        m = BANNED.search(line)
        if m:
            error(rel, n, "prose", f"banned phrase {m.group(0)!r} (docs/AGENTS-MD.md R6)")


CHAIN = re.compile(r"[\w-]+(?: → [\w-]+)+")


def canonical_chains(root):
    chains = []
    text = (root / "docs/PIPELINES.md").read_text()
    fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            fence = not fence
            continue
        if fence and re.fullmatch(CHAIN.pattern, line.strip()):
            chains.append(line.strip().split(" → "))
    return chains


def count_word_near(lines, i):
    for j in range(max(0, i - 2), min(len(lines), i + 3)):
        # "Four steps:" introduces the chain; "the next two steps" does not.
        m = re.search(r"\b(\w+) (?:stages|steps):", lines[j], re.I)
        if m and m.group(1).lower() in NUMBER_WORDS:
            return j + 1, NUMBER_WORDS[m.group(1).lower()]
    return None, None


def check_chains(rel, text, chains):
    lines = text.splitlines()
    # The formatter wraps a chain written in prose, so match across single
    # line breaks. One character for one keeps every offset, so a match's
    # line number is still the count of newlines before it.
    joined = re.sub(r"\n(?!\n)", " ", text)
    # Spaces and tabs only, so a match cannot run past a paragraph break.
    for m in re.finditer(r"[\w-]+(?:[ \t]+→[ \t]+[\w-]+)+", joined):
        seq = re.split(r"[ \t]+→[ \t]+", m.group(0))
        i = text.count("\n", 0, m.start())
        for canon in chains:
            if seq[:2] != canon[:2]:
                continue
            if seq != canon:
                error(rel, i + 1, "chain",
                      f"'{' → '.join(seq)}' differs from docs/PIPELINES.md: {' → '.join(canon)}")
                continue
            ln, n = count_word_near(lines, i)
            if n is not None and n != len(canon):
                error(rel, ln, "chain", f"says {n} but the chain has {len(canon)}")


def read(root, rel):
    """The file's text with CRLF normalised, or None after reporting why not."""
    try:
        return (root / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError) as e:
        error(rel, 1, "read", f"unreadable: {e.__class__.__name__}")
        return None


def check_counts(root):
    skills = sorted((root / "skills").glob("*/SKILL.md"))
    kinds_text = (root / "docs/CONNECTIONS.md").read_text().split("## The kinds", 1)[-1]
    kinds_table = kinds_text.split("\n## ", 1)[0]
    facts = {
        "recalibrate": sum("\n## `recalibrate`" in s.read_text() for s in skills),
        "stage-skills": sum("\nuser-invocable: false" in s.read_text() for s in skills),
        "kinds": len(re.findall(r"^\| `[\w-]+` \|", kinds_table, re.M)),
        "ship-pr-fields": len(re.findall(r"^wayfare-ship-pr\|",
                                         (root / "scripts/hero-fields.sh").read_text(), re.M)),
    }
    claims = [
        ("recalibrate", r"\b(\w+) skills (?:accept|carry) (?:the verb|`recalibrate`)"),
        ("recalibrate", r"`recalibrate` is on (\w+) skills"),
        ("stage-skills", r"\b(\w+) skills are stages\b"),
        ("kinds", r"\b(\w+) kinds(?=,|\s+are other)"),
        ("ship-pr-fields", r"about the (\w+) fields `?wayfare-ship-pr`? reads"),
    ]
    for rel in tracked(root, "*.md"):
        text = read(root, rel)
        if text is None:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for fact, pat in claims:
                for m in re.finditer(pat, line, re.I):
                    word = m.group(1).lower()
                    if word in NUMBER_WORDS and NUMBER_WORDS[word] != facts[fact]:
                        error(rel, n, "count", f"says {word} but the count is {facts[fact]}")


def check_links(root, rel, text):
    if rel in LINK_EXEMPT:
        return
    base = (root / rel).parent
    for n, line in prose_lines(text):
        targets = re.findall(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", line)
        targets += re.findall(r"^\s{0,3}\[[^\]]+\]:\s+(\S+)", line)
        for target in targets:
            if re.match(r"[a-z]+:|#|/", target):
                continue
            path = target.split("#", 1)[0].split("?", 1)[0]
            if path and not (base / path).exists():
                error(rel, n, "link", f"{target} does not resolve")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    args = ap.parse_args()
    root = pathlib.Path(args.root or subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
        check=True).stdout.strip())

    for required in ("docs/PIPELINES.md", "docs/CONNECTIONS.md", "scripts/hero-fields.sh"):
        if not (root / required).is_file():
            print(f"check_docs: {required} is missing; the chain and count checks read it",
                  file=sys.stderr)
            return 2
    chains = canonical_chains(root)
    for rel in tracked(root, "*.md"):
        text = read(root, rel)
        if text is None:
            continue
        if re.fullmatch(r"skills/[^/]+/SKILL\.md", rel):
            check_frontmatter(rel, text)
            check_steps(rel, text)
        elif frontmatter(text)[0] is not None:
            check_yaml_only(rel, text)
        if re.fullmatch(r"skills/[^/]+/SKILL\.md|references/.+\.md", rel):
            check_skill_prose(rel, text)
        if rel.startswith(("skills/", "references/", "assets/")):
            check_attribution(rel, text)
        check_markers(rel, text)
        check_prose(rel, text)
        check_chains(rel, text, chains)
        check_links(root, rel, text)
    check_counts(root)
    for rel in tracked(root, "*.yml"):
        error(rel, 1, "yml", "use .yaml (PLACE-06)")

    for e in errors:
        print(e)
    if errors:
        print(f"check_docs: {len(errors)} error(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
