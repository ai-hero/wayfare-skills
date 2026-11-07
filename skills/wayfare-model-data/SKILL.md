---
name: wayfare-model-data
# prettier-ignore
description: "Model stored data, write migrations, add indexes, cache reads, and fix slow queries in a MongoDB and Redis backend. Use before adding or changing a stored field, collection, store method, query, index, cached read, or boot migration. Use when an endpoint is slow or uncached, even if nobody mentions the database. Use audit to report a repo's gaps."
argument-hint: "[audit] | CHANGE_OR_SLOW_QUERY"
compatibility: "Requires the complete Wayfare plugin, git, and a Go backend on MongoDB and Redis. Evidence steps require docker or a running dev stack with mongosh. Never requires production access."
---

# Model data: one representation, one access path, indexed and measured

Fleet backends store documents in MongoDB, and most cache reads in Redis. Each
repo holds its own copy of the store and cache helpers. This skill gives every
data change the same contract, then requires evidence for it.

## Arguments

- `$ARGUMENTS`:
  - (a description of a change) - apply the contract to that change.
  - (a slow endpoint or query) - run the optimize route.
  - `audit` - report the repo's gaps against the contract. Change no file.

## Step 0: Load the repo

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
. "$WAYFARE_ROOT/scripts/hero-lib.sh" || { echo "wayfare: cannot load hero-lib.sh from $WAYFARE_ROOT, export WAYFARE_ROOT as the plugin root"; exit 1; }
hero_fleet_step0 || exit 1
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cat "$ROOT/HERO.md" 2>/dev/null || echo "NO_HERO_CONFIG"
MONGO_RC=0
git -C "$ROOT" grep -q --untracked 'go.mongodb.org/mongo-driver' -- '*.go' || MONGO_RC=$?
case "$MONGO_RC" in
  0) ;;
  1) echo "NO_MONGO" ;;
  *) echo "GREP_FAILED rc=$MONGO_RC" ;;
esac

```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo: stop and follow
**At the fleet root** in [docs/FLEET-MD.md](../../docs/FLEET-MD.md).

If `NO_MONGO` printed, report that this skill does not apply and stop. If
`GREP_FAILED` printed, report the failure and stop. Do not read it as
`NO_MONGO`. If `HERO.md` is missing, continue with detection.

## Step 1: Find this repo's versions of the helpers

The helpers have the same purpose across the fleet but different names. Read the
repo's own files before you write code. Follow the repo's existing variant. Do
not move a repo to another variant as part of a feature.

```bash
cd "$(git rev-parse --show-toplevel)" || exit 1
git grep -l 'bson:"' -- '*.go' ':!*_test.go'
git grep -nE 'func .*\) (Workspace|collection|tenant|coll)\(|func .*[Ss]copedFilter' -- '*.go' ':!*_test.go'
git grep -nE 'IndexModel|keys: +bson' -- '*.go' ':!*_test.go'
git grep -nE 'func .*Migrate|migrations = ' -- '*.go' ':!*_test.go'
git grep -nE 'cachedSlice|cachedCollections|cacheRegistry|BumpGeneration' -- '*.go' ':!*_test.go'
git grep -lE 'testcontainers|MONGODB_URI|MONGODB_TEST_URI|DRIFT_TEST_MONGO_URI' -- '*_test.go'
```

The commands find, in order, each item below. If a repo fits no variant, say so
and read its code. Do not assume a helper exists.

- **Stored types:** `lib/domain`, `lib/types`, `lib/store`, or drift's `lib/`
  envelope.
- **Tenant handle:** `scoped`, `tenant`, a filter helper such as
  `projectScopedFilter`, or a `realm_id` written by hand. No match means that
  each query writes its owner clause by hand.
- **Index declarations:** `migrate.go` steps, `EnsureIndexes` in `store.go`, or
  per-collection `ensure*Indexes`.
- **Migrations:** an ordered slice, or auth's named boot steps with markers.
- **Cached reads:** a command monitor, explicit `invalidate*` calls, or no cache
  by decision.
- **Test database:** testcontainers, a URI from the environment, or fakes only.

Read the repo's `DESIGN.md` entries about the store and the cache. A recorded
decision overrides a default below. drift caching nothing is one such decision.
If you must break a recorded decision, ask the user first.

Then find where the data runs:

- `docker-compose.prod.yaml` cannot answer this. An app on Atlas can also define
  a `mongo:` service, and an environment value overrides its URI.
- Ask the user whether production is Atlas Flex or a `mongo:8` container. Atlas
  Flex has the limits in [references/optimize.md](references/optimize.md).
- Do not write the answer into this plugin. This repo is public.

## Step 2: Apply the contract

These rules apply to every route.

1. **One stored representation.** Each stored entity has one bson-tagged struct
   in the repo's stored-types package.
2. **Proto is the wire contract only.** A generated type never reaches Mongo. A
   hand-written converter sits between the two.
3. **The store is the only path to Mongo and to cached rows.** Handlers never
   hold a collection. A tenant filter comes from the repo's tenant handle when
   it has one.
4. **A query and its index ship in one PR.** The index is declared in the repo's
   migration or index list, with an explicit name.
5. **A list read is bounded.** It has a limit and keyset pagination. Record the
   reason in a comment if a read stays unbounded.
6. **A cached read uses the repo's helper.** Authorization gates are not cached
   unless the repo's `DESIGN.md` says so.
7. **A schema change is a boot migration.** It is named and idempotent, and it
   keeps the old shape readable until no running code needs it.
8. **A performance claim has evidence.** Evidence is an explain result or a
   measured duration. Read shape alone produces a candidate, not a finding.

## Step 3: Follow the route

Read only the reference for the route. A change can use more than one route.

| The task | Read |
| -- | -- |
| A new or changed collection, field, type, or relationship | [references/model.md](references/model.md) |
| A new index, backfill, rename, removal, or other schema change | [references/migrate.md](references/migrate.md) |
| A new query, a slow endpoint, or a decision to cache a read | [references/optimize.md](references/optimize.md) |
| `audit` | All three, then Step 5 |

## Step 4: Verify

Run all of these before you report the work as complete.

1. Run the explain procedure in [references/optimize.md](references/optimize.md)
   for each new or changed query. Record the plan and the examined-to-returned
   counts.
2. Run each new migration twice on the same database. The second run must change
   nothing.
3. If you cached a read, run a test with two owners. The second owner must not
   receive the first owner's rows.
4. Run the repo's test and lint commands.

For a diagnosis with no change, run only item 1. List the other items as not
run. If a check cannot run, say so in the report. Do not state that a query uses
an index if you did not run explain. Do not state that a change made an endpoint
faster if you did not measure before and after.

## Step 5: Audit output

For `audit`, change no file. Report one row per finding, and sort by the failure
that costs most: missing tenant scope first, then correctness, then speed.

```
FILE:LINE | RULE | SHAPE | EVIDENCE (explain, measured, or candidate) | FIX
```

Label a finding `candidate` until explain confirms it. Report which paths you
did not read. Do not rank by traffic unless you have traffic data.

## Gotchas

- **Production access is not part of this skill.** Never run explain, create an
  index, or run a backfill against production unless the user asks for that
  action in this session. Indexes reach production through the boot migration.
- **"document db" here means MongoDB, not Amazon DocumentDB.** Do not apply
  DocumentDB's planner, `$hint`, or index limits.
- **A shared comment is wrong about index names.** `hero-template`,
  `add-api-feature`, and some clones say that a same-name index with a new spec
  no-ops and reports success. It fails with error 86 and stops the boot. See
  [references/migrate.md](references/migrate.md).
- **MongoDB's published optimizer skill does not fit Flex.** Its general route
  depends on Performance Advisor, which Flex does not offer.
- **A driver error from a write can contain personal data.** A duplicate-key
  error quotes the duplicated value. Read the logging rules in
  [references/optimize.md](references/optimize.md) before you log a store error.
- **Do not copy a pattern from another repo's store without checking it.** The
  copies have diverged, and a neighbour's query can have the same index gap.
