# `init` on an empty directory: scaffold, then initialize

Run by `wayfare:wayfare-init-repo` when there is no repo yet, or when adding a
subproject to a monorepo. Scaffold the project, then fall through to
`references/init.md`, which writes `HERO.md` and the plan object.

This was `wayfare:wayfare-init-repo`. Same procedure, same templates; it is the
empty-directory case of one verb rather than a second entry point, so nobody has
to decide which of the two to run.

## Step 0: Load Configuration

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cat "$ROOT/HERO.md" 2>/dev/null || echo "NO_HERO_CONFIG"
[ -f "$PWD/FLEET.md" ] && [ ! -f "$PWD/HERO.md" ] && echo "FLEET_ROOT" || true
```

If `FLEET_ROOT` printed, this folder is a fleet, not a repo: stop and follow
**At the fleet root** in `docs/FLEET-MD.md`.

Read `HERO.md` for repo type (single vs monorepo), code quality tools, and
coding conventions. If missing, suggest `wayfare:wayfare-init-repo` and proceed
with defaults.

## Step 1: Parse Arguments

- `recalibrate` as the first word is the verb, not a project name. Run wayfare's
  own `recalibrate` (`SKILL.md`, *`recalibrate`*) and stop. A project genuinely
  named `recalibrate` has to be created by hand.
- **Project name** (required): First word. Ask if missing.
- **Description** (optional): Remaining text.

## Step 2: Determine Context

```bash
git rev-parse --is-inside-work-tree 2>/dev/null && echo "IN_REPO" || echo "STANDALONE"
ls */pyproject.toml */package.json 2>/dev/null | head -5
```

Ask based on context:

| Context | Question |
| -- | -- |
| Not in a repo | Create standalone repo, or add to an existing one? |
| In a repo with siblings | Add as a new subproject? |
| Empty repo | Initialize this repo with the new project? |

## Step 3: Choose Project Type

Ask the user:

1. **Python backend**: FastAPI with uv
2. **Python library**: a reusable package (uv)
3. **Python CLI**: a command-line tool (uv)
4. **Full-stack**: FastAPI plus Next.js or Vite with shadcn
5. **Frontend only**: Next.js or Vite with shadcn
6. **Node.js service**: an Express or Fastify backend

## Step 4: Scaffold

### Python Backend (FastAPI)

Read uv FastAPI guide at <https://docs.astral.sh/uv/guides/integration/fastapi/>

```bash
uv init PROJECT_NAME
cd PROJECT_NAME
uv add fastapi uvicorn[standard]
```

Structure:

```
PROJECT_NAME/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── routers/__init__.py
│   ├── services/__init__.py
│   └── schemas/__init__.py
├── pyproject.toml
└── uv.lock
```

### Python Library

```bash
uv init --lib PROJECT_NAME
```

### Python CLI

```bash
uv init PROJECT_NAME
```

Add entry point in `pyproject.toml`:

```toml
[project.scripts]
PROJECT_NAME = "project_name:main"
```

### Full-stack

```
PROJECT_NAME/
├── backend/    # FastAPI
└── frontend/   # Next.js or Vite
```

Backend: same as Python Backend above.

Frontend (ask Next.js or Vite):

- **Next.js**: Follow <https://ui.shadcn.com/docs/installation/next>

  ```bash
  npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"
  cd frontend && npx shadcn@latest init -d
  ```

  Add API proxy in `next.config.js`:

  ```javascript
  async rewrites() {
    return [{ source: '/api/:path*', destination: 'http://localhost:8000/api/:path*' }];
  }
  ```

- **Vite**: Follow <https://ui.shadcn.com/docs/installation/vite>

  Add API proxy in `vite.config.ts`:

  ```typescript
  server: {
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } }
  }
  ```

### Frontend Only

Same as full-stack frontend, at project root instead of `frontend/`.

### Node.js Service

```bash
mkdir PROJECT_NAME && cd PROJECT_NAME
npm init -y
npm install express typescript @types/node @types/express tsx
npx tsc --init
```

## Step 5: Create AGENTS.md (+ CLAUDE.md symlink)

House standard: `AGENTS.md` is the real file and `CLAUDE.md` symlinks to it, so
one file serves Claude Code, Cursor, and Copilot without drift. Write
`AGENTS.md`, then:

```bash
ln -s AGENTS.md CLAUDE.md
```

If `ln -s` fails (Windows without Developer Mode), write a one-line `CLAUDE.md`
containing `See [AGENTS.md](./AGENTS.md).` and tell the user why.

`wayfare:wayfare-init-repo` (Step 1) fills in the Tech Stack / Best Practices /
Coding Conventions sections after it investigates, so leave them out here.

```markdown
# PROJECT_NAME

DESCRIPTION

## Development

### Prerequisites
- [Python 3.12+ and uv | Node.js 20+]

### Setup
[How to install dependencies]

### Run
[How to start dev servers]

### Test
[How to run tests]

## Project Structure
[Brief description of key directories]
```

## Step 6: Initialize Git (if standalone)

```bash
git init
git add -A
git commit -m "$(cat <<'EOF'
chore: initialize PROJECT_NAME

DESCRIPTION

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

## Step 7: Chain to wayfare-setup-dev → config → first-commit

The init-project pipeline does not stop at scaffolding. After Step 6, render the
DAG:

```
[2/4] (✓) scaffold → (▶) wayfare-setup-dev → ( ) config → ( ) first-commit

Now running: wayfare-setup-dev
```

Then run `wayfare:wayfare-setup-dev` to install required CLIs and authenticate.
After that completes, render:

```
[3/4] (✓) scaffold → (✓) wayfare-setup-dev → (▶) config → ( ) first-commit

Now running: the config pass (references/init.md)
```

Run `wayfare:wayfare-init-repo` to investigate the freshly scaffolded project
and write `HERO.md`. (Pipeline 3 runs as a nested DAG inside this step.)

Finally render:

```
[4/4] (✓) scaffold → (✓) wayfare-setup-dev → (✓) config → (▶) first-commit

Now running: first-commit
```

If the repo was initialized standalone in Step 6 with an initial commit, the
`first-commit` step folds HERO.md and AGENTS.md (written by the config pass)
into a follow-up commit:

```bash
git add HERO.md AGENTS.md CLAUDE.md
git commit -m "$(cat <<'EOF'
chore: add HERO.md and AGENTS.md from wayfare:wayfare-init-repo

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

If the project was added to an existing repo, defer the commit to
`wayfare:wayfare-push-pr` (the user's normal flow).

## Step 8: Summary

```
Create Project Summary
======================
Project: PROJECT_NAME
Type: [Python Backend | Full-stack | ...]
Location: PATH

Pipeline:
  (✓) scaffold → (✓) wayfare-setup-dev → (✓) config → (✓) first-commit

Created:
  - Project structure
  - AGENTS.md (+ CLAUDE.md symlink)
  - HERO.md
  - [Git repo initialized]

Run first: cd PROJECT_NAME

Next step: wayfare:wayfare-check-preflight — Step 0.3, sanity-check tooling, .env, ports (print only — model-invocation-restricted, cannot auto-run)
```

Don't also print `wayfare:wayfare-build-task`; `wayfare-check-preflight`'s own
next-steps lead there once it passes.

## Notes

- Always creates AGENTS.md with a CLAUDE.md symlink. Uses uv for all Python
  projects.
- Frontend UI comes from the design-system registry in HERO.md when one is
  configured, else stock shadcn. Run `wayfare:wayfare-recomponentize-ui` after
  scaffolding to establish the atomic component layers.
- Does not push or create remote repos. Local scaffolding only.
