---
name: wayfare-audit-compliance
# prettier-ignore
description: "Audit this repo against the compliance baseline, or audit the fleet at merged state. Report register defects, regenerate CONSISTENCY.md, and draft template backports. Use to check compliance without a full roadmap sync."
argument-hint: ""
compatibility: "Requires the complete Wayfare plugin, git, and Python 3; fleet mode also requires sibling checkouts and FLEET.md."
---

# Audit the repo, or the fleet, against the compliance register

Run the compliance stage of `wayfare:wayfare-sync-plan` independently. Also
draft backports, which `sync` does not draft. `scripts/audit.py` computes
results for each check and repo from the register in
`assets/compliance/README.md`.

## Instructions

### Step 0: load

```bash
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If the command prints `FLEET_ROOT`, select the family audit below. Otherwise,
select the repo audit. Read `../../references/loading.md` before the repo audit.
Complete its checklist first.

### The audit

Read `../../references/improve.md`. It owns both forms: the repo audit with its
backport drafts, and the family audit at the fleet root with its register-defect
reporting and `CONSISTENCY.md` regeneration.

## Next steps

- Items the audit proposed, now on the roadmap →
  `wayfare:wayfare-advance-item ID`
- A full convergence instead of compliance alone → `wayfare:wayfare-sync-plan`
