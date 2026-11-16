# Store writes: the channels a skill writes through

A skill writes where its channel says, never wherever the working tree happens
to be. Two channels are fixed here: an item's own fields, and `DESIGN.md`.

## Item writes

An item is written through `hero-lib.sh`, never by editing its file: under a
Wayfare server the item file is a read-only render.
`hero_item_set_status ID STATUS [RESOLUTION]` moves status,
`hero_item_set ID KEY VALUE` sets any other field,
`hero_item_tick ID "LINE TEXT"` ticks a Subtask or DoD line, and
`hero_item_log ID TAG "TEXT"` appends a dated `## Log` line.

Every status, `resolution`, `branch:` and `replaced_by` change goes through
those calls, in prose as in practice: an instruction to edit a `status:` or
`branch:` line by hand is the one the store layer exists to replace, and
`scripts/validate.sh` fails it in the routed skills and in `references/*.md`. A
resolution rides the status call (`hero_item_set_status ID done shipped`;
`promoted` and `obsolete` close an idea or anti-feature). `replaced_by` is set
with `hero_item_set ID replaced_by NEW`, only after
`hero_item_set_status ID dropped`, because it refuses an item that is not yet
dropped. The server has no field for it, so there it is a `replaced_by` log
line. On a server `ready`, `accepted` and `new` are a person's marks and the
status call refuses them.

## The DESIGN.md channel

`DESIGN.md` changes only in a commit on a branch that a live item owns. A skill
that has settled something `DESIGN.md` should say never writes it on the default
branch, whatever the file's state and bootstrap included: the working tree then
disagrees with the branch, the next architecture review reads that as drift, and
the change has no item to carry or review it.

**A branch a live item owns** is the current branch when it equals the `branch:`
of some item that is not `done` or `dropped`, read with `hero_item_field` so the
local and server stores answer the same way. Any other branch, including a
detached head, is treated as the default branch.

### A decision a planning pass settles

The entry is drafted as text, not written to the file. It goes in a
`## DESIGN.md` section on the governed item, or in the goal's `### Design` when
the item is a member of a goal that carries `## Plan`. The entry is the grilled
answers, in this shape and appended in date order:

```markdown
### YYYY-MM-DD — DECISION_TITLE

- Context: what forced a choice (the grilled Context answer)
- Decision: what was chosen, over what alternatives (fold the grilled
  Alternatives in here)
- Consequences: what this commits us to (fold the grilled Reversibility
  answer in here)
```

Applying it is work, so the item carries one Subtask, "Append the DESIGN.md
entry on this branch", and one DoD line, "`DESIGN.md` carries the YYYY-MM-DD
DECISION_TITLE entry". The build appends the entry to `## Decisions` on that
item's branch, and `wayfare:wayfare-review-architecture` owns the format. It
never touches `Last updated` or `Source ref`: only
`wayfare:wayfare-sync-architecture` moves the anchor, and an appender that moves
it claims the whole file matches that commit.

### A change the architecture skills confirm

`wayfare:wayfare-sync-architecture` applies confirmed edits only on a branch a
live item owns. Anywhere else it files one `shape: docs` task per run and writes
nothing, bootstrap included. The task's `## Context` holds the review findings,
its DoD holds the confirmed claims (for a bootstrap, the confirmed outline, one
line per section), and its Subtask is to apply them to `DESIGN.md` on its own
branch, which is where `Source ref` is stamped. Filing an item is a store write
like any other, so it follows the item channel above.

`wayfare:wayfare-review-architecture` reports the case that slipped through: a
`DESIGN.md` modified in the working tree on a branch no live item owns is an
`uncommitted` finding, and it fixes nothing.
