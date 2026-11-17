entity: tool@1

# Tool

One physical tool on the library's shelves. Two identical drills are two tools.

- **Owned by:** this app.
- **Identity:** `tool_id`, the number on the tag fixed to the tool.
- **Grain:** one per physical tool.

## Attributes

| Attribute | Type | Required | Notes |
| -- | -- | -- | -- |
| tool_id | string | yes | the tag number |
| name | string | yes | for example "cordless drill" |
| category | string | yes | one of `power`, `hand`, `garden`, `ladder` |
| status | enum | yes | `available`, `reserved`, `on-loan`, `returned`, `in-repair`, `retired` |
| last_checked_on | date | no | set by the returns desk's condition check |

## Relationships

- **loan:** one-to-many; at most one loan is open at a time.

## Rules

- Only an `available` tool can be reserved.
- A `returned` tool is not `available` until its condition is recorded.
