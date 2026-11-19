screen: catalog@1

# Catalog

serves: borrow-tool.find, borrow-tool.reserve

for: persona:weekend-member@1

## Loads

- **on enter:** `ListTools(status: available)`, first page, giving tool.tool_id,
  name, category and status.
- **refreshes:** after a reservation, and on "Load more".

## Places

- ToolCard, once per tool in the page

## States

| State | When | Shows |
| -- | -- | -- |
| ready | the list loaded | the ToolCards |
| empty | no tool is `available` | "Every tool is out right now" |
| signed out | the session has ended | a Sign in button; the list is not shown |
| failed | the list could not load | "Could not load the catalog" and Try again |
