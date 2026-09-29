---
name: wayfare-audit-compliance
# prettier-ignore
description: "Run the compliance register audit on its own (this repo against the baseline, or the whole fleet at merged state), report register defects, regenerate CONSISTENCY.md, and draft backports to the template. Use to check conformance without a full roadmap sync."
argument-hint: ""
compatibility: "Requires the complete Wayfare plugin, git, and Python 3; fleet mode also requires sibling checkouts and FLEET.md."
---

# Audit the repo, or the fleet, against the compliance register

The compliance stage of `wayfare:wayfare-sync-plan`, runnable on its own, plus
the half `sync` never does: the backports. `scripts/audit.py` computes (check x
repo) results from the register described in `assets/compliance/README.md`.

## Instructions

### Step 0: load

```bash
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

`FLEET_ROOT` selects the family audit below. Otherwise this is a repo audit;
read `../../references/loading.md` and work its checklist first.

### The audit

Read `../../references/improve.md`. It owns both forms: the repo audit with its
backport drafts, and the family audit at the fleet root with its register-defect
reporting and `CONSISTENCY.md` regeneration.

## Next steps

- Items the audit proposed, now on the roadmap →
  `wayfare:wayfare-advance-item ID`
- A full convergence instead of compliance alone → `wayfare:wayfare-sync-plan`
