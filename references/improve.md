# `wayfare-audit-compliance`: the compliance audit and the backports

The compliance audit on its own, for this repo or the whole fleet.

`wayfare-audit-compliance` takes no argument. In a repo it runs the `compliance`
stage exactly as `sync` does, with the same engine call, the same items and the
same confirm flow and the same filing to the `issues` connection
([finding-tickets.md](finding-tickets.md)), including its fan-out branch when
launched with `launched as a fan-out agent`, and then does the one thing `sync`
never does: **the backport half**. Run the engine once more for the fleet's
template (`--repo TEMPLATE`, the `template:` row in FLEET.md) and, for every
check the template fails where this repo is the `reference`, draft a message
into the template's `.plans/inbox/` per `docs/MESSAGES.md`: `from` this repo,
`to` the template, `about` the item here if one exists, an `## Ask` naming the
check and the file in this repo that satisfies it. That deposit is the only
write outside this repo the messages standard allows, and it is confirmed like
any outward-facing act: show the drafts, write on the user's word. Outside a
fleet there is no template and no backport; say so.

**At a fleet root** (Step 0 printed `FLEET_ROOT`), `wayfare-audit-compliance` is
the family audit:

1. Run the engine for the whole family, at merged state: `scripts/audit.py --md`
   (it snapshots each repo at `origin/main`; pass `--no-snapshot` only when the
   user asks to audit the checkouts as they sit). Print the table.
2. Regenerate the fleet's table: `scripts/consistency.py` writes
   `CONSISTENCY.md` into the register checkout, with `FIRST_SEEN.json` beside
   it: the date each open failure was first seen, which the table's ages and
   deadlines count from. It is a git repo; propose one commit of both files and
   make it on the user's word.
3. Read the register's `reference:` rows against the results: every check where
   the reference repo itself fails is a **register defect** (the reference is
   wrong, or the repo regressed). Report it first; it is the one finding nobody
   else surfaces.
4. Offer the per-repo fan-out per **At the fleet root** in `docs/FLEET-MD.md`:
   the user picks repos, and each gets `wayfare:wayfare-audit-compliance` in a
   subagent, which proposes its own items in its own store. Each launch prompt
   carries `launched as a fan-out agent: return finding keys, file no tickets`
   (finding-tickets.md, *In a fan-out*). The fleet form writes into no repo's
   store, items are a repo's own decision, made in that repo.
5. File the control findings as the single writer, once every fan-out agent has
   reported ([finding-tickets.md](finding-tickets.md)). The route is the
   `issues` connection of the `template:` row's HERO.md. One ticket per failing
   check, listing the failing repos from step 1's results at origin/main; update
   an existing ticket's list instead of filing a second one. A repo whose cell
   for that check is `ERROR` keeps its line as it was. Close a check's ticket
   with the evidence comment when its failing set is empty. To find the tickets
   for checks that now pass everywhere, list the route's open tickets carrying
   `compliance-label` and re-check each `[CHECK_ID]` title against step 1. This
   is the only run that closes a control ticket in a fleet.

A family whose FLEET.md rows all say `group: none` is not a family; say that
instead of auditing nothing and reporting clean.
