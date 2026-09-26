---
description: "Repo-specific exceptions to the AI Hero design system rules: facts this repo alone knows."
paths:
  - "**/*.tsx"
  - "**/*.jsx"
  - "**/*.css"
---

# This repo's design-system exceptions

This file is created once by the installer and never touched again: a
re-vendor of `design-system.md` cannot overwrite or delete anything written
here. That is the point: it is the only place a repo-specific fact can live
where an upstream fix is guaranteed not to erase it.

Add a fact here when it is true of THIS repo and would be wrong to state as a
general rule: an app-authored file with no registry equivalent, a check not
yet wired, a migration already in progress with a temporary exception. Delete
an entry once it stops being true; a stale exception here is invisible to every
check in the family, so nothing else will catch it going stale.

Leave this file's body empty (just this header) until there is a real
repo-specific fact to record.
