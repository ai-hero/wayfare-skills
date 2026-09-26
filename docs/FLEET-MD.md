# The FLEET.md standard

What a fleet folder's map must be, why, and how the skills behave when run
from it. `scripts/hero-lib.sh` reads it, `scripts/fleet-scan.sh` checks it,
and `wayfare:wayfare-sync-fleet` writes it.

## The principle

A **fleet** is a folder of sibling checkouts. `FLEET.md` at its top is the
operator's local map: which repos live here, which of them are family, and
which host port each dev stack claims.

It is **local and unversioned**. It describes *your* fleet, the repos you
have checked out and work across, not the organization's inventory. Two
people's fleets overlap without matching. So the file is never inside a git
repo, never committed, and never the source of truth for anything a repo
itself needs: a fact a repo depends on lives in that repo's `HERO.md`.

Three things it is for:

| Need | How FLEET.md serves it |
| --- | --- |
| **Discovery**, a skill run at the fleet root knows the repos | `hero_fleet_repos` lists them; the skill fans out (below) |
| **Membership**: "match the fleet" applies to some folders and not others | This file is the authority: a repo is fleet when a row gives it a real `group:`. No row is also not fleet: a folder does not join by being cloned here, and `--review` says nothing about one. A `group: none` row is for a non-member that still needs something recorded, usually a `port:` it binds on the host |
| **Ports**, every dev stack publishes one host port and they must not collide | `port:` per repo is where a port is **claimed**; `wayfare-review-fleet` checks the compose file implements it |
| **Awareness**, a repo's own instructions say it belongs to a fleet | `sync` writes a `## Fleet` section into each fleet repo's `AGENTS.md` |

## The file format

```markdown
# Fleet
<!-- Local map of the checkouts beside this file. wayfare:wayfare-sync-fleet updates it. -->

## Fleet

- name: acme
- org: acme-inc          # GitHub owner most rows live under; none if mixed
- template: hero-template
- port-range: 33000-33099
- template-port: 33099   # the template's parking slot; a clone still on it is a bug
- register: .fleet/      # the compliance register overlay + generated CONSISTENCY.md; a private checkout

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
   collision and what lets the scanner pick the app's port over a database's
   in a multi-service compose file. `template` names the row the compliance
   engine compares callers against and the repo `wayfare-audit-compliance` backports
   to; `template-port` is recorded for the operator. `register` names the
   checkout holding the fleet's compliance overlay (default `.fleet/`); a
   mapped register that is not cloned stops the engine rather than running
   baseline-only.
2. **`## Groups`**, names are yours, one line each saying what membership
   means. `none` is reserved and always means not-fleet.
3. **`## Repos`**, one `### NAME` block per checkout. `NAME` is the folder
   name, `[A-Za-z0-9._-]` only. `path` defaults to `./NAME`; `group` defaults
   to `none`; `what` is one line. `port` is the **assignment**: a new dev
   stack claims the next free port in this file first and implements it in
   the repo second: the row is where the choice is made, and the compose default
   is where it takes effect, and `review` reports the two disagreeing.
   Anything else the repo needs belongs in the repo.
4. **Prose after `## Repos` is fine**, conventions, known cross-repo issues,
   a change-routing table. The reader only parses `- key: value` lines under
   the headings it is asked for and skips code fences, so examples are safe.
5. **The grammar is HERO.md's.** Same reader, same guards: a value that starts
   with `-` or carries a control character is refused, never used.

## Reading it

| Function (`scripts/hero-lib.sh`) | Returns |
| --- | --- |
| `hero_fleet_root [START]` | nearest ancestor of `START` (default `$PWD`) holding `FLEET.md` without `HERO.md` beside it, a committed FLEET.md is passed over |
| `hero_at_fleet_root [DIR]` | true when `DIR` (default `$PWD`) has `FLEET.md` and no `HERO.md`, a fleet folder, not a repo |
| `hero_fleet_field KEY [FLEET_ROOT]` | a `## Fleet` value |
| `hero_fleet_repo_field NAME KEY [FLEET_ROOT]` | a value from `### NAME` under `## Repos` |
| `hero_fleet_repos [FLEET_ROOT]` | `NAME<TAB>ABSOLUTE_PATH<TAB>GROUP<TAB>PORT` per trusted row, one parse; untrusted rows go to stderr and the function returns 3 |
| `hero_compose_port DIR [RANGE]` | the host port `DIR`'s dev compose file publishes; `-` no compose file, `?` none readable |

`FLEET_ROOT` defaults to `hero_fleet_root`, so from inside a repo every read
targets the fleet that checkout lives in.

`scripts/fleet-scan.sh FLEET_ROOT --list` enumerates the checkouts on disk
with their compose port; `--review` diffs disk against the rows and prints
`CODE<TAB>NAME<TAB>DETAIL`. The codes and their meanings are the script's
`--help`. `--review` exits 1 when there is anything to fix, and 2 for a
folder that is not a fleet (no `FLEET.md`, or a `HERO.md` beside it). Disk is
always scanned. A registry that only re-reads itself reports a fleet that no
longer exists.

## Fleet-aware repos

`FLEET.md` is local, so a fresh clone of a fleet repo knows nothing about it.
The repo's own `AGENTS.md` carries the pointer: a `## Fleet` section, vendored
from `assets/fleet/agents-md-fleet-section.md` by `wayfare-sync-fleet`, saying that
the repo lives beside its siblings, that the map is unversioned, that the
host port is claimed in the map and not invented in the repo, and that hero
skills fan out from the folder. It is generic on purpose. It names no fleet,
no port, no sibling, so it is true in every clone. `review` reports a fleet
repo without it as `NOT_FLEET_AWARE`. The section is the only thing `sync`
writes into a repo, and it is written to the working tree for the user to
ship; `sync` never commits.

## At the fleet root

Every per-repo skill's Step 0 tests for the fleet root and prints
`FLEET_ROOT` when it is there. From then on, the skill follows this
procedure instead of its own Step 1, because the folder is not a project, and
running a repo skill against it either fails late or, worse, half-works.

1. **Show the registry.** `hero_fleet_repos`, as a table of name, group, path.
2. **Ask which repos this run covers.** Names, a group name, or `all`, where
   `all` means every row whose group is not `none`. Never assume `all`, and
   never include a `none` row the user did not name: those are the repos
   "match the fleet" must not reach.
3. **Conversational skills stay in this session.** `wayfare-grill-idea` and
   `wayfare-write-handoff` are a dialogue with the user; a subagent has no one to talk to.
   Pick one repo, `cd` into it, and continue here.
4. **Every other skill runs once per chosen repo, in a subagent, in
   parallel.** Use the Agent tool (`general-purpose`) with a prompt of this
   shape, substituting the absolute path from the registry:

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

   A subagent cannot ask the user, so a skill with a user gate (wayfare-build-task's
   mark-ready and merge, wayfare-push-pr's confirm) stops at the gate and reports it.
   That is correct: answer the gate from inside that repo, not fleet-wide.
5. **Relay every report, per repo.** The user sees one summary block per
   repo, what happened, what stopped, what needs them.

Two exceptions. `wayfare-init-repo` at the fleet root scaffolds *into* the
folder (`FLEET_ROOT/NAME`) and then runs `wayfare-sync-fleet` to add the row. That
is the natural place to create a project. `fleet` itself is the only skill
whose subject is the folder rather than a repo.

## Anti-patterns

- **Committing it.** A `FLEET.md` inside a repo is one person's checkout
  layout imposed on everyone who clones, and, in a cloned repo, attacker
  content. Every reader treats a folder holding both files as a repo:
  `hero_fleet_root` passes it over and keeps walking, `review` exits 2, so a
  committed one is inert.
- **Reading it as the org inventory.** `gh repo list ORG` is what exists;
  `FLEET.md` is what you have. `sync` may print the difference; it never adds
  a row for a repo that is not on disk.
- **A compose default that disagrees with the row.** The row is the
  assignment; the compose default is the implementation. `review` reports the
  two disagreeing (`PORT_MISMATCH`; a claim with no compose file yet is
  `PORT_UNIMPLEMENTED`, a claim awaiting its dev stack), and the fix is
  changing every place the port appears in that repo, compose dev, compose
  prod, and whatever `just health` curls, because missing one brings the
  stack up on the new port while the health check reports the old.
