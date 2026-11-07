# Migrate route

Read this file for a new index, backfill, rename, removal, or other schema
change. The behaviour marked **measured** comes from `mongo:8` on 2026-11-07.

## The model

Migrations are ordered, named Go steps. They run on every boot, before the
service accepts traffic. A failed step stops the boot. There is no version table
and no down step in most repos. Replicas and overlapping deploys can run the
same step at the same time, so each step must be idempotent without a lock.

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
| New name, same keys, different options | Error 85 `IndexOptionsConflict`. The boot stops |
| No name, extended key list | A second index is created silently |
| `unique` over existing duplicates | Error 11000 `DuplicateKey`. The boot stops |

## Change an existing index

If the keys change:

1. Add a step that creates the replacement under a new name.
2. Deploy, and confirm that the new index exists.
3. Add a later step that drops the old name. Treat `IndexNotFound` as success.

If only options such as `unique` change, the old and new index cannot exist
together, because that is error 85:

1. Add one step that drops the old name, then creates the new name.
2. Tell the user that reads on those keys are unindexed between the two calls.

## Before you add a unique index

1. Query for duplicates in the migration, with an aggregation on the unique
   keys.
2. Resolve the duplicates in an earlier step. Ask the user how to resolve them
   if the rows belong to customers.
3. Remember that a missing field counts as a value unless the index is partial.

## Change a shape in three releases

Use expand and contract. Each release must run beside the previous one.

1. **Expand.** Add the new field or index. Write both shapes. Read the old
   shape.
2. **Backfill.** Add a step that converts old rows. Read the new shape, and fall
   back to the old one.
3. **Contract.** Add a later step that removes the old field. Delete the
   fallback.

Do not combine these into one release if old and new code overlap during deploy.
Auth overlaps. Read the repo's deploy method before you assume it does not.

## Backfill rules

- Filter so a finished row does not match, for example
  `{field: {$ne: desired}}`. A second run must match nothing.
- Use a bulk update with that filter. Do not count rows and then insert.
- Do not scan a whole collection on each boot. A step that always scans costs
  the same on every restart. Use a filter with an index, or use the repo's
  marker mechanism where one exists.
- Check the boot budget. Repos bound boot at different values, from 30 seconds
  to 10 minutes. A slow step that exceeds the budget stops the deploy.
- Log the count changed and the duration.

## Destructive steps

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
- The step ran against a database in the old shape.
- Old code can read what the new code writes during the deploy overlap.
- Every destructive step was confirmed by the user.
