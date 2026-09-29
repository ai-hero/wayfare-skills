---
name: wayfare-create-skill
# prettier-ignore
description: Create an Agent Skill or a supported client-specific agent, rule, or hook with clear triggers and success criteria. Use when extending an agent client or adding a reusable workflow.
argument-hint: "DESCRIPTION_OF_THE_CAPABILITY | recalibrate"
compatibility: "Requires the complete Wayfare plugin; client-specific components also require that client's plugin format and runtime."
disable-model-invocation: true
---

# Create Skill: build agent components

A skill is a folder with a `SKILL.md` in it, following the open
[Agent Skills](https://agentskills.io/specification) format. This skill writes
one, or the subagent, rule, or hook that fits better.

## Arguments

- `recalibrate` - Tune the `HERO.md` fields this skill reads, then stop (see
  below). Matched before the description.
- `$ARGUMENTS` - Description of what you want the skill to do

## Component Types

| Type | Location | Use When |
| -- | -- | -- |
| **Skill** | `.claude/skills/NAME/SKILL.md` | Workflows, guidelines |
| **Subagent** | `.claude/agents/NAME.md` | Isolated execution |
| **Rule** | `.claude/rules/NAME.md` | Always-on constraints |
| **Hook** | `settings.json` | Event-triggered automation |

User-level skills go in `~/.claude/skills/` for cross-project availability.

## The format

```
skill-name/
├── SKILL.md              # Required: frontmatter + instructions
├── scripts/              # Optional: code the agent runs
├── references/           # Optional: docs loaded on demand
└── assets/               # Optional: templates, data
```

### Frontmatter

```yaml
---
name: verb-object
# prettier-ignore
description: What it does and when to use it, with discriminating task keywords.
argument-hint: [args]
# Omit for skills an orchestrator like wayfare-build-task needs to chain. Setting it
# makes the skill user-only, so nothing can call it automatically.
disable-model-invocation: true
# Omit unless this skill plugs into wayfare:wayfare-sync-plan. If it does, say
# where: `plan` (a stage of `wayfare-sync-plan`), `verify` (a Definition-of-Done
# checker whose last stdout line is
# `verdict: PASS | FAIL | UNVERIFIED — reason`), or `recipe` (a way to
# build that planning can name). Wayfare
# finds this by itself, so never list the skill in HERO.md. It asks once
# per session before running one.
wayfare: sync
---
```

Only `name` and `description` are required by the spec. `argument-hint` and
`disable-model-invocation` are Claude Code fields, and `wayfare` is this
plugin's own; a standalone portable skill carries neither. A Wayfare skill is
not standalone because it uses plugin-global scripts and references, so it also
declares standard `compatibility` metadata naming that package boundary and any
required tools or network access.

- `name`: 1-64 chars, lowercase letters, digits and hyphens; no leading,
  trailing or doubled hyphen; must equal the folder name. Use verb-object.
- `description`: 1-1024 chars. Say what the skill does and when to use it,
  phrased as an instruction ("Use when the user..."). Name the user's intent,
  not the mechanics, and list the cases where they won't say the keyword. It is
  the only thing the agent reads before deciding to load the skill.

Optional spec fields: `license`, `compatibility` (only when the skill needs
specific tools or network), `metadata`, `allowed-tools`.

### Body

The agent loads the whole `SKILL.md` on activation, so every line competes with
the conversation for attention. Three rules:

1. **Add what the agent lacks.** Project conventions, non-obvious edge cases,
   the exact tool to use. Not what a PDF is. Ask of each line: "would the agent
   get this wrong without it?" If no, cut it.
2. **Keep it under 500 lines.** Longer material goes in `references/`, with the
   instruction saying *when* to read each file ("read `references/api-errors.md`
   if the API returns non-200"), not a bare "see references/".
3. **Match specificity to fragility.** Prose where several approaches are fine;
   exact commands where the sequence matters. Give a default and mention
   alternatives briefly, never a menu.

Use capability language such as "inspect the file", "run the command", or
"invoke the named skill through the active client". Do not hard-code another
client's Read, Bash, Skill, or subagent call syntax. Read
`../../references/client-capabilities.md` when a workflow depends on chaining,
delegation, progress channels, or client settings. Read
`../../references/authorization.md` when the skill changes local or external
state; preserve consequential gates without asking again for ordinary work the
invocation already authorized.

Patterns that earn their place: a **Gotchas** list (facts that defy reasonable
assumptions), a **template** for any output that must have a shape, a
**checklist** for multi-step work, and a **validate-then-proceed** loop (run the
check, fix, re-run, only then continue).

Scripts in `scripts/` must never prompt for input, must answer `--help`, and
should print structured output to stdout and diagnostics to stderr. Reference
them by path relative to the skill root.

### Anti-patterns

| Don't | Do Instead |
| -- | -- |
| "When to Use" section in body | Put triggers in the frontmatter description |
| 1000-line SKILL.md | Split into `references/` with load conditions |
| Duplicate info across files | Single source of truth |
| Lowercase angle bracket placeholders | Use UPPER_CASE (e.g., PROJECT_NAME) |
| Generic advice ("handle errors well") | The specific correction the agent needs |

## `recalibrate`

`wayfare:wayfare-create-skill recalibrate` tunes the config this skill reads,
then stops. It does not go on to run the skill. You want to see which field was
wrong, not spend a whole run finding out.

Dispatch on it before parsing any other argument, in whichever step does that
parsing. When the first token of `$ARGUMENTS` is exactly `recalibrate`, print
`wayfare-create-skill: running recalibrate`, follow the four phases in
[docs/RECALIBRATE.md](../../docs/RECALIBRATE.md) (report, ask, write, commit)
using the table below as the report, and stop.

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
"$WAYFARE_ROOT/scripts/hero-fields.sh" wayfare-create-skill
```

Ask only about rows whose CURRENT is parenthesised: `(unset)`, `(no-section)`,
`(refused)`, `(absent)`, `(no-file)`. Also ask about any row the user says is
wrong. A row that already holds the right value is not a question.

## Instructions

### Step 0: Load Configuration

**If `$ARGUMENTS` is exactly `recalibrate`, run the `recalibrate` section above
and stop.** Everything below reads `$ARGUMENTS` as free text describing the
skill to build, so the verb would otherwise be planned and built as one.

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cat "$ROOT/HERO.md" 2>/dev/null || echo "NO_HERO_CONFIG"
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo: stop and follow
**At the fleet root** in `docs/FLEET-MD.md`.

Use `HERO.md` to understand the project's stack and conventions when creating
skills that reference project-specific tools.

### Step 1: Understand the Goal

Ask for:

1. What should this do? Use a verb-object name, like `deploy-service` or
   `notify-slack`.
2. When should it trigger? (what signals or user requests)
3. What does success look like?

Ground the content in real expertise, not general knowledge: a task just
completed in this conversation, a runbook, a style guide, review comments,
recent fixes. A skill written from nothing says "follow best practices" and
helps nobody.

### Step 2: Plan the Component

Pick the component type from the table above. For a skill, decide what goes in
`SKILL.md` (the core procedure, every run) and what goes in `references/`,
`scripts/` or `assets/` (loaded only when a step needs it). Scope it as one
coherent unit of work: narrow enough to trigger precisely, wide enough that one
task does not need three skills.

### Step 3: Create the Files

```bash
mkdir -p .claude/skills/SKILL_NAME
```

Write `SKILL.md` with frontmatter and instructions, then any referenced files.

### Step 4: Validate

- `name` meets the spec rules above and matches the folder
- `description` says what and when, under 1024 chars
- `SKILL.md` is under 500 lines
- No lowercase angle bracket placeholders
- Every file the body references exists, one level deep from the skill root
- No empty `scripts/`, `references/` or `assets/` folder

Then run the skill once on a real task and fold the corrections back in. When
the agent makes a mistake you have to correct, that correction is a Gotchas
entry.

### Step 5: Summary

```
Create Skill Summary
====================
Component: skill | subagent | rule | hook
Name: SKILL_NAME
Location: PATH

Created:
  - SKILL.md (N lines)

Test: Invoke with wayfare:SKILL_NAME in a new conversation

Next step: wayfare:wayfare-audit-plugin, to check the new skill's quality and
wiring. Print this line only; wayfare-audit-plugin is user-only and cannot be
started automatically.
```

Don't also print `wayfare:wayfare-push-pr`; `wayfare-audit-plugin`'s own
next-steps already lead there.
