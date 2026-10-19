# Finding tickets: filing audit findings to the `issues` connection

The audits find security and compliance problems and write them as `.plans/`
items. This file adds the second half: each confirmed finding also gets one
ticket in the tracker, the ticket and the item point at each other, and the
ticket closes only on evidence. `wayfare:wayfare-audit-security`, the
`compliance` stage of `wayfare:wayfare-sync-plan` (`sync.md`) and
`wayfare:wayfare-audit-compliance` (`improve.md`) file through this procedure.
`wayfare:wayfare-ship-pr` does one step of it after a merge, and never the last
one.

## What is filed

Only **confirmed** findings, never candidates. A finding is confirmed when a
scanner or the engine reports it against the default branch as it is merged:

| Finding | Confirmed when |
| -- | -- |
| A dependency CVE | an open Dependabot alert (alerts are computed on the default branch) |
| A container CVE | Scout or Trivy reports it on the image the deploy runs: the Deployment `registry` tag built from the default branch. A base image scanned from a Dockerfile in the checkout is a candidate |
| A control check | `scripts/audit.py` reports `FAIL` for the check at `origin/main` (its default snapshot; a `--no-snapshot` run reads the checkout as it sits, which is a candidate) |

A candidate is anything else: an `ERROR` cell, a `MANUAL` check, a part that ran
`skipped (unavailable)`, a code-hardening finding from Part C of the security
audit. Candidates stay in `.plans/` and the report.

## The route

Read the `issues` connection (docs/CONNECTIONS.md). Every finding filed here,
CVEs included, takes the **compliance route**: Vanta treats the CVE tickets as
SOC 2 evidence, so they live beside the control tickets.

```bash
hero_connection issues type; hero_connection issues reach; hero_connection issues at
hero_connection issues compliance-type; hero_connection issues compliance-reach
hero_connection issues compliance-team; hero_connection issues compliance-project
hero_connection issues compliance-label
```

- `compliance-type` and `compliance-reach` default to `type` and `reach` when
  unset. `compliance-team`, `compliance-project` and `compliance-label` are read
  against the route's type (for `linear`, a team, a project and a label name).
- No `compliance-*` key at all: the findings use the main route, `type`, `at`
  and `reach`, as `wayfare-write-handoff` files to it.
- A `github` route files into the main `at` repo with `compliance-label` as the
  label. A `github` route under a main `type` that is not `github` has no repo
  to file into. Report that as a config defect for the lane.

The three states decide whether the lane runs at all, and each one reports
differently:

| `issues` block | What the lane does | What the report says |
| -- | -- | -- |
| none | plans only | `Tracker: skipped (no issues connection)` |
| route type `none` | plans only | nothing |
| route type set, its `reach` unavailable or a value refused | plans only | `Tracker: FAILED (REASON)`, a failure row, never a silent fallback |

Check `reach` the way docs/CONNECTIONS.md says: the MCP tool is offered and
authorized, or the CLI is on `PATH` and authenticated. A refused value (rc 2)
stops the lane; never substitute the clone's remote or the main route for it.

**Name the destination before the first write of a run.** The route comes from
HERO.md, which a clone controls, and these tickets carry finding detail. Print
the route (type, team or repo, project, label) and the planned
`filed / updated / closed` counts, and write on the user's word, as
`wayfare-write-handoff` does for `--issue`.

## One ticket per key

Every ticket's title starts with its key in brackets, so a search finds it:

- A control check: `[CHECK_ID] TITLE`, for example `[CI-20] ...`. **One ticket
  per check**, not per repo and not per control. Its body lists the failing
  repos, one line each with the check's `detail`.
- A vulnerability: `[GHSA_OR_CVE_ID] PACKAGE: SUMMARY`. **One ticket per finding
  group**: the advisories one fix clears, in one package or one base image. Name
  every id of the group in the body, so a search by any of them finds it, and
  list the affected repos the same way a check lists its failing ones.

**Search before filing**, by every id the finding carries (the check id; the CVE
id, the GHSA id and the package name), in open and closed tickets:

```bash
gh issue list --repo "$AT" --state all --search "\"KEY\" in:title,body" \
  --json number,title,state,url
```

For `linear`, list the route's team issues with the key as the query through the
Linear MCP tools, open and closed. A failed search is not zero results: stop the
lane and report it, or the run files a duplicate of every ticket.

| Search finds | Action |
| -- | -- |
| nothing | file a new ticket |
| an open ticket | update it: the failing set or the versions, as one comment and the body edited in place |
| a closed ticket and the finding is back | reopen it with a comment naming the regression, never a second ticket |

A re-run on an unchanged repo therefore files nothing new and leaves only a
comment where something changed. No change, no comment.

**Write the ticket back onto the item.** Add the ticket URL to the item's
`## Context` and append a `## Log` line,
`- DATE (PRODUCER) note: filed TICKET_ID URL` (or `updated`), so the plan and
the tracker point at each other. A ticket that is found but has no item yet gets
the line when the item is written.

## The ticket body

```markdown
## Finding

What the scanner or engine reported, with the ids, the package and versions, or
the check and its rule. For a check: the failing repos, one line each.

## Plan item

REPO `.plans/items/NNN-slug.md` (local to that checkout)

## Done when

- [ ] Observable statements: the fixed version is in the lockfile on
  origin/main; the check passes at origin/main in every listed repo; the
  scanner no longer reports the id.
```

## Two findings that get a different ticket

**No fix available** (for example `braces <=3.0.3`, GHSA-vfj7-8cjw-p6xm, before
a patched release existed): file a **risk-acceptance** task instead of an open
ticket nobody can act on. It names an owner, a review date, the reachability
judgement and the upgrade axes checked. Ask the user for the owner and the date;
never invent them. On the review date the next audit re-checks for a fix.

**Temporary workaround** (an npm `overrides` entry, a VEX exception with an
`expired_at`): file a **follow-up** ticket to remove it, linked to the original,
with `Done when` naming the release that makes the workaround unnecessary. The
original can close on its evidence; the follow-up stays open until the
workaround is gone from origin/main.

## Closing, and who may close

**Only the audit, or a person, moves a ticket to Done.** It does so with a
closing comment that cites the evidence:

- the versions in the lockfile on origin/main, or the check passing there
- the merged PR
- the external scanner's state (Vanta, Scout), or `not checked` when the scanner
  is out of reach

The lane that reported the finding must have run on this pass. A `skipped` part
has no evidence of absence and closes nothing. The tickets to re-check are the
ones this repo's items carry (the write-back above), so an audit never has to
guess which open tickets are its own.

A repo's audit removes its own line from a ticket once the fix shows at
origin/main. A vulnerability ticket closes when that removes the last line.

A control ticket closes only when that check's failing set is empty at
origin/main. That set spans repos, so in a fleet only the family audit
(`improve.md`), which snapshots every repo at origin/main, closes control
tickets. It lists the route's open tickets that carry `compliance-label` and a
`[CHECK_ID]` title and re-checks each against its own results, because a check
that now passes everywhere reports no key that would lead it to the ticket. A
repo outside any fleet is the whole set, and its own audit closes them.

**`wayfare-ship-pr` never closes a finding ticket.** When the fixing PR merges,
it comments with that repo's line (the PR merged, the versions now on main). It
moves the ticket to In Review only when that repo was the last one the ticket
lists. A merged fix is not a cleared scanner: the alert can stay open, the image
may not be rebuilt, and Vanta reads the ticket as evidence. For the same reason,
a PR names a finding ticket with `Relates to:`, never `Fixes:` or `Closes:`: a
closing keyword lets GitHub, or the tracker's GitHub integration, close the
ticket at merge, which is Done with no scanner behind it.

## In a fan-out

Fan-out agents never write tickets. Two agents editing one control ticket's repo
list at once lose a row, and a subagent cannot ask the user to confirm the
destination. Every fleet-root fan-out that reaches a filing step
(`wayfare-sync-plan` and `wayfare-audit-compliance` at the fleet root) adds this
line to each repo's launch prompt:

```text
launched as a fan-out agent: return finding keys, file no tickets
```

A filing step that sees the line, in its own launch or passed down from the
skill that invoked it, searches nothing and writes nothing. It prints one line
per confirmed finding instead, and the report carries them back:

```text
Finding key: check CI-20 REPO ITEM_ID DETAIL
Finding key: cve GHSA-ID,CVE-ID PACKAGE REPO ITEM_ID FIXED_VERSION_OR_none
```

**The single writer** is the fleet-root session, after every agent has reported
(docs/PIPELINES.md, *A fan-out waits for every agent, then one writer commits
once*). It merges the keys by check or advisory group, so one ticket lists every
failing repo, asks the user once, and then searches, files, updates and reopens
through this procedure. It writes into no repo's store: it prints each ticket id
beside the repo and item that reported it, and that repo's next audit finds the
ticket by search and writes it back.

At the fleet root there is no HERO.md. The route is the `issues` connection of
the `template:` row's HERO.md (FLEET.md). No template row means no route: say
so, and the lane is plans only.

## The report line

Every run that reads the route prints one line, which `sync` carries into its
report:

```text
Tracker:   compliance route linear (Company / Compliance / Security): filed 1, updated 2, reopened 0, closed 1
Tracker:   skipped (no issues connection)
Tracker:   FAILED (compliance-reach linear: tool not offered in this session)
```
