# Hero Configuration
<!-- This file configures wayfare. See wayfare:wayfare-init-repo to update. -->

## Repository

- type: single
- default-branch: main
- branch-convention: github-standard
- commit-convention: conventional
- merge-method: squash
- auto-delete-branches: true
- task-runner: just

## CI/CD

- platform: github-actions
- workflows: auto-approve
- auto-approve-installed: true
- auto-approve-gates: prior-review-required, all-threads-resolved, claude-metadata-check

## Deployment

- platform: none
- registry: none
- argocd: false

## Coding Agent

- agent: claude-code
- config: .claude/

## Code Review Agent

<!-- No external review bot posts to PRs here (checked #68-#72: only
     github-actions[bot], which is this repo's own auto-approve workflow).
     `agent: none` (not a made-up value) is what tells wayfare-build-task's Step 7
     to skip the bot-await poll; self-review already runs as wayfare-build-task's own
     Step 5 via wayfare:wayfare-review-pr regardless of this field. -->
- agent: none
- trigger: none
- poll-method: none
- bot-username: none

## Code Quality

- pre-commit: true
- linters: markdownlint, shellcheck, codespell
- hooks: detect-secrets, validate-plugin, audit, shell-unit-tests, agents-md, agents-md-commit-msg

## Connections

<!-- What this repo is attached to on the outside; see docs/CONNECTIONS.md.
     `type: none` means LOOKED, there is none; an absent block would mean
     nobody has looked, and sync would ask again every run. -->

### design

- type: none # PERMANENT: wayfare is a plugin repo with no product and no UI (per AGENTS.md); it will never have a design project. Do not re-propose at sync

### design-system

- type: none # no fleet folder or sibling checkout with `role: producer` found

### reference

- type: none # this repo IS the fleet's plugin; hero-template is a consumer of it, not a template for it

### architecture

- type: self # the root DESIGN.md is the record; nothing outside this repo holds it

### infrastructure

- type: none # no dev stack, no IaC (this repo ships no product)

### issues

- type: github
- at: ai-hero/wayfare-skills
- reach: gh
- issue-prefix: none

## Wayfare

- source-repo: .

## Projects

### wayfare-skills

- path: ./
- language: markdown
- framework: claude-code-plugin
- test-command: none
- dev-command: none
