process: return-tool@2

# Return a tool

**Purpose:** a returned tool is checked before anyone else borrows it, so the
next member gets a tool that works.

realizes: lend-a-tool@1 stage 5

| Step | Actor | Touches | What happens |
| -- | -- | -- | -- |
| receive | desk volunteer | loan.returned_on (update), tool.status (update) | takes the tool back; it becomes `returned` |
| inspect | desk volunteer | loan.condition_on_return (update), tool.last_checked_on (update) | records the condition with the guided check |
| restock | desk volunteer | tool.status (update) | a `good` or `worn` tool becomes `available`; a `broken` one becomes `in-repair` |
