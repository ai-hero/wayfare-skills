# Model route

Read this file for a new or changed collection, field, type, or relationship.

## Representation

Keep one struct per stored entity, in the stored-types package you found in Step
1\. A store-only struct is acceptable for a projection or a raw row that a caller
never sees as the entity.

A new field needs these decisions in the same change:

1. **Field name.** Use `snake_case` in the bson tag. Do not reuse the name of a
   removed field.
2. **Absent value.** Old documents do not have the new field. State what the
   code reads for an absent field, and test it.
3. **Proto.** Add the field with the next free number, and never renumber. Run
   the repo's `proto-breaking` command before you change a shipped proto.
4. **Converter.** Update the hand-written converter in both directions.
5. **Cache shape.** Read the repo's `lib/cache`. If a cached struct changes
   shape, bump `keyVersion` so a new binary does not decode old JSON.

## Conventions

Follow the repo's existing choice for each item below. Use the default in a new
repo only.

| Item | Default | Trap |
| -- | -- | -- |
| Id | The repo's existing id type | Mixed id types across references make joins fail with no error. Compare a reference's type with its target's `_id` |
| Time | UTC `time.Time`, field name `created_at` or `updated_at` | A date stored as a string sorts by text and cannot use date operators |
| Tenant | First field of the document and of each compound index | A field that is only in the filter does not protect a cache key |
| Delete | Hard delete unless the product needs a restore | A soft-delete field must appear in every filter and in the index that serves it |
| Concurrency | A version or timestamp in the update filter | A read followed by a blind write loses updates |
| Polymorphic document | One `type` field and one struct per type | A map of unknown fields cannot be indexed or validated |

## Embed or reference

Choose from the read pattern, then check the bound.

- **Embed** if the child is read with its parent and the child count has a known
  small bound.
- **Reference** if the child is read alone, is updated often, or has no bound.
- **Never** use an array that grows with user activity. A document has a 16 MB
  limit. Each element also adds index entries when the array is indexed.
- **Do not copy** a table-per-entity design from a relational model. If two
  collections are always read together, embed one in the other.
- **Copy a field** from another entity only if a read needs it often. Name who
  updates the copy when the source changes.

## List large values separately

A list read returns the whole document unless it has a projection. A field that
holds a body, a transcript, or file content must have one of these:

- a separate collection for the large value, or
- a projection on each list read that omits the large value.

## Completion check

- The change has one stored struct and no new parallel type.
- An old document without the field decodes and behaves as you stated.
- The query for each new access pattern has a route through
  [optimize.md](optimize.md).
