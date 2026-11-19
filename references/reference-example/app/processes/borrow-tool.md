process: borrow-tool@1

# Borrow a tool

**Purpose:** a member finds a free tool, holds it, and takes it home with a date
to bring it back.

realizes: value-stream:lend-a-tool@1 stage 1, stage 2, stage 3

uses: capability:tool-discovery@1, capability:reservation@1

follows: decision:loan-rules@1

| Step | Actor | Touches | What happens |
| -- | -- | -- | -- |
| find | persona:weekend-member@1 | tool (read) | browses or searches the catalog; only `available` tools can be chosen |
| reserve | persona:weekend-member@1 | tool.status (update) | holds the tool for a pickup day; it becomes `reserved` |
| hand-over | persona:shift-volunteer@1 | loan (create), tool.status (update) | records the loan with its due date; the tool becomes `on-loan` |
