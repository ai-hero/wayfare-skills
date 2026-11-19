# The reference layer, worked example

**Fictional.** The Example Tool Library is invented for this page: a
volunteer-run library where neighbors borrow tools instead of buying them. It is
no customer, company or real library, and every name, number and role in it is
made up. It shows the format in [../reference-layer.md](../reference-layer.md)
at the depth the skills cite.

The example has two folders because the format has two homes:

| Folder | Stands for | Holds |
| -- | -- | -- |
| [fleet/](./fleet/) | `reference/` in the library's fleet repo, beside `FLEET.md` | business (vision, strategy, market, value streams, capabilities) and organization (structure, roles, governance) |
| [app/](./app/) | `reference/` in the library's lending app | personas, entities, processes, UX flow, prototype |

Every pin in `app/` resolves to a file in `fleet/` or `app/` at that version.

## One trace, top to bottom

Stage 5 of `value-stream:lend-a-tool@1`, *Return and inspect*, is the
constraint: returned tools wait for a volunteer to check them, so they sit on
the returns shelf instead of going back on loan. The stream serves
`goal:tools-that-work@1`, owned by `role:repair-volunteer@1`.

In the app, `process:return-tool@2` realizes that stage, uses
`capability:returns@1` and `capability:condition-tracking@1`, and hands a broken
tool to `decision:retire-a-tool@1`. Its actor is `persona:shift-volunteer@1`, a
persona that cites `role:desk-volunteer@1`. Its `inspect` step touches
`loan.condition_on_return` and `tool.status`, which `entity:loan@2` and
`entity:tool@1` define. `screen:returns-desk@1` is for that persona, serves that
step and places `component:condition-check@1`, whose **Save check** affordance
writes the condition and moves the tool to `available` or `in-repair`. The
prototype's seed holds one returned drill waiting on the shelf, so a person can
click through that step before any code exists.

## What the skills do with it

- An item that builds the returns desk opens its `## Context` with
  `Reference: screen:returns-desk@1, component:condition-check@1, process:return-tool@2, entity:loan@2, role:desk-volunteer@1`.
  The last pin resolves through the fleet repo's checkout.
- In a clone with no fleet checkout beside it, that last pin reads
  `unresolved: no fleet reference`: the business layer is unverified, the run
  goes on, and nothing writes a local copy of the role.
- A build that needs a new role, say a volunteer who only runs repair evenings,
  starts with a fleet PR that adds the role at `@1`; the app item pins it and
  depends on that PR, which merges first.
- An item planned last month and pinned to `entity:loan@1` is listed as stale,
  with the `entity:loan@2` changelog line that says what it must re-check.
