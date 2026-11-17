prototype: tool-library@1

# Prototype

A click-through of the reference that is cheap enough to throw away. People try
the catalog and the returns desk here before any real code is written, so a
missing state or a wrong attribute turns up while it costs a minute to fix.

## Shape

- **A small browser app** whose screens follow `flows/`.
- **SQLite in the browser.** `schema.sql` is written from `entities/`;
  `seed.sql` is the demo data. Nothing persists: every start, and **Reset
  demo**, drops the database and loads the seed again.
- **The seed reaches every state.** It holds a free drill, a held ladder, a
  member at the three-loan limit, and a returned drill waiting four days for its
  check, so every state in `flows/` can be reached by clicking.
- **A docked guided tour** walks `borrow-tool` and `return-tool` step by step,
  naming the step and the entity field each click changes.

## Files

| File | Holds |
| -- | -- |
| `schema.sql` | the entities as tables |
| `seed.sql` | the demo data |

This example carries the two SQL files only; a real prototype adds its screens
beside them.
