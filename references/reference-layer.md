# The reference layer: what the app is meant to be, written before the code

Some repos keep a `reference/` folder at their root. It describes the app as it
is meant to be, top-down, before any code exists for it: where the business
creates value, the entities, the processes, the UX flow, and a throwaway
prototype. An agent that builds from a mockup sees one state of one screen; the
reference also gives it the entities, the rules and the steps that the mockup
hides.

**Everything here applies only when the repo has `reference/`.** Every skill
hook calls `hero_reference_dir` first, and when it returns 1 the hook is skipped
without a word: no question, no line in a report, no `Reference:` line. A repo
without the folder behaves exactly as it did before this layer existed.

[reference-example/](./reference-example/) is one fictional product traced
through every layer. The skills cite it; read it beside this page.

## The five layers

| Layer | Holds | Where |
| -- | -- | -- |
| 1. Value streams and capabilities | where the business creates value: stages, their measures, the constraint, issues, where AI should change the work | `value-streams/VERB-NOUN.md`, `capabilities.md` |
| 2. Entities | identity, grain, attributes, relationships, rules, owned or separate | `entities/NAME.md` |
| 3. Processes | purpose, steps, actor, the entities each step touches, and the stage it realizes | `processes/NAME.md` |
| 4. UX flow | per screen: what it loads, what it places, its states; per component: what it takes, its affordances | `flows/screens/NAME.md`, `flows/components/NAME.md` |
| 5. Prototype | a runnable click-through on in-browser SQLite, cheap enough to throw away | `prototype/` |

Each layer points at the one above it by id, never down. A process says which
stage it `realizes`; a screen says which process steps it `serves` and which
entity fields it shows; a component's affordance names the call it makes and the
entity field that call changes.

### Value streams

A value stream describes the business, not the app. It draws on three public
bodies of work:

- **BIZBOK** (Business Architecture Guild) for the shape: a stream named
  verb-noun, a triggering stakeholder, a value proposition, and stages that each
  carry entrance and exit criteria, a value item, the participating stakeholders
  and the enabling capabilities. `capabilities.md` is the capability map the
  stages point into, one row per capability with its owner, the systems that
  serve it today, and its heat (`strong`, `adequate`, `weak`).
- **Lean value stream mapping** (Rother and Shook, *Learning to See*) for the
  measures on each stage (volume, lead time, process time, percent complete and
  accurate, and the source of each number, `unknown` until measured) and for
  typing every issue as one of the eight wastes: defects, overproduction,
  waiting, unused talent, transportation, inventory, motion, extra processing.
- **Theory of Constraints** (Goldratt, *The Goal*) for marking the one stage
  that limits throughput, and for ranking work at the constraint first.

On top of those, each stage gets our assessment: the AI opportunity (`automate`,
`augment`, `agent` or `none`), readiness (data, a system of record, risk) and a
priority. A **Realized by** table lists the processes that realize each stage; a
stage no process realizes yet is where an agent proposes new reference files.
Open **Questions** close the file, each saying how it would be answered. A
stream is a hypothesis until its measures are taken, and says so.

### Entities, processes, flows, prototype

- **Entity:** owned by this app or by another system; identity; grain (one per
  what); an attribute table (name, type, required, notes); relationships with
  cardinality; rules a build must enforce.
- **Process:** a purpose line, `realizes: STREAM@VERSION stage N`, and a step
  table (step id, actor, the entity or field it touches, what happens).
- **Screen:** `serves:` process steps; **Loads** (what, when, and what it
  refreshes); **Places** (the components); **States** (each with when and what
  it shows, error states included).
- **Component:** `used on:` screens; **Takes**; **Affordances**, each with its
  condition, the call, the field it changes and where the person lands;
  **States**.
- **Prototype:** a README carrying the header, `schema.sql` written from the
  entities, `seed.sql` that reaches every state the flows name, and a docked
  guided tour that walks the processes. It is rebuilt from the seed on every
  start and keeps nothing.

## Headers and versions

Every reference file opens with one header line, `KIND: ID@VERSION`, for example
`entity: loan@2`. The kinds are `value-stream`, `capability`, `entity`,
`process`, `screen`, `component` and `prototype`. `README.md` and `CHANGELOG.md`
at the folder's root carry none.

- **Versions are integers**, `@1`, `@2`, one per file. A section has no version
  of its own.
- **Bump only when the meaning changes**: something a build pinned to the old
  version would now do wrong. An attribute, a relationship or its cardinality, a
  rule, a process step or its order, what a screen loads, a screen state, what
  an affordance writes, a stage, measure or answered question.
- **Never bump for wording**: a typo, a clearer sentence, an added example.

Each bump adds one line to `reference/CHANGELOG.md`, newest first, saying what
changed and what an item pinned to the old version must re-check:

```
- entity:loan@2: `due_on` is now required at checkout; a build pinned to @1 must reject a loan without one.
```

An agent reads that line, not the git diff. A changelog line may name several
`kind:id@version` tokens when one change bumped several files.

## Links point one way

Work points at the reference; the reference never points at the work.

- **An item pins what it builds.** The first line of its `## Context` is
  `Reference: KIND:ID@VERSION, KIND:ID@VERSION`, naming every reference file the
  change builds or changes, at the version it builds against.
- **A PR carries the same line** in its body, the union of its items' pins.
- **A reference file names no code path.** No `src/...`, no file the build will
  write, nothing that moves when the code does. The reference and the code meet
  only at names: entity attributes, process step ids, screen and component ids,
  call names. The prototype's own files are inside `reference/` and are exempt.

When the build finds the reference wrong, the reference changes in the same PR,
with its bump and its changelog line, and the pin names the new version.

## The functions

All in `scripts/hero-lib.sh`. Each one that reads the folder returns 1 when the
repo has none; `hero_reference_pr_body` then returns the body unchanged.

| Function | Prints |
| -- | -- |
| `hero_reference_dir [ROOT]` | the folder's path |
| `hero_reference_index [ROOT]` | every headed file as `kind:id`, its version, its path |
| `hero_reference_pins FILE...` | the pins on FILE's `Reference:` lines (`-` reads stdin) |
| `hero_reference_resolve FILE [ROOT]` | each pin, the file's current version (`none` when gone), its path |
| `hero_reference_line FILE...` | one `Reference:` line with every pin |
| `hero_reference_branch_line [BRANCH] [ROOT]` | that line for every item whose `branch:` is BRANCH |
| `hero_reference_pr_body BODY [ROOT]` | BODY with the branch's line after its `## Summary` paragraph |

## The hooks

Each skill carries a few lines that point here; none restates the format.

| Skill | When `reference/` exists |
| -- | -- |
| wayfare-grill-idea, wayfare-one-shot | **Propose the reference edit first, then pin it.** Before the plan, read the files the work touches. When the reference already says what the work builds, pin those files at their current versions. When the work changes what a file means, the first Subtask is that edit (with its bump and changelog line), shown to the person with the plan, and the pin names the new version. When no file covers it, propose the new file at `@1` the same way. The pin is the first line of the item's `## Context`. |
| wayfare-write-handoff | Carries the item's `Reference:` line into the handoff unchanged, and pins what the session changed in `reference/`. |
| wayfare-build-task | Before the first edit, runs `hero_reference_resolve` on the item and reads every pinned file. A pin whose version is behind the file is re-read against its changelog lines, and a pin with no file is a Step 2 ambiguity. |
| wayfare-push-pr | Passes the PR body through `hero_reference_pr_body`, which adds the branch's `Reference:` line under the summary. |
