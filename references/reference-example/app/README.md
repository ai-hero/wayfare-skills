# reference/ in the example app repo

**Fictional**, like the rest of [../README.md](../README.md). In an app repo
this folder is `reference/` at the root: what the library's lending app is meant
to be. Its business and organization are not here; they live in the fleet repo
([../fleet/](../fleet/)) and every file here cites them by pin.

| File | Header | Layer |
| -- | -- | -- |
| `personas/weekend-member.md` | `persona: weekend-member@1` | personas |
| `personas/shift-volunteer.md` | `persona: shift-volunteer@1` | personas |
| `entities/member.md` | `entity: member@1` | entities |
| `entities/tool.md` | `entity: tool@1` | entities |
| `entities/loan.md` | `entity: loan@2` | entities |
| `processes/borrow-tool.md` | `process: borrow-tool@1` | processes |
| `processes/return-tool.md` | `process: return-tool@2` | processes |
| `flows/screens/catalog.md` | `screen: catalog@1` | UX flow |
| `flows/screens/returns-desk.md` | `screen: returns-desk@1` | UX flow |
| `flows/components/tool-card.md` | `component: tool-card@1` | UX flow |
| `flows/components/condition-check.md` | `component: condition-check@1` | UX flow |
| `prototype/README.md` | `prototype: tool-library@1` | prototype |

`CHANGELOG.md` records the two bumps so far: `entity:loan@2` and
`process:return-tool@2`.
