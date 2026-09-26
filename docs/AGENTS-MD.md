# The AGENTS.md standard

What a repo's agent-instructions file must be, why, and how it is checked.
`scripts/check-agents-md.sh` enforces R1 to R6 mechanically; R7 to R10 need
judgment and are applied in a rewrite pass.

## The principle

The file loads into every session, before the task, and every line competes with
the task for attention. Anthropic's test for each line, as of August 2026:
*would removing this cause Claude to make mistakes?* If not, cut it. Files past
~200 lines measurably reduce adherence; repository overviews raise cost with no
measured gain in task success; LLM-generated files that restate the repo made
agents worse than no file at all.

The file is for what the code cannot show: traps, the check to run, conventions
that differ from tool defaults, and pointers to where the rest lives. Everything
else has a better home:

| It is… | Put it in |
| -- | -- |
| A fact the tree or a manifest already states (layout, stack, dependencies) | Nowhere, or `HERO.md` if a tool needs it |
| A data model, contract, or boundary | `DESIGN.md` (`wayfare:wayfare-sync-architecture`) |
| A multi-step procedure | A skill; loads only when used |
| A rule for one area of the tree | `.claude/rules/NAME.md` with `paths:` frontmatter |
| Something that must happen every time | A hook; prose is a request, a hook is enforcement |
| A style rule a linter can hold | The linter |

## The checks

Mechanical, and `check-agents-md.sh` fails the commit:

1. **R1, one file.** `AGENTS.md` is the file; `CLAUDE.md` is a symlink to it.
   Two regular files diverge silently. A repo with only one of the two warns.
2. **R2: 200 lines or fewer,** with a warning above 150. Block HTML comments are
   stripped before load and do not count, so maintainer notes are free.
3. **R3, rules over 60 lines carry `paths:`.** An unscoped rule loads in every
   session; a scoped one only when a matching file is read.
4. **R4, one line of emphasis.** More than one
   `IMPORTANT`/`NEVER`/`ALWAYS`/`MUST`/`CRITICAL` line warns; more than five
   fails. When many lines shout, none stands out.
5. **R5, no derivable sections.** A heading that is exactly one of `Layout`,
   `Tech Stack`, `Technology Stack`, `Directory Structure`, `Directory Layout`,
   `Project Structure`, `Folder Structure`, `Data Model`,
   `Architecture Overview`, `Dependencies`, `File-by-file` (a trailing colon,
   dash, or parenthetical is allowed) may hold at most five lines, a pointer,
   not the content.
6. **R6, no banned phrases** in the file, the rules, or commit messages:
   `load-bearing`, `honest take`, `belt and suspenders`, `that's the unlock`,
   `you're absolutely right`, `delve`. A writing rule may list them inside a
   code fence.

Judgment, applied in a rewrite, not by the script:

1. **R7, every "don't" names the "do".** Bare prohibitions without an
   alternative doubled task time in measurement.
2. **R8: every rule names a trap.** Same test as the comments rule: would
   someone undo this for a reason the line prevents? A rule the agent already
   follows unprompted is deleted; a rule that only worked around an older
   model's limit is deleted.
3. **R9, commands are copy-pasteable and include the verification.** "Run
   `just test`; boot the stack and hit `/readyz`", not "test your changes".
4. **R10, pointers, not copies.** `file:line`, `DESIGN.md`, a skill name. No
   pasted snippet over five lines; snippets rot.

## Beyond the file

The file is one lever. These address exploration cost and over-confirmation
directly and belong in the same rollout:

- `permissions.deny` `Read(...)` rules on committed generated code, so the agent
  never spends context on output.
- A code-intelligence plugin for the language, so a symbol lookup replaces a
  grep-and-read loop.
- Investigation in an Explore subagent; the main session keeps the conclusion.
- Verification by running the check, not by re-reading the diff, and a
  `PostToolUse` hook for the formatter, so it happens every time.

## Running it

```bash
bash scripts/check-agents-md.sh                # this repo
bash scripts/check-agents-md.sh /path/to/repo  # any repo
bash scripts/check-agents-md.sh /path/to/repo --warn-only   # report, exit 0
bash scripts/check-agents-md.sh --commit-msg .git/COMMIT_EDITMSG
```

Exit codes: `0` no rule errors (or `--warn-only`); `1` a rule error; `2` a usage
error or no instructions file; `3` the checker could not run (a tool missing, a
file unreadable). `--warn-only` downgrades only rule errors, and `--commit-msg`
takes no other options.

In this repo it runs from pre-commit on `AGENTS.md`, `CLAUDE.md`,
`.claude/rules/`, and the checker itself, and as a `commit-msg` hook. In any
other repo, run it against the repo path from the installed plugin.

## Sources

- Claude Code docs: [Memory](https://code.claude.com/docs/en/memory),
  [Best practices](https://code.claude.com/docs/en/best-practices),
  [Large codebases](https://code.claude.com/docs/en/large-codebases),
  [Extend Claude Code](https://code.claude.com/docs/en/features-overview)
- Anthropic:
  [The new rules of context engineering for Claude 5 generation models](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)
  (Jul 2026);
  [Steering Claude Code](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more)
  (Jun 2026)
- Augment Code:
  [A good AGENTS.md is a model upgrade. A bad one is worse than no docs at all.](https://www.augmentcode.com/blog/how-to-write-good-agents-dot-md-files)
- HumanLayer:
  [Writing a good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
