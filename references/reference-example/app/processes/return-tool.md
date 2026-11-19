process: return-tool@2

# Return a tool

**Purpose:** a returned tool is checked before anyone else borrows it, so the
next member gets a tool that works.

realizes: value-stream:lend-a-tool@1 stage 5

uses: capability:returns@1, capability:condition-tracking@1

follows: decision:retire-a-tool@1

| Step | Actor | Touches | What happens |
| -- | -- | -- | -- |
| receive | persona:shift-volunteer@1 | loan.returned_on (update), tool.status (update) | takes the tool back; it becomes `returned` |
| inspect | persona:shift-volunteer@1 | loan.condition_on_return (update), tool.last_checked_on (update) | records the condition with the guided check |
| restock | persona:shift-volunteer@1 | tool.status (update) | a `good` or `worn` tool becomes `available`; a `broken` one becomes `in-repair`, where decision:retire-a-tool@1 takes over |
