---
description: "UI constraints for the AI Hero design system: registry components and semantic tokens only."
paths:
  - "**/*.tsx"
  - "**/*.jsx"
  - "**/*.css"
---

# UI: the AI Hero design system

UI comes from AI Hero's private shadcn registry (`@aihero`), not from scratch,
not from stock shadcn. **Before writing any component, search the registry.**
There are ~80 installable components (66 primitives + 12 blocks: button, card,
field, table, chart-\*, app-shell, top-bar, landing-page, …) alongside ~80 usage
examples:

```bash
npx shadcn@latest search @aihero -q "WHAT_YOU_NEED" -c PATH_TO_UI
npx shadcn@latest view @aihero/ITEM -c PATH_TO_UI   # inspect the API first
npx shadcn@latest add @aihero/ITEM -c PATH_TO_UI
```

`-c` is not decoration: it sets the CLI's working directory, which is both where
`components.json` is read and where `.env` is looked up (see **Auth**). Prefer
the repo's task-runner wrapper (`just ui-add …`) where one exists. It passes
`-c` and exports the token.

Every path below (`src/components/...`) is relative to `PATH_TO_UI`, not the
repo root, the same frame `-c` establishes above. For the common layout where
that's `ui/`, read `src/components/ui/` as `ui/src/components/ui/`.

Hand-rolling a component that already exists in the registry is the primary
defect this rule prevents.

## Vendored, not authored

Installed components land in `src/components/ui/` (primitives) and
`src/components/blocks/` (sections). **Never edit them in place.** A local edit
is silently reverted by the next `shadcn add --overwrite`. To change one:
compose around it, pass `className` (every item merges via `cn()`), or change it
upstream in the design system and re-add.

## Tokens only

Semantic classes only: `bg-background`, `text-muted-foreground`, `border-input`,
`bg-destructive`. Never raw palette (`bg-zinc-100`, `text-gray-500`), never hex
or `oklch()` literals in components; those belong in the `@theme` token layer.

- Text on a colored surface uses the paired foreground token (`bg-primary` →
  `text-primary-foreground`), never an eyeballed shade.
- Dark mode comes free via tokens and the `.dark` class, never
  `prefers-color-scheme`. **A `dark:` color override means you used the wrong
  token.**

## Spacing, shape, type

- **Parents own layout.** Use `gap-*` / `space-*` in the container; components
  never carry margins (`m-*`, `mt-*`, `ms-*`) on their root element.
- Spacing scale only: no `p-[13px]`, `gap-[7px]`. If the scale lacks a step, the
  design is wrong, not the scale.
- Radii from the token scale (`rounded-sm|md|lg|full`); no `rounded-[10px]`.
- **No shadows**: elevation is borders and hairlines. `--shadow-*: initial`
  makes any `shadow-*` class a lint error, by design, once `@aihero/theme` is
  adopted. Check `design-system.local.md` for whether that's actually landed in
  this repo yet; the design-token hook flags shadows either way, but only the
  token-layer override turns it into a hard lint failure.
- z-index from the named scale
  (`z-dropdown < z-sticky < z-overlay < z-modal < z-toast`); never `z-[9999]`.
- Type from the scale (`text-sm`, `font-medium`, tracking tokens); no arbitrary
  font sizes.
- Variants via `cva` with typed props: no ternary/string-concat className soup.
  Merge with `cn()`. Never hand-sort classes; `prettier-plugin-tailwindcss` owns
  the order.

## Icons and accessibility

- Lucide only, sized `size-4` / `size-5`, `aria-hidden` unless the icon is the
  only label.
- Every interactive element has a visible `focus-visible:` ring. Removing an
  outline without a replacement is a defect.
- Disabled states use `disabled:` variants + `aria-disabled`, not opacity hacks
  on wrapper divs.
- Respect `prefers-reduced-motion` for any animation.

## Component layers

Vendored registry code stays flat; this app's own components are atomic:

```text
src/components/
├── ui/          # vendored registry primitives  — never edit
├── blocks/      # vendored registry sections    — never edit
├── atoms/       # app-specific primitives the registry lacks (rare)
├── molecules/   # compositions of ui/ + atoms/
├── organisms/   # domain-aware sections
└── templates/   # layout shells with slot props — structure only, zero copy
```

Imports flow **downward only**: templates → organisms → molecules → atoms →
(`ui/`, `blocks/`). `ui/` and `blocks/` are the floor: any layer may import
them. Place each component at the lowest layer that fits; promote only when it
gains domain knowledge or composition, never preemptively.

`atoms`/`molecules` are stateless and generic: no fetching, no auth, no domain
types. `organisms` may hold domain types but still receive data via props.
`templates` never hardcode copy.

## Auth

`REGISTRY_TOKEN` (a Personal Access Token from `auth.aihero.studio/profile`) is
the only registry variable this project needs. **Never commit it.**

Two placements work, and only these two:

1. **Exported before the CLI runs**: e.g. a task-runner recipe that reads the
   repo-root `.env`. Preferred when the repo already keeps secrets at the root,
   since it avoids a second copy of the token.
2. **In the `.env` inside the CLI's `--cwd`**: for `-c ui`, that means
   `ui/.env`.

The trap: the CLI loads `.env` from its **`--cwd`** (defaulting to the process's
working directory), *not* from the repo root and *not* from wherever
`components.json` happens to live. Those last two are easy to conflate, because
`-c ui` points at the directory that holds `components.json`, but env is
resolved first, before that file is even located, so a token in the repo-root
`.env` with `-c ui` is never read. The error is
`Set the required environment variables to your .env or .env.local file`, which
reads as a missing value rather than a wrong directory. Verified against shadcn
4.13.1, whose loader is
`join(options.cwd, ".env.local"|".env.development"|".env")`.

Do not "simplify" this to "it reads `.env` next to `components.json`". That
restatement holds only while `--cwd` and the config directory coincide, and it
tells the next reader that `-c` is irrelevant to token discovery.

In `components.json` write the plain `${REGISTRY_TOKEN}` form only: the CLI
regex is `/\$\{(\w+)\}/g`, so `${VAR:-default}` ships as a literal string and
surfaces as a confusing 401.

Full procedure: `wayfare:wayfare-recomponentize-ui`.

## This repo's own exceptions

**Read `.claude/rules/design-system.local.md` before touching `ui/` in this
repo.** It holds facts specific to this codebase that the rules above cannot
know: an app-authored file with no registry equivalent, a migration already in
progress, a lint rule not yet wired. This file (`design-system.md`) is NOT
refreshed automatically: a drifted copy gets flagged (a `.new` file written,
exit 2) for manual reconciliation, never silently overwritten. `.local.md` is
created once, empty, on first install, and never touched again by any installer,
which is what lets it hold repo truth that a re-vendor of this file cannot
delete.
