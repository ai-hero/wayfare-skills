# `init`: investigate the repo and write its config

Run by `wayfare:wayfare-init-repo`. Deeply investigate the repository,
auto-detect its settings, confirm the findings with evidence-based questions,
then write `HERO.md` and the plan object `.plans/PLAN.md`.

This was `wayfare:wayfare-init-repo`. It is the same procedure; it is reached
through wayfare now, because "configure the repo" and "plan the repo" were never
two decisions a person should have to sequence themselves.

## Step 1: Establish AGENTS.md as the Agent Instructions File

**House standard: `AGENTS.md` is the real file; `CLAUDE.md` is a symlink to
it.**

`AGENTS.md` is the cross-agent open standard (agents.md), which Cursor, Copilot,
and others read. Claude Code reads `CLAUDE.md`. A symlink means one file serves
every agent with zero duplication and no drift between them. **Always write
content to `AGENTS.md`, never to `CLAUDE.md`.**

Detect the current state. Note that `-L` must be tested *before* `-f`, since
`-f` is true for a symlink pointing at an existing file:

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT"

if [ -L CLAUDE.md ]; then
  TARGET=$(readlink CLAUDE.md)
  [ "$TARGET" = "AGENTS.md" ] && echo "STATE=CORRECT" || echo "STATE=SYMLINK_WRONG_TARGET target=$TARGET"
elif [ -f CLAUDE.md ] && [ -f AGENTS.md ]; then
  echo "STATE=BOTH_REGULAR_FILES"
elif [ -f CLAUDE.md ]; then
  echo "STATE=CLAUDE_ONLY"
elif [ -f AGENTS.md ]; then
  echo "STATE=AGENTS_ONLY"
else
  echo "STATE=NEITHER"
fi
```

Act on the state. **Never delete a `CLAUDE.md` whose content is not already
preserved in `AGENTS.md`.**

| State | Action |
| -- | -- |
| `CORRECT` | Nothing to do. Edit `AGENTS.md` in Step 5. |
| `NEITHER` | Create `AGENTS.md` with the scaffold below, then `ln -s AGENTS.md CLAUDE.md`. |
| `AGENTS_ONLY` | Create the symlink: `ln -s AGENTS.md CLAUDE.md`. |
| `CLAUDE_ONLY` | Rename, then link: `git mv CLAUDE.md AGENTS.md && ln -s AGENTS.md CLAUDE.md`. Content is preserved by the rename, so nothing is lost. |
| `BOTH_REGULAR_FILES` | **Stop and ask the user.** Two independent files exist. Show a diff, propose merging `CLAUDE.md`'s unique content into `AGENTS.md`, and only replace `CLAUDE.md` with a symlink once the user confirms the merge. Never silently discard either file. |
| `SYMLINK_WRONG_TARGET` | Report it and ask. Do not repoint a symlink the user aimed somewhere deliberately. |

For `CLAUDE_ONLY`, use `git mv` when the file is tracked so history follows the
rename; fall back to plain `mv` if git reports it is untracked.

Scaffold for a new `AGENTS.md` (content is filled in during Step 5):

```markdown
# AGENTS.md

<!-- CLAUDE.md is a symlink to this file. Edit AGENTS.md, never CLAUDE.md. -->

## Tech Stack
<!-- Auto-managed by wayfare:wayfare-init-repo. See HERO.md for full configuration. -->
See [HERO.md](./HERO.md) for the full tech stack configuration detected by `wayfare:wayfare-init-repo`.

## Best Practices
<!-- Auto-managed by wayfare:wayfare-init-repo. See HERO.md for full configuration. -->
See [HERO.md](./HERO.md) for project conventions, code quality tools, and CI/CD configuration.

## Coding Conventions
<!-- Auto-managed by wayfare:wayfare-init-repo. See HERO.md for full configuration. -->
See [HERO.md](./HERO.md) for coding conventions detected from the codebase.
```

**If `AGENTS.md` already has content:**

- Read it and check for `## Tech Stack`, `## Best Practices`, and
  `## Coding Conventions`.
- If a section is **missing**, append it.
- If a section exists but does **not** reference `HERO.md`, add:
  `See [HERO.md](./HERO.md) for details managed by wayfare:wayfare-init-repo.`
- **Do not** remove or overwrite content the user wrote. Only add the pointer if
  it is absent.

**Windows note:** symlinks need Developer Mode or elevated privileges. If
`ln -s` fails, fall back to a regular `CLAUDE.md` containing the single line
`See [AGENTS.md](./AGENTS.md).` and tell the user why.

**Why this matters:** `AGENTS.md`/`CLAUDE.md` is loaded into context at
conversation start. Without a HERO.md reference, Claude won't consult HERO.md
for tech stack decisions (OpenTofu vs Terraform) or coding conventions
(snake_case, structured logging, no DB mocks). The pointer ensures the agent
reads HERO.md for authoritative configuration, and it survives a context
compaction, which loaded skills may not.

## Step 2: Check for Existing HERO.md Configuration

```bash
ls "$ROOT/HERO.md" 2>/dev/null && echo "EXISTS" || echo "NEW"
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo: stop and follow
**At the fleet root** in `docs/FLEET-MD.md`.

If `HERO.md` exists and `recalibrate` was not passed, show current config and
ask if user wants to update it. If `recalibrate`, read the existing file to
compare against new findings.

## Step 3: Deep Investigation

Launch a thorough investigation of the repository. Use an Explore subagent or do
it yourself. The goal is to gather **evidence** for every configuration
decision.

### 3a: Coding Agent & AI Tooling

Detect which AI coding agent(s) the team uses. This must come first, because it
determines which hooks, configs, and integrations are possible.

```bash
# Claude Code
ls .claude/ .claude-plugin/ AGENTS.md CLAUDE.md .claude/settings.json 2>/dev/null
ls .claude/hooks/ 2>/dev/null
cat .claude/settings.json 2>/dev/null

# Cursor
ls .cursor/ .cursorrules .cursor/rules/ 2>/dev/null
cat .cursorrules 2>/dev/null | head -20

# Windsurf
ls .windsurf/ .windsurfrules 2>/dev/null

# Copilot
ls .github/copilot-instructions.md .copilot/ 2>/dev/null

# Aider
ls .aider* 2>/dev/null

# Other signals
ls .ai/ .llm/ 2>/dev/null
grep -r "claude\|cursor\|copilot\|windsurf\|aider" .pre-commit-config.yaml 2>/dev/null | head -5
```

**What to look for:**

- `.claude/` directory or `AGENTS.md`/`CLAUDE.md` → Claude Code user, so hooks,
  skills, and MCP servers are available
- `.cursorrules` or `.cursor/rules/` → Cursor user: rules files, no hook system
- `.github/copilot-instructions.md` → Copilot user: instructions file
- `.windsurfrules` → Windsurf user: rules file
- Multiple signals → the team uses different agents, so note all of them
- Pre-commit hooks referencing AI tools → existing self-review or lint
  integration

**If no coding agent detected**, ask: *"What AI coding agent does your team use?
(Claude Code, Cursor, Windsurf, Copilot, other)"* This determines what hooks and
integrations hero skills can set up (e.g., pre-commit self-review,
agent-specific rules files).

### 3b: Code Review Agent

Detect which external code review bot the team uses for automated PR reviews.

```bash
# Config files for known review agents
ls .greptile/ .greptile.yaml .greptile.yml 2>/dev/null
ls .coderabbit.yaml .coderabbit.yml 2>/dev/null
ls .github/copilot-review.yml 2>/dev/null

# Check recent PR comments for bot activity (last 5 PRs)
gh pr list --state merged --limit 5 --json number --jq '.[].number' 2>/dev/null | while read pr; do
  gh api "repos/{owner}/{repo}/pulls/$pr/comments" --jq '.[].user.login' 2>/dev/null
done | sort | uniq -c | sort -rn | head -5

# Check the repository's GitHub App installation (look for review bots)
gh api "/repos/{owner}/{repo}/installation" --jq '{app_slug, app_name}' 2>/dev/null
```

**What to look for:**

- `.coderabbit.yaml` → CodeRabbit. Trigger: auto on push, poll-method: comments,
  bot-username: `coderabbitai`
- `.greptile/` or `.greptile.yaml` → Greptile. Trigger: `@greptile review`
  comment, poll-method: check-runs, bot-username: `greptile-bot`
- Bot usernames in recent PR comments → identifies active review agent
- GitHub Copilot code review enabled → trigger: auto on push, poll-method:
  comments, bot-username: `copilot`

**If no review agent detected**, set `agent: none`. Optionally ask: *"Does your
team use an automated code review bot (Greptile, CodeRabbit, Copilot review,
etc.)?"*

### 3b-2: Design System & UI Registry

Only relevant when the project has a frontend. Skip entirely if there is no UI.

```bash
# Is there a UI at all?
ls components.json 2>/dev/null
grep -lE '"(react|vue|svelte|next|@angular/core)"' package.json 2>/dev/null
ls -d src/components components app/components 2>/dev/null

# Already wired to a registry?
grep -A6 '"registries"' components.json 2>/dev/null

# PRODUCER signals — this repo PUBLISHES a design system rather than consuming one
ls registry.json 2>/dev/null
ls -d registry-dist 2>/dev/null
grep -rl "shadcn build" package.json scripts/ 2>/dev/null
grep -o '"ui": *"[^"]*"' components.json 2>/dev/null

# Existing UI library, if any
grep -oE '"(@mui/material|@chakra-ui/react|@mantine/core|antd|@radix-ui/[a-z-]+)"' package.json 2>/dev/null | sort -u

# Atomic structure already present?
ls -d src/components/{atoms,molecules,organisms,templates} 2>/dev/null

# Token discipline — how much drift exists today
grep -rlE '#[0-9a-fA-F]{3,6}\b' --include="*.tsx" src/ 2>/dev/null | wc -l
```

**What to look for:**

- `registry.json` + `registry-dist/` + a `shadcn build` script → this repo is a
  **producer**. Set `role: producer` on the `design-system` connection so
  `wayfare:wayfare-recomponentize-ui` refuses to run here. A registry repo's
  pipeline is mockup → design system; consuming its own output would invert it.
- `components.json` with a `registries` block → already a consumer; read the
  namespace and URL from it rather than asking.
- `components.json` whose `"ui"` alias points at an internal atomic dir (e.g.
  `@/components/atoms`) rather than `@/components/ui` → another producer signal.
- A frontend with no `components.json` → candidate consumer. Ask (see Group 6).
- Existing MUI/Chakra/Mantine/Ant → note it. **Never propose migrating UI
  libraries during init.** That is a project, not a config decision.
- Atomic dirs already present → record `atomic-layers: true`.

### 3c: Repository & Collaboration Model

```bash
# Basic structure
git rev-parse --show-toplevel
git remote -v
git branch -r | head -20
git log --oneline -20
git shortlog -sn --all | head -10

# Default branch
git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null || echo "UNKNOWN"

# Collaboration signals
ls LICENSE CONTRIBUTING.md CODE_OF_CONDUCT.md CODEOWNERS .github/PULL_REQUEST_TEMPLATE* .github/ISSUE_TEMPLATE* 2>/dev/null

# Allowed merge methods on the GitHub remote — the team's PR merge
# button is constrained by these flags. We surface the allowed set so
# Step 4 can ask the user to pick one (preferring squash when allowed).
# Also fetch deleteBranchOnMerge — when false, wayfare:wayfare-ship-pr will
# delete merged branches itself.
gh repo view --json mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed,deleteBranchOnMerge 2>/dev/null
```

**What to look for:**

- Remote URL → hosting platform: `github.com` → GitHub (`gh`), `gitlab.com` →
  GitLab (`glab`), `bitbucket.org` → Bitbucket
- Multiple contributors in git log → team project with shared conventions
- LICENSE + CONTRIBUTING.md → open-source, may need DCO sign-off
- CODEOWNERS → enforced code review ownership
- PR templates → structured PR process
- Branch naming patterns in `git branch -r` → extract the **branch template**
  (e.g., `feature/PROJ-123-DESC`, `fix/DESC`, `PREFIX/ISSUE_ID-DESC`)
- Commit message patterns in `git log` (e.g., `feat:`, `fix:`, `PROJ-123:`)
- Allowed merge methods → `merge-method` field. Prefer `squash` when allowed;
  otherwise `rebase`; otherwise `merge`. If multiple are allowed, ask the user
  once to pin the team's choice.
- `deleteBranchOnMerge` → `auto-delete-branches` field. If true, GitHub already
  deletes merged branches and `wayfare:wayfare-ship-pr` will skip cleanup. If
  false, the skill will delete the remote and local branch after a successful
  merge unless `auto-delete-branches: false` overrides it in HERO.md.

### 3c-2: The other connections

The remaining kinds in `## Connections` (docs/CONNECTIONS.md). Each is cheap to
probe and expensive to guess, and the answer that matters most is which of the
three states it is in: unset, `type: none`, or set.

```bash
# reference — the template this repo was cloned from
git log --reverse --format='%s' | head -3          # a template's initial commit often survives
grep -n '^- template:' ../FLEET.md 2>/dev/null     # the fleet names its template row

# architecture — is the record here, or somewhere else?
ls DESIGN.md docs/architecture* 2>/dev/null

# infrastructure — IaC in this repo, or a sibling that holds it
ls -d terraform infra deploy k8s helm charts 2>/dev/null
grep -n '^### ' ../FLEET.md 2>/dev/null | head -20
```

**What to look for:**

- A root `DESIGN.md`, or agreement that this repo owns its own record →
  `architecture` is `type: self`. A separate docs repo → `type: repo` and the
  row name.
- IaC directories **here** → `type: self`. Not `none`: the infrastructure
  exists, it just is not somewhere else, and `none` would say this system has no
  IaC at all. A sibling holding the manifests → `type: terraform`/ `kubernetes`
  and its row.
- No template, no IaC repo, no external architecture record → write
  `type: none`, which is the answer "looked, there is none". Write nothing at
  all only when you genuinely did not look; an empty block and a `none` block
  mean different things and sync treats them differently.

### 3d: Project Management & Issue Tracking

```bash
# Issue templates often reveal the PM tool
ls .github/ISSUE_TEMPLATE/*.yml .github/ISSUE_TEMPLATE/*.md 2>/dev/null
cat .github/ISSUE_TEMPLATE/*.yml 2>/dev/null | head -40

# Check commit messages for ticket IDs
git log --oneline -30 | grep -oE '[A-Z]+-[0-9]+' | sort -u | head -5

# Check branch names for ticket IDs
git branch -r | grep -oE '[A-Z]+-[0-9]+' | sort -u | head -5

# Linear, Jira, etc. references in config
grep -r "linear\|jira\|asana\|shortcut" .github/ 2>/dev/null | head -5
```

**What to look for:**

- Ticket IDs like `PROJ-123` in commits/branches → extract the prefix; it is
  `issue-prefix` on the `issues` connection
- Linear/Jira mentions in templates → the connection's `type`, and `reach` is
  the MCP server or CLI that reads it
- GitHub issue references (`#123`, `Fixes #123`) → `type: github`, `at` the repo
  slug, `reach: gh`

### 3e: CI/CD Platform & Workflows

```bash
# GitHub Actions
ls .github/workflows/*.yml .github/workflows/*.yaml 2>/dev/null

# Read workflow names and triggers
for f in .github/workflows/*.yml .github/workflows/*.yaml; do
  [ -f "$f" ] && echo "=== $f ===" && head -20 "$f"
done 2>/dev/null

# Other CI platforms
ls .gitlab-ci.yml Jenkinsfile .circleci/config.yml .travis.yml buildkite.yml 2>/dev/null

# What the CI does (test, lint, build, deploy, release)
grep -l "test\|lint\|build\|deploy\|release" .github/workflows/*.yml 2>/dev/null
```

**What to look for:**

- Which workflows exist and what they do (test, lint, build images, deploy)
- Whether CI runs on PR, push to main, or both
- Required status checks (signals what must pass before merge)
- Whether `.github/workflows/auto-approve.yaml` (or `.yml`) already exists,
  which `wayfare:wayfare-ship-pr` needs

```bash
# Check whether the shared auto-approve workflow is installed
# Either spelling counts — GitHub honours both, and repos in this family
# carry a mix. Checking only one reinstalls a workflow that already exists.
AA=$(ls .github/workflows/auto-approve.yaml .github/workflows/auto-approve.yml 2>/dev/null | head -1)
# Match the caller's `uses:` line first, then the literal trigger for repos
# still carrying the old inline copy. Matching only '@auto-approve' made this
# depend on a COMMENT in the caller — the trigger itself moved into the shared
# workflow — so trimming that comment would have reported every migrated repo
# as missing and re-prompted to install what it already has.
#
# INSTALLED and STALE are different answers. A caller vendored before the
# 2026-09-21 rename still says `ai-hero/hero-skills/...`, and a workflow
# `uses:` does NOT follow a repo-rename redirect — that run fails at startup,
# zero jobs, no failing step. STALE means auto-approve is BROKEN in this repo,
# and reporting it INSTALLED says the opposite of the truth.
if [ -z "$AA" ]; then
  echo "AUTO_APPROVE_MISSING"
elif grep -qE 'hero-skills/\.github/workflows/auto-approve\.ya?ml@' "$AA" 2>/dev/null; then
  echo "AUTO_APPROVE_STALE"
elif grep -qE 'wayfare-skills/\.github/workflows/auto-approve\.ya?ml@|@auto-approve' "$AA" 2>/dev/null; then
  echo "AUTO_APPROVE_INSTALLED"
else
  echo "AUTO_APPROVE_MISSING"
fi
```

**`AUTO_APPROVE_STALE` means auto-approve is broken here, right now.** Say that
plainly rather than filing it as a migration to get to: the `uses:` names a repo
that no longer answers, so every `@auto-approve` on this repo fails at startup.
Run the installer; it writes a `.new` beside the existing file and exits 2
rather than overwriting, so the swap is the user's to make and the diff is worth
showing. Separately, and for a different reason, nobody should ever create a
repo at the old name: a consumer still pointed there would hand it
`ANTHROPIC_API_KEY` and an approve-capable token.

```bash
# And whether it has been merged to the default branch — issue_comment
# workflows only trigger from the default branch, so a PR-branch-only
# install does nothing.
DEFAULT_BRANCH=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@')
# Refresh before checking — a stale origin/$DEFAULT_BRANCH would report
# AUTO_APPROVE_NOT_ON_DEFAULT for a workflow that was actually just merged.
# On fetch failure, report the result as unknown rather than letting a
# possibly-stale ref produce a silent false AUTO_APPROVE_ON_DEFAULT that
# suppresses the "will be a no-op" warning the user actually needs.
if git fetch origin "$DEFAULT_BRANCH" 2>/dev/null; then
  { git cat-file -e "origin/$DEFAULT_BRANCH:.github/workflows/auto-approve.yaml" 2>/dev/null \
    || git cat-file -e "origin/$DEFAULT_BRANCH:.github/workflows/auto-approve.yml" 2>/dev/null; } \
    && echo "AUTO_APPROVE_ON_DEFAULT" || echo "AUTO_APPROVE_NOT_ON_DEFAULT"
else
  echo "AUTO_APPROVE_ON_DEFAULT_UNKNOWN (fetch failed — verify manually before trusting this check)"
fi
```

### 3f: Required CLI Tools & Developer Toolchain

```bash
# Version control & hosting
which gh 2>/dev/null && gh --version
which git 2>/dev/null && git --version

# Project management CLIs
which linear 2>/dev/null && linear --version 2>/dev/null
which jira 2>/dev/null && jira --version 2>/dev/null

# Language runtimes & package managers
which node 2>/dev/null && node --version
which python 2>/dev/null && python --version
which python3 2>/dev/null && python3 --version
which go 2>/dev/null && go version
which rustc 2>/dev/null && rustc --version
which uv 2>/dev/null && uv --version
which pnpm 2>/dev/null && pnpm --version
which yarn 2>/dev/null && yarn --version
which bun 2>/dev/null && bun --version
which cargo 2>/dev/null && cargo --version

# Infrastructure tools
which docker 2>/dev/null && docker --version
which kubectl 2>/dev/null && kubectl version --client 2>/dev/null
which helm 2>/dev/null && helm version --short 2>/dev/null
which tofu 2>/dev/null && tofu --version 2>/dev/null
which terraform 2>/dev/null && terraform --version 2>/dev/null
which aws 2>/dev/null && aws --version 2>/dev/null
which gcloud 2>/dev/null && gcloud --version 2>/dev/null | head -1
which az 2>/dev/null && az --version 2>/dev/null | head -1

# Code quality
which pre-commit 2>/dev/null && pre-commit --version
```

**What to look for:**

- Which tools the project actually requires (cross-reference with deps, CI,
  Dockerfiles, Makefiles)
- Distinguish between **required** (project won't build/run without it) vs.
  **recommended** (nice to have)
- Note minimum versions if the project depends on specific features
- These go into HERO.md `## Developer Setup` as team-shared requirements.
  Individual installation and auth are handled by `wayfare:wayfare-setup-dev`

### 3g: Deployment & Infrastructure

```bash
# Container
ls Dockerfile* docker-compose*.yml docker-compose*.yaml 2>/dev/null

# Kubernetes
ls -d k8s/ kubernetes/ charts/ helm/ kustomize/ 2>/dev/null
ls k8s/*.yml k8s/*.yaml kubernetes/*.yml kubernetes/*.yaml 2>/dev/null | head -10

# Serverless / PaaS
ls vercel.json netlify.toml fly.toml render.yaml app.yaml Procfile serverless.yml 2>/dev/null

# ArgoCD
ls -d argocd/ 2>/dev/null
grep -r "argocd\|argo-cd" .github/ k8s/ 2>/dev/null | head -5

# Container registry references
grep -r "ghcr.io\|ecr\.\|docker.io\|dockerhub\|acr\.\|gcr.io\|artifact-registry" .github/workflows/ Dockerfile* 2>/dev/null | head -10

# Namespace / environment references
grep -r "namespace\|environment\|staging\|production" k8s/ .github/workflows/ 2>/dev/null | head -10
```

**What to look for:**

- Dockerfile → containerized app, look for registry in CI
- K8s manifests → Kubernetes deployment, look for namespaces
- vercel.json / netlify.toml → serverless/static deployment
- ArgoCD references → GitOps workflow
- Environment names → staging, production, etc.

### 3h: Code Quality & Developer Tooling

```bash
# Pre-commit
ls .pre-commit-config.yaml 2>/dev/null && cat .pre-commit-config.yaml

# Python quality tools
ls ruff.toml pyproject.toml setup.cfg mypy.ini .flake8 .pylintrc 2>/dev/null
grep -A5 "\[tool.ruff\]\|\[tool.black\]\|\[tool.mypy\]\|\[tool.pytest\]\|\[tool.isort\]" pyproject.toml 2>/dev/null

# JavaScript/TypeScript quality tools
ls .eslintrc* .prettierrc* tsconfig.json biome.json .stylelintrc* 2>/dev/null

# Editor config
ls .editorconfig 2>/dev/null
```

**What to look for:**

- Pre-commit config → which hooks run (linters, formatters, type checks)
- ruff/eslint → linter
- black/prettier/biome → formatter
- mypy/pyright/tsc strict → type checker
- What's enforced in CI vs. just local

### 3i: Project Structure & Tech Stack

```bash
# Root project files (dependency files)
ls pyproject.toml package.json go.mod Cargo.toml build.gradle pom.xml requirements.txt 2>/dev/null

# Monorepo indicators
ls pnpm-workspace.yaml lerna.json nx.json turbo.json 2>/dev/null
grep -l "workspaces" package.json 2>/dev/null

# Subproject detection
ls */pyproject.toml */package.json 2>/dev/null | head -20
ls apps/*/package.json packages/*/package.json services/*/pyproject.toml 2>/dev/null | head -20

# Framework detection (read the actual deps)
grep -E "fastapi|django|flask|starlette" pyproject.toml 2>/dev/null
grep -E "next|vite|remix|astro|nuxt|svelte|express|nestjs|hono" package.json 2>/dev/null

# Task runners / command wrappers (these define canonical commands)
ls Makefile justfile Taskfile.yml 2>/dev/null
cat Makefile 2>/dev/null | grep -E "^[a-zA-Z_-]+:" | head -20
cat justfile 2>/dev/null | grep -E "^[a-zA-Z_-]+:" | head -20

# Package scripts (canonical command source for JS/TS)
grep -A30 '"scripts"' package.json 2>/dev/null

# Python scripts (canonical command source)
grep -A10 "\[project.scripts\]\|\[tool.poetry.scripts\]" pyproject.toml 2>/dev/null

# Install commands
# Python: look for uv, pip, poetry, conda
grep -E "uv sync|pip install|poetry install|conda" Makefile justfile README.md 2>/dev/null | head -5
# JS: look for which package manager
ls pnpm-lock.yaml yarn.lock package-lock.json bun.lockb 2>/dev/null

# Test setup
ls pytest.ini conftest.py jest.config* vitest.config* playwright.config* cypress.config* 2>/dev/null
grep -E "test-command\|scripts.*test\|pytest\|jest\|vitest" pyproject.toml package.json 2>/dev/null

# Lint / format / typecheck commands
grep -E "lint|format|check|typecheck|mypy|ruff|eslint|prettier|biome" Makefile justfile 2>/dev/null | head -10
grep -E '"lint"|"format"|"check"|"typecheck"' package.json 2>/dev/null

# Dev server
grep -E "dev.*command\|scripts.*dev\|scripts.*start\|uvicorn\|gunicorn" pyproject.toml package.json 2>/dev/null

# Ports
grep -E "port\|PORT\|:3000\|:8000\|:8080\|:5173\|:4000" pyproject.toml package.json .env.example docker-compose*.yml 2>/dev/null | head -10
```

**What to look for:**

- Language and framework from dependency files
- Monorepo structure (nx, turborepo, `workspaces` in `package.json`, multiple
  `pyproject.toml`): one repo with many packages. A folder of sibling checkouts
  is a **fleet**, mapped by `FLEET.md` (`wayfare:wayfare-sync-fleet`), and is
  not a monorepo
- **Dependency file** per project (pyproject.toml, package.json, go.mod, and so
  on), needed by `wayfare:wayfare-audit-security` and
  `wayfare:wayfare-push-pr`'s test phase
- **Lock file** → identifies the package manager (pnpm-lock.yaml → pnpm,
  yarn.lock → yarn, etc.)
- **Install command** (for example `uv sync` or `pnpm install`), needed by
  `wayfare:wayfare-push-pr`'s test phase before running
- **Task runner** (Makefile, justfile, Taskfile). If present, prefer its targets
  as canonical commands (e.g., `make test` over `uv run pytest`)
- **Exact lint/format/typecheck commands**: not just tool names;
  `wayfare:wayfare-push-pr`'s test phase needs runnable commands for
  verification
- Test commands from scripts section or config files
- Dev server commands and default ports
- Entry points for CLIs

### 3j: Coding Conventions & Team Patterns

Investigate the codebase for established conventions the team follows. These are
critical, because the agent must follow the same patterns the team uses.

```bash
# Existing style guides or contributing docs
ls CONTRIBUTING.md STYLE_GUIDE.md docs/CONVENTIONS.md docs/STYLE*.md 2>/dev/null
cat CONTRIBUTING.md 2>/dev/null | head -80

# Existing agent instructions for conventions already documented
cat AGENTS.md 2>/dev/null

# Import style — relative vs absolute, aliased paths
# (sample 5-10 source files from different directories)
head -20 src/**/*.{ts,tsx,py,go,rs} 2>/dev/null | head -60
grep -r "from \.\|from src\|from @/\|from ~/\|import \.\|import src" --include="*.py" --include="*.ts" --include="*.tsx" -l 2>/dev/null | head -5

# Naming conventions — sample function/class/variable names
grep -rE "^(def |class |function |const |export (const|function|class))" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.go" --include="*.rs" 2>/dev/null | head -20

# Error handling patterns
grep -rE "(try:|except |catch\(|\.catch\(|Result<|anyhow::|thiserror)" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.go" --include="*.rs" 2>/dev/null | head -10

# Logging patterns
grep -rE "(logger\.|logging\.|console\.(log|error|warn)|log\.(info|error|warn|debug)|slog\.|tracing::)" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.go" --include="*.rs" 2>/dev/null | head -10

# Test patterns — naming, structure, fixtures vs mocks
ls tests/ test/ __tests__/ spec/ 2>/dev/null
grep -rE "(describe\(|it\(|test\(|def test_|func Test|#\[test\]|#\[cfg\(test\)\])" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.go" --include="*.rs" 2>/dev/null | head -10

# Dependency injection / configuration patterns
grep -rE "(Depends\(|@inject|@Inject|providers\.|Container)" --include="*.py" --include="*.ts" --include="*.tsx" 2>/dev/null | head -5

# API patterns — REST conventions, response shapes
grep -rE "(router\.|@app\.(get|post|put|delete|patch)|app\.(get|post|put|delete|patch)|@(Get|Post|Put|Delete|Patch))" --include="*.py" --include="*.ts" --include="*.tsx" 2>/dev/null | head -10

# Database / ORM patterns
grep -rE "(Base\.metadata|declarative_base|mapped_column|Column\(|prisma\.|drizzle|knex|sqlx|diesel)" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.go" --include="*.rs" 2>/dev/null | head -10

# Documentation patterns — docstrings, JSDoc, etc.
grep -rE '("""|\/\*\*|/// |//!)' --include="*.py" --include="*.ts" --include="*.tsx" --include="*.go" --include="*.rs" 2>/dev/null | head -10
```

**What to look for, adapted to the detected tech stack:**

For **Python** projects:

- snake_case vs camelCase for functions/variables
- Import style: absolute (`from app.models`) vs relative (`from .models`)
- Docstring format: Google, NumPy, or Sphinx style
- Async patterns: `async def` usage, asyncio vs trio
- Error handling: custom exception classes, bare except usage
- Type hints: inline vs stub files, Optional vs `| None`

For **TypeScript/JavaScript** projects:

- Named exports vs default exports
- Path aliases (`@/`, `~/`) vs relative imports
- Interface vs Type for object shapes
- Barrel files (`index.ts` re-exports) usage
- `async/await` vs `.then()` chains
- Error handling: custom error classes, error boundaries

For **Go** projects:

- Package naming and layout (standard vs flat)
- Error wrapping style: `fmt.Errorf("...: %w", err)` vs custom
- Interface placement: consumer-side vs provider-side
- Context propagation patterns

For **Rust** projects:

- Error handling: `anyhow` vs `thiserror` vs custom
- Module structure: `mod.rs` vs file-based
- Trait patterns and generics usage

**Cross-language patterns to detect:**

- File/folder naming: kebab-case, snake_case, PascalCase
- API response shape conventions (envelope pattern, error format)
- Logging approach: structured vs unstructured, which library
- Config management: env vars, config files, secrets handling
- Test organization: co-located vs separate directory, naming patterns
  (`test_*`, `*.test.ts`, `*_test.go`)

**Rationale detection: when to ask "why"**

Most conventions are self-evident (snake_case in Python, PascalCase classes), so
do not ask why for those. But flag and ask about anything that is:

- **An exception to the language/framework default** (e.g., no default exports
  in TS, relative imports in a flat Python project)
- **A deliberate avoidance** (e.g., no ORM, no mocks, no barrel files)
- **A tool choice that has a common alternative** (e.g., OpenTofu over
  Terraform, pnpm over npm, Bun over Node)
- **A pattern that would surprise a new team member or Claude**

For these, ask the user: *"I noticed you use X instead of Y. Is there a specific
reason? This helps Claude avoid suggesting Y in the future."*

Keep rationale brief for mild preferences, elaborate for hard-won lessons (e.g.,
"mocks hid a migration bug").

## Step 4: Synthesize Findings into Smart Questions

Based on your investigation, present findings grouped by **what the hero skills
need**. Do NOT ask generic questionnaire questions. Instead, present
evidence-based confirmations.

**IMPORTANT: When asking clarifying questions, switch to plan mode or present
ALL questions in a single numbered list (1. 2. 3. ...) so the user can answer
them efficiently in one go. Never ask questions in freeform prose scattered
across the output.**

**Format for each finding:**

```
[CONFIRMED] SETTING: VALUE
  Evidence: EVIDENCE
  Used by: wayfare:wayfare-push-pr

[NEEDS CONFIRMATION] SETTING: BEST_GUESS
  Evidence: EVIDENCE (and why ambiguous)
  Question: QUESTION
  Used by: wayfare:wayfare-build-task

[NOT DETECTED] SETTING
  Looked for: WHAT_WAS_CHECKED
  Question: QUESTION
  Used by: wayfare:wayfare-ship-pr
```

**Group findings into these categories, presented in this order:**

### Group 0: "Your coding agent" (`wayfare:wayfare-init-repo recalibrate`, `wayfare:wayfare-setup-dev`)

- Coding agent (Claude Code, Cursor, Windsurf, etc.)
- Whether hooks/pre-commit integration is possible

Do NOT offer to install a pre-commit hook for
`wayfare:wayfare-init-repo recalibrate`. Skills surface a stale-HERO.md hint on
demand instead; see `scripts/check-hero-staleness.sh`.

### Group 1: "For committing and pushing code" (`wayfare:wayfare-push-pr`, `wayfare:wayfare-ship-pr`)

- Hosting platform (GitHub, GitLab, Bitbucket), read from the remote URL
- Commit convention (evidence from git log patterns)
- Branch naming convention and branch template (evidence from branch -r
  patterns)
- Default branch
- Merge method for PRs: squash, rebase, or merge. Detect with
  `gh repo view --json squashMergeAllowed,rebaseMergeAllowed,mergeCommitAllowed`;
  pick the **first allowed in this preference order: squash → rebase → merge**.
  If multiple are allowed, confirm with the user once and write the choice to
  `merge-method` in HERO.md.
- Whether GitHub auto-deletes merged head branches, via
  `gh repo view --json deleteBranchOnMerge`. If false, `wayfare:wayfare-ship-pr`
  will clean up the remote + local branch after merge. Record as
  `auto-delete-branches` in HERO.md.
- Pre-commit hooks and what they run
- Linters, formatters
- Task runner (if Makefile/justfile provides commit/push/lint targets)

### Group 2: "For planning and tracking work" (`wayfare:wayfare-build-task`)

- PM tool (evidence from templates, commit messages, integrations)
- Issue ID prefix (evidence from commit/branch patterns)
- MCP server name if applicable

### Group 3: "For testing and verification" (`wayfare:wayfare-push-pr` test phase)

- Per-project: language, framework, dependency file, install command
- Per-project: test, lint, format, typecheck commands (prefer task runner
  targets if available)
- Per-project: dev command, port
- Type checkers
- Task runner (Makefile, justfile, etc.) and its available targets
- Monorepo vs single repo structure

### Group 4: "For CI/CD and deployment" (`wayfare:wayfare-push-pr`, `wayfare:wayfare-ship-pr`, `wayfare:wayfare-audit-security`)

- CI platform and workflow names
- Deployment platform
- Container registry
- ArgoCD / GitOps
- Namespaces / environments
- Whether to install `.github/workflows/auto-approve.yaml` for
  `wayfare:wayfare-ship-pr`. If it is absent, ask: *"`wayfare:wayfare-ship-pr`
  lets you comment `@auto-approve` on a PR to get a Claude-verified approval
  (gated by self-review, no unresolved threads, and PR-metadata checks). Install
  `.github/workflows/auto-approve.yaml`? It also requires an `ANTHROPIC_API_KEY`
  repo secret."*
  - If the user says yes, run the install in Step 6a below.
  - If the workflow exists locally but is not on the default branch yet, remind
    the user that `@auto-approve` will be a no-op until that file lands on the
    default branch.

### Group 6: "For UI work" (`wayfare:wayfare-recomponentize-ui`)

Skip this group entirely for projects with no frontend.

- **Producer detected** (`registry.json` / `registry-dist/` / `shadcn build`):
  do not ask whether to adopt a design system. Confirm instead: *"This repo
  publishes a design system. I'll set `role: producer` so
  `wayfare:wayfare-recomponentize-ui` refuses to run here, because it would try
  to consume this repo's own output. Correct?"*
- **Consumer already wired** (`registries` block present): confirm the namespace
  and URL read from `components.json`; no question needed.
- **Frontend, no registry**: ask once. *"Use the AI Hero design system
  (`@aihero`, <https://design.aihero.studio>) for UI in this project? It needs a
  `REGISTRY_TOKEN` in `.env`, a Personal Access Token from
  auth.aihero.studio/profile. Choosing no keeps stock shadcn / your current UI
  library; `wayfare:wayfare-recomponentize-ui` still does the atomic refactor
  either way."*
- If yes, also ask: *"Install the enforcement layer
  (`.claude/rules/design-system.md` + a PostToolUse token check)? It is what
  makes the constraints apply reliably rather than only when a skill happens to
  trigger."* If the user agrees, run the install in Step 6b.
- **Never** propose migrating off an existing UI library here.

### Group 5: "Coding conventions for consistent code" (all skills that write code)

- Naming conventions (functions, files, folders)
- Import style and organization
- Error handling patterns
- Logging approach
- Test structure and naming
- API patterns (if applicable)
- Any other strong patterns detected in the codebase

Present ALL findings at once, clearly marking what's confirmed vs. what needs
input. Ask the user to confirm or correct.

**Example output:**

```
Hero Init - Investigation Results
=================================

I analyzed the repo and here's what I found:

FOR COMMITTING & PUSHING (wayfare:wayfare-push-pr)
────────────────────────────────────────────────────
[OK] Commit convention: conventional
     Evidence: 18/20 recent commits use "feat:", "fix:", "chore:" format

[OK] Default branch: main
     Evidence: origin/HEAD → origin/main

[OK] Pre-commit: enabled (ruff, black, mypy)
     Evidence: .pre-commit-config.yaml with 3 hooks

[??] Branch convention: unclear
     Evidence: Branches show mixed patterns:
       - feature/add-auth, feature/fix-login (feature/* pattern)
       - PROJ-45-update-deps (ticket-first pattern)
     → Which pattern do you prefer?

FOR PLANNING & TRACKING (wayfare:wayfare-build-task)
─────────────────────────────────────
[??] PM tool: likely Linear
     Evidence: Found "linear" in .github/workflows/sync.yml,
     commits reference LIN-XXX IDs
     → Is Linear your PM tool? What MCP server name?

[OK] Issue prefix: LIN
     Evidence: 8 commits reference LIN-### pattern

FOR TESTING & VERIFICATION (wayfare:wayfare-push-pr test phase)
────────────────────────────────────────
[OK] Single repo, Python + FastAPI
     Evidence: pyproject.toml with fastapi dependency, no subprojects

[OK] Test command: uv run pytest
     Evidence: [tool.pytest.ini_options] in pyproject.toml, tests/ dir

[??] Dev command: probably "uv run uvicorn app.main:app --reload"
     Evidence: uvicorn in deps, app/main.py exists, but no
     scripts section defined
     → Is this the right dev command?

[OK] Port: 8000
     Evidence: Found in docker-compose.yml port mapping

FOR CI/CD & DEPLOYMENT (wayfare:wayfare-push-pr, wayfare:wayfare-ship-pr)
──────────────────────────────────────────────────
[OK] CI: GitHub Actions
     Evidence: 3 workflows: ci.yml (test+lint), build.yml (docker),
     deploy.yml (k8s)

[OK] Deployment: Kubernetes
     Evidence: k8s/ directory with deployment.yml, service.yml

[OK] Registry: ghcr.io
     Evidence: build.yml pushes to ghcr.io/org/repo

[??] ArgoCD: possibly
     Evidence: Found argocd/ directory but no sync config
     → Do you use ArgoCD for deployment?

[--] Namespaces: not detected
     → What k8s namespaces do you deploy to?

CODING CONVENTIONS (wayfare:wayfare-build-task, wayfare:wayfare-push-pr)
──────────────────────────────────────────────
[OK] Naming: snake_case functions, PascalCase classes
     Evidence: 40+ function defs follow snake_case, all classes PascalCase

[OK] Imports: absolute (from app.models import ...), grouped stdlib/third-party/local
     Evidence: consistent across 15 source files sampled

[OK] Error handling: custom exceptions in app/exceptions.py, no bare except
     Evidence: AppError, NotFoundError, ValidationError classes found
     → All exceptions inherit AppError — is there a reason? (e.g., global handler mapping)

[OK] Logging: structlog with bound loggers
     Evidence: structlog in deps, logger = structlog.get_logger() in 8 files
     → Using structured logging — is this for a specific observability stack? (Datadog, ELK, etc.)

[OK] Tests: tests/ mirror src/, test_*.py naming, pytest fixtures (no mocks for DB)
     Evidence: tests/test_users.py, tests/test_auth.py, conftest.py with DB fixtures
     → I notice no DB mocks anywhere — is this intentional? If so, why?

[??] Docstrings: mixed — some Google-style, some missing
     Evidence: 6/15 public functions have docstrings, all Google format
     → Should all public functions have Google-style docstrings?

EXCEPTIONS & GOTCHAS
─────────────────────
[??] OpenTofu instead of Terraform
     Evidence: Found opentofu in deps, no terraform references
     → Is this a licensing decision? Claude would default to suggesting Terraform otherwise.

Please confirm or correct the [??] items, and fill in the [--] items.
Everything marked [OK] will be used as-is unless you say otherwise.
```

## Step 5: Incorporate Answers & Generate HERO.md

After the user responds, merge confirmed findings + user answers and write
`HERO.md`:

```markdown
# Hero Configuration
<!-- Generated by wayfare:wayfare-init-repo. Re-run with wayfare:wayfare-init-repo recalibrate to refresh. -->

## Coding Agent
- primary: claude-code # or cursor, windsurf, copilot, aider
- agents: AGENT_LIST # list all if team uses multiple
- hooks: true # or false — whether the agent supports pre-commit/hook integration
- rules-file: AGENTS.md # CLAUDE.md is a symlink to it; or .cursorrules, .windsurfrules, copilot-instructions.md
<!-- HERO.md is refreshed on demand by `wayfare:wayfare-init-repo recalibrate`.
     Skills detect when HERO.md is stale (project config newer than HERO.md)
     and prompt the user to run the refresh themselves. There is no
     pre-commit hook for this — it was too slow.
-->

## Code Review Agent
<!-- External code review bot that reviews PRs automatically.
     Used by wayfare:wayfare-respond-pr --loop to trigger, poll, and fix feedback iteratively. -->
- agent: AGENT_TYPE (greptile|coderabbit|copilot|none)
- trigger: TRIGGER_METHOD (e.g., "@greptile review" comment, auto on push, label)
- poll-method: POLL_METHOD (check-runs|comments|pipeline-status)
- bot-username: BOT_USERNAME (GitHub username of the bot, for filtering comments)

## Repository
- type: single # or monorepo
- hosting: github # or gitlab, bitbucket, other
- default-branch: main
- branch-convention: github-standard # or custom
- branch-template: "feat/ISSUE_ID-desc" # or "fix/desc"
- commit-convention: conventional # or angular, none
- merge-method: squash # or rebase, merge
<!-- Preferred PR merge method. Default: squash. Used by wayfare:wayfare-ship-pr
     when calling `gh pr merge`. Must be one of the methods allowed by the
     remote (gh repo view --json squashMergeAllowed,...). -->
- auto-delete-branches: true # or false
<!-- Whether GitHub auto-deletes merged head branches (deleteBranchOnMerge).
     If false, wayfare:wayfare-ship-pr deletes the remote + local branch after
     a successful merge. Override to false in HERO.md to keep merged
     branches around (e.g. for downstream tooling). -->
- task-runner: make # or just, taskfile, npm-scripts, none

## CI/CD
- platform: DETECTED
- workflows:
  - WORKFLOW_NAME

- required-checks: LIST_OF_REQUIRED_CHECKS

## Deployment
- platform: kubernetes # or vercel, ecs, fly
- registry: ghcr.io
- argocd: true # or false
- namespaces:
  - NAMESPACE

## Connections
<!-- Everything this repo is attached to on the outside, one `### kind` block
     each; see docs/CONNECTIONS.md. `type: none` means LOOKED, there is none.
     An ABSENT block means nobody has looked, which is what makes wayfare go
     looking — the two are not the same and must not be collapsed. -->

### issues
<!-- The tracker work is filed in. -->
- type: linear # or jira, github, none
- at: WORKSPACE_OR_OWNER/NAME
- reach: linear # the MCP server or CLI that reaches it
- issue-prefix: PROJ

### design
<!-- Used by wayfare:wayfare-sync-plan — field semantics in
     references/configuration.md. `type: none` unless this repo tracks
     features against a design project. -->
- type: none # claude-design | figma | none
- at: none # a claude.ai/design link or project UUID; `ask` prompts for the link each session and stores nothing
- reach: auto # auto | designsync | figma | manual — manual = you carry exported design files into the local snapshot (two-account setups)
<!-- reconciliation: path, in the DESIGN PROJECT, of a rolling reconciliation
     document the target already keeps. Left unset for the same reason ux-flow is:
     unset means "nobody has looked", and `none` asserts "looked, it keeps none"
     on your behalf. -->
<!-- ux-flow: path of the UX prototype flow / guided tour in the design project, or
     `none` if the design genuinely has none. Left unset on purpose: unset means
     "nobody has looked yet", which is what wayfare needs in order to go looking.
     Writing `none` here would assert "looked, there isn't one" on your behalf and
     permanently suppress its no-ux-flow report. Uncomment and set a real path:
       - ux-flow: flows/
     NOTE the leading indent on that example — the reader skips fenced blocks but
     NOT HTML comments, so a `- key:` at column 1 inside a comment is read as live
     config. Keep commented examples indented. -->

### reference
<!-- The template or reference implementation this repo should still resemble;
     wayfare-audit-compliance backports to it. -->
- type: none # repo | none
- at: none # a FLEET.md row name, or OWNER/NAME

### architecture
<!-- Where the architecture record lives. `self` = this repo's root DESIGN.md. -->
- type: self # self | repo | docs | none

### infrastructure
<!-- The repo holding this system's Terraform / Kubernetes manifests. -->
- type: none # terraform | kubernetes | self (it is in this repo) | none
- at: none # a FLEET.md row name

### design-system
<!-- Used by wayfare:wayfare-recomponentize-ui and the upstream reconciliation
     lane. `type: none` for a project with no frontend. -->
- type: registry # registry | none
- at: none # a FLEET.md row name (preferred — a path is right on one machine only), or ../NAME where there is no fleet. Its own `design` connection is where the design system's design is read from
- role: consumer # or producer
<!-- producer = this repo PUBLISHES the design system (builds registry.json,
     serves /r/*). wayfare:wayfare-recomponentize-ui refuses to run in a producer
     repo: its pipeline is mockup -> design system, and consuming its own
     output would invert that. Setting `enabled: false` has the same effect. -->
- namespace: "@aihero"
- registry-url: https://design.aihero.studio/r/{name}.json
- token-env-var: REGISTRY_TOKEN
<!-- A Personal Access Token from auth.aihero.studio/profile, kept in .env and
     never committed. In components.json use the plain ${REGISTRY_TOKEN} form
     only — the CLI expands /\$\{(\w+)\}/g, so ${VAR:-default} ships as a
     literal string and surfaces as a confusing 401. -->
- docs: https://design.aihero.studio
- handbook: handbook/consuming-the-registry.md # in the design-system repo
- atomic-layers: true # app components use atoms/molecules/organisms/templates
- enforcement: rules+hook # or none
<!-- rules+hook installs .claude/rules/design-system.md (path-scoped to UI files)
     and a PostToolUse token check. These apply regardless of whether a skill
     triggers; a skill alone depends on model discretion. -->

<!-- For a project with a frontend but no design system, record the source so
     wayfare-recomponentize-ui knows what to pull primitives from (indented — a `- key:`
     at column 1 inside a comment is still read as live config by hero_field):
       - role: consumer
       - source: shadcn        # or mui, chakra, mantine, antd, none
       - atomic-layers: true
-->

## Code Quality
- pre-commit: true # or false
- linters: [ruff, eslint]
- formatters: DETECTED
- type-checkers: [mypy, tsc]

## Wayfare
<!-- The one wayfare key that is not a connection: a repo is not attached to
     itself. Everything else wayfare reads lives in ## Connections above. -->
- source-repo: .

## Developer Setup
<!-- What every developer needs installed to work on this project.
     This is team-shared — individual auth/config is handled by wayfare:wayfare-setup-dev. -->

### Required Tools
<!-- Only tools the project won't build/run/test without -->
- TOOL_NAME: MIN_VERSION — WHAT_IT_IS_USED_FOR
<!-- Examples:
  - node: >=20 — runtime
  - pnpm: >=9 — package manager (NOT npm)
  - uv: >=0.4 — Python package manager
  - docker: any — local dev containers
  - gh: any — PR workflows, CI checks
  - tofu: >=1.6 — infrastructure (NOT terraform)
  - kubectl: any — deployment
-->

### Recommended Tools
<!-- Nice to have, but project works without them -->
<!-- Examples:
  - pre-commit: auto-runs linters on commit
  - linear: CLI for issue management
-->

### MCP Servers
<!-- MCP servers that hero skills or Claude need to interact with external tools -->
<!-- Examples:
  - linear (mcp__linear) — for wayfare:wayfare-build-task issue planning
- slack (mcp__slack) — for notifications
-->

## Coding Conventions
<!-- Detected patterns from the codebase. Adapt to the project's language/framework. -->
<!-- Rationale rules:
     - Standard/expected conventions: one-liner or omit rationale entirely
     - Non-obvious choices or exceptions to common defaults: explain WHY in a
       "reason:" line so Claude (and new team members) understand the intent -->

### Naming
- functions: snake_case # or camelCase
- classes: PascalCase
- files: snake_case # or kebab-case, PascalCase
- folders: snake_case # or kebab-case

### Imports
- style: absolute # or relative, aliases
- ordering: stdlib, third-party, local

### Error Handling
- pattern: DESCRIPTION
- custom-exceptions: true # or false; path to exceptions file if true
- reason: "all exceptions inherit AppError so the global handler can map them to HTTP status codes"

### Logging
- library: structlog # or logging, console
- style: structured # or unstructured
- reason: REASON_IF_NON_OBVIOUS

### Tests
- location: tests/ # or co-located, __tests__/
- naming: test_* # or *.test.ts, *_test.go
- fixtures: FIXTURE_DESCRIPTION
- reason: REASON_IF_NON_OBVIOUS

### API Patterns
<!-- Only include if the project has APIs -->
- style: REST # or GraphQL, gRPC
- response-format: RESPONSE_SHAPE_DESCRIPTION
- reason: REASON_IF_NON_OBVIOUS

### Documentation
- docstrings: Google # or NumPy, JSDoc, none
- required-for: public-functions # or all, none

### Exceptions & Gotchas
<!-- List anything that deviates from what Claude or a new developer would assume.
     These MUST have a reason. Keep the list short — only genuine exceptions. -->
<!-- Examples:
  - Use OpenTofu, NOT Terraform — reason: licensing; the team migrated after the BSL change
  - Use pnpm, NOT npm or yarn — reason: strict dependency resolution required for monorepo
  - No default exports — reason: refactoring tools can't track default exports across the codebase
  - DB tests hit real Postgres, never mock — reason: mocked tests passed but prod migration failed in Q3
-->

## Projects

### PROJECT_NAME
- path: PATH
- language: python # or typescript, go
- framework: fastapi # or next, express
- dependency-file: pyproject.toml # or package.json, go.mod, Cargo.toml
- install-command: "uv sync" # or "pnpm install", "go mod download"
- test-command: DETECTED_OR_CONFIRMED
- lint-command: "ruff check ." # or "pnpm lint", "make lint"
- format-command: "ruff format ." # or "pnpm format", "make format"
- typecheck-command: "mypy ." # or "pnpm typecheck", "make check"
- dev-command: DETECTED_OR_CONFIRMED
- port: DETECTED_OR_CONFIRMED
```

**Only include sections that are relevant.** If there's no CI/CD, no deployment,
etc., omit those sections entirely rather than filling them with "none". Keep it
clean.

**Also update `AGENTS.md` Tech Stack and Best Practices sections** (never write
to `CLAUDE.md`, which is a symlink) with a human-readable summary of the key
findings. This ensures Claude has immediate context without needing to parse
HERO.md. Example:

```markdown
## Tech Stack
<!-- Auto-managed by wayfare:wayfare-init-repo. See HERO.md for full configuration. -->
- **Language:** Python 3.12
- **Framework:** FastAPI
- **Infrastructure:** OpenTofu (NOT Terraform), Kubernetes
- **Database:** PostgreSQL via SQLAlchemy
- **CI/CD:** GitHub Actions
See [HERO.md](./HERO.md) for the full tech stack configuration.

## Best Practices
<!-- Auto-managed by wayfare:wayfare-init-repo. See HERO.md for full configuration. -->
- **Commits:** Conventional commits (`feat:`, `fix:`, `chore:`)
- **Branches:** `feature/*`, `fix/*` off `main`
- **Code Quality:** ruff (linter), black (formatter), mypy (type checker)
- **Pre-commit:** Enabled — runs ruff, black, mypy
- **Tests:** `uv run pytest` — always run before pushing

## Coding Conventions
<!-- Auto-managed by wayfare:wayfare-init-repo. See HERO.md for full configuration. -->
- **Naming:** snake_case functions, PascalCase classes, kebab-case files
- **Imports:** Absolute (`from app.models import ...`), grouped stdlib → third-party → local
- **Error handling:** Custom exceptions in `app/exceptions.py`, no bare `except`
- **Logging:** structlog with bound loggers
- **Tests:** `tests/` mirrors `src/`, pytest fixtures, no DB mocks
- **Docstrings:** Google-style for all public functions
See [HERO.md](./HERO.md) for full coding conventions.
```

Tailor the bullet points to what was actually detected. Include anything that
Claude might otherwise get wrong (e.g., "OpenTofu NOT Terraform", "pnpm NOT
npm", "Bun NOT Node").

## Step 6: Validate & Confirm

Show the generated file and a one-line-per-skill summary:

```
HERO.md written to REPO_ROOT/HERO.md

How your hero skills will use this:
  wayfare:wayfare-push-pr       → conventional commits, pre-commit runs ruff + black + mypy,
                               PRs via gh against main, link LIN-### issues,
                               check GitHub Actions: ci, build, deploy
  wayfare:wayfare-build-task      → fetch from Linear (mcp__linear), branch as feature/LIN-###-DESC
  wayfare:wayfare-push-pr (test)    → uv sync, then ruff check + mypy + pytest, smoke at :8000
  wayfare:wayfare-ship-pr       → k8s namespaces: staging, production
  wayfare:wayfare-sync-plan  → architecture (single repo, Python + FastAPI, k8s), harden (pyproject.toml deps, ghcr.io registry), roadmap, goals
  wayfare:wayfare-setup-dev     → require node, uv, gh, docker; recommend pre-commit, linear CLI
  wayfare:wayfare-init-repo recalibrate → re-investigate and refresh HERO.md on demand (run when project config changes)

Does this look right? [Y/n]
```

After confirmation, suggest:

```
Run wayfare:wayfare-setup-dev to configure your local dev environment
(git config, CLI tools, authentication) based on this HERO.md.
```

## Step 6a: Optionally Install Auto-Approve Workflow

If the user agreed to install `.github/workflows/auto-approve.yaml` (Group 4
confirmation), copy it into their repo using the bundled installer. The
installer's exit code is the contract, so capture it and branch on it explicitly
so an existing customized workflow is never silently overwritten or treated as
"installed":

```bash
WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
PLUGIN_ROOT=""
[ -x "$WAYFARE_ROOT/scripts/install-auto-approve.sh" ] && PLUGIN_ROOT="$WAYFARE_ROOT"

INSTALL_RC=255
INSTALL_OK=false           # workflow file is in the right state to be staged
INSTALL_FRESH_WRITE=false  # the installer actually created or refreshed the file this run

# Capture pre-existence so we can tell "freshly installed" apart from
# "already up to date" — both produce exit 0, but the user-facing
# reminder text below should only fire on a fresh write.
# Check BOTH spellings, the same way the installer does. Checking only .yml
# reports "freshly installed" for a repo whose file is .yaml, and fires the
# merge-it-to-main reminder at someone who has had the workflow on main for
# months.
WF_EXISTED_BEFORE=false
for ext in yaml yml; do
  [ -f "$ROOT/.github/workflows/auto-approve.$ext" ] && WF_EXISTED_BEFORE=true
done

if [ -z "$PLUGIN_ROOT" ]; then
  echo "Could not locate scripts/install-auto-approve.sh under WAYFARE_ROOT ($WAYFARE_ROOT)."
  echo "Export WAYFARE_ROOT as the plugin root, or copy"
  echo ".github/workflows/auto-approve.yaml from the plugin into this repo manually."
else
  set +e
  "$PLUGIN_ROOT/scripts/install-auto-approve.sh" "$ROOT"
  INSTALL_RC=$?
  set -e
fi

case "$INSTALL_RC" in
  0)
    # Workflow file is in sync with the plugin — safe to stage.
    INSTALL_OK=true
    if [ "$WF_EXISTED_BEFORE" = "false" ]; then
      INSTALL_FRESH_WRITE=true
    fi
    ;;
  2)
    # Say nothing about paths here. The installer adopts whichever spelling
    # the repo already uses and has already printed the real diff/replace
    # commands for it; re-stating them with a hardcoded .yml gave a .yaml repo
    # two commands that both fail on "No such file or directory" and left the
    # actual .yaml.new orphaned in the tree.
    echo ""
    echo "Skipping auto-stage of the workflow file — follow the installer's"
    echo "instructions above, then re-run."
    ;;
  3)
    echo "The wayfare plugin is missing assets/auto-approve/caller.yaml."
    echo "Reinstall the plugin; this is not a problem with your repo."
    ;;
  255)
    # Plugin not found — already explained above.
    ;;
  *)
    echo "Installer failed with exit code $INSTALL_RC. Investigate before committing."
    ;;
esac
```

Reminders shown only when the workflow was newly created this run
(`INSTALL_FRESH_WRITE=true`). For an already-up-to-date repo (`INSTALL_OK=true`
but `INSTALL_FRESH_WRITE=false`), skip the "installed at..." text, which would
be misleading.

1. **Merge the workflow to the default branch.** GitHub only honors
   `issue_comment` workflows that already exist on the default branch.
2. **Add an `ANTHROPIC_API_KEY` repo secret.** The workflow uses it for Claude
   verification.

```
Auto-approve installed at .github/workflows/auto-approve.yaml.

Next steps before wayfare:wayfare-ship-pr will work:
  1. git add .github/workflows/auto-approve.yaml
  2. Commit, open a PR, and merge to DEFAULT_BRANCH
  3. Add ANTHROPIC_API_KEY in repo settings -> Secrets and variables -> Actions
```

## Step 6b: Optionally Install Design-System Enforcement

If the user opted in during Group 6, install the rule + hook. Same exit-code
contract as Step 6a: branch on it explicitly rather than assuming success:

```bash
DS_RC=255
DS_OK=false

if [ -n "$PLUGIN_ROOT" ] && [ -x "$PLUGIN_ROOT/scripts/install-design-system.sh" ]; then
  set +e
  "$PLUGIN_ROOT/scripts/install-design-system.sh" "$ROOT"
  DS_RC=$?
  set -e
else
  echo "Could not locate scripts/install-design-system.sh in the plugin root."
fi

case "$DS_RC" in
  0) DS_OK=true ;;
  2)
    echo ""
    echo "An existing rule or hook differs from the plugin's; .new files were written."
    echo "Diff and reconcile before committing. Skipping auto-stage."
    ;;
  255) ;;
  *) echo "Installer failed with exit code $DS_RC. Investigate before committing." ;;
esac
```

`$PLUGIN_ROOT` is resolved in Step 6a, so run that lookup first if Step 6a was
skipped.

Remind the user only when the install succeeded:

```
Design-system enforcement installed.
  .claude/rules/design-system.md      — loads on **/*.{tsx,jsx,css}
  .claude/hooks/check-design-tokens.sh — advisory; DESIGN_TOKENS_STRICT=1 to enforce

Next: add REGISTRY_TOKEN to .env (never commit it), then run
wayfare:wayfare-recomponentize-ui to migrate the UI.
```

## Step 7: Commit HERO.md

Always commit `HERO.md` to the repo. Do NOT ask whether to commit or whether to
add it to `.gitignore`. Stage and commit it immediately after user confirmation
in Step 6 (and Step 6a if the workflow was installed).

Only stage the workflow file when Step 6a reported the file is in sync with the
plugin (`INSTALL_OK=true`, covering both the fresh-install and
already-up-to-date paths). When the installer returned exit 2 (`EXISTS`, drift
detected), the working file is still the user's original, and committing it now
would falsely claim `wayfare:wayfare-init-repo` installed the new version.

**Stage `AGENTS.md`, not just `CLAUDE.md`.** `CLAUDE.md` is a symlink, so
staging it alone commits the link and silently drops every content change,
because those live in `AGENTS.md`. Stage both: the symlink itself needs
committing the first time it is created.

```bash
FILES_TO_ADD=("HERO.md" "AGENTS.md" "CLAUDE.md")
# Whichever spelling the installer adopted — hardcoding .yml stages nothing
# in a .yaml repo, so the workflow silently never reaches the commit.
if [ "${INSTALL_OK:-false}" = "true" ]; then
  for ext in yaml yml; do
    [ -f ".github/workflows/auto-approve.$ext" ] && \
      FILES_TO_ADD+=(".github/workflows/auto-approve.$ext")
  done
fi
if [ "${DS_OK:-false}" = "true" ]; then
  FILES_TO_ADD+=(".claude/rules/design-system.md" ".claude/hooks/check-design-tokens.sh" ".claude/settings.json")
fi
git add "${FILES_TO_ADD[@]}"
git commit -m "chore: initialize HERO.md and update AGENTS.md via wayfare:wayfare-init-repo"
```

Never stage `.env`. If Group 6 added a `REGISTRY_TOKEN`, confirm `.gitignore`
covers `.env` before committing anything.

## `recalibrate` Mode

When `recalibrate` is passed:

1. Read existing `HERO.md` and `AGENTS.md`, and re-check the CLAUDE.md symlink
   state from Step 1
2. Re-run full investigation (Step 3, all sub-steps)
3. Compare findings against the current config, flagging what changed, what is
   new, and what was removed
4. Show only deltas: `[CHANGED]`, `[NEW]`, `[REMOVED]` markers
5. Ask user to confirm updates
6. Preserve any custom content or comments the user added to both files
7. Write updated `HERO.md` and refresh the `AGENTS.md` summary sections

## Key Principles

- **Investigate first, ask second.** Never ask what you can detect.
- **Show your evidence.** Every finding should cite what file/pattern you found.
- **Ask smart questions.** "I see X, does that mean Y?" not "What is your Z?"
- **Be purpose-driven.** Frame everything as "skill X needs this to work."
- **Omit irrelevant sections.** If no deployment, don't include a Deployment
  section.
- **One round of questions.** Present all findings at once with a single
  numbered list of questions (1. 2. 3. ...), get all answers at once. Use plan
  mode or a numbered format, never freeform prose questions.

## The plan object

`HERO.md` is only half of what `init` writes. The other half is
`.plans/PLAN.md`, the plan object (`docs/PLAN.md`), and without it
`hero_ready_items` refuses the store outright: it cannot tell an empty roadmap
from an unreadable one, so it declines to guess.

Three cases, decided by what is already on disk:

1. **No `.plans/` at all** → create the store and write `PLAN.md`: `schema: 1`,
   the repo slug, the default branch, today's date, `next_id: 1`, the
   `source.root` and `source.head` this run resolved, and a `target:` block only
   when the `design` connection's `at` is a project id rather than `none`. Fill
   `## Scope` from the investigation: one paragraph on what this repo is and
   what the plan over it is for. Every planning round reads it as the frame its
   proposals have to fit, so "TODO" there is a round planning against nothing.

2. **A `.plans/` holding items but no `PLAN.md` with `schema:`** → an unmigrated
   store from the nine-kind schema. Run the migrator and say so:

   ```bash
   WAYFARE_ROOT="${CLAUDE_PLUGIN_ROOT:-${WAYFARE_ROOT:-$HOME/.claude/plugins/wayfare-skills}}"
   bash "$WAYFARE_ROOT/scripts/migrate-plan.sh" "$(hero_store_path)"
   ```

   Report its warnings rather than swallowing them; an unrecognized `kind`
   migrates as `task`/`story` and wants a human look. Then fill `## Scope`,
   which the migrator cannot know.

3. **A `PLAN.md` already at `schema: 1`** → converge it, do not rewrite it.
   Refresh `source.head` and `target.head`; leave `next_id` alone unless it is
   behind the highest id in `items/`; never touch `## Log`.

**Never write `PLAN.md` into a directory that is not a git repo.**
`hero_work_store` refuses to create a store it cannot add to
`.git/info/exclude`, because a store that is not ignored is one that gets
committed, and `.plans/` is private by design.

## Examples

```
wayfare:wayfare-init-repo              # Investigate, write HERO.md and PLAN.md
wayfare:wayfare-init-repo recalibrate  # Re-investigate and update existing config
```
