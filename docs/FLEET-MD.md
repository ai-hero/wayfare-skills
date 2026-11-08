# The FLEET.md standard

What a fleet folder's map must be, why, and how the skills behave when run from
it. `scripts/hero-lib.sh` reads it, `scripts/fleet-scan.sh` checks it, and
`wayfare:wayfare-sync-fleet` writes it.

## The principle

A **fleet** is a folder of sibling checkouts. Its map, `FLEET.md`, says which
repos belong, which of them are family, and which host port each dev stack
claims.

The map lives **in the register repo**, at `.fleet/FLEET.md`: `.fleet/` is the
clone of the fleet's private register repo (the one `register-repo:` names), and
the folder holding `.fleet/` is the fleet root. The checkouts sit in the fleet
root next to `.fleet/`, not inside the register, and nothing is placed at the
top of the folder for the map. The map is versioned with the register, so a new
machine gets it by cloning, and every change to it has history and review like
the register's other files. It is never the source of truth for anything a repo
itself needs: a fact a repo depends on lives in that repo's `HERO.md`.

Beside the map, the register holds the compliance overlay (`CONTROLS.yaml`,
`CHECKS.yaml`, `checkers.py`, rule 1 below) and **`setup.yaml`**, the machine
setup every developer in the fleet gets ([SETUP-YAML.md](./SETUP-YAML.md)).

Because the map is shared, it names the fleet, not your machine. A row whose
checkout you never cloned is normal: `review` reports it as `NOT_CLONED`, for
information, and `sync` offers to clone it to `FLEET_ROOT/NAME`, never anywhere
else.

**Who can steer it.** The map decides which repos the compliance audit judges,
so whoever can merge to the register repo can steer the audit. The map cannot
point the audit at another register: the engine refuses any `register:` that is
not `.fleet/` itself, because a register PR could otherwise name a sibling
checkout whose `main` its author controls, with a matching `register-repo:`, and
have that sibling's `checkers.py` imported as reviewed. With that refusal, the
people who can steer the audit through the map are the people who can already
change the register's `checkers.py`.

**The map is reviewed like the overlay.** Fan-out and `review` read the map from
the working tree of `.fleet/`, so a row you add is usable on your machine at
once. The audit treats the map as part of the register: when `.fleet/FLEET.md`
differs from the version on the freshly fetched `origin/main` (uncommitted,
unpushed, or not yet pulled), the register reads UNREVIEWED, its `checkers.py`
does not load, and `--fail-on` exits 3, exactly as for an edited
`CONTROLS.yaml`. Merge and pull the change, and the audit trusts it.

**The register is pinned per machine.** `register-repo:` is written inside the
checkout it vouches for, so a cloned fork of the register carrying its own map
could name itself. Each machine therefore pins the register it trusts in
`${XDG_CONFIG_HOME:-~/.config}/wayfare/registers`, outside every repo: one line
per fleet, the fleet root's absolute physical path, whitespace, the register as
`HOST/OWNER/NAME` (lowercase, no `.git`, so `git@github.com:acme/reg.git` and
`https://github.com/acme/reg` are both `github.com/acme/reg`; a local-path
register is `file` followed by its absolute path), with `#` starting a comment.
A two-part `OWNER/NAME`, the first spelling, reads as `github.com/OWNER/NAME`.
`hero_register_pin` and `audit.py`'s `pinned_register()` read it. An `origin`
whose host, owner or name differs from the pin, or a `register-repo:` that
differs from its owner and name, makes the register UNREVIEWED. **The pin is
required.** With no line for the fleet root, the audit reads the register
UNREVIEWED and `fleet-scan.sh --review` exits 2; both print the exact line to
add (or say why the root cannot be pinned: a path with whitespace, or an
unreadable pin file), `ROOT HOST/OWNER/NAME`, with `HOST/OWNER/NAME` a
placeholder you fill in once you have confirmed the register's `origin` is your
fleet's register. Nothing from the map or the remote is pasted into it. The pin
is also where `sync` takes the host and owner it clones from, never the map's
`org:`.

### A new machine

1. Make the fleet folder, outside any git work tree (`mkdir ~/workspaces/acme`).
2. Clone the register into it as `.fleet/`
   (`git clone git@github.com:acme-inc/fleet-register.git .fleet`). The map is
   now at `.fleet/FLEET.md`.
3. Pin the register on this machine, from the fleet folder:
   `mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/wayfare" && printf '%s %s\n' "$(pwd -P)" github.com/acme-inc/fleet-register >> "${XDG_CONFIG_HOME:-$HOME/.config}/wayfare/registers"`.
4. Run `wayfare:wayfare-setup-dev` from the fleet folder. It sets the machine up
   from `.fleet/setup.yaml`, offers to clone the rows not cloned here, and
   restores their local-only files from an old machine. On a machine without
   wayfare yet, the bootstrap in [SETUP-YAML.md](./SETUP-YAML.md) comes first.
   `wayfare:wayfare-sync-fleet` also offers the clones, without the setup, and
   offers the pin if step 3 was skipped.

### Moving from a top-level FLEET.md

The map used to be a local `FLEET.md` at the top of the fleet folder. It is no
longer read. A folder holding only that file is an error everywhere the map is
read (`hero_fleet_map` rc 2, `FleetMapError` in Python), naming this move, never
"no fleet": a skill would otherwise run its repo procedure in the fleet folder,
and the audit would run without the fleet's overlay. Copy it into the register
(`cp FLEET.md .fleet/FLEET.md`), commit and PR it there, then delete the
top-level copy. While both exist, `.fleet/FLEET.md` is read and a one-line
stderr note, once per process, names the leftover copy to delete. A
`.fleet/FLEET.md` that exists but is not a readable file (a directory, a
dangling link, no read permission) is an error, never a reason to report no
fleet.

Three things it is for:

| Need | How FLEET.md serves it |
| -- | -- |
| **Discovery**, a skill run at the fleet root knows the repos | `hero_fleet_repos` lists them; the skill fans out (below) |
| **Membership**: "match the fleet" applies to some folders and not others | This file is the authority: a repo is fleet when a row gives it a real `group:`. No row is also not fleet: a folder does not join by being cloned here, and `--review` says nothing about one. A `group: none` row is for a non-member that still needs something recorded, usually a `port:` it binds on the host |
| **Ports**, every dev stack publishes one host port and they must not collide | `port:` per repo is where a port is **claimed**; `wayfare-review-fleet` checks the compose file implements it |
| **Awareness**, a repo's own instructions say it belongs to a fleet | `sync` writes a `## Fleet` section into each fleet repo's `AGENTS.md` |

## The file format

```markdown
# Fleet
<!-- The fleet map, kept in the register repo. wayfare:wayfare-sync-fleet updates it. -->

## Fleet

- name: acme
- org: acme-inc          # GitHub owner most rows live under; none if mixed
- template: hero-template
- port-range: 33000-33099
- template-port: 33099   # the template's parking slot; a clone still on it is a bug
- register: .fleet/      # the compliance register overlay + generated CONSISTENCY.md; a private checkout
- register-repo: acme-inc/fleet-register   # the register checkout's origin, OWNER/NAME

## Groups

- template: cloned to start a project; carries the stack it produces
- apps: share the stack, the component registry, and the dependency baseline
- infra: same conventions; no dev stack, so no port
- none: lives here but is not fleet, so "match the fleet" does not apply

## Repos

### auth

- path: ./auth
- group: apps
- port: 33000
- what: OAuth 2.1 / OIDC identity provider

### research

- group: none
- what: notebooks and one-off experiments
```

Rules:

1. **`## Fleet`**: `name` is required. `org` lets `sync` list what you have
   *not* cloned; `port-range` is where `sync` picks the next free port for a
   collision and what lets the scanner pick the app's port over a database's in
   a multi-service compose file. `template` names the row the compliance engine
   compares callers against and the repo `wayfare-audit-compliance` backports
   to; `template-port` is recorded for the operator. `register` names the
   checkout holding the fleet's compliance overlay. It may only be `.fleet/`
   (the default), and any other value stops the engine (see *Who can steer it*).
   `register-repo` names that checkout's `origin` as `OWNER/NAME`; it is how a
   fresh fleet folder knows what to clone, and the engine compares it to the
   checkout's `origin` URL. The register is reviewed the way code is: it has a
   private `origin` remote whose `main` takes changes only through a reviewed
   PR, and the engine reads `CONTROLS.yaml`, `CHECKS.yaml` and `checkers.py`
   from `origin/main`, fetched that run, not from the working tree. The engine
   trusts that remote's branch protection; it does not check it. A register with
   no remote, or whose `origin/main` does not resolve, is read at its HEAD, and
   only a register with no `.git` is read from its working tree. Anything short
   of a clean, pushed, freshly fetched `origin/main` is unreviewed: an
   uncommitted or unpushed change to those three files, a `.fleet/FLEET.md` that
   differs from `origin/main`, a failed fetch, no remote, no `.git` at all, no
   `register-repo` key, an `origin` that is not the repo `register-repo` names,
   or either of those disagreeing with this machine's pin (*The register is
   pinned per machine*). Then the report header's `register:` line names which,
   the overlay's changes to baseline controls and checks are dropped, its own
   checks read MANUAL, the register's `checkers.py` is not loaded, and
   `--fail-on` exits 3.
2. **`## Groups`**, names are yours, one line each saying what membership means.
   `none` is reserved and always means not-fleet.
3. **`## Repos`**, one `### NAME` block per checkout. `NAME` is the folder name,
   `[A-Za-z0-9._-]` only. `path` defaults to `./NAME`, and a `path` written
   absolute (`/…`, or `~/…` with `~` read as `$HOME`) is listed wherever it
   points, which is how a plugin checkout outside the folder joins a fan-out.
   The map is shared content, so an absolute row is a place someone else named:
   a skill reads it and runs in it when the folder already exists, and nothing
   ever clones or writes there (`review` reports a missing one as
   `ABSENT_OUTSIDE`). A relative `path` that resolves outside the folder, by
   `..` or by a symlink, is a bad row and is skipped (`BAD_ROW`). Whether a path
   is absolute is decided on the path as written (`/…`, `~` or `~/…`); only a
   relative path is held to the fleet folder, wherever it resolves. Roots found
   by `hero_fleet_root` or `fleet_root()` are never inside a git work tree; an
   explicit `FLEET_ROOT` argument or `--fleet` is the operator's own word.
   `group` defaults to `none`; `what` is one line. `port` is the **assignment**:
   a new dev stack claims the next free port in this file first and implements
   it in the repo second: the row is where the choice is made, and the compose
   default is where it takes effect, and `review` reports the two disagreeing.
   Anything else the repo needs belongs in the repo.
4. **Prose after `## Repos` is fine**, conventions, known cross-repo issues, a
   change-routing table. The reader only parses `- key: value` lines under the
   headings it is asked for and skips code fences, so examples are safe.
5. **The grammar is HERO.md's.** Same reader, same guards: a value that starts
   with `-` or carries a control character is refused, never used.

## Reading it

| Function (`scripts/hero-lib.sh`) | Returns |
| -- | -- |
| `hero_fleet_map DIR` | the map's path for fleet folder `DIR`: `DIR/.fleet/FLEET.md`, never a top-level `DIR/FLEET.md` (named once per shell for deletion when both exist); rc 1 when neither exists or `DIR` is itself named `.fleet`, rc 2 when only the top-level `FLEET.md` exists (the error names the move), or when `.fleet/FLEET.md` exists but is not a readable regular file, or either `.fleet` or `.fleet/FLEET.md` is a symlink (git reviews a link's target string, not what it points at) |
| `hero_fleet_root [START]` | nearest ancestor of `START` (default `$PWD`) with a map (`hero_fleet_map`) and no `HERO.md` beside `.fleet/`, outside any git work tree (`.git` on the folder or an ancestor other than `$HOME`); a committed map is passed over, a walk from inside `.fleet/` (a git checkout or not) lands on its parent, and rc 2 means the nearest trusted folder's map is unreadable |
| `hero_at_fleet_root [DIR]` | true when `DIR` (default `$PWD`) has a map, no `HERO.md`, and sits outside any git work tree: a fleet folder, not a repo; rc 2 for an unreadable map |
| `hero_register_pin FLEET_ROOT` | the register `HOST/OWNER/NAME` this machine pins for the fleet (a two-part pin as `github.com/…`), or rc 1 |
| `hero_require_register_pin FLEET_ROOT` | `hero_register_pin`, or rc 1 with the pin file and the exact line to add on stderr (or why the root cannot be pinned, or that the pin file is unreadable). It checks that a pin exists, not that it matches the register's `origin`: the audit checks that |
| `hero_fleet_step0 [DIR]` | Step 0's one form, `hero_fleet_step0 \|\| exit 1`: prints `FLEET_ROOT` at a fleet folder, nothing in a repo, and `FLEET_MAP_BROKEN` with rc 2 for an unreadable map |
| `hero_fleet_field KEY [FLEET_ROOT]` | a `## Fleet` value |
| `hero_fleet_repo_field NAME KEY [FLEET_ROOT]` | a value from `### NAME` under `## Repos` |
| `hero_fleet_repos [FLEET_ROOT]` | `NAME<TAB>ABSOLUTE_PATH<TAB>GROUP<TAB>PORT` per trusted row, one parse; untrusted rows go to stderr and the function returns 3 |
| `hero_compose_port DIR [RANGE]` | the host port `DIR`'s dev compose file publishes; `-` no compose file, `?` none readable |

`FLEET_ROOT` defaults to `hero_fleet_root`, so from inside a repo every read
targets the fleet that checkout lives in. A member joined by an absolute row can
live outside the fleet folder, and then from inside its own checkout
`hero_fleet_root` finds no fleet (rc 1) or a different one; pass each read
`FLEET_ROOT` explicitly.

`scripts/fleet-scan.sh FLEET_ROOT --list` enumerates the checkouts on disk with
their compose port; `--review` diffs disk against the rows and prints
`CODE<TAB>NAME<TAB>DETAIL`. The codes and their meanings are the script's
`--help`. `--review` exits 1 when there is anything to fix, and 2 for a folder
that is not a fleet (no `.fleet/FLEET.md`, a `HERO.md` beside it, or a folder
inside a git work tree). `NOT_CLONED`, a row whose path under the fleet folder
does not exist, is printed but never fixes the exit code on its own: the shared
map names repos you may never clone here. Its port claim still counts toward
`PORT_COLLISION`. A missing checkout that looks like drift is a real finding:
`MOVED` (an unmapped checkout whose `origin` names the row's repo),
`DANGLING_LINK`, `NO_PARENT` (a relative `path:` whose parent folder is missing)
and `ABSENT_OUTSIDE` (an absolute row with no folder). Disk is always scanned. A
registry that only re-reads itself reports a fleet that no longer exists.

## Fleet-aware repos

`FLEET.md` lives in the register, so a fresh clone of a fleet repo knows nothing
about it. The repo's own `AGENTS.md` carries the pointer: a `## Fleet` section,
vendored from `assets/fleet/agents-md-fleet-section.md` by `wayfare-sync-fleet`,
saying that the repo lives beside its siblings, that the map is the register's
`.fleet/FLEET.md`, that the host port is claimed in the map and not invented in
the repo, and that hero skills fan out from the folder. It is generic on
purpose. It names no fleet, no port, no sibling, so it is true in every clone.
`review` reports a fleet repo without it as `NOT_FLEET_AWARE`. The section is
the only thing `sync` writes into a repo, and it is written to the working tree
for the user to ship; `sync` never commits.

## Repos that can receive a message

A message or reply to a sibling is a file in its `.plans/inbox/`, and the sender
refuses to create a missing inbox ([MESSAGES.md](./MESSAGES.md)): `.plans/`
stays out of git only through the recipient's own `.git/info/exclude`, so an
inbox written from outside could be committed. A fleet repo without an inbox
silently strands every reply addressed to it. `review` reports both halves:

| Code | Meaning | Fix |
| -- | -- | -- |
| `NO_INBOX` | a repo whose group is not `none` has no `.plans/inbox/` | run a wayfare skill that opens the store, such as `wayfare-sync-plan`, in that repo; its Step 0 (`hero_work_store`) writes the exclude entry, then creates the store and the inbox |
| `PLANS_NOT_EXCLUDED` | a repo, `none` included, has a `.plans/` that `git check-ignore` says is not ignored | the same, in that repo; Step 0 writes `.plans/` to its `.git/info/exclude`. In a `none` repo the store is stray, so ask whether to remove it instead |

A `none` repo is exempt from `NO_INBOX`: the fleet does not message it, and a
send to it is meant to fail. Never create an inbox from the fleet root. The
repo's own setup writes the exclude entry first and the inbox second, and that
order is what keeps the store out of its commits.

## At the fleet root

Every per-repo skill's Step 0 tests for the fleet root and prints `FLEET_ROOT`
when it is there. From then on, the skill follows this procedure instead of its
own Step 1, because the folder is not a project, and running a repo skill
against it either fails late or, worse, half-works.

1. **Show the registry.** `hero_fleet_repos`, as a table of name, group, path.

2. **Ask which repos this run covers.** Names, a group name, or `all`, where
   `all` means every row whose group is not `none`. Never assume `all`, and
   never include a `none` row the user did not name: those are the repos "match
   the fleet" must not reach.

3. **Conversational skills stay in this session.** `wayfare-grill-idea` and
   `wayfare-write-handoff` are a dialogue with the user; a subagent has no one
   to talk to. Pick one repo, `cd` into it, and continue here.
   `wayfare-check-audit-claim` also stays in this session and needs no repo,
   because a claim belongs to none. `wayfare-audit-deep` never fans out: it
   stops at the fleet root and asks for one repo.

4. **Every other skill runs once per chosen repo, in a subagent, in parallel.**
   Use the Agent tool (`general-purpose`) with a prompt of this shape,
   substituting the absolute path from the registry:

   ```
   cd ABSOLUTE_REPO_PATH. Every command in this task runs inside that repo.
   It is one checkout in a fleet. Modify no sibling. Read one only for the
   two probes docs/MESSAGES.md names, the duplicate check before sending a
   message, and the mutual-suspension check, and make exactly one kind of
   write outside this repo: a file in a sibling's .plans/inbox/, per that
   standard, on the user's confirmation.
   Invoke the skill wayfare:SKILL_NAME with arguments: ARGS.
   Report: what changed, any PR URLs, any messages deposited, and anything
   that needs the user.
   ```

   A subagent cannot ask the user, so a skill with a user gate
   (wayfare-build-task's mark-ready and merge, wayfare-push-pr's confirm) stops
   at the gate and reports it. That is correct: answer the gate from inside that
   repo, not fleet-wide.

5. **Relay every report, per repo.** The user sees one summary block per repo,
   what happened, what stopped, what needs them.

Three exceptions. `wayfare-init-repo` at the fleet root scaffolds *into* the
folder (`FLEET_ROOT/NAME`) and then runs `wayfare-sync-fleet` to add the row.
That is the natural place to create a project. `wayfare-setup-dev` at the fleet
root sets up the machine from `.fleet/setup.yaml`, then runs its per-repo
procedure in each repo the person picks, in this session, because its gates ask
the person (its `WORKFLOW.md`). `fleet` itself is the only skill whose subject
is the folder rather than a repo.

## Anti-patterns

- **Committing it to a product repo.** The map is committed in one place, the
  register. A `.fleet/FLEET.md` (or a top-level `FLEET.md`) committed inside any
  other repo is, in a cloned repo, attacker content. Every reader treats a
  folder holding a map and a `HERO.md` as a repo: `hero_fleet_root` passes it
  over and keeps walking, `review` exits 2, so a committed one is inert. A
  folder is never a fleet root, HERO.md or not, when it or any ancestor other
  than `$HOME` holds `.git` (a dotfiles repo at `$HOME` is not a clone), because
  the audit would execute the clone's `.fleet/checkers.py`; `hero_fleet_root`,
  the audit's `fleet_root()` and `analysis/ingest/fleet.py` pass it over with a
  stderr note. The test is on the folder holding `.fleet/`, never on `.fleet/`
  itself, so the register being its own git checkout under a plain fleet folder
  still loads (its `checkers.py` runs only from a reviewed `origin/main`; see
  rule 1). Keeping the fleet folder itself under git stops it resolving.
- **Reading it as the org inventory.** `gh repo list ORG` is what exists;
  `FLEET.md` is what the fleet governs. `sync` may print the difference; it
  never adds a row for a repo that is not on disk on this machine.
- **Dropping a row because it is not cloned here.** `NOT_CLONED` means this
  machine has no checkout, not that the repo is gone. A row is dropped only when
  the person says the repo is retired.
- **A compose default that disagrees with the row.** The row is the assignment;
  the compose default is the implementation. `review` reports the two
  disagreeing (`PORT_MISMATCH`; a claim with no compose file yet is
  `PORT_UNIMPLEMENTED`, a claim awaiting its dev stack), and the fix is changing
  every place the port appears in that repo, compose dev, compose prod, and
  whatever `just health` curls, because missing one brings the stack up on the
  new port while the health check reports the old.
