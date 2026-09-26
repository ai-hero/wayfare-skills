# Compliance register: the baseline

`scripts/audit.py` computes (check × repo) results from a register with two
halves:

| Half | Where | Holds |
| --- | --- | --- |
| baseline | this directory, shipped with the plugin | controls and checks any repo on this workflow is held to; generic rationale only |
| overlay | the fleet's register checkout (FLEET.md `register:`, default `.fleet/`) | the fleet's incident history, `applies_to: [GROUP, …]` narrowings, any controls or checks of its own, and a `checkers.py` holding the checkers that know its repos by name. It may NOT name a repo in a check: `reference:` and `known_violations` are retired and rejected at load |

Merged by id, overlay fields winning. A check's `applies_to` may name
FLEET.md groups (`template`, `apps`, `infra`, …); a repo outside them reads
n/a, which is how a fleet keeps an infra repo in the family without holding
it to app-shaped conventions. It may instead name a capability (`go`, `ships-image`,
the closed set in `audit.py`'s `CAPABILITIES`), which the checker detects
for itself and the engine ignores. Any other name fails to load. Explicit
per-capability repo lists are not a thing: they are a copy of what
detection answers, and copies go stale.

A mapped register that is not cloned is an error, never a baseline-only run:
the audit would report a fleet that got greener because its overlay was
missing. Outside a fleet only the baseline
applies and the family is the current repo. Results are never stored: a
stored result is a copy, and copies drift. `scripts/consistency.py` writes
the fleet's human table into the register checkout, never here.

Unlike the other assets, nothing here is installed into a repo. A repo that
carries a copy of the register fails REG-01.
