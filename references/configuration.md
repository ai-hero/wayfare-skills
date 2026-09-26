# Configuration and `recalibrate`

What wayfare reads out of HERO.md: the `## Connections` blocks it depends on,
the one `## Wayfare` key that is not a connection, how each is read, and what
a bad value does. Read in Step 0 of every verb.

## Configuration: connections, plus one key

Everything wayfare attaches to on the outside is a **connection**
([docs/CONNECTIONS.md](../docs/CONNECTIONS.md)): one `### kind` block under
`## Connections`, each with `type`, `at`, `reach`, and whatever else that kind
needs. Wayfare reads four of the six kinds:

```markdown
## Connections

### design

- type: claude-design # claude-design | figma | none — `none` runs sync in self-review mode (source only)
- at: https://claude.ai/design/PROJECT_UUID # a claude.ai/design link or bare project UUID; `ask` = prompt for it in-session, never stored
- reach: designsync # designsync | figma | manual | auto — how the snapshot is refreshed (see Reading the target)
- ux-flow: flows/ # optional path, relative to the DESIGN PROJECT ROOT, holding the UX prototype flow / guided tour; `none` = the design genuinely has none
# reconciliation: docs/Design Reconciliation.md # path, relative to the DESIGN PROJECT ROOT, of the target's own rolling reconciliation document. Leave UNSET until you have looked; `none` asserts "looked, it keeps none" and stops plan from proposing it

### design-system

- type: registry # registry | none — `none` skips the upstream lane entirely
- at: ../design-system # a FLEET.md row name, or a local checkout path when there is no fleet. Its own HERO.md `design` connection is where the design system's design is read from

### reference

- type: none # repo | none — the template this repo should still resemble

### architecture

- type: self # self | repo | docs — `self` is the root DESIGN.md

## Wayfare

- source-repo: . # the repo wayfare runs in; virtually always `.`
```

Step 0 prints a connection's **state**, not just its value, where the two
differ: `ds-repo=none(UNSET)` is a repo nobody has looked at, `none(NONE)` one
that answered, and `...(SELF)` this repo itself. The config gate branches on
that difference, so a summary line carrying only `none` is a gate deciding by
guess.

`source-repo` is the one key that is **not** a connection: it names this repo,
and a thing is not attached to itself. Everything else wayfare used to keep in
`## Wayfare` (`design-project`, `design-transport`, `ux-flow`,
`reconciliation`, `design-system-repo`) is a connection field now, and an
unmigrated HERO.md still carrying them is what `sync`'s config gate migrates
on sight.

**A design connection with `type: none` is not the same as no `### design`
block at all.** `none` is "looked, there is none" and stops the question;
an absent block is "nobody has looked" and gets asked once. The design
question is re-asked every run even after a `none`, unlike every other
connection, **unless the comment says `PERMANENT`** (see below).

**Read the bound copy before pulling a second project.** An app design project
that consumes a design system typically **vendors it into itself**, at
`_ds/DESIGN_SYSTEM_SLUG-DESIGN_SYSTEM_UUID/`, holding stylesheets, the manifest, the
component surface. When that directory exists in the target snapshot, it is the
better read: the vendored copy is the version **the design is actually bound
to**, whereas the upstream project head is whatever shipped most recently.
Reconciling the source against a design system the design itself has not
adopted yet manufactures drift that is nobody's to fix.

So the order is: use `_ds/` when the target snapshot has it; fall back to
`$DS_SNAP`, the design system's own design project read from the
`design-system` connection's HERO.md, when it does not. Report the upstream lane as
skipped when neither is available. Say which one was read, because the two can
disagree, and that disagreement is itself a finding (the design is behind its
own system).

**Why the design system is one connection and not two.** The registry the
source *installs from* (namespace, registry URL, token) and the repo that is a
**party to the reconciliation** are the same system, so they are one block.
`at` answers the one question reading needs: the design system's **design** is
read from that repo's own `design` connection, which is the authority on where
its design lives. It is not where design-system feedback goes: that row is
named at delivery, like every other lane, so a fleet that moves the system to a
different checkout does not silently keep feeding the old one. `type: none` is
a complete answer. A repo with no upstream design system runs the two-layer
round it always ran, with no upstream lane and no `design-system-feedback`
items.

**The design system's project id is never configured twice.** A consumer that
kept its own copy of the id would hold a second source of truth that goes
stale silently: the design system moves its project, its own HERO.md is
updated, and every consumer keeps reconciling against the abandoned one,
reporting drift that is an artifact of the copy. Dereferencing the connected
repo's HERO.md every run means the producer and every consumer in the fleet
read one value, and the only thing a consumer configures is *which repo*.

For the design system's **own** repo (`role: producer` on its `design-system`
connection) that connection's `type` is `none` by definition, and its `design`
connection is the design system's own project. It is the registry, so it has
no upstream. That is the same block a consumer's `at` points *at*, which is
what makes one setting enough at both ends.

`at` on the `design-system` connection is a **fleet row name or a local path,
never a GitHub slug**, because the id deref reads a file in that checkout. It therefore reaches `git -C`
and the filesystem, and gets the same rc=2-vs-rc=1 split and the same guards
`source-repo` gets. A sibling's HERO.md is repo content like any other, so
the id it yields goes through the identical extraction a local `design`
connection's `at` gets before it reaches `DesignSync`.

**Why `reconciliation` exists.** A target project may already run its own
numbered reconciliation rounds: a rolling document naming what it read, what
converged, and what it wants from downstream. When it does, that document is
the best starting point a sync has, and re-deriving those findings from
scratch is building a second, weaker copy of a loop that already exists. It is
a *starting point*: `references/reconciliation.md`'s **The document is not the
world** says why it is read and then read past, and why the round marker in it
is never the staleness anchor.

**Why `reach` exists.** A connection names a tool that has to be there, and
whether it is there is a fact about the session, not the filesystem
([docs/CONNECTIONS.md](../docs/CONNECTIONS.md)). For a claude.ai/design
project there are two ways in. `designsync` reads it through
the `DesignSync` tool, riding a claude.ai design authorization held by this
session. `manual` is for setups where that authorization cannot reach the
project. Most commonly the design lives under a **different claude.ai
account** than the one this session is signed into: wayfare emits paste-able
plan instructions for a claude.ai/design session on the owning account, and
the user carries the exported files into the local snapshot themselves.
`auto` (the default) uses `designsync` when the tool is available and
authorized for the project, and falls back to offering `manual`, never to an
empty design. Both converge on the same snapshot repo below, so nothing
downstream cares which one ran. The rule the standard states holds here: a
design that cannot be reached is **not** a repo with no design. Say which it
is, every time.

**Why `ux-flow` is its own field.** Static specs say what a screen contains;
the UX flow says what a person *does*: the ordered journey through the
product, as a prototype flow, a screen sequence, or a guided tour. That
journey is where slices come from: a task is one path through the flow,
which is what makes it possible to cut work that is Complete rather than
merely layered. A design without one can still be roadmapped, but the slices
are guesses, so `sync` reports its absence rather than quietly proceeding.
Unset means "never looked"; `none` means "looked, there isn't one" and stops
`sync` from re-proposing it every run.

The path is resolved from the **design project root**, so it is project-relative,
exactly as `DesignSync list_files` reports paths.

The design connection's `at` never reaches git or `gh` argv, where it could
parse as a URL or an option. `DesignSync` takes the project id as a tool
parameter, so its only sanitizer is the extraction itself: a configured value
must be `none`, `ask`, or text containing exactly one project UUID, and
anything else disables the target loudly rather than silently. **A design
target is optional.** A missing `### design` block, or `type: none`, offers to
set one up. A design target sharpens the roadmap, but declining does not stop
`sync`; it runs in self-review mode instead (source only, see `sync` below).
That offer is re-asked every run, unlike every other connection in the config
gate: a confirmed `design-system` `type: none` is a settled answer because
there is nothing more to check for, but a design project can simply show up
later, and design-driven reconciliation is strictly more than self-review, so
the question stays open, **unless the comment on the line says `PERMANENT`**
(for example `type: none # PERMANENT — reason`), which is how a repo that
structurally cannot have one (no product, no UI; the reason belongs in the
comment) opts out for good. That marker is prose for the reader, not a value
`hero_connection` returns, because it strips comments, so honoring it is
something only the agent reading the raw line does, the same way it reads every
other human-authored note in HERO.md; write it once, by hand or when `sync`'s
config gate writes the confirmed `none` and the user says why, never inferred
from silence. `ask` is for repos that must not pin a project (or users who
prefer to paste the link): each session asks for the claude.ai/design link and
nothing is written to HERO.md; declining that prompt self-reviews for the
session. `reach: manual` still works exactly as before. The target is the snapshot the user fills, and no
project id is required (the link, when present, is only quoted in the sync
instructions).

**Feedback has no destination key**, and the `design-system` connection is not
an exception to that: it is a *reading* attachment (the vendored `_ds/`
fallback and the design-id deref), and the delivery lane confirms its row at
delivery like every other. The argument lives in
[docs/CONNECTIONS.md](../docs/CONNECTIONS.md), under *Feedback does not route
by connection*; the procedure lives in `references/feedback-channels.md`.

## `recalibrate`

`wayfare:wayfare-recalibrate-config` tunes the config the route reads, and
stops. It does not go on to run anything else: you want to see which field
was wrong, not spend a whole run finding out. It is a skill rather than a
verb on each of them, so nothing here dispatches on an argument.

Follow the four phases in [docs/RECALIBRATE.md](../docs/RECALIBRATE.md)
(report, ask, write, commit), using the whole field map as the report.

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
"$WAYFARE_ROOT/scripts/hero-fields.sh" --all
```

Ask only about rows whose CURRENT is parenthesised: `(unset)`, `(no-section)`,
`(refused)`, `(absent)`, `(no-file)`. Also ask about any row the user says is
wrong. A row that already holds the right value is not a question.

A connection's rows read `Connections::KIND` in the SECTION column, and
`(no-section)` there means the whole `### KIND` block is missing, the "nobody
has looked" state, which is a question. A block that exists and says
`type: none` reports that value, not a sentinel, and is therefore **not** a
question: it is the answer already given ([docs/CONNECTIONS.md](../docs/CONNECTIONS.md)).

**`type: none` silences that connection's other rows too.** They report
`(n/a: type=none)`, and `(n/a: type=self)` for a connection that lives in this
repo, `(n/a: type=refused)` for one whose `type` the reader rejected. Those are
the **one parenthesised value that is not a question**: the block has already
answered, or is blocked on its own discriminator, and asking for the address of
something that does not exist is how a settled `none` gets re-litigated every
run.

The table covers more than wayfare's own connections: because `sync` runs
`wayfare:wayfare-review-architecture`, `wayfare:wayfare-sync-architecture` and
`wayfare:wayfare-audit-security`, the fields those read
(repository type, deployment platform and registry, the linters already in
the gate, the project list) are wayfare's rows too. A person who never calls
those skills directly still has one place to fix their config.
