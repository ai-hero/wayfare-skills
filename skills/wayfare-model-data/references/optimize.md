# Optimize route

Read this file for a new query, a slow endpoint, or a decision to cache a read.
The behaviour marked **measured** comes from `mongo:8` on 2026-11-07, with
20,000 documents and `limit(20)`.

## Order of work

Follow this order. Do not begin with a cache.

1. **Measure.** Get the request's duration and its number of Mongo commands. If
   the repo has no slow-command log or query counter, count commands by reading
   the code path. Report that production was not measured.
2. **Count round trips.** Remove query loops. Each command pays network latency.
3. **Bound the read.** Add a limit, keyset pagination, and a projection.
4. **Fix the index.** Use explain to confirm the fix.
5. **Cache last.** A cache hides a slow miss and does not repair it.

## Where evidence comes from

Run this check first: is the app on Atlas Flex or the `mongo:8` container?

| Source | `mongo:8` container | Atlas Flex |
| -- | -- | -- |
| explain on a local copy of the shape | Yes | Yes, in the dev stack |
| Database profiler | Yes | Not documented, so test before you rely on it |
| Performance Advisor, Real-Time Panel, log download | Not applicable | **No** |
| Driver command monitor in the app | Yes | Yes. **This is the production evidence on Flex** |

Atlas limits on Flex that affect queries:

- 500 operations per second, and then a cooldown that queues requests.
- 500 connections and 5 GB of storage, which includes indexes.
- In-memory sort limit of 32 MB, with no `allowDiskUse`. A large unindexed sort
  fails on Flex.
- Metrics show only connections, logical size, network, and op counts.

Compare the app's region with its cluster's region. They can differ. A droplet
and a cluster in different regions pay the distance on every command.

## Add a slow-command log

If the repo logs no command durations, propose this as its own PR. If the repo
has a monitor chain such as `chainMonitors`, add to it. If it has no command
monitor, install one. Log at `Warn` above a configurable threshold.

- Record the collection at `Started`, keyed by `RequestID`. The outcome events
  carry no command body. Evict by age.
- Log the command name, collection, and `Duration` at the outcome. If the entry
  was evicted, log without the collection. The oldest commands are the slowest.
- Do not log filter values. They hold subjects and email addresses.

## Run explain

Use the dev stack, or a disposable container if the repo has no dev stack.
Replace `EXPLAIN_NAME` with a name unique to this run, because other sessions
can run this at the same time:

```bash
docker run -d --rm --name EXPLAIN_NAME mongo:8 --quiet
docker exec EXPLAIN_NAME mongosh --quiet test --eval 'SCRIPT'
```

1. Create the repo's declared indexes for the collection with the exact keys.
   Use the declared name. If the repo declares no name, use the driver's
   default.
2. Insert at least 10,000 documents across more than one tenant. Set the rows
   per tenant and per parent to a realistic value, because they set each
   examined count. State your values in the report.
3. Run the exact filter, sort, and limit:

```javascript
db.COLL.find(FILTER).sort(SORT).limit(N).explain("executionStats")
```

Read these fields:

- `queryPlanner.winningPlan`: walk the stages.
- `executionStats.totalDocsExamined`, `totalKeysExamined`, and `nReturned`.

Delete the container when you finish: `docker rm -f EXPLAIN_NAME`.

The examined counts prove the plan. Local timings do not predict production,
because a small seed hides a scan and the container has no network distance. A
better plan with the same local time is not proof of a production gain.

| Result | Meaning |
| -- | -- |
| `COLLSCAN` | No usable index. Add one, unless the collection is small and bounded |
| `SORT` stage above the scan | The index does not supply the order. The whole match is read and sorted |
| Examined far above returned | The index narrows too little. Move the selective keys forward |
| `IXSCAN`, examined close to returned, no `SORT`, `nReturned` above 0 | Correct |
| `nReturned` is 0 | Proves nothing. Fix the seed or the filter, then run it again |

## Build the compound index

Order the keys as **tenant, then equality, then sort, then range**. Match the
sort direction, or its exact reverse.

The index must include every key of the query's sort, including a tie-break.

| Shape (measured) | Plan | Examined / returned |
| -- | -- | -- |
| Index `{ws, created_at:-1}`, sort `{created_at:-1}` | `IXSCAN`, no sort | 20 / 20 |
| Index `{ws, created_at:-1}`, sort `{created_at:-1, _id:-1}` | **`SORT`** | **1000 / 20** |
| Index `{ws, created_at:-1, _id:-1}`, same sort | `IXSCAN`, no sort | 20 / 20 |
| Index `{ws, status, created_at:-1}`, filter `{ws}`, sort `{created_at:-1}` | **`SORT`** | keys **1000** / 20 |
| Same index, filter `{ws, status: {$in: [a, b]}}`, same sort | `SORT_MERGE` | 20 / 20 |
| Index `{user, archived, updated:-1}`, filter `{pid, user}` | `IXSCAN` on `user` only | **100 / 1** |
| Index `{user, pid}`, same filter | `IXSCAN` | 1 / 1 |
| Partial index on `status $exists`, filter does not name `status` | **`COLLSCAN`** | **3802 / 20** |
| Same index, filter includes `status: {$exists: true}` | `IXSCAN` | 20 / 20 |

Three of these shapes recur in the fleet:

- **Keyset pagination** sorts on `(created_at, _id)`. The index must end with
  both keys.
- **An optional filter** leaves a middle key unconstrained, which breaks the
  sort. When a handler has an `include*` flag, run explain with the flag on and
  off.
- **A lookup by id** with a tenant prefix reads every row of that tenant unless
  the id is in the index.

A partial index serves only a filter that implies its partial expression. Add
that clause to the filter.

## Limit index count

Each index costs a write and, on Flex, storage. Before you add one:

- Check whether an existing index can serve the query with one more key.
- Remove a new index that is a prefix of another index.
- Keep a collection at about 20 indexes or fewer.

## Regex

A prefix-anchored, case-sensitive `$regex` narrows an index. An unanchored or
case-insensitive one can read the whole index or collection. On a user-typed
search, use a normalized field with a prefix query, or Atlas Search on a
supported tier.

## Remove query loops

A store call inside a loop is one round trip per row. Fetch with `$in` on the
ids, then join in Go. Keep the `$in` list bounded. Count commands in a test with
the repo's query counter, if it has one. `auth`'s `QueryCounter` is the
reference.

## Cache a read

Use the repo's helper. Read its header comments first.

1. Add the collection to the repo's cache registry and TTL lookup, if it has
   them. Names differ by repo: `cachedCollections`, `cacheRegistry`, `ttlFor`,
   `readKey`, `listTTL`.
2. Name the read. Pass each owner axis that the filter scopes by.
3. Pass anything else that changes the returned rows as its own key part.
4. Confirm how writes invalidate. The monitor handles this in most repos.
   `aihero-wayfare` uses explicit `invalidate*` calls, and
   `TestEveryWriteInvalidates` enforces them. Add the call there.
5. Add a test with two owners.

Do not cache these reads unless the repo's `DESIGN.md` allows it:

- An ownership or authorization check.
- A read inside a transaction. The helper bypasses it.
- A read followed by a write that depends on it.

Invalidation is per collection. One write retires every cached read of that
collection, for every tenant. A collection with frequent writes gains little, so
measure the hit rate before you rely on the cache.

## Completion check

- Each new query has an explain result in the PR description.
- Each list read has a limit, or a comment that says why it has none.
- No store call was added inside a loop.
- Each speed claim has a before and after measurement.
