# How a task is shaped

The slice rule and the fine-tuning pass. Read before proposing any item in
`wayfare-sync-plan`, and before accepting one a person brings.

## Slices, not layers: every `story` task is SLC

**A `shape: story` task is a vertical slice through the whole system, shaped
like a user story, never a layer of one.** This is the shaping rule the rest of
the skill serves, and it is the one wayfare gets asked to break most often.

The rule is scoped to one shape on purpose. `structural`, `visual`, `defect`,
`dependency` and `docs` tasks are exempt, and all five for the same reason: the
surface already ships, so there is no story left to cut (docs/PLAN.md, *Shape*).
The exemption is narrow. **A task of any exempt shape that could have been
written as a user story was given the wrong shape**, and that is the finding.

Every `story` task must be **S**imple, **L**ovable, and **C**omplete:

- **Simple**: the smallest version of the story that still stands on its own.
- **Lovable**: a real person can use it and would want to. Not a stub, not a
  seam only the next task can reach.
- **Complete**: it works **every single time**, end to end, for the path the
  story names. Complete does **not** mean "everything": a slice that handles one
  currency completely is complete; one that handles all six currencies except
  that nothing renders is not.

So the roadmap is a sequence of stories, shaped
`AS_A user I_CAN do X SO_THAT Y`, each cutting through every layer it needs
(schema, service, route, UI, tests) to make that one story work. It is **not** a
sequence of layers that only add up to something usable at the end.

| Not a task (layer) | A task (slice) |
| -- | -- |
| "Data model for trips" | "I can save a trip and see it in my list" |
| "Trips API routes" | "I can rename a saved trip" |
| "Trips frontend" | "I can share a trip with a link that opens read-only" |

The architecture still matters, but it orders the **subtasks inside** a slice
(schema → structs → routes → frontend), never the tasks themselves. Layer names
belong on `## Subtasks` lines; a task *titled* for a layer is the smell that a
slice was sliced the wrong way.

**Complete is verified by looking, not by reading.** A slice can read correct in
source, with the right props, the right component and the right DoD line checked
off, and still fail Complete, because composition bugs (a crop that zooms into
an illegible fragment, an overflow, a broken breakpoint) are invisible in code
and only show up rendered. Any DoD line asserting a user-facing outcome,
"matches the target design," "renders correctly," "a visitor sees X", gets
verified by actually rendering the page and looking, not by re-reading the
component that was just written. See *Visual verification* under Step 0.

`depends_on` between tasks follows the **story**, not the stack: "edit a saved
trip" depends on "save a trip" because the earlier story must exist for the
later one to mean anything. It never encodes "the data model should come first".
Inside a slice, it already does. A roadmap where nearly every task depends on
the one before it has usually been cut horizontally; say so.

## Polish: the fine-tuning pass

Coverage and fidelity are different questions, and a sync that only asks the
first one declares a screen `done` while it looks wrong. **Coverage asks whether
the story ships; polish asks whether the shipped screen matches the design when
you put the two side by side and look.** A task can satisfy every line of its
Definition of Done and still sit on 20px of padding where the design has 32,
wrap a label the design keeps on one line, clip a card at the tablet breakpoint,
and render no focus ring at all. None of that is visible in a diff, and none of
it is what `uncovered` means.

So `sync` runs a **visual pass** over the screens that already ship, and what it
finds becomes `shape: visual` tasks. Visual is exempt from the SLC test for the
same reason `structural` is: it is not a story because the story already
shipped. It is the refinement of a surface that exists. A `visual` task that
could have been written as a user story is an `uncovered` task that was
mis-filed.

**Two sections own this pass and neither is optional.**
`references/reconciliation.md`'s *Reading a screen visually* owns **what to look
for**: the defect checklist and the three rules that keep the pass from becoming
a taste argument: compare like for like, a gap is a value and not an adjective,
and authority decides the direction before the row is written. *Visual
verification* under Step 0 owns **how to render**: extract the target with
`git -C "$SNAP" archive`, never `git checkout` in `$SNAP`, serve from a
throwaway server, one browser context per agent. Read both before the pass; what
follows is only what the pass *writes*.

**A visual divergence routes three ways, and choosing is the work:** a
`shape: visual` task when the code is wrong; a `signal` on `channel: design`
when the shipped surface is the better answer; a `signal` on
`channel: design-system` when the same wrong value comes out of an upstream
token or component and every consumer therefore has it (fixing that one locally
is the fork this skill forbids). Never let it default to the first. A round that
files every pixel difference as our bug is reconciling against a design the
product has legitimately overtaken.

**One item per screen or region, never per pixel.** Fifty one-line items is a
bug tracker, not a roadmap, and nobody will pick up the forty-ninth. Group the
findings for a screen into one item whose Definition of Done is the list of
measured assertions, ordered by how visible they are. Split only when two
regions of the screen would be fixed by different people in different files.

**Visual work never gates coverage, and nothing enforces that but you.**
`hero_ready_items` groups by status and never by type, so a `ready` visual task
with no `depends_on` lists as READY next to any task and wayfare-build-task will
offer it. The ordering is therefore a rule about *authoring*: a screen that is
half-built does not need its padding audited, and a roadmap that spends its next
three PRs on 4px is one that has stopped shipping. So give a visual task a
`depends_on` naming the tasks it must not jump, and propose it after the
coverage rows in the same report, so the sequencing has to be written into the
item, because the listing will not supply it. A screen whose own task is still
open needs no visual task at all: its drift belongs in that task's Definition of
Done.
