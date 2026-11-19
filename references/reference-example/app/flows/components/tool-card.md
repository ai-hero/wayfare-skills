component: tool-card@1

# ToolCard

used on: catalog

## Takes

- tool.tool_id, name, category, status
- whether the member can reserve another tool (fewer than three open loans)

## Affordances

- **Reserve** (when the tool is `available` and the member is under the limit)
  calls `ReserveTool(tool_id)`, which sets tool.status to `reserved`; the member
  stays on the catalog and the card shows "Held for you".

## States

- **available:** the Reserve button
- **held:** "Held for you", no button
- **at limit:** "Return a tool to reserve another", no button
