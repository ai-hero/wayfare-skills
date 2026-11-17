process: borrow-tool@1

# Borrow a tool

**Purpose:** a member finds a free tool, holds it, and takes it home with a date
to bring it back.

realizes: lend-a-tool@1 stage 1, stage 2, stage 3

| Step | Actor | Touches | What happens |
| -- | -- | -- | -- |
| find | member | tool (read) | browses or searches the catalog; only `available` tools can be chosen |
| reserve | member | tool.status (update) | holds the tool for a pickup day; it becomes `reserved` |
| hand-over | desk volunteer | loan (create), tool.status (update) | records the loan with its due date; the tool becomes `on-loan` |
