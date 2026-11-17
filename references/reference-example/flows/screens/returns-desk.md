screen: returns-desk@1

# Returns desk

serves: return-tool.receive, return-tool.inspect, return-tool.restock

Used by desk volunteers only.

## Loads

- **on enter:** `ListTools(status: returned)`, oldest return first, giving
  tool.tool_id, name and the open loan's member and returned_on.
- **refreshes:** after every saved check.

## Places

- ConditionCheck, for the tool the volunteer picks from the list

## States

| State | When | Shows |
| -- | -- | -- |
| ready | at least one tool is waiting | the waiting list, oldest first, with its age in days |
| clear | nothing is waiting | "Nothing waiting for a check" |
| not permitted | the person is not a desk volunteer | "Desk volunteers only" |
| failed | the list could not load | "Could not load returns" and Try again |
