# The connections standard

What a repo is attached to on the outside, declared in one place, in one shape.
`scripts/hero-lib.sh` reads it (`hero_connection`, `hero_connections`),
`scripts/hero-fields.sh` maps it, and `wayfare:wayfare-recalibrate-config` tunes
it.

## The principle

A repo is not self-contained. Its design lives in Figma or a claude.ai/design
project, its primitives come from a component registry, it was cloned from a
template it should still resemble, its architecture may be written down
somewhere else entirely, its infrastructure is Terraform in another repo, and
its tickets are in Linear or GitHub.

Each of those is a **connection**: something outside this repo that this repo
reads, conforms to, or reports to.

> **A connection has a kind, a type, a locator, and a way to be reached. It may
> also be absent, and absent is an answer, not a gap.**

Before this, each attachment invented its own config: a key here, a whole
`## Section` there, one of them a GitHub slug, another a local path, a third a
UUID, and no two agreeing on what "not set up" meant. The cost is not tidiness.
A repo with no component registry and a repo whose registry is merely
unreachable need different fixes, and config that cannot tell them apart sends
every run down the same silent fallback.

## The kinds

Six, and the list is closed. A new kind is a change to this file, because every
kind is something a skill knows how to *use*; a name nothing reads is config
theatre.

| Kind | What it is | Typical `type` |
| -- | -- | -- |
| `design` | where the product's design lives: the surface being built toward | `claude-design`, `figma` |
| `design-system` | the component registry the UI sources primitives from | `registry` |
| `reference` | the template or reference implementation this repo should still resemble | `repo` |
| `architecture` | where the architecture record lives, when it is not this repo's own `DESIGN.md` | `repo`, `docs`, `self` |
| `infrastructure` | the repo holding this system's Terraform, Kubernetes manifests, or equivalent | `terraform`, `kubernetes`, `self` |
| `issues` | the tracker work is filed in | `github`, `linear` |

**`self` is available to every kind**, and it is not a synonym for `none`.
`self` says the thing exists and lives in this repo: the architecture record is
the root `DESIGN.md`, the Terraform is in `infra/` here. `none` says it does not
exist anywhere. Collapse them and a repo that holds its own IaC is
indistinguishable from one with no infrastructure at all, which is the
three-state rule below losing a state one kind at a time.

`design` and `design-system` are **different connections and always will be**.
One is the product's own surface; the other is the vocabulary that surface is
drawn in. They are owned by different people, answered on different evidence,
and a repo routinely has one without the other.

## The block

```markdown
## Connections

### design

- type: claude-design # claude-design | figma | none
- at: 6f1c2e88-0a3d-4c77-9d21-8b5e2f4a1c90
- reach: designsync # the MCP tool, CLI, or `checkout` that reads it; `manual` = a person carries the files
- ux-flow: flows/ # kind-specific, resolved inside the connection
- reconciliation: docs/Design Reconciliation.md

### design-system

- type: registry
- at: ../design-system # a FLEET.md row name, or a path when there is no fleet
- reach: checkout
- role: consumer # consumer | producer
- namespace: "@aihero"
- registry-url: https://design.aihero.studio/r/{name}.json
- token-env-var: REGISTRY_TOKEN

### issues

- type: github
- at: acme/web
- reach: gh
- issue-prefix: none

### infrastructure

- type: none # looked, this system has no IaC repo
```

Four keys are universal; everything else in a block is specific to that kind and
documented where the kind is used.

| Key | Holds |
| -- | -- |
| `type` | which flavour of this kind, or `none` |
| `at` | the locator the `type` expects: a UUID, a `FLEET.md` row name, a path, an `OWNER/NAME`, a workspace |
| `reach` | what must exist in the session to read it: an MCP tool name, a CLI binary, `checkout`, or `manual` |
| the rest | kind-specific |

**The grammar is HERO.md's**, because it *is* HERO.md: same `- key: value`
lines, same reader, same guards. A value that starts with `-` or carries a
control character is refused and never used.

Two keys get a shape on top of that, because they reach a command line rather
than a comparison:

- **`reach` is `[A-Za-z0-9._-]+`.** It names one tool, and this file tells the
  agent to go check that the tool is there. A value carrying `;`, `|`, `$(` or a
  space is a command that probe would run, and refusing a leading `-` does not
  stop it.
- **`issues.at` is shaped by its `type`.** `github` puts a repo there and it
  reaches `gh --repo`, so it is `OWNER/NAME`, a shape that also excludes a host
  qualifier, which would file this repo's work into someone else's GitHub
  Enterprise with this user's token. `linear` and `jira` put a workspace there
  instead, and holding those to `OWNER/NAME` would refuse the config
  `wayfare-init-repo` itself writes. Passing a shape is not being the right
  destination: an outward-facing filing still has the user name it in-session.

Both rules live in one place, `hero_connection_guard`, and every reader calls
it. The listing and the field reader each carrying their own copy is not
hypothetical: they disagreed about `at: None` until a review caught it.

## Absent, unset, and unreachable are three states

This is the whole reason the standard exists, and collapsing any pair of them
reintroduces a defect that has already been shipped once:

| State | Written as | Means | What a run does |
| -- | -- | -- | -- |
| **unset** | no `### kind` block | nobody has looked | ask once, then record the answer |
| **absent** | `type: none` | looked; it does not exist anywhere | proceed without it, and stop re-asking |
| **in-repo** | `type: self` | it exists and lives here, so nothing external is attached | read it locally; never go looking outside |
| **unreachable** | `type` set, `reach` unavailable | it exists and this session cannot read it | report it and degrade **loudly** |

Unset collapsed into absent is how a missing UX flow silently stops being
reported. Absent collapsed into unreachable is how a repo with no design system
gets told to install one every run. **Unreachable collapsed into absent is the
expensive one**: "you are logged out" becomes "there is no design system", the
run continues on a two-layer round it should never have run, and the finding it
silently dropped was the one worth having.

One exception to *absent means stop asking*, and it is deliberate: the `design`
connection is re-proposed every run even after `type: none`, because a design
project can simply show up later and design-driven reconciliation is strictly
more than self-review. A repo that structurally cannot have one opts out for
good by writing `PERMANENT` in the comment on that line. That marker is prose
the agent reads, not a value `hero_connection` returns, so it is the one piece
of connection state the readers cannot see; a `permanent:` key would be the
better shape and is not worth a second spelling until something else needs it.

A connection may also be **refused**: `at` held something the reader rejected as
unsafe. That is not absence either. Report it as a config defect and fix
HERO.md; never fall through to `none`.

## Reaching one is an agentic check, not a shell function

`reach` names a tool, and whether that tool is available is a fact about the
**session**, not about the filesystem. There is nothing to implement: before the
stage that uses a connection, confirm the thing named is actually there.

| `reach` | The check |
| -- | -- |
| an MCP tool (`designsync`, `figma`, `linear`) | the tool is offered in this session and authorized for `at` |
| a CLI (`gh`, `terraform`, `kubectl`) | the binary is on `PATH` and authenticated |
| `checkout` | `at` resolves to a directory on disk (`hero_connection_repo`); a caller that needs it to be a git repo runs `git -C ... rev-parse` itself, read-only |
| `manual` | nothing to check; a person carries the content in |

Two rules about that check, both learned the hard way:

- **Distinguish structural from transient.** A registry that does not exist is
  structural; a registry you are not authenticated to is transient. Silently
  converting "you are logged out" into "here, do it by hand" hides a one-command
  fix.
- **Never re-derive a connection from another one.** Using the design-system
  connection because the design connection is unreachable is a misroute, not a
  fallback. The kinds are not substitutes for each other.

`reach: checkout` resolves **read-only**. `at` comes from HERO.md, which is repo
content and therefore attacker-controlled in a clone, so it reaches `git -C` and
nothing that writes:

```bash
ROOT_OF_IT=$(hero_connection_repo design-system) # rc 0 resolved, 1 none, 3 unreachable
```

`hero_connection_repo` is the only place that turns an `at` into a path, and
that is deliberate. It is where the row-name-or-path question below is answered;
where `type` is read **before** `at`, so a `type: none` block cannot be
resurrected by a locator someone forgot to delete and a `type: self` resolves to
this repo instead of reading as absent; and where 3, 2 and 1 stay apart, so a
missing checkout, a refused value and a declared absence each reach the caller
as themselves. A caller that resolves `at` itself re-decides all of that,
differently.

Never call `hero_work_store` on a connection's path. That function creates
`.plans/` and edits `.git/info/exclude` in whatever root it is handed, and a
connection is a thing this repo *reads*.

## `at` names a fleet row when the connection is a repo

Four of the six kinds are other repositories. When there is a fleet
([FLEET-MD.md](./FLEET-MD.md)), `at` holds the **row name**, not a path:

```markdown
- at: design-system   # the FLEET.md row; the path is the map's business
```

The map is local and unversioned, and paths differ per machine; a row name is
the same in every clone, which is what lets the connection live in a versioned
file. Resolve it with `hero_connection_repo`, never by hand: it tries the fleet
map first (through `hero_fleet_repos`, the one parse that applies the trust
rules) and falls back to a path for a repo with no fleet around it. A path is
what a row name resolves *to*, never a second place to configure the same thing.

**A connection is not a fleet row, and a fleet row is not a connection.**
`FLEET.md` says which checkouts exist beside this one; a connection says which
of them this repo depends on and how. A fleet of twenty repos gives one repo at
most six connections.

## Reading it

| Function (`scripts/hero-lib.sh`) | Returns |
| -- | -- |
| `hero_connection KIND KEY [ROOT]` | one value from `### KIND` under `## Connections` |
| `hero_connections [ROOT]` | `KIND<TAB>TYPE<TAB>AT<TAB>REACH` per declared block, one parse. rc 0, 1 (no readable HERO.md), 3 (a block was skipped) |
| `hero_connection_repo KIND [ROOT]` | `at` resolved to an absolute checkout. rc 0 resolved, 1 none, 2 refused or not a repo kind, 3 unreachable **or half-written** (a `type` with no `at`, an `at` with no `type`) |
| `hero_connection_guard KIND KEY VALUE [TYPE]` | the shape rules for the values that reach a command line. rc 0 allowed, 2 refused |

`hero_connections` is what the Step 0 of the wayfare skills prints, so those
runs state which attachments this repo declares before any stage acts on one. It
prints one row per block that exists, including blocks whose `type` is `none`. A
declared absence is information, and dropping it from the listing makes it
indistinguishable from unset. `AT` and `REACH` are `-` when unset, never empty,
so a caller's `IFS=$'\t' read` is safe, and `-` is unambiguous only because the
trust rule refuses any value starting with `-`: relax that check and the
placeholder stops being a placeholder. A block with **no** `type:` line prints
`?` rather than `none`, because half-written is not the same answer as
declared-absent. An untrusted value skips the row to stderr and the function
returns 3, exactly as `hero_fleet_repos` does.

## Feedback does not route by connection

What building teaches goes back out as a **message** into a sibling's
`.plans/inbox/`, addressed by a `FLEET.md` row the user names at delivery
(`references/feedback-channels.md`). Connections do not name that destination,
for a reason that is easy to miss:

**Only a repo can receive feedback.** A Figma file, a claude.ai/design project
and a Linear workspace are connections this repo *reads*; none of them has an
inbox, an agent, or a promotion gate. A signal about a design that lives in
Figma still travels to whichever repo's people own that design, and which repo
that is, is a fleet question with a human answer. Writing the destination into
the connection would answer it once, wrongly, for every future signal, and for
the non-repo types it would promise a delivery that cannot happen.

So: connections say what this repo reads. The fleet says where a message can go.
A connection that is not a repo has no return path at all, and the packet path
is what carries it.

## Which kinds have readers today

A kind earns its place by being something a skill knows how to use, so it is
worth saying plainly which are wired and which are declared ahead of their
consumer. `design`, `design-system` and `issues` are read today (Step 0,
`wayfare-sync-plan`'s config gate, `wayfare-recomponentize-ui`, `preflight`).
`reference`, `architecture` and `infrastructure` are declared and reported and
nothing branches on them yet: their consumers are `wayfare-audit-compliance`
(which finds its template through `FLEET.md` today), the architecture stage, and
the harden stage.

That gap is the anti-pattern below with a deadline on it, not an exception to
it. A kind still unread by the time its named consumer ships is config behaving
like a comment, and should be cut rather than kept.

## Anti-patterns

- **A seventh kind invented in a repo.** Nothing reads it. Config that no skill
  consumes looks like configuration and behaves like a comment.
- **Two connections for one attachment.** The design system's project id
  configured both here and in its own repo is two sources of truth, and the copy
  goes stale in silence. Point at the repo and dereference.
- **`type: none` used for "unreachable".** It stops the questions, which is
  exactly wrong for something that exists and is merely broken.
- **A path where a row name belongs.** It is correct on one machine.
- **Reading a connection's repo with anything that writes.** There is one write
  outside this repo, it goes into an inbox, and it is a message.
