# Migrate route

Read this file for a new index, backfill, rename, removal, or other schema
change. The behaviour marked **measured** comes from `mongo:8` on 2026-11-07.

## The model

Five rules, stated for any store. This file gives the MongoDB mechanics.

1. **Every migration works with the release before it, including after a
   rollback.** The rollout starts the new task before it stops the old one, and
   a failed rollout restores the old image without undoing the migration. So the
   old release must keep reading and writing the data the migration left.
2. **A destructive step carries a `contract:` comment** naming the last release
   that read the old shape. Nobody drops a shape a release can still read.
3. **Migrations run under a lease in the store, and only the API role
   migrates.** Steps stay idempotent anyway.
4. **A backfill is a background job, never part of boot.** Boot creates indexes
   and does fast shape fixes only.
5. **The rule belongs to the store, not to MongoDB.** A SQL store would change
   the mechanics below and keep the five rules.

Migrations are ordered, named Go steps. A failed step stops the boot of the API
role. There is no down step in most repos.

### The lease

A lease is one document in a small collection, for example `migration_lock` with
`_id: "migrate"`. It is not a version table and not a migration framework.

- Take it with `findOneAndUpdate` on
  `{_id: "migrate", $or: [{expiresAt: {$lt: now}}, {expiresAt: {$exists: false}}]}`,
  upsert, and set `holder` and `expiresAt: now + ttl`. A duplicate key error
  means someone else holds it.
- Renew `expiresAt` on a timer while steps run, only if `holder` still matches.
  Stop the runner if a renewal fails.
- Release it when the steps finish. A crashed holder frees the lease by expiry.
- A waiter polls with a deadline shorter than the healthcheck start period in
  the deploy file, then exits non-zero. A waiter that outlasts the start period
  gets killed by the health check, which hides the real cause.
- Expiry means two holders can overlap in principle, for example after a long
  pause. That is why each step stays idempotent.

Only the API entrypoint calls the runner. Use the repo's existing role switch.
Do not invent an environment variable for it. Workers, cron tasks and other
roles wait for the schema through their own readiness check and never migrate.

Add a step in the repo's existing mechanism. If the repo has separate baseline
indexes and a migration list, follow its comments about which one to use. Do not
add a migration framework or a version table. Do not edit a shipped step to mean
something new. Add a new step instead.

## Index names (measured)

Always set an explicit name. Include each key in the name, in order.

| Action | Result |
| -- | -- |
| Same name, same spec | No-op. This is the idempotence |
| Same name, different keys or options | Error 86 `IndexKeySpecsConflict`. The boot stops |
| New name, same keys, adds `unique`, `sparse`, or `partialFilterExpression` | Succeeds. Both indexes exist |
| New name, same keys, identical options or `expireAfterSeconds` | Error 85 `IndexOptionsConflict`. The boot stops |
| No name, extended key list | A second index is created silently |
| `unique` over existing duplicates | Error 11000 `DuplicateKey`. The boot stops |

## Change an existing index

Create the replacement first, then remove the old index. This order keeps reads
indexed. It also keeps a unique constraint enforced.

1. Add a step that creates the replacement under a new name.
2. Deploy, and confirm that the new index exists.
3. Add a later step that drops the old name.
4. Confirm the drop with `getIndexes`. On `mongo:8` a drop of a missing name
   returned `ok`, so a wrong old name passes with no error.

Error 85 needs a different path:

- For identical options, keep the old name. A rename alone gains nothing.
- For `expireAfterSeconds`, change the value with `collMod`.

## Before you add a unique index

1. Query for duplicates in the migration, with an aggregation on the unique
   keys.
2. Resolve the duplicates in an earlier step. Ask the user how to resolve them
   if the rows belong to customers.
3. Remember that a missing field counts as a value unless the index is partial.

## Change a shape in three releases

Use expand and contract. Each release must run beside the previous one, and must
still work if the next release rolls back to it.

1. **Expand.** Add the new field or index. Write both shapes. Read the old
   shape.
2. **Backfill.** Start a background job that converts old rows. Read the new
   shape, and fall back to the old one.
3. **Contract.** Add a later step that removes the old field. Delete the
   fallback. Ship it only after the completion marker says the backfill
   finished.

Do not combine these into one release if old and new code overlap during deploy.
Read the repo's deploy file before you assume they do not overlap.

The rollback case: if the expand release fails its rollout, the old image comes
back with the new field or index still in place. It must ignore them. If the
backfill release rolls back, the converted rows must still read under the old
code, which is why expand writes both shapes first. The contract release is the
one that cannot be rolled back, so it is the one that waits for the marker.

The same order applies to a wire contract. A field removed from a protobuf
message follows the same three releases, and `buf breaking` is the check that
the new schema still reads the previous release's messages.

## Backfill rules

A backfill never runs at boot. It is a resumable background job that starts
after the server listens.

- Filter so a finished row does not match, for example
  `{field: {$ne: desired}}`. A second run must match nothing, and a restart
  resumes where the filter leaves off.
- Use a bulk update with that filter, in batches. Do not count rows and then
  insert.
- Do not scan a whole collection on each start. Use a filter with an index.
- Log the count changed and the duration for each batch.
- Write a completion marker when a run finds no rows left. The contract release
  checks the marker before it removes the old shape.
- The job may overlap with another replica's job, so each batch is idempotent.
  Take the lease again only if the job must not overlap.

## Destructive steps

A destructive step is a drop, a delete, `$unset`, `$rename`, a new unique index
or `collMod`. Each carries a comment in this form, because it cannot be undone
by rolling back the image:

```go
// contract: v1.42.0 is the last release that reads the old shape
```

Stop and ask the user before you add any step that deletes rows, drops a
collection, or removes a field with data. Show these items:

- The filter, and a count from a copy of the data if one is available.
- A check of what the filter does with a missing field. `{$not: {$in: [...]}}`
  also matches a document with no such field.
- The restore path. Name the backup the restore uses.

A destructive step runs on every boot, so its filter must stay safe after future
writes.

## Remove an index

Removal has two stages because a rebuild is expensive.

1. Find a candidate with `$indexStats`. Its counters reset on restart, so a low
   count proves little after a recent deploy.
2. Confirm that no index carries correctness. A unique index protects data even
   with zero reads.
3. Ask the user to hide the index in production with `db.COLL.hideIndex(NAME)`
   and to watch latency. Do not run this yourself.
4. Add a migration step that drops it.

## Flex

Flex does not support rolling index builds, so each build runs on the live
cluster. Add a new index before its collection grows if you can.

## Completion check

- The step ran twice, and the second run changed nothing.
- The previous release still works against the migrated database.
- Every destructive step carries a `contract:` marker.
- The backfill is a background job with a completion marker, not a boot step.
- The step ran against a database in the old shape.
- Old code can read what the new code writes during the deploy overlap.
- Every destructive step was confirmed by the user.
