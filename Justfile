# wayfare gates. CI calls these recipes rather than restating the commands
# in YAML (CI-09): a gate that exists in two places drifts, and the copy that
# drifts is the one nobody runs locally.

_default:
    @just --list

# Everything CI runs, in CI's order.
check: lint test validate

# Delegated to pre-commit rather than calling shellcheck/markdownlint
# directly: pre-commit already pins their versions and manages their envs, so
# a direct call would need those tools installed separately and could run a
# different version than the commit hook enforces.

# Static checks: shell and prose.
lint:
    @pre-commit run shellcheck --all-files
    @pre-commit run markdownlint --all-files
    @pre-commit run mdformat --all-files
    @pre-commit run check-docs --all-files

# rglob, not glob: glob drops any path component starting with a dot, so
# .github/ and .pre-commit-config.yaml would be invisible and this would
# validate almost nothing while printing OK.

# Structured data parses.
typecheck:
    @python3 -c "\
    import json, sys, yaml; \
    from pathlib import Path; \
    j=[p for p in Path('.').rglob('*.json') if '.git/' not in str(p)]; \
    y=[p for p in list(Path('.').rglob('*.yml'))+list(Path('.').rglob('*.yaml')) if '.git/' not in str(p)]; \
    [json.load(open(p)) for p in j]; \
    [yaml.safe_load(open(p)) for p in y]; \
    print(f'{len(j)} JSON + {len(y)} YAML parsed')"

# Globbed, so a new scripts/*.test.sh gates without touching this recipe or
# the workflow.

# Shell unit suites.
test:
    #!/usr/bin/env bash
    set -euo pipefail
    for t in scripts/*.test.sh; do
      echo "-- $t"
      bash "$t"
    done

# Plugin structure: skill frontmatter, cross-references, naming.
validate:
    @bash scripts/validate.sh

# Delegated to pre-commit for the same reason lint is: these hooks are pied
# there, and a second copy of the same formatter can disagree with the one the
# commit gate enforces.

# Apply the formatting fixers.
format:
    @pre-commit run trailing-whitespace --all-files || true
    @pre-commit run end-of-file-fixer --all-files || true
    @pre-commit run mixed-line-ending --all-files || true
    @pre-commit run pretty-format-yaml --all-files || true

# The installers write <file>.new beside a file that differs rather than
# overwriting it, so a repo that has run one carries leftovers. Everything else
# here is a tool cache, not build output — this repo produces no artifacts.

# Remove installer leftovers and tool caches.
clean:
    @find . -name '*.new' -not -path './.git/*' -print -delete
    @rm -rf .ruff_cache .pytest_cache
    @echo "clean"
