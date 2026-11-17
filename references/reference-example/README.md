# reference/ (worked example)

**Fictional.** The Example Tool Library is invented for this page: a
volunteer-run library where neighbors borrow tools instead of buying them. It is
no customer, company or real library, and every name, number and person in it is
made up. It shows the format in [../reference-layer.md](../reference-layer.md)
at the depth the skills cite.

In a repo, this folder is `reference/` at the root.

## The tree

| File | Header | Layer |
| -- | -- | -- |
| `value-streams/lend-a-tool.md` | `value-stream: lend-a-tool@1` | 1. value stream |
| `capabilities.md` | `capability: tool-library@1` | 1. capability map |
| `entities/member.md` | `entity: member@1` | 2. entity |
| `entities/tool.md` | `entity: tool@1` | 2. entity |
| `entities/loan.md` | `entity: loan@2` | 2. entity |
| `processes/borrow-tool.md` | `process: borrow-tool@1` | 3. process |
| `processes/return-tool.md` | `process: return-tool@2` | 3. process |
| `flows/screens/catalog.md` | `screen: catalog@1` | 4. UX flow |
| `flows/screens/returns-desk.md` | `screen: returns-desk@1` | 4. UX flow |
| `flows/components/tool-card.md` | `component: tool-card@1` | 4. UX flow |
| `flows/components/condition-check.md` | `component: condition-check@1` | 4. UX flow |
| `prototype/README.md` | `prototype: tool-library@1` | 5. prototype |

`CHANGELOG.md` records the two bumps so far: `entity:loan@2` and
`process:return-tool@2`.

## One trace, top to bottom

Stage 5 of `lend-a-tool`, *Return and inspect*, is the constraint: returned
tools wait for a volunteer to check them, so they sit on the returns shelf
instead of going back on loan. `process:return-tool@2` realizes that stage. Its
`inspect` step touches `loan.condition_on_return` and `tool.status`, which
`entity:loan@2` and `entity:tool@1` define. `screen:returns-desk@1` serves that
step and places `component:condition-check@1`, whose **Save check** affordance
writes the condition and moves the tool to `available` or `in-repair`. The
prototype's seed holds one returned drill waiting on the shelf, so a person can
click through that step before any code exists.

## What the skills do with it

- An item that builds the returns desk opens its `## Context` with
  `Reference: screen:returns-desk@1, component:condition-check@1, process:return-tool@2, entity:loan@2`.
- An item planned last month and pinned to `entity:loan@1` is listed as stale,
  with the `entity:loan@2` changelog line that says what it must re-check.
- A change to the catalog that adds a filter by tool category, with no pin and
  no edit here, is a behavior change the reference does not describe.
