---
name: wayfare-recomponentize-ui
# prettier-ignore
description: "Refactor UI into atomic layers, replace off-token styling, and source primitives from a configured registry or stock shadcn. Use when asked to recomponentize, refactor UI, adopt a design system, or clean up component structure."
argument-hint: "[--audit-only] [REGISTRY_NAMESPACE] | recalibrate"
compatibility: "Requires the complete Wayfare plugin and the package manager, UI framework, and registry access used by the target project."
---

# Recomponentize UI: atomic components, sourced from the design system

Refactor the app's UI into atomic component layers. Replace locally written
primitives when equivalent upstream primitives exist.

Always **recomponentize components into atomic layers**. Always **replace
styling that violates design tokens**. If a registry is available, **replace
local primitives with registry components**.

## Pipeline DAG

```
preflight → enforce → inventory → map → install → recomponentize → codemod → verify
```

Print the DAG line at the start of each step:

```
[N/8] (✓) preflight → (▶) enforce → ( ) inventory → ( ) map → ( ) install → ( ) recomponentize → ( ) codemod → ( ) verify

Now running: enforce
```

Install enforcement before rewriting code. The path-scoped rule must guide the
migration and future work.

If no registry is configured, still run `map` and `install`. Use stock shadcn or
the project's existing UI library.

## Arguments

- `$ARGUMENTS`:
  - `recalibrate` - tune the `HERO.md` fields this skill reads, then stop (see
    below). Matched before every other form.
  - (none) - full pass using the component source resolved in Step 0
  - `--audit-only` - run `wayfare-check-preflight`, `inventory`, `map`. Report
    the plan, change nothing. Skips `enforce` too: installing the rule and hook
    writes files, which `--audit-only` promises not to do.
  - `REGISTRY_NAMESPACE` - override the registry, for example `@acme`

## `recalibrate`

`wayfare:wayfare-recomponentize-ui recalibrate` tunes this skill's config. It
stops after tuning and does not run the main procedure.

Check for `recalibrate` before you parse other arguments. If the first token of
`$ARGUMENTS` is exactly `recalibrate`, print
`wayfare-recomponentize-ui: running recalibrate`, follow the four phases in
[docs/RECALIBRATE.md](../../docs/RECALIBRATE.md): report, ask, write, commit.
Use the table below as the report. Stop after these phases.

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
"$WAYFARE_ROOT/scripts/hero-fields.sh" wayfare-recomponentize-ui
```

Ask only about rows whose CURRENT value is `(unset)`, `(no-section)`,
`(refused)`, `(absent)`, or `(no-file)`. Also ask about rows the user identifies
as wrong. Do not ask about a row that already has the correct value.

## Step 0: Resolve the component source

**If the first token of `$ARGUMENTS` is exactly `recalibrate`, run the
`recalibrate` section above and stop.** Do this before the producer opt-out
below, which halts the skill entirely on a `role: producer` repo and would take
the verb down with it.

### Producer repos must opt out, so check this first

**If `HERO.md` says `role: producer` (or `enabled: false`) under
`## Design System`, stop immediately.** Report that this repo *publishes* the
design system and exit without changing anything. A registry repo's pipeline
runs mockup → design system. This skill would reverse that direction and make
the repo consume its own output.

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
# Reads a whole BLOCK, not a scalar field — hero_connection cannot express this.
# Both spellings: the connection block, and the `## Design System` section an
# unmigrated repo still carries. Matching only the first returns empty on those
# repos, and `sed` exits 0 on empty, so the `||` fallback never fires and the
# run reads as "no registry configured" for a repo that has one.
sed -n -e '/^### design-system/,/^#\{2,3\} /p' -e '/^## Design System/,/^## /p' "$ROOT/HERO.md" 2>/dev/null `# hero-lint: allow-inline` | grep . || echo "NO_DESIGN_SYSTEM_CONFIG"
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If the command prints `FLEET_ROOT`, stop this repo procedure. Follow **At the
fleet root** in `docs/FLEET-MD.md`.

A repo is a producer if it builds a `registry.json`, serves `/r/*`, or its
`components.json` aliases `ui` to an internal atomic directory rather than
`@/components/ui`. If those signals are present but `HERO.md` says `consumer`,
trust the signals, stop, and tell the user `HERO.md` looks wrong.

### Pick the component source

Resolve in this order and **state which one you picked** before proceeding:

| Condition | Source |
| -- | -- |
| The `design-system` connection carries a `namespace` | That registry |
| No config, but the user wants one | Offer `@aihero` at `https://design.aihero.studio`. Needs a token (Step 1) |
| No registry, `components.json` exists | Stock shadcn: `npx shadcn@latest add ITEM` |
| No registry, another UI lib in `package.json` (MUI, Chakra, Mantine, Ant) | That library's primitives. Do not migrate libraries uninvited |
| Nothing, just plain HTML and CSS | Recomponentize and codemod only. **Ask** before introducing any dependency |

Expected keys on the `design-system` connection (docs/CONNECTIONS.md):
`namespace`, `registry-url`, `token-env-var`, `docs`, `atomic-layers`. A repo
that has not migrated still carries them under `## Design System`. Read that as
the same block rather than reporting no registry. AI Hero defaults:

- namespace: `@aihero`
- registry-url: `https://design.aihero.studio/r/{name}.json`
- token-env-var: `REGISTRY_TOKEN`
- docs: `https://design.aihero.studio`

**If the registry publishes a consumer handbook, read it first and let it win
over this skill.** For `@aihero` that is `handbook/consuming-the-registry.md` in
the `ai-hero/design-system` repo, which ships a canonical consumer AGENTS.md
stanza and consumer SKILL.md. Install those rather than re-deriving them.

Never introduce a UI library into a project that has none without asking. The
atomic refactor is valuable on its own and carries no new dependency.

## Step 1: Preflight (`wayfare-check-preflight`)

**Skip to Step 2 when the source is "recomponentize only". The enforcement layer
still applies.** Otherwise, never run `npx shadcn init` on an existing project.
It does not add the `registries` block and may pick a conflicting style.

| Check | Requirement |
| -- | -- |
| `components.json` | Has a `registries` block for the namespace and `"ui": "@/components/ui"` |
| Token expansion | Header is `Bearer ${REGISTRY_TOKEN}`, the plain form ONLY |
| `.env` | Holds the token. `.gitignore` covers `.env` BEFORE the token is written |
| `src/lib/utils.ts` | Exports `cn` (clsx + tailwind-merge) |
| `tsconfig.json` | `baseUrl: "."` and `paths: { "@/*": ["./src/*"] }` |
| CSS entry | Imports tailwind (v4). `components.json` names it in `tailwind.css` |
| Runtime deps | `react@^19`, `react-dom@^19`, `tailwindcss@^4`, `clsx@^2`, `tailwind-merge@^3`, `shadcn@^4.13.0` |

**Trap: never write `${VAR:-default}`.** The CLI's expansion regex is
`/\$\{(\w+)\}/g`, so the default form ships as a literal header string and
surfaces as a confusing 401 instead of a missing-variable error.

**Trap: do not copy the design system's own `components.json`.** A registry
repo's config points at localhost and aliases `ui` to its internal atomic dir.
Those are wrong in a consumer.

If the project has a committed `.env`, rename it to `.env.example`, strip the
value, and gitignore the real one. Never commit a token.

**Trap: `.env` must sit next to `components.json`, not in the cwd.** Verified
empirically against shadcn 4.13:

| `.env` location | cwd | Result |
| -- | -- | -- |
| repo root | repo root, `-c ui` | **fails** |
| repo root | `ui/` | fails |
| `ui/` | repo root, `-c ui` | works |
| `ui/` | `ui/` | works |
| none, `REGISTRY_TOKEN` exported | anywhere | works |

So in a monorepo whose UI lives in `ui/`, the token goes in `ui/.env` even when
the repo's house convention keeps every other secret in a root `.env`. A root
`.env` produces
`Set the required environment variables to your .env or .env.local file`, which
reads like a missing variable rather than a wrong-directory problem, so it is
easy to misdiagnose. Exporting the variable in the shell or a task-runner recipe
also works and beats duplicating the secret.

Confirm the wiring before going further. Install the theme item first so tokens
land before any component references them:

```bash
npx shadcn@latest add NAMESPACE/theme
grep -- "--primary" src/styles.css
```

## Step 2: Install enforcement (`enforce`)

A skill only fires when the model chooses it, and model-discretion triggering is
least reliable for exactly this kind of well-trained task. These layers do not
depend on that choice, so install both:

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
"$WAYFARE_ROOT/scripts/install-design-system.sh" "$ROOT"
```

It writes, without overwriting customized files (exit 2 on drift, same contract
as `install-auto-approve.sh`):

- `.claude/rules/design-system.md`, path-scoped to `**/*.{tsx,jsx,css}`, so the
  constraints load whenever an agent reads a UI file rather than when a
  description happens to match.
- `.claude/hooks/check-design-tokens.sh` plus `PostToolUse` wiring, which flags
  raw hex, palette classes, and component-root margins on write.

Then add the registry's AGENTS.md stanza (Part 8 of the `@aihero` handbook) and
the consumer SKILL.md (Part 9). If the registry ships them, paste verbatim.

Optionally port the registry's lint config (for `@aihero`,
`eslint.taste.config.mjs`, covering Tailwind correctness, token discipline and
an a11y floor). Its atomic-boundaries block **does** apply once Step 6's layers
exist. Add `ui` and `blocks` as the lowest elements in the layer matrix.

## Step 3: Inventory the current UI (`inventory`)

Find every hand-rolled element, every oversized component, and every off-token
style. Use an Explore subagent for a large codebase.

```bash
# Hand-rolled primitives that likely exist upstream
grep -rnE '<(button|input|select|textarea|table|dialog|nav|header|footer)\b' --include="*.tsx" --include="*.jsx" src/

# Recomponentization candidates — size outliers
find src -name "*.tsx" -exec wc -l {} + | sort -rn | head -20

# Off-token styling — the codemod targets from Step 7
grep -rnE 'className="[^"]*\b(bg|text|border|ring)-(slate|gray|zinc|neutral|stone|red|blue|green|amber)-[0-9]' --include="*.tsx" src/
grep -rnE '#[0-9a-fA-F]{3,8}\b|oklch\(' --include="*.tsx" --include="*.ts" src/
grep -rnE 'className="[^"]*\bshadow-|z-\[|rounded-\[|text-\[[0-9]' --include="*.tsx" src/
grep -rnE 'className="[^"]*\bdark:(bg|text|border)-' --include="*.tsx" src/
```

Record for each finding: file, line, what it is, and the UI concept it expresses
("a primary action", "a labelled form field with error text"). The concept, not
the markup, is what you search for in Step 4.

## Step 4: Map local → upstream (`map`)

For every concept in the inventory, find its upstream equivalent. Use **both**
paths, because they surface different things:

**Search the catalog** (finds by category keyword):

```bash
npx shadcn@latest search NAMESPACE -q "form"
npx shadcn@latest view NAMESPACE/field    # inspect the API before committing
```

There is no `--registry` flag. Read registries only from `components.json`. For
`@aihero` the full catalog is `GET /r/registry.json`. There is no
`/r/index.json`.

**Browse the docs/gallery site** (finds by appearance): open it with the browser
tools and look at the rendered components. Search matches keywords. The gallery
matches *appearance*. A local "stat card" may be a `tile` or a `kpi-strip`, and
only the gallery makes that obvious. For stock shadcn, use
`ui.shadcn.com/docs/components`.

Optionally wire the registry's MCP server for in-editor search:

```bash
npx shadcn@latest mcp init --client claude
```

It reads `components.json` for registries **and** auth headers, so there is no
separate MCP auth. If `/mcp` reports no tools, run `npx clear-npx-cache`.

**Produce a mapping table and show it to the user before installing:**

```
LOCAL                          → UPSTREAM ITEM        CONFIDENCE  NOTE
src/components/Btn.tsx         → @aihero/button       high        variant=default|destructive
src/components/StatCard.tsx    → @aihero/tile         medium      confirm against gallery
src/components/Wizard.tsx      → (none)               —           keep; recomponentize only
```

Items with no upstream equivalent stay local. They still get recomponentized
(Step 6) and codemodded (Step 7). Do not force a bad match.

## Step 5: Install and rewrite call sites (`install`)

```bash
npx shadcn@latest add NAMESPACE/button NAMESPACE/card
npx shadcn@latest add NAMESPACE/button --dry-run --diff   # review a re-add
```

`registryDependencies` resolve transitively, so asking for `field` also brings
`label` and `separator`. `add` defaults to `--overwrite false`.

**Installed files are vendored, not authored.** This is the rule that matters
most: rewrite *call sites*, never the vendored files. A local edit to
`components/ui/*` is silently reverted by the next `shadcn add --overwrite`. To
change a vendored component: compose around it, pass `className` (every item
merges via `cn()`), or change it upstream and re-add.

Delete the local component only after its last call site is migrated and
typecheck passes.

## Step 6: Recomponentize (`recomponentize`)

**This step always runs. It is the point of the skill.** It runs for components
with no upstream match, for projects with no registry at all, and for the app
code that composes vendored primitives. Swapping in new components without
recomponentizing leaves the same monolith wearing new classes.

Use this layout. Keep vendored code flat. Put the app's own components in atomic
layers:

```
src/components/
├── ui/          # vendored primitives (registry or shadcn) — never edit
├── blocks/      # vendored sections                        — never edit
├── atoms/       # app-specific primitives upstream lacks (should be rare)
├── molecules/   # compositions of ui/ + atoms/
├── organisms/   # domain-aware sections; may import domain types
└── templates/   # layout shells with slot props — structure only, zero copy
```

Layer rules, enforced in review:

- **atoms / molecules** are stateless and generic: no fetching, no auth, no
  domain types. Props in, UI out. Every one accepts and merges `className`.
- **organisms** may import domain types and compose molecules, but must not
  fetch data. Supply data through props.
- **templates** define *where things go* via slot props (`header`, `sidebar`,
  `children`). They never hardcode copy or fetch data.
- **Imports flow downward only:** templates → organisms → molecules → atoms →
  (`ui/`, `blocks/`). `ui/` and `blocks/` are the floor, and any layer may
  import them. An atom importing a molecule is a defect. Restructure instead of
  suppressing the defect.
- **Same-layer imports** only for *family* relationships. Test: can you describe
  the importer without naming a different concept? "A row of buttons" is still
  buttons → atom. The moment a component combines distinct siblings (`input` +
  `button` = `search-bar`), it belongs one layer up.
- Place each component at the **lowest layer that fits**. Promote only when it
  gains domain knowledge or composition. Never preemptively.

Signals a component needs recomponentizing: boolean-prop explosion, a molecule
fetching data, two organisms sharing copy-pasted JSX, a component importing from
a higher layer, a file well above the codebase's median length.

When you move a component file, update every call site that imports it. Never
leave a temporary re-export shim. Finish the move or do not start it.

## Step 7: Codemod off-token styling (`codemod`)

| Found | Replace with |
| -- | -- |
| Raw palette (`bg-zinc-100`, `text-gray-500`) | Semantic token (`bg-muted`, `text-muted-foreground`) |
| Hex / `oklch()` literal in TSX | A token in the `@theme` layer |
| `dark:` **color** override | Delete it. A `dark:` color means the wrong token was used |
| Margin on a component root (`m-*`, `mt-*`, `ms-*`) | `gap-*` / `space-*` on the **parent**. Parents own layout |
| Arbitrary spacing (`p-[13px]`, `gap-[7px]`) | The spacing scale. If a step is missing, change the scale |
| `z-[9999]` | The named z-scale (`z-dropdown` < `z-sticky` < `z-overlay` < `z-modal` < `z-toast`) |
| `rounded-[10px]`, `text-[15px]`, any `[Npx]` | The radius / type / spacing scale |
| `shadow-*` | Remove. Elevation is borders and hairlines (`@aihero` house rule) |
| Non-Lucide icons | Lucide, sized `size-4` / `size-5`, `aria-hidden` unless it is the only label |
| Text on a colored surface | The paired foreground token (`bg-primary` → `text-primary-foreground`) |
| Removed focus outline | A visible `focus-visible:` ring. Removing one without a replacement is a defect |
| Opacity hack for disabled | `disabled:` variants + `aria-disabled` semantics |

Also: variants via `cva` with typed props, never ternary/string-concat className
soup. Never sort classes by hand. `prettier-plugin-tailwindcss` owns the order.

The no-shadow rule and the exact token vocabulary are registry-specific. With
stock shadcn, keep its default token names (`bg-background`,
`text-muted-foreground` are shared) and **do not** strip shadows. That is an
`@aihero` house rule, not a shadcn one.

## Step 8: Verify (`verify`)

```bash
npx tsc --noEmit
```

Then, using the browser tools, render the migrated screens and confirm:

1. Each replaced component renders correctly in **light and dark**. Dark mode is
   the `.dark` class, never `prefers-color-scheme`.
2. Transitive deps arrived (installing `field` must also produce `label.tsx` and
   `separator.tsx`).
3. `grep -- "--primary" CSS_ENTRY` finds the theme's variables.
4. No visual regression on screens you did not intend to touch.
5. No import-direction violations: nothing in `atoms/` imports from `molecules/`
   or above.

Run the project's own lint/typecheck/test commands from `HERO.md` before
reporting done.

## Report

```
Recomponentize UI Summary
=========================
Source:          NAMESPACE (REGISTRY_URL) | stock shadcn | recomponentize-only
Components:      N replaced upstream, M kept local
Recomponentized: N files → atoms/molecules/organisms/templates
Codemods:        N palette → token, N margins → parent gap, N arbitrary values
Enforcement:     .claude/rules/design-system.md, PostToolUse hook, AGENTS.md stanza
Verified:        tsc clean · light+dark checked on N screens · import direction clean

Unmapped (kept local, recomponentized only):
  - PATH — reason

Next step: wayfare:wayfare-push-pr
```

## Key Principles

- **Recomponentizing is the job.** Sourcing from a registry is the bonus, not
  the point. A pass that swaps components without restructuring has failed.
- **Search before you build.** Hand-rolling an existing component is the defect
  this skill prevents.
- **Vendored, not authored.** Rewrite call sites. Never edit `ui/` or `blocks/`.
- **The concept, not the markup.** Search for what an element *means*.
- **Gallery and search are complementary.** Search matches keywords. The gallery
  matches appearance.
- **Never force a match, never add a library uninvited.** No upstream equivalent
  → keep it local, recomponentize it, and say so.
