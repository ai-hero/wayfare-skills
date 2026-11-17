# reference changelog

One line per version bump, newest first:
`KIND:ID@VERSION: what changed; what an item pinned to the old version must re-check`.

- process:return-tool@2: an `inspect` step now sits between `receive` and
  `restock`; a build pinned to @1 must not put a returned tool back on loan
  before its condition is recorded.
- entity:loan@2: `due_on` is now required at checkout and `condition_on_return`
  was added; a build pinned to @1 must reject a loan without a due date and
  store the condition the returns desk records.
- value-stream:lend-a-tool@1, capability:tool-library@1, entity:member@1,
  entity:tool@1, entity:loan@1, process:borrow-tool@1, process:return-tool@1,
  screen:catalog@1, screen:returns-desk@1, component:tool-card@1,
  component:condition-check@1, prototype:tool-library@1: first written.
