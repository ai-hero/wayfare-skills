# The work-item format

What `wayfare:wayfare-grill-idea` writes, read at its Step 4 before any item is
emitted. One markdown file per item at `.plans/items/NNN-slug.md`:

```markdown
---
id: 7 # a plain integer; only the filename is zero-padded (007-slug.md) for sorting
type: task # every item is a wayfare item
shape: story # story | structural | visual | defect | dependency | docs — see docs/PLAN.md
origin: wayfare-grill-idea # the producer that wrote this item
title: I can sign in with the device flow # a user story for a `story` task; the structural change for a `structural` one
status: planning # new | accepted | planning | ready | active | committed | review | done | dropped  (planning = awaiting the user's ready-mark; readiness is DERIVED, not stored; committed = on a goal's branch, unmerged; a non-empty awaiting: suspends the item at whatever status it holds, docs/MESSAGES.md)
resolution: # set only at done — shipped on a task; the full set is in docs/PLAN.md
depends_on: [3, 5] # ids that must be `done` before this can start — blockers only
discovered_from: 4 # optional; the item this was found while working — provenance, never blocks
one_way_door: false # true = expensive to reverse; got extra scrutiny
source: services/auth/ # paths in the source repo this changes
# target: auth/ — paths in the design project this satisfies; absent when the repo has no design target
anchors:
  source: FULL_COMMIT_SHA # source head planned against
success: "User completes device-flow login in under 30s; e2e test green"
---

## Context

Why this work exists — the principal-level framing, not a restatement of the title.

## Non-goals

What is explicitly out of scope for this item.

## Approach

The chosen approach and why it won over the alternative(s) considered,
including the quicker one that was not taken and what it would have cost. A
plan that reads as if only one option existed cannot be reviewed.

## Failure modes

How it can break and the blast radius of each.

## Subtasks

- [ ] 1. Ordered checklist — how it gets built, cutting down through the layers of this one slice; wayfare-build-task checks lines off as it goes

## Definition of Done

- [ ] What must be observably true when it ships — at least one line states the story working end to end

## Notes

Second-order effects, ongoing cost, and any open question still worth flagging.

## Log

- YYYY-MM-DD (author) note: dated, append-only lines; the build appends its `mistake` and `signal` lines here, and docs/PLAN.md says what goes in each
```

`## Subtasks`, `## Definition of Done`, and `## Log` come from wayfare's Item
formats and are required on every item: wayfare-build-task works `## Subtasks`,
gates close-out on `## Definition of Done`, and records PR URLs in `## Log`. An
item without them is a legacy item, readable but not what any skill writes
today. `## Log` belongs to the build rather than to planning. Emit it empty on a
task, and a build creates it on any item whose format has none.

Keep the body proportional to the risk: a two-way-door chore might have a
one-line Approach and empty Non-goals; a one-way-door schema change earns every
section. The frontmatter fields are always present, with two exceptions:
`discovered_from` appears only on items that were found while working another,
and `ready_marked:`, a `YYYY-MM-DD` date stamped by wayfare-grill-idea's Step 5
flip, appears from the moment the user marks the item ready. This block is the
canonical field definition: the status enum and `ready_marked:` semantics are
defined here, and where other skills (wayfare, harden, handoff) show frontmatter
of their own they follow these meanings rather than reinventing them (the status
enum is the one lifecycle in `docs/PLAN.md` and `ready_marked:` keeps its
meaning). `type`, `shape` and `origin` are defined by `docs/PLAN.md`. **Every
producer writes them**: wayfare (`sync`), wayfare-grill-idea,
`wayfare:wayfare-build-task` (Step 2a carve-outs),
`wayfare:wayfare-write-handoff`, and `wayfare:wayfare-audit-security`, each
stamping its own name as `origin`. Schema 1 requires `type`; an item without one
lists as invalid.
