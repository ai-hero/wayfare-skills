# The reference layer: what the app is meant to be, written before the code

A reference describes the product as it is meant to be, top-down, before any
code exists for it: the customer's business and organization, then each app's
personas, entities, processes, UX flow, and a throwaway prototype. An agent that
builds from a mockup sees one state of one screen; the reference also gives it
the entities, the rules, the steps and the business reasons that the mockup
hides. The reference is what the production app is built from, so every field
below is one a lower layer or the build consumes.

**Everything here applies only when the repo has `reference/`.** Every skill
hook calls `hero_reference_dir` first, and when it returns 1 the hook is skipped
without a word: no question, no line in a report, no `Reference:` line. A repo
without the folder behaves exactly as it did before this layer existed.

[reference-example/](./reference-example/) is one fictional customer traced
through both homes. The skills cite it; read it beside this page.

## Two homes

What we know about one customer's business and organization is written once, in
that customer's **fleet repo**. Each **app repo** keeps what is its own and
cites the fleet by pin.

| Home | Where | Holds |
| -- | -- | -- |
| fleet repo | `reference/` beside `FLEET.md` and the compliance register, in the register checkout every machine clones as `.fleet/` | `business/` (vision, strategy, market, value streams, capabilities) and `organization/` (structure, roles, governance) |
| app repo | `reference/` at the repo root | `personas/`, `entities/`, `processes/`, `flows/`, `prototype/` |

One customer has one fleet repo. A second repo per customer beside the register
was rejected (two pins, two clones, an arbitrary split), and so was business in
the app repos (one copy per app, and the copies drift). A fleet that holds
several customers' apps holds only its own customer's business in its register;
another customer gets its own fleet repo.

The fleet repo is private and reviewed by PR. Its empty version, every field a
placeholder, is what `hero_reference_fleet_scaffold` writes.

## The layers

### In the fleet repo

| Layer | Holds | Where |
| -- | -- | -- |
| Business | vision, strategy goals, market, value streams, capabilities | `business/vision.md`, `business/strategy.md`, `business/market.md`, `business/value-streams/VERB-NOUN.md`, `business/capabilities.md` |
| Organization | units and reporting lines, roles, governance decisions | `organization/structure.md`, `organization/roles/ROLE.md`, `organization/governance.md` |

### In the app repo

| Layer | Holds | Where |
| -- | -- | -- |
| 1. Personas | one app's view of a person in a role or a segment | `personas/NAME.md` |
| 2. Entities | identity, grain, attributes, relationships, rules, owned or separate | `entities/NAME.md` |
| 3. Processes | purpose, the stage it realizes, steps, actor, the entities each step touches | `processes/NAME.md` |
| 4. UX flow | per screen: what it loads, what it places, its states; per component: what it takes, its affordances | `flows/screens/NAME.md`, `flows/components/NAME.md` |
| 5. Prototype | a runnable click-through on in-browser SQLite, cheap enough to throw away | `prototype/` |

## The fields

The fleet files hold these fields and no others. A free-form topic page was
rejected: the build cannot cite a field nobody defined.

| File | Fields |
| -- | -- |
| `business/vision.md` | mission, vision, customer outcome |
| `business/strategy.md` | per goal id: statement, measure, target, horizon, owner role |
| `business/market.md` | segments (id, who, need) and offerings (id, what, segment) |
| `business/value-streams/VERB-NOUN.md` | trigger, stages, outcome, owner role, `serves:` goal, where AI changes the work |
| `business/capabilities.md` | per capability id: what, the stages that use it |
| `organization/structure.md` | units, reporting lines |
| `organization/roles/ROLE.md` | purpose, responsibilities, unit |
| `organization/governance.md` | per decision: what, decides, approves, consulted |

No named people: a role is a job, not the person holding it this year. No board
or executive biographies.

A field nobody knows yet reads `unknown`, never a guess. A value stream stays a
hypothesis until its measures are taken, and says so.

### Value streams

A value stream describes the business, not an app. It draws on three public
bodies of work:

- **BIZBOK** (Business Architecture Guild) for the shape: a stream named
  verb-noun, a trigger, an outcome, and stages that each carry entrance and exit
  criteria, a value item, the participating roles and the enabling capabilities.
- **Lean value stream mapping** (Rother and Shook, *Learning to See*) for the
  measures on each stage (volume, lead time, process time, percent complete and
  accurate, and the source of each number, `unknown` until measured) and for
  typing every issue as one of the eight wastes: defects, overproduction,
  waiting, unused talent, transportation, inventory, motion, extra processing.
- **Theory of Constraints** (Goldratt, *The Goal*) for marking the one stage
  that limits throughput, and for ranking work at the constraint first.

*Where AI changes the work* gives each stage the AI opportunity (`automate`,
`augment`, `agent` or `none`), readiness (data, a system of record, risk) and a
priority. Open **Questions** close the file, each saying how it would be
answered. A stage that no app process realizes yet is where an agent proposes
new app reference files; the stream itself never lists the processes, because it
is shared by every app.

### Personas and roles

A **role** is a job in the customer's organization, shared by every app. A
**persona** is one app's view of a person, and cites what it is a view of: a
person inside the organization cites `role:ID@VERSION`, a person the customer
serves cites `segment:ID@VERSION`, and a persona that is both cites both. A
persona file holds its `cites:` line, what the person does in this app, their
context, what they need from the screens, and what frustrates them today.

### Entities, processes, flows, prototype

- **Entity:** owned by this app or by another system; identity; grain (one per
  what); an attribute table (name, type, required, notes); relationships with
  cardinality; rules a build must enforce.
- **Process:** a purpose line; `realizes: value-stream:ID@VERSION stage N`;
  `uses:` the capabilities; `follows:` the governance decisions it carries out;
  and a step table (step id, actor as a persona pin, the entity or field it
  touches, what happens).
- **Screen:** `serves:` process steps; `for:` the personas who use it; **Loads**
  (what, when, and what it refreshes); **Places** (the components); **States**
  (each with when and what it shows, error states included).
- **Component:** `used on:` screens; **Takes**; **Affordances**, each with its
  condition, the call, the field it changes and where the person lands;
  **States**.
- **Prototype:** a README carrying the header, `schema.sql` written from the
  entities, `seed.sql` that reaches every state the flows name, and a docked
  guided tour that walks the processes. It is rebuilt from the seed on every
  start and keeps nothing.

## Headers, pins and versions

A reference file opens with its header: one line per id it defines,
`KIND: ID@VERSION`, for example `entity: loan@2`. Most files define one id. A
fleet file that is a table of ids (`strategy.md`, `market.md`,
`capabilities.md`, `structure.md`, `governance.md`) opens with one header line
per row, so `goal: more-loans@1` and `goal: tools-that-work@1` sit at the top of
`strategy.md`. **Put a blank line between header lines**: a Markdown formatter
such as mdformat joins adjacent lines into one paragraph, and a joined header
defines nothing. `README.md` and `CHANGELOG.md` carry none.

| Kind | Home | Defined in |
| -- | -- | -- |
| `vision` | fleet | `business/vision.md` |
| `goal` | fleet | `business/strategy.md`, one per row |
| `segment`, `offering` | fleet | `business/market.md`, one per row |
| `value-stream` | fleet | `business/value-streams/VERB-NOUN.md` |
| `capability` | fleet | `business/capabilities.md`, one per row |
| `unit` | fleet | `organization/structure.md`, one per row |
| `role` | fleet | `organization/roles/ROLE.md` |
| `decision` | fleet | `organization/governance.md`, one per row |
| `persona` | app | `personas/NAME.md` |
| `entity`, `process`, `screen`, `component`, `prototype` | app | their layer's folder |

A **pin** is `KIND:ID@VERSION` with no space, for example
`role:desk-volunteer@1`. Pins are names, not paths, so a file can move without
rewriting one.

- **Versions are integers**, `@1`, `@2`, one per id. A section has no version of
  its own.
- **Bump only when the meaning changes**: something a build pinned to the old
  version would now do wrong. An attribute, a relationship or its cardinality, a
  rule, a process step or its order, what a screen loads, a screen state, what
  an affordance writes, a stage, measure or answered question, a goal's target,
  a role's responsibilities, who approves a decision.
- **Never bump for wording**: a typo, a clearer sentence, an added example.

Each bump adds one line to that home's `reference/CHANGELOG.md`, newest first,
saying what changed and what an item pinned to the old version must re-check:

```
- entity:loan@2: `due_on` is now required at checkout; a build pinned to @1 must reject a loan without one.
```

An agent reads that line, not the git diff. A changelog line may name several
pins when one change bumped several ids.

## Links point up

Within the reference, a file names only what sits above it:

- **`organization/` names nothing below it.** A role names its unit; nothing in
  the organization names a goal, a stream or an app.
- **`business/` names owner roles**, and its own ids: a stream `serves:` a goal
  and its stages name capabilities. It never names an app file.
- **App files cite up into the fleet.** A persona cites a role or a segment; a
  process cites a value stream stage, a capability, a persona and a governance
  decision; a screen cites a persona. An app file below them names the app ids
  above it: a screen `serves:` process steps, a component affordance names the
  entity field its call changes.

Work points at the reference; the reference never points at the work.

- **An item pins what it builds.** The first line of its `## Context` is
  `Reference: KIND:ID@VERSION, KIND:ID@VERSION`, naming every reference file the
  change builds or changes, fleet pins included, at the version it builds
  against.
- **A PR carries the same line** in its body, the union of its items' pins.
- **A reference file names no code path.** No `src/...`, no file the build will
  write, nothing that moves when the code does. The reference and the code meet
  only at names: entity attributes, process step ids, screen and component ids,
  call names. The prototype's own files are inside `reference/` and are exempt.

When the build finds the reference wrong, the reference changes in the same PR,
with its bump and its changelog line, and the pin names the new version.

## Resolving a pin

An app resolves a pin in its own `reference/` first, then in the fleet repo's
`reference/` in the register checkout, `../.fleet/reference/` from an app cloned
beside it. `hero_reference_resolve` does both.

**A missing fleet is unverified, never invented.** When a fleet-kind pin does
not resolve in the app and no register checkout (or no `reference/` in it) is in
reach, the pin is reported `unresolved: no fleet reference` and the business
layer is **unverified**. The run continues: a standalone clone still plans and
builds. Nothing writes a local stand-in for the missing file: a copy of a role
or a goal in the app is the drift two homes exist to prevent.

App CI does not check fleet pins, since an app's CI has no register checkout.
The fleet audit does: check REF-01 in `scripts/audit.py` fails a repo that cites
a fleet-kind pin, under `reference/` or on an open plan item's `Reference:`
line, whose id at that version is not on the register's `origin/main`. Run it
for the whole fleet with
`(cd "$WAYFARE_ROOT" && env -u VIRTUAL_ENV -u CONDA_PREFIX -u UV_PYTHON -u UV_PROJECT_ENVIRONMENT uv run --no-config --quiet scripts/audit.py --fleet FLEET_FOLDER --control REF-01)`.

## Changing a business fact

**Fleet PR first; the app PR depends on it.** A build that needs a new or
changed business or organization fact proposes the fleet edit as its first
Subtask: a PR to the fleet repo with the version bump and its changelog line.
The app item pins the new version and depends on that PR, and the fleet PR
merges first. Until it does, the app's pin is not on the register's
`origin/main` and REF-01 fails, which is the order holding.

## Confidentiality

wayfare is public, so its worked example is fictional. The fleet scaffold, and a
fleet template made from it, carry placeholders only. A customer's real strategy
lives only in that customer's private fleet repo, never in an app repo another
team can read and never in this plugin.

## Starting a reference

`hero_reference_scaffold [ROOT]` writes the app home: `README.md` pointing here,
an empty `CHANGELOG.md`, and an empty folder for each app layer (`personas/`,
`entities/`, `processes/`, `flows/screens/`, `flows/components/`, `prototype/`).
`hero_reference_fleet_scaffold [ROOT]`, run in the fleet repo, writes the fleet
home: `README.md`, `CHANGELOG.md`, and every business and organization file with
every field a placeholder. Placeholder headers are upper case (`role: ROLE@1`),
so nothing indexes or resolves until someone fills the file in. Both refuse a
repo that already has `reference/`. The first real content is written by
planning, not by a scaffold.

## Where the line sits

`PRODUCT.md` is the whiteboard view: what the product does, one statement per
feature. `DESIGN.md` is how the code is structured. `reference/` is what the app
is meant to be, entity by entity and screen by screen, with the business it
serves in the fleet repo. Each names the others by id where it needs to and
copies none of their detail.

## The functions

All in `scripts/hero-lib.sh`. Each one that reads the folder returns 1 when the
repo has none; `hero_reference_pr_body` then returns the body unchanged.

| Function | Prints |
| -- | -- |
| `hero_reference_dir [ROOT]` | the folder's path |
| `hero_reference_fleet_dir [ROOT]` | the register checkout's `reference/` for the repo at ROOT; rc 1 when there is none |
| `hero_reference_scaffold [ROOT]` | nothing; writes the app home, rc 1 when the folder exists |
| `hero_reference_fleet_scaffold [ROOT]` | nothing; writes the fleet home, rc 1 when the folder exists |
| `hero_reference_index [ROOT]` | every header line as `kind:id`, its version, its path |
| `hero_reference_pins FILE...` | the pins on FILE's `Reference:` lines (`-` reads stdin) |
| `hero_reference_resolve FILE [ROOT]` | each pin, its current version (`none` when gone, `unresolved: no fleet reference` when a fleet pin has no fleet to look in), its path |
| `hero_reference_line FILE...` | one `Reference:` line with every pin |
| `hero_reference_branch_line [BRANCH] [ROOT]` | that line for every item whose `branch:` is BRANCH |
| `hero_reference_stale [ROOT]` | each open item pinned behind its file, with the changelog entries between |
| `hero_reference_code_paths [ROOT]` | each line of a reference file that names a code path |
| `hero_reference_unbumped BASE [ROOT]` | each reference file changed since BASE with its header unmoved |
| `hero_reference_pr_body BODY [ROOT]` | BODY with the branch's line after its `## Summary` paragraph |

## The hooks

Each skill carries a few lines that point here; none restates the format.

| Skill | What it does (each gated on `hero_reference_dir`) |
| -- | -- |
| wayfare-grill-idea, wayfare-one-shot | **Propose the reference edit first, then pin it.** Before the plan, read the files the work touches. When the reference already says what the work builds, pin those files at their current versions. When the work changes what a file means, the first Subtask is that edit (with its bump and changelog line), shown to the person with the plan, and the pin names the new version. When no file covers it, propose the new file at `@1` the same way. When the edit is to a business or organization fact, the first Subtask is the fleet PR and the app item depends on it. A pin `hero_reference_resolve` prints as `unresolved: no fleet reference` is stated in the plan as an unverified business layer; nothing is written in its place. The pin is the first line of the item's `## Context`. |
| wayfare-write-handoff | Carries the item's `Reference:` line into the handoff unchanged, and pins what the session changed in `reference/`. |
| wayfare-build-task | Before the first edit, runs `hero_reference_resolve` on the item and reads every pinned file. A pin behind its file is checked against the changelog entries between; one that contradicts the plan, or a pin with no file, is a Step 2 ambiguity. An unresolved fleet pin is reported as an unverified business layer and the build continues. |
| wayfare-push-pr | Passes the PR body through `hero_reference_pr_body`, which adds the branch's `Reference:` line under the summary. |
| wayfare-review-pr | Flags a behavior change whose PR has no `Reference:` line, and each `hero_reference_code_paths` hit, as Important; warns on each `hero_reference_unbumped` file whose diff changed meaning. |
| wayfare-sync-plan | Reports `hero_reference_stale` as **reference-stale** in the source lane, quoting the changelog entries. |
| wayfare-init-repo | Offers `hero_reference_scaffold` once, only when the repo has no `reference/`. |
| wayfare-model-data | Starts from the entities the work touches: identity, grain, attributes, relationships, rules. |
| wayfare-recomponentize-ui | Starts from the screens and components in `flows/`, their states included. |
| wayfare-sync-product, wayfare-sync-architecture | State the line between `PRODUCT.md`, `DESIGN.md` and `reference/` (*Where the line sits*). |
