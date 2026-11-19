capability: tool-discovery@1

capability: reservation@1

capability: returns@1

capability: condition-tracking@1

# Capabilities

What the library must be able to do, not how. One row per capability; a value
stream stage names the capabilities it uses.

| Capability | What | Stages that use it |
| -- | -- | -- |
| tool-discovery | knowing which tools exist and which are free | lend-a-tool 1, 2 |
| reservation | holding a tool for a member and recording the loan | lend-a-tool 2, 3 |
| returns | taking a tool back and closing its loan | lend-a-tool 5 |
| condition-tracking | knowing whether each tool works | lend-a-tool 5, 6 |
