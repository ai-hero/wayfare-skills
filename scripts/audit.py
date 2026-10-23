#!/usr/bin/env python3
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

"""Compute (check x repo) results for the harness compliance DB.

Three levels, and this script owns the third:

    control  — CONTROLS.yaml. What we want complied with.
    check    — CHECKS.yaml. A checklist item testing FOR a control. One
               control has several, possibly at different scopes: a `ui`
               check and a `backend` check can both prove C-TOOLCHAIN.
    result   — computed HERE, live, per (check x repo). Never stored: a
               stored result is a copy, and copies drift.

Checks with no implemented checker report MANUAL, never PASS — a check
nothing verifies must not masquerade as one that passed. Referential
integrity is enforced on load: a check naming an unknown control, or a
control that no check tests, is a hard error.

Usage:
    scripts/audit.py                        # every repo, every check
    scripts/audit.py --repo auth            # one repo
    scripts/audit.py --control C-HEALTH     # every check under a control
    scripts/audit.py --control CI-01        # one specific check
    scripts/audit.py --md                   # markdown table
    scripts/audit.py --fail-on high         # non-zero exit for CI

Where things live: the ENGINE and a generic BASELINE register ship with
the wayfare plugin (this file, assets/compliance/), and run from the plugin
checkout's origin/main, not from whatever branch it sits on (see below); the
fleet's own OVERLAY — its
incident history and any checks of its own — lives in the
fleet folder's register checkout, named by FLEET.md's `register:` key
(default .fleet/). The two are merged by id, overlay winning. Run inside a
fleet (any checkout below a FLEET.md) and the family is FLEET.md's rows
whose group is not `none`; run anywhere else and the family is the current
repo alone, baseline only. --fleet PATH names the fleet root explicitly.

Each repo is audited at --ref (default origin/main) in a detached worktree,
not at whatever branch the checkout sits on; --no-snapshot audits the
checkouts as they sit. The engine, the register and the plugin assets vendored
checks compare against are read the same way, from ~/.claude/plugins/wayfare-skills
at origin/main after a fetch: main() extracts that commit and re-runs itself from
it, so checkers and register come from one sha. HERO_SKILLS_PLUGIN=<checkout>
runs the invoked engine and reads that checkout's working tree instead, to test
unmerged work. The report header names which one was used (`engine:` and
`assets:`).
"""

import argparse
import contextlib
import importlib.util
import io
import json
from datetime import datetime
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

try:
    import yaml
except ImportError:
    sys.exit("pyyaml required: pip install pyyaml")

HERE = pathlib.Path(__file__).resolve().parent.parent   # the wayfare plugin
BASELINE = HERE / "assets" / "compliance"               # generic register, public
# Set by configure(): the fleet root (or the lone repo's parent), the fleet's
# register overlay directory (None outside a fleet), the template repo's row
# name (None outside a fleet), and each family repo's directory.
ROOT = None
REGISTER = None
TEMPLATE = None
REPO_DIR = {}
_OVERLAY_LOADED = set()
GROUP_REPOS = {}    # FLEET.md group -> set of family repo names; see applies()

PASS, FAIL, NA, MANUAL, ERROR = "PASS", "FAIL", "n/a", "MANUAL", "ERROR"
STATUSES = {PASS, FAIL, NA, MANUAL, ERROR}

# The repos this register governs. Explicit, and it has to be — but the
# decision is FLEET.md's, not this file's: a row whose group is not `none` is
# in, and configure() fills FAMILY from it. Outside a fleet the family is the
# one repo this runs in.
#
# Membership is a decision, not something to sniff for: a heuristic ("every
# sibling with a CLAUDE.md") once pulled an ungoverned checkout into a
# cross-repo comparison and made that check unsatisfiable, which kills a
# register the same way a false PASS does — just from the other end.
FAMILY = ()

# Capability names a check's applies_to may use besides FLEET.md groups. A
# capability is DETECTED by the checker (has_go, has_ui, …), never resolved to
# a repo list here; the closed set exists so a misspelt group name cannot fall
# through as "a capability the checker will handle" and silently reach every
# repo — the inverse of the stale-list failure applies() describes.
CAPABILITIES = {"go", "node", "node-ssr", "python", "ui", "backend",
                "dev-stack", "ships-image", "schema", "container", "ci", "repo"}

# The register's own files, repo-relative. A content check that greps for a
# banned string finds these first: they have to spell what they ban. Excluding
# them is not special-pleading — it is the difference between the map and the
# territory.
REGISTER_FILES = ("CONTROLS.yaml", "CHECKS.yaml", "scripts/audit.py")

# name -> the tree actually audited: a detached worktree of --ref while
# snapshot_family() is live, else the checkout as it sits. The register audits
# what is MERGED, not what is checked out — a sibling mid-branch with an agent
# in it is not the fleet's state — so a checker that looks across the family
# goes through repo_path(), never ROOT / name.
REPO_PATH = {}


def repo_path(name):
    return REPO_PATH.get(name, REPO_DIR.get(name, ROOT / name))


def in_git_worktree(d):
    """Whether d or an ancestor other than $HOME holds a .git entry. Walks the
    filesystem so GIT_DIR cannot lie. $HOME is skipped: a dotfiles repo there is
    not a clone, and counting it would stop every fleet under $HOME resolving."""
    home = pathlib.Path.home().resolve()
    return any((p / ".git").exists() for p in (d, *d.parents) if p != home)


def fleet_root(start=None):
    """The nearest ancestor holding FLEET.md that is neither beside a HERO.md
    nor inside a git work tree, or None: a committed FLEET.md is a clone's
    content, and its register would run the clone's checkers.py. Tests the
    FLEET.md folder, never the register, which is the real fleet's own
    checkout."""
    d = pathlib.Path(start or os.getcwd()).resolve()
    while True:
        if (d / "FLEET.md").is_file() and not (d / "HERO.md").is_file():
            if not in_git_worktree(d):
                return d
            print(f"fleet_root: passing over {d}; a folder inside a git work tree is never a fleet root", file=sys.stderr)
        if d.parent == d:
            return None
        d = d.parent


def read_fleet(root):
    """FLEET.md's `## Fleet` keys and `## Repos` rows, mirroring hero-lib's
    hero_fleet_field / hero_fleet_repos. Fenced blocks are skipped and a
    trailing `# comment` is stripped from every value."""
    fields, repos, sec, cur, fence = {}, [], None, None, False
    seen = set()
    try:
        text = (root / "FLEET.md").read_text()
    except (OSError, UnicodeDecodeError) as e:
        sys.exit(f"{root / 'FLEET.md'}: cannot read: {e}")
    for line in text.splitlines():
        if line.startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        if line.startswith("## "):
            sec, cur = line[3:].strip(), None
            continue
        if sec == "Repos" and line.startswith("### "):
            name = line[4:].strip()
            # Same rejections as hero_fleet_repos, and said out loud the same
            # way: a row this parser drops and the shell keeps (or the reverse)
            # is a family that differs between the two tools with no message.
            if not re.fullmatch(r"[A-Za-z0-9._-]+", name) or name in (".", ".."):
                print(f"read_fleet: skipping '{name}' — a repo name is [A-Za-z0-9._-] only", file=sys.stderr)
                cur = None
                continue
            if name in seen:
                print(f"read_fleet: skipping '{name}' — duplicate row", file=sys.stderr)
                cur = None
                continue
            seen.add(name)
            cur = {"name": name, "group": "none", "path": "", "port": ""}
            repos.append(cur)
            continue
        m = re.match(r"^- ([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), re.sub(r" *#.*$", "", m.group(2)).strip().strip("\"'")
        if sec == "Fleet":
            fields[key] = val
        elif sec == "Repos" and cur is not None and key in ("path", "group", "port"):
            # An empty group is `none`, as hero_fleet_repos reads it: a
            # half-filled row must not join the family by accident.
            cur[key] = (val.lower() or "none") if key == "group" else val
    return fields, repos


def configure(root=None, load_overlay=True):
    """Bind ROOT, FAMILY, REGISTER, TEMPLATE and REPO_DIR — from FLEET.md when
    inside a fleet, else from the current repo alone. Called by main() and by
    consistency.py; the import-time call below makes the module usable from
    tests without one.

    The import-time call passes load_overlay=False: it runs in whatever engine
    was invoked, before run_at_origin() decides which engine runs, so loading
    the register's checkers.py there executes fleet code under a stale engine."""
    global ROOT, FAMILY, REGISTER, TEMPLATE
    if root:
        root = pathlib.Path(root).resolve()
        if not (root / "FLEET.md").is_file():
            sys.exit(f"--fleet {root}: no FLEET.md there")
    else:
        root = fleet_root()
    REPO_DIR.clear()
    GROUP_REPOS.clear()
    if root is None:
        rc, top = sh(pathlib.Path.cwd(), "git rev-parse --show-toplevel")
        repo = pathlib.Path(top.strip()) if rc == 0 and top.strip() else pathlib.Path.cwd()
        ROOT, FAMILY, REGISTER, TEMPLATE = repo.parent, (repo.name,), None, None
        REPO_DIR[repo.name] = repo
        return
    fields, repos = read_fleet(root)
    ROOT = root
    reg = fields.get("register") or ".fleet/"
    REGISTER = (root / reg.rstrip("/")).resolve()
    # The register is the fleet's own state and sits inside the fleet: an
    # escaping value would make consistency.py write outside it.
    if root not in REGISTER.parents:
        sys.exit(f"FLEET.md register: {reg} resolves outside the fleet ({REGISTER})")
    # A mapped-but-missing register is the one state that must not run: the
    # audit would proceed baseline-only and report a fleet that got greener
    # because its overlay — every check the fleet added on top of the five in
    # the baseline — was simply not there.
    if not REGISTER.is_dir():
        sys.exit(f"register checkout missing: FLEET.md names `register: {reg}` but {REGISTER} does not exist — clone it or fix the key")
    TEMPLATE = fields.get("template") or None
    names = []
    for row in repos:
        if row["group"] == "none":
            continue
        raw = row["path"] or row["name"]
        # Only `~` and `~/…` expand, as in hero_fleet_repos: `~user/x` stays a
        # relative path there, so it must here.
        written_absolute = raw == "~" or raw.startswith(("/", "~/"))
        if written_absolute:
            raw = os.path.expanduser(raw) if raw[0] == "~" else raw
        path = (root / raw).resolve()
        if not written_absolute and root not in path.parents:
            print(f"configure: skipping '{row['name']}' — path resolves outside the fleet: {path}", file=sys.stderr)
            continue
        if path in REPO_DIR.values():
            other = next(k for k, v in REPO_DIR.items() if v == path)
            print(f"configure: skipping '{row['name']}' — same directory as '{other}'", file=sys.stderr)
            continue
        REPO_DIR[row["name"]] = path
        names.append(row["name"])
        GROUP_REPOS.setdefault(row["group"], set()).add(row["name"])
    FAMILY = tuple(names)
    if load_overlay:
        _load_overlay_checkers()


def _load_overlay_checkers():
    """Import REGISTER/checkers.py, the fleet's own checkers, once. It sees this
    module as `audit` whatever name it was loaded under (`__main__` from the
    CLI, `audit` from consistency.py and the tests), so `from audit import
    check` inside it binds to THIS module's registry rather than a second copy
    that would register into a table nobody reads."""
    if REGISTER is None or REGISTER in _OVERLAY_LOADED:
        return
    f = REGISTER / "checkers.py"
    if not f.is_file():
        return
    # Loaded under `audit` by consistency.py and the tests, `__main__` by the
    # CLI; either way the overlay's `import audit` must find THIS module.
    this = sys.modules.get(__name__)
    if this is not None:
        sys.modules.setdefault("audit", this)
    spec = importlib.util.spec_from_file_location("fleet_checkers", f)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # a broken overlay must not read as "no overlay"
        sys.exit(f"{f}: could not load the fleet's checkers: {type(e).__name__}: {e}")
    _OVERLAY_LOADED.add(REGISTER)


def applies(check, repo_name):
    """Whether a check's `applies_to` reaches this repo. `all` (or absent)
    reaches everyone. A name that is a FLEET.md group (template, apps,
    infra, …) reaches that group's rows. Any other name is a capability the
    checker detects for itself (has_go, has_ui, …) and is left to it. An
    explicit repo list per capability (the old `applies_to_groups`) is not
    honoured on purpose: it is a copy of what detection already answers, and
    the first time it went stale it exempted three template clones from
    every Go and Node check. A lone repo outside a fleet is reached by every
    check, since there is no group to be outside of.

    Purpose is why this exists: an infra repo is in the fleet and holds a
    different kind of code, so the overlay can say `applies_to: [template,
    apps]` on an app-shaped convention and the infra rows read n/a instead
    of failing a rule that was never about them."""
    want = check.get("applies_to") or "all"
    names = [str(n).lower() for n in ([want] if isinstance(want, str) else list(want))]
    if "all" in names or not GROUP_REPOS:
        return True
    groups = [n for n in names if n in GROUP_REPOS]
    if not groups:
        return True
    return any(repo_name in GROUP_REPOS[n] for n in groups)


# Every git the engine runs must see the repo under `cwd`, not whatever repo
# the caller is inside: a pre-commit hook exports GIT_DIR / GIT_INDEX_FILE for
# the repo being committed, and with them inherited every `git ls-files` and
# `git worktree` here answers about THAT repo — the audit then reports the
# plugin's tree as every family member's.
_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def sh(cwd, cmd):
    """Run a shell command, return (rc, stdout). Never raises."""
    try:
        # dev tooling; cmd is a literal in this file (or the fleet's checkers), or interpolates
        # only regex-pinned tokens (ARCH-02: 40 hex chars) — never raw external input
        p = subprocess.run(
            cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=60, env=_ENV  # nosemgrep: python.lang.security.audit.subprocess-shell-true.subprocess-shell-true
        )
        return p.returncode, p.stdout.strip()
    except Exception:
        return 1, ""


def sh3(cwd, cmd):
    """sh() with stderr. Raises on the failure classes sh() hides (timeout,
    missing cwd) so a caller inside run_matrix reports ERROR, never PASS."""
    p = subprocess.run(
        cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=60, env=_ENV  # nosemgrep: python.lang.security.audit.subprocess-shell-true.subprocess-shell-true
    )
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def tracked(repo, *pathspecs):
    """Tracked paths matching the pathspecs. A failed `git ls-files` raises:
    an empty listing from a command that did not run is not a clean repo."""
    rc, out, err = sh3(repo, "git ls-files -- " + " ".join(shlex.quote(x) for x in pathspecs))
    if rc:
        raise RuntimeError(f"git ls-files failed in {repo.name}: {err or f'rc={rc}'}")
    return out.splitlines()


def uncommented(text):
    """Strip YAML comments so a checker can't match the prose ABOUT a bug
    and report it as the bug.

    Learned the hard way: GATE-02 greps for the invalid v1 spelling
    `shadow: true`, and hero-template's .golangci.yaml has a header comment
    warning that that spelling silently does nothing. The checker matched
    the warning and failed the one config in the fleet that is correct. A
    false FAIL is as corrosive as a false PASS — it trains you to ignore
    the report.
    """
    out = []
    for line in text.splitlines():
        s = line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
        out.append(s)
    return "\n".join(out)


def yml(repo, stem):
    """Resolve a YAML path by stem, accepting either extension.

    PLACE-06 moves the fleet from .yml to .yaml, and the repos convert one at
    a time. A checker that hardcodes either extension breaks every repo on the
    other side of the migration — so resolve by stem and let the repo be
    mid-flight. Prefers .yaml (the target) and falls back to .yml.
    """
    for ext in (".yaml", ".yml"):
        f = repo / f"{stem}{ext}"
        if f.is_file():
            return f
    return repo / f"{stem}.yaml"


def has_go(repo):
    return (repo / "go.work").exists() or any(repo.glob("*/go.mod"))


def has_node(repo):
    return (repo / "package.json").is_file() or (repo / "ui" / "package.json").is_file()


def has_python(repo):
    # A repo "contains Python" as a PRODUCT language — backend or research —
    # not as harness tooling. A pyproject/requirements marks a real project;
    # otherwise, tracked .py OUTSIDE scripts/ (this repo's own compliance
    # harness is Python and must not make every repo that copies it look like a
    # Python project) and outside vendored trees. git ls-files so node_modules
    # and a vendored mockup/ never count.
    if (repo / "pyproject.toml").is_file() or (repo / "requirements.txt").is_file():
        return True
    _rc, out = sh(repo, "git ls-files '*.py' | grep -vE 'node_modules/|/mockup/|^scripts/' | head -1")
    return bool(out.strip())


def precommit(repo):
    """Raw .pre-commit-config.yaml text, or "". Matched as text on purpose: the
    same tool appears under different hook ids across the fleet (ui-lint /
    eslint / eslint-taste), so the checks look for the TOOL signature, not a
    canonical id a repo has no reason to adopt."""
    f = repo / ".pre-commit-config.yaml"
    return f.read_text() if f.is_file() else ""


def _missing_hooks(repo, required):
    """required: {label: [substrings, any of which proves the tool runs]}.
    Returns the labels whose tool is absent from the pre-commit config."""
    text = precommit(repo)
    missing = []
    for label, needles in required.items():
        if not any(n in text for n in needles):
            missing.append(label)
    return missing


def has_ui(repo):
    """Does this repo ship a web front end at all?

    Every family repo used to be a product app, so ui/backend checks could
    assume the subsystem existed and report FAIL when they could not find it.
    The wayfare plugin is a Claude Code plugin — no ui/, no package.json, no Go
    module — and under that assumption it failed AUTH-01, AUTH-02, UI-01 and
    STRUCT-03 for not having a version gate, OAuth vars and an .nvmrc it has
    no use for. That is the "check that cannot be satisfied" this register's
    own FAMILY comment warns kills a register. Absent subsystem is n/a, not a
    violation.
    """
    return (repo / "ui" / "src").is_dir() or (repo / "package.json").is_file()


def has_backend(repo):
    """Does this repo ship a service with HTTP endpoints? See has_ui."""
    return (repo / "go.mod").is_file() or (repo / "lib").is_dir() or (repo / "src").is_dir()


def _ships_image(repo):
    return bool(list(repo.glob("Dockerfile*")))


def workflows(repo):
    d = repo / ".github" / "workflows"
    return sorted(list(d.glob("*.yml")) + list(d.glob("*.yaml"))) if d.is_dir() else []


def own_port(repo):
    """The repo's own family port = the compose dev default. That file is
    what actually binds, so it is the source of truth; everything else is
    derived (PORT-02)."""
    f = yml(repo, "docker-compose.dev")
    if not f.is_file():
        return None
    m = re.search(r"HOST_PORT:-(\d{4,5})", f.read_text())
    return m.group(1) if m else None


# Each checker returns (status, detail). Keyed by check id.
CHECKS = {}


def check(cid):
    def deco(fn):
        CHECKS[cid] = fn
        return fn

    return deco


@check("STRUCT-01")
def _(r):
    if not list(r.glob("Dockerfile*")):
        return NA, "no Dockerfile"
    return (PASS, "") if (r / ".dockerignore").is_file() else (FAIL, "missing")


@check("STRUCT-02")
def _(r):
    if not has_go(r):
        return NA, "no Go"
    return (PASS, "") if yml(r, ".golangci").is_file() else (FAIL, "missing")


@check("STRUCT-03")
def _(r):
    if not has_ui(r):
        return NA, "no UI"
    return (PASS, "") if (r / ".nvmrc").is_file() else (FAIL, "missing")


@check("STRUCT-04")
def _(r):
    pc = r / ".pre-commit-config.yaml"
    if not pc.is_file() or "detect-secrets" not in pc.read_text():
        return NA, "no detect-secrets"
    return (PASS, "") if (r / ".secrets.baseline").is_file() else (FAIL, "no baseline")


@check("STRUCT-05")
def _(r):
    # Read the COMMITTED .gitignore, not `git check-ignore`.
    #
    # check-ignore reports the effective state, which folds in
    # .git/info/exclude — a per-clone, unversioned file. Three repos here
    # carry `.claude/` in their local exclude, so check-ignore called this
    # a FAIL on this machine while the repo config was correct and would
    # behave correctly on any other clone or in CI. This control is about
    # what the repo ships, so read what the repo ships.
    f = r / ".gitignore"
    if not f.is_file():
        return FAIL, "no .gitignore"
    lines = [l.strip() for l in uncommented(f.read_text()).splitlines() if l.strip()]
    if ".claude/" in lines or ".claude" in lines:
        return FAIL, ".claude/ blanket-ignored — skills can never be committed"
    if not any(l.startswith(".claude/") for l in lines):
        return FAIL, "no .claude rule — local settings untracked only by luck"
    if "!.claude/skills/" not in lines:
        return FAIL, "skills not un-ignored"
    if ".claude/settings.local.json" not in lines:
        return FAIL, "settings.local.json not ignored"
    return PASS, "narrow rule"


@check("STRUCT-06")
def _(r):
    _rc, out = sh(r, r"git ls-files | grep -E '(^|/)\.DS_Store$|(^|/)Thumbs\.db$'")
    return (FAIL, f"{len(out.splitlines())} tracked") if out else (PASS, "")


@check("PLACE-01")
def _(r):
    _rc, out = sh(
        r,
        # .terraform/ is a module cache: third-party Dockerfiles land there
        # on `terraform init` and are no more this repo's than node_modules'.
        "find . -name 'Dockerfile*' -not -path '*/node_modules/*' -not -path '*/.terraform/*' "
        "-not -path './.git/*' -not -path './Dockerfile*' -not -path './.*'",
    )
    if not out:
        return PASS, "all Dockerfiles at root"
    # The rule allows a separately-scaled sidecar IF its escape from the root
    # .dockerignore is documented THERE. That is the condition that makes it
    # variance, and it is checkable: the root .dockerignore must name the
    # subfolder. Whether the sidecar also avoids `COPY . .` still needs a
    # human, so this reports MANUAL rather than PASS — a documented exception
    # should not go green unexamined, but nor should it stay permanently red
    # and train people to ignore the report.
    strays = [x.strip() for x in out.splitlines() if x.strip()]
    di = r / ".dockerignore"
    doc = di.read_text() if di.is_file() else ""
    undocumented = [x for x in strays
                    if x.split("/")[1] not in doc] if doc else strays
    if undocumented:
        return FAIL, "undocumented: " + " ".join(undocumented)
    return MANUAL, "documented sidecar: " + " ".join(strays) + " — re-verify it copies named files only"


@check("PLACE-02")
def _(r):
    return (FAIL, "bare docker-compose.yml") if (r / "docker-compose.yml").is_file() else (PASS, "")


def registry():
    """The family port table, DERIVED from each family repo's compose default.

    There is no registry file: the compose default is what actually binds,
    so it is the only thing that cannot lie. Scanning for it means the
    table is computed from reality rather than maintained by hand — which
    is why there is nothing to copy, and therefore nothing to drift
    (PORT-01).
    """
    out = {}
    for name in FAMILY:
        d = repo_path(name)
        if not (d / ".git").exists():
            continue
        p = own_port(d)
        if p:
            out[name] = p
    return out




@check("PORT-02")
def _(r):
    mine = own_port(r)
    if not mine:
        return NA, "no dev stack"
    ports = {mine}
    j = r / "Justfile"
    if j.is_file():
        ports |= set(re.findall(r"HOST_PORT:-(\d{4,5})", j.read_text()))
    if len(ports) > 1:
        return FAIL, "disagree: " + ",".join(sorted(ports))
    if not mine.startswith("330"):
        return FAIL, f"binds {mine}, not a family port"
    return PASS, mine






@check("CI-01")
def _(r):
    wfs = workflows(r)
    if not wfs:
        return NA, "no workflows"
    bad = 0
    for w in wfs:
        for line in w.read_text().splitlines():
            if not re.search(r"^\s*(-\s*)?uses:", line):
                continue
            # A first-party ai-hero/* reusable WORKFLOW may ride `main` or a
            # v-tag — the CI-01 carve-out. Narrow on every axis:
            #   - only a reusable workflow, not a plain ai-hero action, which
            #     is no kind of fleet-wide distribution mechanism;
            #   - only `main`, the callee's PROTECTED default branch, never an
            #     arbitrary branch. @main is acceptable BECAUSE the plugin repo
            #     gates main on review — approval required, stale approvals
            #     dismissed, last-push approval required. A feature branch is
            #     gated on nothing, and this caller hands the callee
            #     ANTHROPIC_API_KEY and pull-requests: write;
            #   - a v-tag stays permitted for repos not yet migrated.
            if re.search(
                r"uses:\s*ai-hero/[^/]+/\.github/workflows/[^@\s]+@(main|v[0-9][^\s]*)\s*(#.*)?$",
                line,
            ):
                continue
            if not re.search(r"@[0-9a-f]{40}", line):
                bad += 1
    return (FAIL, f"{bad} unpinned") if bad else (PASS, "")


@check("CI-02")
def _(r):
    return (PASS, "") if yml(r / ".github", "dependabot").is_file() else (FAIL, "missing")


def _entry_dirs(u):
    """The directories an entry covers, in Dependabot's own precedence:
    `directory` wins over `directories` (Dependabot rejects setting both)."""
    directory = u.get("directory")
    return [directory] if directory else (u.get("directories") or ["/"])


def _entry_label(u):
    """`ecosystem@directory`, so two entries on the same ecosystem (two npm
    directories, say) are told apart in the FAIL detail."""
    return f"{u.get('package-ecosystem', '?')}@{','.join(str(d) for d in _entry_dirs(u))}"


def _ignores_semver_major(u):
    return any(
        rule.get("dependency-name") == "*"
        and "version-update:semver-major" in (rule.get("update-types") or [])
        for rule in u.get("ignore") or []
    )


def _group_batches_majors(g, digest_pinned):
    types = set(g.get("update-types") or [])
    if not types:
        return not digest_pinned
    return "major" in types or not {"minor", "patch"} <= types


@check("CI-14")
def _(r):
    f = yml(r / ".github", "dependabot")
    if not f.is_file():
        return NA, "no dependabot config"
    doc = yaml.safe_load(f.read_text()) or {}
    updates = doc.get("updates", []) or []
    if not updates:
        return FAIL, "no update entries"
    # Every version-update ["*"] group is judged, not just the first:
    # Dependabot matches update-types as well as patterns, so a major that
    # misses an earlier [minor, patch] group still lands in a later
    # unfiltered one. And a tag+digest FROM (node:26-alpine@sha256:…) still
    # gets tag bumps — only a digest-only ref (no :tag) has no major to batch.
    bad = []
    for u in updates:
        star_groups = [
            g for g in (u.get("groups") or {}).values()
            if g.get("applies-to") != "security-updates" and "*" in (g.get("patterns") or [])
        ]
        if not star_groups:
            bad.append(f"{_entry_label(u)}: no catch-all group")
            continue
        if _ignores_semver_major(u):
            continue
        # Only an unfiltered group can be saved by the digest exemption, so
        # skip the filesystem walk unless one is actually in play.
        needs_digest_check = u.get("package-ecosystem") == "docker" and any(
            not g.get("update-types") for g in star_groups
        )
        digest_pinned = needs_digest_check and _docker_entry_digest_pinned(r, u)
        if any(_group_batches_majors(g, digest_pinned) for g in star_groups):
            bad.append(f"{_entry_label(u)}: catch-all batches majors")
    if bad:
        return FAIL, "; ".join(bad)
    return PASS, "every catch-all group is minor+patch, semver-major is ignored, or docker is digest-pinned"


@check("CI-15")
def _(r):
    f = yml(r / ".github", "dependabot")
    if not f.is_file():
        return NA, "no dependabot config"
    doc = yaml.safe_load(f.read_text()) or {}
    updates = doc.get("updates", []) or []
    if not updates:
        return FAIL, "no update entries"
    # A quarantine window on version updates only — default-days is the option
    # every ecosystem supports (docker/actions support nothing finer). Security
    # updates for known advisories are exempt by design, so this does not slow a
    # real patch.
    missing = [
        u.get("package-ecosystem", "?")
        for u in updates
        if not (u.get("cooldown") or {}).get("default-days")
    ]
    if missing:
        return FAIL, "no cooldown: " + ",".join(sorted(set(missing)))
    return PASS, "each ecosystem quarantines new releases"


# ── template-lag helpers (TMPL-01) ──────────────────────────────────────────
# The template is the seed every clone starts from, so a dependency it pins
# OLDER than the fleet already runs ships that staleness — the x/crypto CVEs —
# into every future clone. These read the declared versions so the check can
# assert the template is not behind any consumer on a dependency they share.

def _semver(v):
    """Leading MAJOR.MINOR.PATCH as a tuple; strips a range operator (^ ~ >=),
    a leading v, and any pre-release/pseudo-version suffix. None when there is
    no MAJOR.MINOR.PATCH to read ("^18", "*", "workspace:*", a git URL).

    A None is SKIPPED, never guessed, so this never false-FLAGS a lag. The risk
    is the opposite direction: a None on the TEMPLATE side drops that dep from
    the comparison, so a real lag on it would be missed. Acceptable because the
    template pins exact versions (go.mod) and caret-with-patch ranges
    (package.json), both of which parse — a None there is itself the anomaly,
    and TMPL-01 turns an all-empty template map into MANUAL rather than PASS.
    Known blind spot: Go pseudo-versions (v0.0.0-<ts>-<hash>) all collapse to
    (0,0,0), so lag between two pseudo-versioned pins is invisible."""
    m = re.match(r"[\^~>=<\s]*v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def _go_versions(repo):
    """{module_path: highest declared version tuple} across every go.mod. An
    unreadable go.mod is skipped, not raised — one bad sibling must not sink the
    whole cross-repo comparison (it would degrade TMPL-01 to MANUAL and hide a
    real lag against the healthy consumers)."""
    deps = {}
    for gomod in repo.glob("*/go.mod"):
        try:
            text = gomod.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            m = re.match(r"\s*([\w.\-]+/[\w./\-]+)\s+(v\d\S*)", line)
            if not m:
                continue
            t = _semver(m.group(2))
            if t and t > deps.get(m.group(1), ()):
                deps[m.group(1)] = t
    return deps


def _npm_versions(repo):
    """{package: highest declared version tuple} from root and ui package.json."""
    deps = {}
    for pj in (repo / "package.json", repo / "ui" / "package.json"):
        if not pj.is_file():
            continue
        try:
            doc = json.loads(pj.read_text())
        except Exception:
            continue
        for section in ("dependencies", "devDependencies"):
            for name, spec in (doc.get(section) or {}).items():
                t = _semver(spec)
                if t and t > deps.get(name, ()):
                    deps[name] = t
    return deps


# A floating spec resolves to whatever is newest AT INSTALL TIME, never
# pinned to anything this repo committed to. `_semver()` correctly returns
# None for these (skip-don't-guess is right — TMPL-01 must not fabricate a
# version to compare), but None is also the return value for a workspace
# protocol or a git URL pinned to a full commit SHA, both legitimate.
#
# An earlier version of this function enumerated the dangerous shapes as a
# closed tuple of literal strings ("latest", "next", "canary", "*"). That
# reproduces, one level down, the exact defect this check exists to catch:
# npm dist-tags are not a fixed vocabulary, so a spec pinned to any OTHER
# tag name (beta, rc, alpha, insiders, nightly, ...) bypassed it silently —
# and a git dependency pinned to a floating BRANCH ref (not a commit SHA)
# has the identical "different tree on every install" risk profile as
# "latest", yet the enumeration exempted every git URL alike, pinned or not.
# Classify structurally instead: floating iff the spec names no version AND
# isn't one of the recognized versionless-but-genuinely-pinned protocols.
def _is_floating_npm_spec(spec):
    s = str(spec).strip()
    # `npm:<pkg>@<range>` aliases another package under a different import
    # name — the alias itself pins nothing; whatever floats or doesn't is the
    # WRAPPED range. The wrapped package name may itself contain "@" (a scope,
    # "npm:@scope/pkg@^1.0.0"), so split on the LAST "@", not the first. No
    # "@" at all (or only the scope's) means the alias names no version,
    # which resolves at install time exactly like a bare dist-tag — floats.
    if s.startswith("npm:"):
        aliased = s[len("npm:"):]
        at = aliased.rfind("@")
        return _is_floating_npm_spec(aliased[at + 1 :]) if at > 0 else True
    # `>=`/`>` with no paired `<`/`<=` anywhere in the spec has no ceiling —
    # "resolves to whatever is newest at install time" is exactly the risk
    # this check exists to catch, even though (unlike a bare tag) it names a
    # digit and so used to pass the `_semver()` short-circuit below un-flagged
    # (">=0.0.0" parses to a real (0, 0, 0) tuple, which reads as "pinned").
    if re.match(r"^>=?\s*\d", s) and "<" not in s:
        return True
    if _semver(s) is not None:
        return False
    if s.startswith(("workspace:", "file:", "link:")):
        return False
    if re.search(r"#[0-9a-f]{40}$", s):
        return False  # git URL pinned to a full commit SHA
    # `(?:[\w-]+:)?` optionally matches the shorthand's host prefix
    # (github:, gitlab:, bitbucket:) before owner/repo#ref — without it, a
    # tag ref containing a digit ("github:owner/repo#v1.2.3") fell through
    # to the digit check below and was misread as a bounded version, when a
    # git tag is no more immutable than a branch: either can be repointed.
    if s.startswith(("git+", "git://")) or re.match(r"^(?:[\w-]+:)?[\w.-]+/[\w.-]+#", s):
        return True  # git URL/shorthand with no SHA pin — a branch/tag, floats
    # _semver() only recognizes a FULL MAJOR.MINOR.PATCH, so a caret/tilde
    # range with fewer components ("^4", "~19", "4.x") returned None above —
    # but "^4" is bounded to major 4 exactly as surely as "^4.0.0" is; it is
    # not floating. The first cut of this function used that None as "treat
    # as potentially floating," which misfired on every partial-range spec
    # already in real use in this family (tailwindcss "^4", eslint "^10",
    # typescript "^5", @types/react "^19"). The actual dividing line a
    # floating spec crosses is having NO version number in it at all — a bare
    # dist-tag (latest, beta, rc, nightly, ...) or the wildcard are pure words;
    # any range, however partial or open-ended, still names a digit.
    if re.search(r"\d", s):
        return False
    # No digits anywhere: a bare tag/word, the wildcard "*", or an empty
    # string — npm's own alternate spelling of "*" — all float.
    return True


def _floating_npm_deps(repo):
    """{package: raw spec} for every dependency pinned to a floating spec, in
    root and ui package.json.

    A malformed package.json is let propagate rather than caught here — this
    mirrors TMPL-01's own reasoning for the same two files: a read failure on
    the very manifest this check protects must not report as PASS just
    because a JSON error was swallowed one function up. The check-runner in
    main() already turns any propagated exception into MANUAL with the error
    text, which is the correct outcome for "could not read this repo's
    dependencies" — silently returning {} here would collapse that into a
    fabricated, wrong PASS instead."""
    out = {}
    for pj in (repo / "package.json", repo / "ui" / "package.json"):
        if not pj.is_file():
            continue
        doc = json.loads(pj.read_text())
        for section in ("dependencies", "devDependencies"):
            for name, spec in (doc.get(section) or {}).items():
                if _is_floating_npm_spec(spec):
                    out[name] = spec
    return out




@check("CI-16")
def _(r):
    if not has_node(r):
        return NA, "no package.json"
    floating = _floating_npm_deps(r)
    if not floating:
        return PASS, "no floating npm tags"
    names = sorted(floating)
    return FAIL, f"{len(names)} floating tag(s): " + ", ".join(names[:6])


# GitHub runs auto-approve.yaml AND auto-approve.yml if both exist, so a check
# that resolves ONE of them (yml()) can pass a gated .yaml while an ungated
# .yml approves PRs beside it. A half-finished PLACE-06 rename leaves exactly
# that state. Anything asserting a property of "the auto-approve workflow"
# has to mean every file GitHub would run.
def _approve_workflows(r):
    return [w for w in workflows(r) if w.stem == "auto-approve"]


# Delegation to the shared workflow. A v-tag OR a full SHA both count: several
# repos pin the SHA, which is stricter than the tag, and demanding the tag
# would fail them for being MORE careful. A branch ref counts as neither.
# `wayfare-skills` only, deliberately. The repo was renamed from hero-skills on
# 2026-09-21, and a workflow `uses:` does NOT follow a rename redirect, so a
# caller still naming the old slug is a workflow that cannot start. Matching it
# here would certify a repo as "delegates to the shared workflow, gated" when
# its auto-approve does not run at all. A stale consumer SHOULD fail this
# check: that failure is the signal driving the re-vendor.
# `ya?ml` because the CALLEE's filename is the plugin repo's business and PLACE-06
# is moving the fleet off .yml — hardcoding it would flip every caller to FAIL
# the day the plugin repo renames its own file.
_DELEGATES = re.compile(
    r"ai-hero/wayfare-skills/\.github/workflows/auto-approve\.ya?ml@"
    r"(main|v[0-9][^\s]*|[0-9a-f]{40})"
)


def _jobs(path):
    try:
        doc = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return None
    return (doc.get("jobs") or {}) if isinstance(doc, dict) else {}


@check("CI-03")
def _(r):
    wfs = _approve_workflows(r)
    if not wfs:
        return NA, "no auto-approve"
    # Parse, don't substring-match. Against raw text, `author_association`
    # anywhere in the file counted as a gate: an inline trailing comment
    # ("# author_association gate dropped, see #123"), a gate on a DIFFERENT
    # job than the one that approves, or an inverted comparison all passed
    # while nothing was actually gated.
    ungated = []
    for w in wfs:
        jobs = _jobs(w)
        if jobs is None:
            return FAIL, f"{w.name} does not parse"
        for name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            cond = str(job.get("if", ""))
            if cond.strip() == "false":  # disabled job cannot approve
                continue
            if _DELEGATES.search(str(job.get("uses", ""))):
                continue
            # Both spellings are in use and both are correct: an `==` chain,
            # and `contains(fromJSON('["OWNER",…]'), …author_association)`.
            # Requiring `==` failed the second, which is the better form.
            # Reject only an outright inversion, which gates on nothing.
            if "author_association" in cond and not re.search(
                r"author_association\s*!=", cond
            ):
                continue
            ungated.append(f"{w.name}:{name}")
    if ungated:
        return FAIL, "ungated: " + ", ".join(ungated[:3])
    return PASS, ""


@check("CI-04")
def _(r):
    wfs = _approve_workflows(r)
    if not wfs:
        return NA, "no auto-approve"
    for w in wfs:
        if "Could not get review from Claude" in w.read_text():
            return FAIL, "fails OPEN"
    # A thin caller holds no API call, so the fail-open string can never
    # appear in it — returning PASS would be asserting a property of a file in
    # ANOTHER repo that this audit cannot see. The docstring's rule applies:
    # a check nothing verifies must not masquerade as one that passed.
    jobs = {}
    for w in wfs:
        jobs.update(_jobs(w) or {})
    if any(
        _DELEGATES.search(str(j.get("uses", "")))
        for j in jobs.values()
        if isinstance(j, dict)
    ):
        return MANUAL, "delegated to the plugin repo"
    return PASS, ""


@check("CI-05")
def _(r):
    wfs = workflows(r)
    if not wfs:
        return NA, "no workflows"
    for w in wfs:
        t = w.read_text()
        if w.stem == "auto-approve":
            continue
        # A workflow that gates a PR AND triggers on pull_request.
        # `pre-commit` is in the alternation because the gate is what the
        # workflow RUNS, not what it is called: a terraform repo whose only
        # gate is `pre-commit run --all-files` on pull_request never uses the
        # words test/lint/verify, and was reported as having no PR gate at all
        # at high severity — while running one on every PR.
        if re.search(r"\bpull_request\b", t) and re.search(r"\b(test|lint|verify|typecheck|pre-commit)\b", t):
            return PASS, w.name
    return FAIL, "no PR test gate"


@check("CI-06")
def _(r):
    wfs = workflows(r)
    if not wfs:
        return NA, "no workflows"
    missing = [w.name for w in wfs if not re.search(r"^permissions:", w.read_text(), re.M)]
    return (FAIL, ",".join(missing)) if missing else (PASS, "")


@check("CI-07")
def _(r):
    wfs = workflows(r)
    if not wfs:
        return NA, "no workflows"
    bad = []
    for w in wfs:
        text = w.read_text()
        if "timeout-minutes" in text:
            continue
        # A workflow whose jobs ONLY call reusable workflows (job-level `uses:`)
        # cannot carry timeout-minutes — GitHub rejects the key on such a job,
        # and the timeout is enforced in the callee. Don't grep-fail the caller.
        try:
            jobs = (yaml.safe_load(text) or {}).get("jobs") or {}
        except Exception:
            jobs = {}
        if jobs and all(isinstance(j, dict) and "uses" in j for j in jobs.values()):
            continue
        bad.append(w.name)
    return (FAIL, f"{len(bad)}/{len(wfs)} workflows lack it") if bad else (PASS, "")


# What makes two runs of one workflow race: each of these writes somewhere
# both runs share (a registry, a tag, a cache, a deploy target).
# `push:` counts unless it is literally false: build-push-action's usual
# spelling is an expression (`push: ${{ github.event_name != 'pull_request' }}`),
# and matching only `true` reads that publishing workflow as n/a.
_RACE_SIGNAL = re.compile(
    r"\bpush:[ \t]*(?:true\b|['\"]?\$\{\{)|\bdocker\s+push\b|\bgit\s+push\b|\bgit\s+tag\b"
    r"|\bcache-to:|\bactions/cache@"
    r"|\b(?:npm|pnpm|yarn)\s+publish\b|\bgh\s+release\s+create\b|\bgcloud\b[^\n]*\bdeploy\b"
    r"|\bfirebase\s+deploy\b|\bkubectl\s+apply\b|\bhelm\s+(?:upgrade|install)\b|\bterraform\s+apply\b"
    r"|\buses:[^\n]*deploy"
)


def _job_races(job):
    """Does this job carry a signal that two concurrent runs would collide?"""
    if not isinstance(job, dict):
        return False
    if job.get("environment") or "deploy" in str(job.get("uses", "")).lower():
        return True
    return bool(_RACE_SIGNAL.search(yaml.safe_dump(job, width=10**9)))


@check("CI-08")
def _(r):
    wfs = workflows(r)
    if not wfs:
        return NA, "no workflows"
    # Concurrency is the rule's remedy for a race, not a virtue of its own: a
    # workflow that only reads has nothing to serialise, and demanding the key
    # there buys a block that exists to satisfy a grep. So it is required only
    # where a race signal is present. GitHub accepts the key at the workflow
    # top or on a job, and a repo that scopes it per racing job is following
    # the rule. The auto-approve exemption is the same reasoning applied by
    # name: it is a reusable caller with no signal of its own.
    missing, racing = [], 0
    for w in wfs:
        text = w.read_text()
        if w.stem == "auto-approve":
            continue
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError:
            doc = None
        if not isinstance(doc, dict):
            # Unparsable: a YAML error must not hide a race, so match the text.
            if _RACE_SIGNAL.search(uncommented(text)):
                racing += 1
                if not re.search(r"^concurrency:", text, re.M):
                    missing.append(w.name)
            continue
        jobs = doc.get("jobs") if isinstance(doc.get("jobs"), dict) else {}
        racers = [j for j in jobs.values() if _job_races(j)]
        if not racers:
            continue
        racing += 1
        if doc.get("concurrency"):
            continue
        if not all(isinstance(j, dict) and j.get("concurrency") for j in racers):
            missing.append(w.name)
    if missing:
        return FAIL, ",".join(missing)
    if not racing:
        # Nothing races. A repo that declares concurrency anyway follows the
        # rule, so it keeps its PASS; only a repo with neither is n/a.
        declared = any(re.search(r"^\s*concurrency:", uncommented(w.read_text()), re.M) for w in wfs)
        return (PASS, "") if declared else (NA, "no workflow carries a race signal")
    return PASS, ""


@check("CI-09")
def _(r):
    wfs = workflows(r)
    if not wfs:
        return NA, "no workflows"
    if any(re.search(r"run:\s*just ", w.read_text()) for w in wfs):
        return PASS, ""
    return FAIL, "CI reimplements gates"


@check("GATE-02")
def _(r):
    f = yml(r, ".golangci")
    if not f.is_file():
        return NA, "no config"
    t = uncommented(f.read_text())
    probs = []
    if not re.search(r"^version:\s*[\"']?2", t, re.M):
        probs.append("not v2")
    if re.search(r"shadow:\s*true", t):
        probs.append("no-op shadow")
    if re.search(r"\bgosimple\b", t):
        probs.append("gosimple")
    return (FAIL, ",".join(probs)) if probs else (PASS, "")


@check("GATE-03")
def _(r):
    f = r / ".pre-commit-config.yaml"
    if not f.is_file():
        return NA, "no pre-commit"
    try:
        c = yaml.safe_load(f.read_text())
    except Exception as e:
        return MANUAL, f"unparsable: {e}"
    # Check the HAZARD, not a proxy for it. The condition is "no hook runs
    # at every stage", which `default_stages: [pre-commit]` is the usual way
    # to achieve — but a config where every hook declares its own `stages:`
    # satisfies it too, and greping for the key alone failed that repo for a
    # problem it does not have.
    if c.get("default_stages"):
        return PASS, "default_stages set"
    loose = [h["id"] for r_ in c.get("repos", []) for h in r_.get("hooks", [])
             if h.get("stages") is None]
    if loose:
        return FAIL, f"{len(loose)} hooks run at every stage"
    return PASS, "every hook declares stages"


@check("GATE-06")
def _(r):
    f = r / ".pre-commit-config.yaml"
    if not f.is_file():
        return NA, "no pre-commit"
    t = f.read_text()
    if "conventional-pre-commit" not in t:
        return FAIL, "no conventional-commit hook"
    m = re.search(r"default_install_hook_types:\s*\[([^\]]*)\]", t)
    if m and "commit-msg" not in m.group(1):
        return FAIL, "commit-msg not installed"
    return PASS, ""


@check("CTR-03")
def _(r):
    # Scoped to what SHIPS or DEPLOYS: Dockerfile.prod and the prod compose.
    #
    # Dockerfile.dev is deliberately out of scope. Two repos track
    # minio:latest there and both carry a written reason at the point of
    # difference — the sidecar is recreated on every dev-stack rebuild and
    # the dev image never reaches production. That is documented VARIANCE,
    # and a checker cannot read prose, so the honest move is to scope the
    # check to where the rule is absolute rather than flag a justified
    # exception forever and train people to ignore it.
    #
    # An unpinned image in a PROD compose is a different thing entirely: an
    # upstream change lands unannounced on something holding real data, and
    # Dependabot cannot bump `latest` because there is no version to
    # compare.
    targets = [r / "Dockerfile.prod", yml(r, "docker-compose.prod")]
    hits = []
    for f in targets:
        if not f.is_file():
            continue
        for i, line in enumerate(uncommented(f.read_text()).splitlines(), 1):
            if ":latest" in line:
                hits.append(f"{f.name}:{i}")
    return (FAIL, ", ".join(hits)) if hits else (PASS, "prod pinned")


@check("DOC-01")
def _(r):
    # AGENTS.md first: once DOC-04 lands, CLAUDE.md is a pointer and checking
    # IT for duplicate sections passes vacuously while the real content goes
    # unchecked. Fixing one check must not blind another.
    f = r / "AGENTS.md"
    if not f.is_file():
        f = r / "CLAUDE.md"
    if not f.is_file():
        return NA, "no AGENTS.md or CLAUDE.md"
    heads = [h.strip() for h in re.findall(r"^#{2,3}\s+(.+)$", f.read_text(), re.M)]
    dupes = {h for h in heads if heads.count(h) > 1}
    return (FAIL, "dupe: " + ",".join(sorted(dupes))) if dupes else (PASS, "")




@check("JUST-01")
def _(r):
    f = r / "Justfile"
    if not f.is_file():
        return NA, "no Justfile"
    t = f.read_text()
    # Split by what the recipe presupposes, not by importance. test/lint/
    # typecheck/clean/format describe work any repo has. build describes
    # something you compile, so it keeps the ui/backend/image predicate.
    # dev-stack and health describe a stack you can stand up and probe, which
    # exists only where a dev compose file or a prod image does: a Go library
    # with a CLI has a backend by has_backend's reckoning and nothing to put
    # in them, so demanding them buys an empty recipe that exists to satisfy a
    # grep, which is worse than the gap because the next reader believes it.
    #
    # Same shape as the AUTH-01 / UI-01 / HLT-01 guards: absent subsystem is
    # n/a, not a violation.
    need = ["test", "lint", "typecheck", "clean", "format"]
    if has_ui(r) or has_backend(r) or (r / "Dockerfile.prod").is_file():
        need.append("build")
    if yml(r, "docker-compose.dev").is_file() or (r / "Dockerfile.prod").is_file():
        need += ["dev-stack", "health"]
    missing = [n for n in need if not re.search(rf"^{re.escape(n)}\b.*:", t, re.M)]
    return (FAIL, "no " + ",".join(missing)) if missing else (PASS, "")


@check("JUST-03")
def _(r):
    if not has_go(r):
        return NA, "no Go"
    f = r / "Justfile"
    if not f.is_file():
        return NA, "no Justfile"
    t = f.read_text()
    if not re.search(r"^\s*set\s+dotenv-load", t, re.M):
        return PASS, "no global dotenv-load"
    # Present. Whether that is a bug depends on what the repo's Go tests
    # assert, which a grep cannot know — hiro sets it and is currently safe
    # (no lib/config; its config test reads a deliberately suffixed var; .env
    # holds nothing a test reads). Our own rule says a difference with a
    # written reason at the point of difference is VARIANCE, so honour the
    # comment and let a human judge it.
    head = t[: t.find("set dotenv-load")]
    if "dotenv-load" in head or len(head.strip().splitlines()) >= 3:
        return MANUAL, "dotenv-load set, with a rationale — verify it still holds"
    return FAIL, "dotenv-load set with no rationale"


# ── Checkers written to close the MANUAL gap ────────────────────────────
#
# 14 of 43 checks had no checker and reported MANUAL — honest, but it meant a
# third of the register documented drift rather than catching it. These close
# the automatable ones. What stays MANUAL below stays MANUAL for a stated
# reason, not because nobody got to it.


@check("CTR-07")
def _(r):
    f = yml(r, "docker-compose.prod")
    if not f.is_file():
        return NA, "no prod compose"
    try:
        doc = yaml.safe_load(f.read_text())
    except Exception as e:
        return MANUAL, f"unparsable: {e}"
    bad = []
    for name, svc in (doc.get("services") or {}).items():
        if not isinstance(svc, dict):
            continue
        # Two models. Swarm services carry `deploy.restart_policy`; classic
        # compose carries a top-level `restart:`. website and design-system
        # deploy via `docker stack deploy`, so they use the former — checking
        # only `restart:` would report them as violations for using the
        # correct spelling for their platform.
        if "deploy" in svc:
            cond = (svc.get("deploy") or {}).get("restart_policy", {}).get("condition")
            if not cond:
                bad.append(f"{name}: no deploy.restart_policy")
            continue
        pol = svc.get("restart", None)
        # `restart: no` is YAML false, and is CORRECT for a wayfare-build-task setup job
        # — it must not be restarted. Treat an explicit false as a policy.
        if pol is None:
            # Setup/init jobs that simply omit it are still wrong: compose
            # defaults to `no`, but the intent should be written down.
            bad.append(f"{name}: no restart policy")
    return (FAIL, "; ".join(bad)) if bad else (PASS, "all services declare one")


@check("CTR-05")
def _(r):
    f = r / "supervisor.mjs"
    if not f.is_file():
        return NA, "no supervisor"
    s = f.read_text()
    probs = []
    # The bug: keeping the code in a local and only applying it from an
    # unref'd timer. When the peer child exits promptly the event loop drains
    # first and Node exits 0 — a crash reported as a graceful stop, so
    # `restart: on-failure` never fires and the unit stays dead.
    if "process.exitCode" not in s:
        probs.append("does not set process.exitCode")
    if re.search(r"setTimeout\(\s*\(\)\s*=>\s*process\.exit\(\s*exitCode\s*\)", s):
        probs.append("exits from an unref'd timer with a local code")
    # A child killed by our own SIGTERM reports code===null. Treating that as
    # a failure makes every graceful stop exit non-zero.
    if "code === null" not in s and "code===null" not in s:
        probs.append("does not treat code===null during teardown as clean")
    return (FAIL, "; ".join(probs)) if probs else (PASS, "exit contract intact")


@check("CTR-06")
def _(r):
    f = r / "dev.sh"
    if not f.is_file():
        return NA, "no dev.sh"
    s = uncommented(f.read_text())
    if not re.search(r"shutdown\(\)\s*\{", s):
        return MANUAL, "no shutdown() to judge"
    probs = []
    # shutdown must take a code and propagate it; the old shape hardcoded
    # `exit 0`, making a segfaulting mongod indistinguishable from
    # `docker compose down`.
    if not re.search(r'code="?\$\{1:-0\}"?', s):
        probs.append("shutdown() takes no exit code")
    if re.search(r"^\s*exit 0\s*$", s, re.M) and 'exit "$code"' not in s:
        probs.append("hardcodes exit 0")
    # The watchdog (a child died unexpectedly) must pass non-zero.
    if "shutdown 1" not in s:
        probs.append("watchdog does not pass a failing code")
    return (FAIL, "; ".join(probs)) if probs else (PASS, "propagates the code")


def _line_at(text, offset):
    return text.count("\n", 0, offset) + 1


def _node_majors(r):
    """Every Node major this repo pins, and where."""
    out = {}
    n = r / ".nvmrc"
    if n.is_file():
        m = re.search(r"\d+", n.read_text())
        if m:
            out[".nvmrc"] = m.group(0)
    for df in sorted(r.glob("Dockerfile*")):
        text = df.read_text()
        for m in re.finditer(r"FROM node:(\d+)", text):
            out[f"{df.name}:{_line_at(text, m.start())}:node"] = m.group(1)
        for m in re.finditer(r"distroless/nodejs(\d+)", text):
            out[f"{df.name}:{_line_at(text, m.start())}:runtime"] = m.group(1)
    for w in workflows(r):
        text = w.read_text()
        for m in re.finditer(r"node-version:\s*[\"']?(\d+)[\"']?", text):
            out[f"{w.name}:{_line_at(text, m.start())}"] = m.group(1)
    return out


_SCRIPT_PATH = re.compile(r"(?<![\w./-])((?:\./)?[\w.-]+(?:/[\w.-]+)*\.(?:sh|bash|py|mjs|cjs|js|ts))\b")


def _run_lines(text):
    """The `run:` bodies of a workflow, or its uncommented text when it will
    not parse."""
    try:
        doc = yaml.safe_load(text)
        jobs = doc.get("jobs") or {}
        return [
            st["run"]
            for j in jobs.values() if isinstance(j, dict)
            for st in j.get("steps") or [] if isinstance(st, dict) and isinstance(st.get("run"), str)
        ]
    except (yaml.YAMLError, AttributeError):
        return [uncommented(text)]


def _recipe_body(justfile, name):
    """The indented body of one Justfile recipe, "" when it is not there."""
    m = re.search(rf"^{re.escape(name)}(?![\w-])[^\n:=]*:(?!=)[^\n]*\n((?:[ \t]+[^\n]*\n?|\n)*)", justfile, re.M)
    return m.group(1) if m else ""


def _script_texts(r, text):
    """Contents of repo files that `text` invokes by path, one hop."""
    out = []
    for m in _SCRIPT_PATH.finditer(text):
        f = (r / m.group(1)).resolve()
        if f.is_file() and r.resolve() in f.parents:
            out.append(f.read_text(errors="replace"))
    return out


def _ci_asserts_node(r):
    """Does CI assert that the Node pins agree? The literal phrase is one
    spelling. The rule is that some step in CI reads the .nvmrc and compares
    it with the distroless/nodejs image, wherever that step lives: in the
    workflow, in a script a `run:` line invokes, or in a `just` recipe it
    calls. Both pins must appear in one of those, comments stripped: a build
    step reading .nvmrc and a docker step naming the image are two mentions,
    not a comparison. One hop, so a wrapper script that shells out to another
    is not followed."""
    jf = r / "Justfile"
    justfile = jf.read_text() if jf.is_file() else ""
    for w in workflows(r):
        text = w.read_text()
        if "node majors agree" in text:
            return True
        units = []
        for run in _run_lines(text):
            units.append(run)
            units += _script_texts(r, run)
            for name in re.findall(r"(?<![\w-])just\s+(?:--\S+\s+)*([\w-]+)", run):
                body = _recipe_body(justfile, name)
                units.append(body)
                units += _script_texts(r, body)
        if any(".nvmrc" in u and "distroless/nodejs" in u for u in map(uncommented, units)):
            return True
    return False


@check("CTR-01")
def _(r):
    pins = _node_majors(r)
    if not pins:
        return NA, "no node pins"
    vals = set(pins.values())
    if len(vals) > 1:
        detail = ", ".join(f"{k}={v}" for k, v in sorted(pins.items()))
        return FAIL, f"majors disagree: {detail}"
    # Agreement is necessary but not sufficient: CI must ASSERT it, or the
    # next edit silently re-splits build-on-N / run-on-M.
    asserts = _ci_asserts_node(r)
    if not asserts:
        return FAIL, f"all on {vals.pop()}, but CI does not assert it"
    return PASS, f"node {vals.pop()}, asserted in CI"


@check("CTR-02")
def _(r):
    if not has_go(r):
        return NA, "no Go"
    out = {}
    for gm in sorted(r.glob("*/go.mod")):
        m = re.search(r"^go (\d+\.\d+)", gm.read_text(), re.M)
        if m:
            out[f"{gm.parent.name}/go.mod"] = m.group(1)
    for df in sorted(r.glob("Dockerfile*")):
        text = df.read_text()
        for m in re.finditer(r"FROM golang:(\d+\.\d+)", text):
            out[f"{df.name}:{_line_at(text, m.start())}"] = m.group(1)
    for w in workflows(r):
        text = w.read_text()
        for m in re.finditer(r"go-version:\s*[\"']?(\d+\.\d+)[\"']?", text):
            out[f"{w.name}:{_line_at(text, m.start())}"] = m.group(1)
    if not out:
        return NA, "no go pins"
    vals = set(out.values())
    if len(vals) > 1:
        return FAIL, "versions disagree: " + ", ".join(f"{k}={v}" for k, v in sorted(out.items()))
    return PASS, f"go {vals.pop()} everywhere"


# config file -> the token that proves something RUNS it.
_RUNNERS = {
    ".golangci.y*ml": "golangci-lint",
    ".markdownlint.yaml": "markdownlint",
    ".prettierrc": "prettier",
    "eslint.config.js": "eslint",
    ".secrets.baseline": "detect-secrets",
}


@check("GATE-01")
def _(r):
    """Trace every committed tool config to something that executes it.

    Dead config is worse than none: it reads as a gate. auth carried a
    .golangci.yaml for years that no hook and no workflow invoked.
    """
    haystack = ""
    for p in (r / ".pre-commit-config.yaml", r / "Justfile"):
        if p.is_file():
            haystack += p.read_text()
    for w in workflows(r):
        haystack += w.read_text()
    for sub in ("ui", "src"):
        pj = r / sub / "package.json"
        if pj.is_file():
            haystack += pj.read_text()
    pj = r / "package.json"
    if pj.is_file():
        haystack += pj.read_text()

    dead = []
    for cfg, token in _RUNNERS.items():
        found = list(r.glob(cfg)) + list(r.glob(f"ui/{cfg}"))
        if not found:
            continue
        if token not in haystack:
            dead.append(f"{cfg} (nothing runs {token})")
    return (FAIL, "; ".join(dead)) if dead else (PASS, "every config has a runner")


@check("JUST-02")
def _(r):
    """A shebang-less recipe must not rely on a pipeline's exit status.

    The original finding here — "no shebang means no early exit, so a failing
    step reports success" — is FALSE, and was verified false: `just` runs each
    line in its own shell and ABORTS the recipe on the first non-zero line
    ("error: Recipe `x` failed on line N"). Multi-line alone is not a hazard.

    The real hazard is narrower. A pipeline's exit status is its LAST
    command's, and there is no `pipefail` without a `#!/usr/bin/env bash`
    recipe — so `false | cat` succeeds and the recipe carries on. That is the
    silent success, and it needs a pipe, not merely a second line.

    hero-template's `health` recipe documents exactly this trap: it avoids
    `curl -fsS ... | jq` because the pipe would swallow curl's status and make
    the documented "non-zero on 503" a lie.
    """
    f = r / "Justfile"
    if not f.is_file():
        return NA, "no Justfile"
    lines = f.read_text().split("\n")
    bad, i = [], 0
    while i < len(lines):
        m = re.match(r"^([a-z][a-z0-9-]*)(\s+\S+)*:", lines[i])
        if not m:
            i += 1
            continue
        name, body, j = m.group(1), [], i + 1
        while j < len(lines) and (lines[j].startswith((" ", "\t")) or not lines[j].strip()):
            if lines[j].strip():
                body.append(lines[j])
            j += 1
        # A shebang recipe runs as one script and can set -o pipefail itself.
        if body and body[0].strip().startswith("#!"):
            i = j
            continue
        for b in body:
            if b.strip().startswith("#"):
                continue
            # A real pipe, not `||`.
            if re.search(r"[^|]\|[^|]", b):
                bad.append(f"{name}: {b.strip()[:40]}")
        i = j
    if bad:
        return FAIL, "unguarded pipe: " + "; ".join(bad)
    return PASS, "no unguarded pipes"


# Files allowed to sit at the repo root. Everything else belongs under docs/.
_ROOT_OK = re.compile(
    r"^("
    # Entry docs and the compliance register. These BELONG at the root — an
    # earlier version of this pattern anchored on the stem only, so README.md
    # never matched ^README$ and the check flagged every file it exists to
    # permit.
    r"(README|CLAUDE|AGENTS|HERO|DESIGN|CONTROLS|CHECKS|CONSISTENCY|CONTRIBUTING|SECURITY|CHANGELOG|LICENSE)"
    r"(\.(md|yaml|yml|txt))?"
    # Harness + build files.
    r"|Justfile|Dockerfile.*|docker-compose.*|go\.work.*|go\.(mod|sum)|dev\.sh|supervisor\.mjs"
    r"|package(-lock)?\.json|tsconfig.*\.json|components\.json|registry\.json"
    r"|vite\.config\.ts|playwright\.config\.ts|eslint.*\.(js|mjs|ts)|firebase\.json"
    r"|uv\.lock|pyproject\.toml|terraform\.auto\.tfvars\.example|.*\.code-workspace"
    r")$"
)


@check("PLACE-04")
def _(r):
    _rc, out = sh(r, "git ls-files --full-name -- ':(exclude)*/*'")
    files = [f.strip() for f in out.splitlines() if f.strip()]
    # A root .go file is a module's own source only when a root go.mod makes
    # it one; _ROOT_OK is a regex over names and cannot see the repo.
    root_module = "go.mod" in files
    loose = []
    for f in files:
        if f.startswith("."):
            continue
        if _ROOT_OK.match(f):
            continue
        if root_module and re.fullmatch(r"[^/]+\.go", f):
            continue
        loose.append(f)
    return (FAIL, ", ".join(sorted(loose))) if loose else (PASS, "root is clean")


@check("DOC-03")
def _(r):
    if not (r / "docs").is_dir():
        return NA, "no docs/"
    stray = (r / "docs" / "design").is_dir()
    return (FAIL, "docs/design/ — use docs/superpowers/specs/") if stray else (PASS, "")


@check("HLT-03")
def _(r):
    if not has_go(r):
        return NA, "no Go backend"
    _rc, out = sh(r, "git grep -lI -E 'IsDev|Environment' -- 'lib/**/*.go' 2>/dev/null")
    if not out:
        return NA, "no environment gate found"
    # The failure mode is comparing the string instead of asking the type:
    # `!= \"production\"` opens disclosure in staging.
    _rc, bad = sh(
        r,
        "git grep -nI -E '(Environment|env)\\s*!=\\s*\"production\"' -- '*.go' 2>/dev/null",
    )
    if bad:
        return FAIL, "string compare against \"production\": " + bad.splitlines()[0][:60]
    return MANUAL, "no string-compare found; confirm probe errors are gated on IsDev()"


@check("DOC-04")
def _(r):
    a, c = r / "AGENTS.md", r / "CLAUDE.md"
    if not a.is_file():
        return FAIL, "no AGENTS.md (the cross-vendor standard)"
    if not c.exists() and not c.is_symlink():
        return PASS, "AGENTS.md only"
    # A SYMLINK, not a prose pointer and certainly not a copy. A pointer file
    # is still a second file: it can accumulate content and drift. A symlink
    # cannot — there is exactly one set of bytes, and git stores it as mode
    # 120000 rather than a blob.
    if not c.is_symlink():
        return FAIL, "CLAUDE.md is a real file — it must be a symlink to AGENTS.md"
    target = os.readlink(c)
    if pathlib.PurePath(target).name != "AGENTS.md":
        return FAIL, f"CLAUDE.md symlinks to {target}, not AGENTS.md"
    return PASS, "CLAUDE.md -> AGENTS.md (symlink)"


@check("JUST-04")
def _(r):
    f = r / "Justfile"
    if not f.is_file():
        return NA, "no Justfile"
    bad = []
    _rc, out = sh(r, "just --summary 2>/dev/null")
    if out:
        bad += ["Justfile:" + x for x in out.split()
                if x in ("dev", "dev-ui", "dev-service", "dev-mongo", "dev-redis", "preview")]
    # SUB-files count. A root Justfile with no host recipe proves nothing if
    # ui/Justfile still has `dev` and service/Makefile still has `run` — the
    # rule is that no path starts a server on the host, not that one file
    # doesn't. The root-only version of this check passed all five repos while
    # four of them shipped exactly that.
    # A language virtual environment is the same evasion as a host recipe: it
    # is an environment that is not the container. None exist in the fleet
    # today; the check is here so one cannot arrive quietly.
    for venv in ("venv", ".venv", "virtualenv"):
        if (r / venv).is_dir():
            bad.append(f"{venv}/ — the container is the environment")
    for sub in list(r.glob("*/Justfile")) + list(r.glob("*/Makefile")):
        if "node_modules" in str(sub):
            continue
        for i, line in enumerate(sub.read_text().splitlines(), 1):
            m = re.match(r"^(run|dev|serve|start):", line)
            if m:
                bad.append(f"{sub.parent.name}/{sub.name}:{i} {m.group(1)}")
    if bad:
        return FAIL, "host-run: " + ", ".join(bad)
    return PASS, "containerized only"























@check("PLACE-05")
def _(r):
    if not list(r.glob("Dockerfile*")):
        return NA, "no Dockerfile"
    if (r / "Dockerfile").is_file():
        return FAIL, "bare Dockerfile — which environment does it build?"
    missing = [n for n in ("Dockerfile.dev", "Dockerfile.prod") if not (r / n).is_file()]
    return (FAIL, "missing " + ", ".join(missing)) if missing else (PASS, "dev + prod")


@check("STRUCT-08")
def _(r):
    if not has_go(r):
        return NA, "no Go backend"
    missing = [d for d in ("ui", "lib", "service") if not (r / d).is_dir()]
    return (FAIL, "missing " + ", ".join(missing)) if missing else (PASS, "ui + lib + service")


def fenced_trees(repo):
    """Directories the repo has already declared are not its source, read from
    .prettierignore.

    Not a hardcoded folder list: the repo states this itself, and PLACE-06 has
    no business inventing its own answer. design-system fences mockup/ out of
    prettier, eslint, tsconfig and docker alike — reading the fence keeps this
    check honest for any repo that vendors something later.
    """
    f = repo / ".prettierignore"
    if not f.is_file():
        return []
    out = []
    for line in uncommented(f.read_text()).splitlines():
        s = line.strip().rstrip("/")
        # Only plain directory prefixes. A glob (dist/**, *.min.js) is about
        # build output, not a vendored tree, and guessing at glob semantics here
        # would quietly widen the carve-out.
        if s and not s.startswith("!") and not any(c in s for c in "*?[]"):
            out.append(s)
    return out


@check("PLACE-06")
def _(r):
    _rc, out = sh(r, "git ls-files '*.yml' | grep -v node_modules")
    files = [x for x in out.splitlines() if x]
    if not files:
        return PASS, "all .yaml"
    fences = fenced_trees(r)
    stray = [x for x in files if not any(x.startswith(d + "/") for d in fences)]
    if stray:
        return FAIL, f"{len(stray)} .yml files (use .yaml): " + " ".join(stray[:3])
    # Name only the fences that actually cover a .yml. .prettierignore also
    # lists lockfiles and generated files, and reporting those as "trees" would
    # make the exception look broader than it is.
    covering = sorted({d for d in fences for x in files if x.startswith(d + "/")})
    # MANUAL, not PASS — same reasoning as PLACE-01: a documented exception
    # should not go green unexamined, but nor should it stay red forever and
    # train people to ignore the report.
    return MANUAL, f"{len(files)} .yml only under fenced {','.join(covering)}/ — re-verify it is still vendored"


@check("CTR-08")
def _(r):
    f = yml(r, "docker-compose.dev")
    if not f.is_file():
        return NA, "no dev compose"
    try:
        doc = yaml.safe_load(f.read_text())
    except Exception as e:
        return MANUAL, f"unparsable: {e}"
    mounts = []
    for svc in (doc.get("services") or {}).values():
        if not isinstance(svc, dict):
            continue
        for v in (svc.get("volumes") or []):
            if isinstance(v, str) and (v.startswith("./") or v.startswith(".:")):
                mounts.append(v.split(":")[0])
    if not mounts:
        return FAIL, "no source mount — a change needs a rebuild"
    # `.:/app` mounts the WHOLE repo, which covers the UI and everything else —
    # a superset of ./ui, not a gap. An earlier version of this check looked
    # only for ./ui or ./src and failed the two repos that do it MORE
    # thoroughly. website documents why it needs the wider mount: vite's envDir
    # is the repo root, not ui/, so a narrower mount would miss the .env the
    # config reads.
    if "." in mounts:
        return PASS, "whole repo (.:/app)"
    if not [m for m in mounts if m in ("./ui", "./src")]:
        return FAIL, "backend mounted but not the UI: " + ", ".join(sorted(set(mounts)))
    return PASS, ", ".join(sorted(set(mounts)))


@check("DATA-01")
def _(r):
    if not has_go(r):
        return NA, "no Go backend"
    _rc, uses_mongo = sh(r, "git grep -lI 'mongo' -- '*/go.mod' 2>/dev/null")
    if not uses_mongo:
        return NA, "no MongoDB"
    _rc, out = sh(r, "git grep -nI 'Migrate(' -- 'service/main.go' 2>/dev/null")
    if not out:
        return FAIL, "no migration runs at boot"
    return PASS, out.splitlines()[0].split(":")[0] + " calls Migrate at boot"


_TEST_SRC = re.compile(r"\.(test|spec|stories)\.tsx?$|(^|/)(__tests__|__mocks__)/")
# A file the framework mounts without anyone importing it: an entry point at a
# source root, or a file-routed page. An `index.tsx` deeper down is a component
# folder's barrel, imported like any other file, so it does not count.
_ENTRY_SRC = re.compile(
    r"(^|/)src/(main|index|App|app|root|_app)\.tsx$|^(main|index|App|app)\.tsx$"
    r"|(^|/)(__root|layout|page)\.tsx$|(^|/)(routes?|pages?)/[^\n]*\.tsx$"
)
_JS_COMMENT = re.compile(r"/\*[\s\S]*?\*/|(?<![:\w])//[^\n]*")
_EXPORT_NAMES = (
    re.compile(r"^export\s+(?:default\s+)?(?:async\s+)?(?:function\*?|const|let|class)\s+([A-Z]\w*)", re.M),
    re.compile(r"^export\s+default\s+([A-Z]\w*)\s*;?\s*$", re.M),
)


def _component_exports(text):
    names = {n for rx in _EXPORT_NAMES for n in rx.findall(text)}
    for body in re.findall(r"^export\s*\{([^}]*)\}", text, re.M):
        for part in body.split(","):
            n = part.split(" as ")[-1].strip()
            if n[:1].isupper():
                names.add(n)
    return names


def _import_graph(r, files):
    """{file: set of files it imports}, resolving relative specifiers by path
    and aliased ones (`@/x`, `~/x`, `#/x`) by trailing path, which is all a
    grep-level audit can know about a tsconfig it does not read. A bare
    specifier is a package: `react` must not resolve to a local `.../react`."""
    key = {}
    for f in files:
        k = re.sub(r"\.(tsx?|jsx?)$", "", f)
        key[re.sub(r"/index$", "", k)] = f
    graph = {}
    for f in files:
        text = (r / f).read_text(errors="replace")
        deps = set()
        for spec in re.findall(r"""(?:from|import)\s*\(?\s*['"]([^'"]+)['"]""", text):
            if spec.startswith("."):
                k = os.path.normpath(os.path.join(os.path.dirname(f), spec))
                hit = key.get(k)
            elif re.match(r"[@~#]/", spec):
                rest = spec[2:]
                hit = next((v for kk, v in key.items() if kk == rest or kk.endswith("/" + rest)), None)
            else:
                hit = None
            if hit and hit != f:
                deps.add(hit)
        graph[f] = deps
    return graph


def _mounted_gate(r, hooks):
    """The file that renders a component sitting on the import chain above the
    version-check hook, or None. The chain is the hook's importers up to three
    hops, tests excluded, and both the gate and what renders it are drawn from
    that chain. A component counts as mounted when another .tsx on the chain
    renders it outside a comment and that file is an entry point, or exports a
    component that is itself mounted, at most two more renders up. An
    organism that renders the gate, imported by a route that never renders the
    organism, is the unmounted gate this check exists for."""
    files = [f for f in tracked(r, "*.ts", "*.tsx") if not _TEST_SRC.search(f)]
    graph = _import_graph(r, files)
    level = {h: 0 for h in hooks if h in graph}
    frontier = set(level)
    for hop in (1, 2, 3):
        frontier = {f for f, deps in graph.items() if f not in level and deps & frontier}
        level.update({f: hop for f in frontier})
    text = {f: _JS_COMMENT.sub("", (r / f).read_text(errors="replace")) for f in level if f.endswith(".tsx")}
    exports = {f: _component_exports((r / f).read_text(errors="replace")) for f in level}

    def renders(f, g):
        return f != g and any(re.search(rf"<{n}[\s/>]", text[f]) for n in exports[g])

    def mounted(g, left):
        for f in text:
            if renders(f, g):
                if _ENTRY_SRC.search(f):
                    return f
                top = left and mounted(f, left - 1)
                if top:
                    return top
        return None

    for g in level:
        if level[g] >= 1 and exports[g]:
            hit = mounted(g, 2)
            if hit:
                return hit
    return None


@check("UI-01")
def _(r):
    if not has_ui(r):
        return NA, "no UI"
    _rc, out = sh(r, "git ls-files | grep -E 'version-gate|use-version-check'")
    if not out:
        return FAIL, "no version check — a stale tab keeps calling a moved API"
    # The files existing is not the point — the gate RENDERING is. A VersionGate
    # imported but never mounted has already shipped once in this family, doing
    # nothing, while this check reported PASS on the strength of the file being
    # there. It was caught by tsc's noUnusedLocals, which is luck, not a gate.
    #
    # So look for the JSX, in a file that is not the component or its own test.
    # An import alone proves nothing: it is exactly what the broken version had.
    _rc, used = sh(
        r,
        "git grep -l '<VersionGate' -- '*.tsx' "
        "':(exclude)*version-gate*' ':(exclude)*.test.tsx' ':(exclude)*.spec.tsx'",
    )
    if used:
        return PASS, f"{len(out.splitlines())} files, mounted in {used.splitlines()[0]}"
    # The gate need not be called VersionGate: a repo can wrap the hook in a
    # banner or a shell component. Follow the hook's importers and accept a
    # render of anything on that chain, at the same standard: JSX in a file
    # that mounts, not an import.
    hooks = [f for f in out.splitlines() if "use-version-check" in f]
    hit = _mounted_gate(r, hooks)
    if hit:
        return PASS, f"{len(out.splitlines())} files, mounted via {hit}"
    return FAIL, "version-gate exists but nothing renders it — a gate that cannot fire"


# A name that IS a credential. Anything matching this belongs in `secrets`.
#
# The DSN carve-out is not a fudge: a Sentry DSN is a public write-only ingest
# key that Vite inlines into the bundle every visitor downloads. Calling it a
# credential because it contains no keyword, or hiding it in `secrets`, would be
# cargo-culting the shape of the rule instead of its reason.
_CREDENTIAL = re.compile(r"[A-Z_]*(TOKEN|SECRET|PASSWORD|CREDENTIAL)[A-Z_]*$|[A-Z_]+_KEY$")


def _ci_refs(repo):
    """Every ${{ secrets.X }} / ${{ vars.X }} in a repo's workflows, as
    {name: {namespace, ...}}. Reads the workflows as text on purpose: a value
    can appear anywhere (env:, with:, run:), and only the reference matters."""
    out = {}
    for wf in workflows(repo):
        for ns, name in re.findall(
            r"\$\{\{\s*(secrets|vars)\.([A-Z_][A-Z0-9_]*)\s*\}\}", wf.read_text()
        ):
            out.setdefault(name, set()).add(ns)
    return out


@check("PRE-01")
def _(r):
    if not precommit(r):
        return FAIL, "no .pre-commit-config.yaml — nothing runs before a commit"
    missing = _missing_hooks(r, {
        "detect-secrets": ["detect-secrets"],
        "detect-private-key": ["detect-private-key"],
        "no-commit-to-branch": ["no-commit-to-branch"],
        "semgrep": ["semgrep"],
    })
    return (FAIL, "missing security hooks: " + ",".join(missing)) if missing \
        else (PASS, "secret/private-key/branch/SAST hooks present")


@check("PRE-02")
def _(r):
    if not precommit(r):
        return FAIL, "no .pre-commit-config.yaml"
    missing = _missing_hooks(r, {
        "end-of-file-fixer": ["end-of-file-fixer"],
        "trailing-whitespace": ["trailing-whitespace"],
        "check-yaml": ["check-yaml"],
        "check-merge-conflict": ["check-merge-conflict"],
        "check-added-large-files": ["check-added-large-files"],
        "conventional-commit": ["conventional-pre-commit", "conventional-commit"],
    })
    return (FAIL, "missing hygiene hooks: " + ",".join(missing)) if missing \
        else (PASS, "file-hygiene hooks present")


@check("PRE-03")
def _(r):
    if not has_go(r):
        return NA, "no Go"
    if not precommit(r):
        return FAIL, "no .pre-commit-config.yaml"
    missing = _missing_hooks(r, {
        "go-fmt": ["go-fmt", "gofmt", "gofumpt"],
        "go-vet": ["go-vet"],
        "go-mod-tidy": ["go-mod-tidy", "mod-tidy"],
        "golangci-lint": ["golangci"],
    })
    return (FAIL, "missing Go hooks: " + ",".join(missing)) if missing \
        else (PASS, "go fmt/vet/mod-tidy/golangci-lint all hooked")


@check("PRE-04")
def _(r):
    if not has_node(r):
        return NA, "no front-end"
    if not precommit(r):
        return FAIL, "no .pre-commit-config.yaml"
    missing = _missing_hooks(r, {
        "eslint": ["eslint"],
        "typecheck": ["tsc", "typecheck"],
    })
    return (FAIL, "missing Node hooks: " + ",".join(missing)) if missing \
        else (PASS, "eslint + typecheck hooked")


@check("PRE-05")
def _(r):
    if not has_python(r):
        return NA, "no Python in this repo"
    if not precommit(r):
        return FAIL, "no .pre-commit-config.yaml"
    missing = _missing_hooks(r, {
        "ruff": ["ruff"],
        "type-checker": ["mypy", "pyright"],
    })
    return (FAIL, "missing Python hooks: " + ",".join(missing)) if missing \
        else (PASS, "ruff + type checker hooked")


@check("CI-11")
def _(r):
    refs = _ci_refs(r)
    if not refs:
        return NA, "no workflow config references"
    bad = sorted(n for n, ns in refs.items() if "vars" in ns and _CREDENTIAL.match(n))
    if bad:
        return FAIL, "credential in vars (unmasked, world-readable): " + ",".join(bad)
    creds = sorted(n for n in refs if _CREDENTIAL.match(n))
    return PASS, f"{len(creds)} credentials, all in secrets"


@check("CI-12")
def _(r):
    mine = _ci_refs(r)
    if not mine:
        return NA, "no workflow config references"
    # Cross-repo by necessity: a split is invisible from inside one repo, which
    # is exactly why it survives. Compare against the FAMILY, not every checkout
    # beside us — see FAMILY.
    fleet = {}
    for name in FAMILY:
        d = repo_path(name)
        if not (d / ".git").exists():
            continue
        for k, v in _ci_refs(d).items():
            fleet.setdefault(k, {}).setdefault(name, set()).update(v)
    split = []
    for name, per_repo in fleet.items():
        if name not in mine:
            continue
        namespaces = set().union(*per_repo.values())
        if len(namespaces) > 1:
            others = sorted(
                f"{rp}:{'/'.join(sorted(ns))}" for rp, ns in per_repo.items()
            )
            split.append(f"{name} ({', '.join(others)})")
    if split:
        return FAIL, "read from both namespaces: " + "; ".join(sorted(split))
    return PASS, f"{len(mine)} names, each one namespace fleet-wide"
















@check("UI-03")
def _(r):
    # The hook itself, never its .test.ts (which sorts first and carries neither
    # the bare-return nor the breadcrumb).
    _rc, out = sh(r, "git ls-files | grep -E 'use-version-check\\.ts$'")
    if not out:
        return NA, "no version-check hook"
    hook = r / out.splitlines()[0]
    src = hook.read_text()
    # A bare `return` on a non-OK status is the silent hole: the endpoint is
    # visibly broken and the gate simply stops, with no trace.
    if re.search(r"if\s*\(\s*!res\.ok\s*\)\s*return\s*;", src):
        return FAIL, "a non-OK /version.json is silently ignored (bare return)"
    if not re.search(r"console\.(warn|error)", src):
        return FAIL, "version-check swallows failures with no breadcrumb"
    return PASS, "non-OK treated as failure; breadcrumb on a chronic break"


@check("SENTRY-01")
def _(r):
    _rc, exp = sh(r, "git grep -l 'SentryErrorBoundary' -- '*sentry*'")
    if not exp:
        return NA, "no Sentry error boundary"
    # Rendered, not merely exported — UI-01's lesson one layer down. The <JSX>
    # in a file that is not the sentry module itself or a test.
    _rc, used = sh(
        r,
        "git grep -l '<SentryErrorBoundary' -- '*.tsx' "
        "':(exclude)*sentry*' ':(exclude)*.test.tsx' ':(exclude)*.spec.tsx'",
    )
    if not used:
        return FAIL, "SentryErrorBoundary exported but never mounted — reports nothing"
    return PASS, f"mounted in {used.splitlines()[0]}"


def _sentry_browser(r):
    """The browser Sentry init file (lib/sentry.ts), or None. Excludes a
    server-side sentry-node.ts."""
    _rc, out = sh(r, "git ls-files | grep -E '(^|/)(ui/)?src/lib/sentry\\.ts$'")
    if not out:
        return None
    return r / out.splitlines()[0]


@check("SENTRY-02")
def _(r):
    f = _sentry_browser(r)
    if f is None:
        return NA, "no browser sentry init"
    src = f.read_text()
    if "parseRate" in src and "TRACES_SAMPLE_RATE" in src:
        return PASS, "traces rate via parseRate(env)"
    if re.search(r"tracesSampleRate\s*:\s*[0-9]", src):
        return FAIL, "tracesSampleRate hardcoded — not tunable without a rebuild"
    return MANUAL, "no parseRate and no literal rate found — verify"


@check("SENTRY-03")
def _(r):
    f = _sentry_browser(r)
    if f is None:
        return NA, "no browser sentry init"
    src = f.read_text()
    if re.search(r"release\s*:\s*(__APP_VERSION__|appVersion)", src):
        return PASS, "release == bundle version string"
    return FAIL, "Sentry release not tied to the bundle version string"


@check("SENTRY-04")
def _(r):
    f = r / "Dockerfile.prod"
    if not f.is_file():
        return NA, "no Dockerfile.prod"
    src = f.read_text()
    if "SENTRY_AUTH_TOKEN" not in src and "sentry_auth_token" not in src:
        return NA, "no Sentry source-map upload in the image"
    if not re.search(r"--mount=type=secret,id=sentry_auth_token", src):
        return FAIL, "sentry token not mounted as a BuildKit secret"
    if re.search(r"^\s*(ARG|ENV)\s+SENTRY_AUTH_TOKEN", src, re.MULTILINE):
        return FAIL, "SENTRY_AUTH_TOKEN declared as ARG/ENV — baked into a layer"
    return PASS, "token via BuildKit secret, never ARG/ENV"


@check("SENTRY-05")
def _(r):
    _rc, out = sh(r, "git ls-files | grep -E 'vite.config.ts$'")
    if not out:
        return NA, "no vite config"
    src = (r / out.splitlines()[0]).read_text()
    # Match the emitted annotation, not the prose about it: the trap comment
    # says "::error::" but never "::error title=Sentry", so this only fires on
    # the live console.error line.
    if "::error title=Sentry" in src:
        return FAIL, "non-rendering ::error:: annotation in the sourcemap errorHandler"
    return PASS, "no dead ::error:: annotation"


@check("SENTRY-06")
def _(r):
    # Only a runtime Node front has a server tier to report from. A static SPA
    # (design-system) has no server entry, so this does not apply.
    server = next(
        (r / c for c in ("ui/src/server.ts", "src/server.ts") if (r / c).is_file()),
        None,
    )
    if server is None:
        return NA, "no Node SSR server entry"
    src = server.read_text()
    # Init (the repo's initSentryServer helper or a direct server Sentry.init)
    # AND the fetch handler wrapped. Either half missing means SSR errors are
    # unreported — SENTRY-01's failure one tier up.
    if "initSentryServer" not in src and not re.search(r"Sentry\.init", src):
        return FAIL, "server entry does not initialize Sentry — SSR errors unreported"
    if "wrapFetchWithSentry" not in src:
        return FAIL, "fetch handler not wrapped — SSR errors escape uncaught"
    return PASS, "server-side init + wrapped fetch"


# Attacker-controllable FREE-STRING contexts that must reach a shell only via
# env:, never spliced into `run:`. This is deliberately narrow:
#
#   - inputs.* and github.head_ref carry arbitrary strings.
#   - github.event.*.{body,title,name,...} are the free-text/branch fields a
#     PR or comment author controls.
#
# It excludes what is NOT a shell-injection vector, so it does not false-fire on
# the safe splices auto-approve.yaml relies on: github.sha / github.ref_name /
# github.repository (trusted slugs), the numeric .number / .id, and
# steps.*.outputs (values the workflow itself produced and, for the verdict,
# pins to an enum before use). The deploy-summary bug this exists for was
# inputs.gh_env spliced into a heredoc — squarely inside this set.
_UNTRUSTED_RUN = re.compile(
    r"\$\{\{\s*(github\.head_ref\b|inputs\.[A-Za-z0-9_]+"
    r"|github\.event\.[A-Za-z0-9_.]*(body|title|name|ref|label|message|login|email|description))"
)


@check("CI-13")
def _(r):
    wfs = workflows(r)
    if not wfs:
        return NA, "no workflows"
    hits = []
    for wf in wfs:
        try:
            doc = yaml.safe_load(wf.read_text())
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        for job in (doc.get("jobs") or {}).values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                run = step.get("run")
                if isinstance(run, str) and _UNTRUSTED_RUN.search(run):
                    hits.append(f"{wf.name}:{(step.get('name') or 'run')}")
    if hits:
        return FAIL, "untrusted context spliced into run: " + "; ".join(sorted(set(hits))[:3])
    return PASS, "untrusted context reaches shell via env: only"


@check("HLT-04")
def _(r):
    if has_go(r):
        _rc, files = sh(
            r,
            "git grep -lI -E 'NewReadyHandler|/readyz|health probe|probe failed' -- '*.go'",
        )
        if not files:
            return NA, "no readyz handler found"
        for rel in files.splitlines():
            if re.search(r"slog\.(Error|Warn)\(", (r / rel).read_text()):
                return PASS, "readyz probe failure logged (slog)"
        return FAIL, "no failure log on the readyz probe path — a 503 with an empty log"
    # Node front: the readyz route / server health module.
    _rc, files = sh(r, "git ls-files | grep -E 'readyz|server/health'")
    if not files:
        return NA, "no readyz handler"
    for rel in files.splitlines():
        p = r / rel
        if p.is_file() and re.search(r"console\.(error|warn)", p.read_text()):
            return PASS, "readyz probe failure logged (console)"
    return FAIL, "no failure log on the readyz probe path — a 503 with an empty log"


@check("UI-02")
def _(r):
    """The commit actually reaches the version generator in the prod build.

    UI-01 proves the gate is mounted. This proves it can ever FIRE, which is a
    different question and the one that was silently answered "no" in 2 of the
    4 repos that had a gate: the generator falls back to git, .dockerignore
    excludes .git, and nothing passed a SHA — so the image stamped "dev" into
    both the baked and the served version. They agree forever. It compiles,
    tests, and deploys green while doing nothing.
    """
    gen = [f for f in sh(r, "git ls-files")[1].splitlines() if "generate-version" in f]
    if not gen:
        return NA, "no version generator (see UI-01)"
    df = r / "Dockerfile.prod"
    if not df.is_file():
        return NA, "no Dockerfile.prod"
    dft = df.read_text()
    # Only a build that cannot reach .git depends on the arg. If the context
    # keeps .git, the generator's own fallback finds the commit and there is
    # nothing to pass.
    di = r / ".dockerignore"
    if not di.is_file() or not re.search(r"(?m)^\.git/?$", uncommented(di.read_text())):
        return NA, ".git in build context — generator resolves the commit itself"
    # Ask the GENERATOR which name it reads. Wiring an ARG it does not read
    # leaves the gate exactly as dead while looking fixed — that happened here,
    # and only a test caught it.
    wants = set(re.findall(r"process\.env\.([A-Z_]+SHA)", (r / gen[0]).read_text()))
    if not wants:
        return MANUAL, f"{gen[0]} reads no *_SHA env — how does it learn the commit?"
    armed = {w for w in wants if re.search(rf"(?m)^ARG\s+{w}\b", dft)}
    if not armed:
        return FAIL, f"Dockerfile.prod passes none of {','.join(sorted(wants))} — every build stamps 'dev'"
    passed = set()
    for wf in workflows(r):
        for w in armed:
            if re.search(rf"{w}=\$\{{\{{\s*github\.sha\s*\}}\}}", wf.read_text()):
                passed.add(w)
    if not passed:
        return FAIL, f"ARG {','.join(sorted(armed))} declared but no workflow passes github.sha"
    return PASS, f"{','.join(sorted(passed))} reaches {gen[0]}"


@check("DOC-06")
def _(r):
    TEST_LINE = "undo this for a reason this comment prevents"
    # A sentence from the guidance body that the AGENTS.md pointer must NOT
    # carry — its presence means the full guide grew back beside the pointer.
    BODY_SENTINEL = "Comment rot is not untidiness"
    rule = r / ".claude" / "rules" / "comments.md"
    if not rule.is_file():
        return FAIL, "no .claude/rules/comments.md"
    if TEST_LINE not in rule.read_text():
        return FAIL, "comments.md lacks the one-line test"
    f = r / "AGENTS.md"
    if not f.is_file():
        return FAIL, "no AGENTS.md (see DOC-04)"
    t = f.read_text()
    if "comments.md" not in t or TEST_LINE not in t:
        return FAIL, "AGENTS.md lacks the pointer + one-line test"
    if BODY_SENTINEL in t:
        return FAIL, "full guidance grew back beside the pointer"
    return PASS, ""


@check("LIC-01")
def _(r):
    # GitHub detects LICENSE/LICENCE/COPYING with an optional extension.
    if not any((r / n).is_file() for n in
               ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING")):
        return FAIL, "no LICENSE at the repo root"
    cfg = r / ".pre-commit-config.yaml"
    if not cfg.is_file():
        return FAIL, "no .pre-commit-config.yaml"
    try:
        raw = cfg.read_text()
    except (OSError, UnicodeDecodeError) as e:
        return MANUAL, f"cannot read .pre-commit-config.yaml: {e}"
    # Grep the raw text rather than parsing: the hook is identified by id and
    # the flag by its literal spelling, and a YAML walk would have to guess
    # which of several repos/hooks entries owns them.
    if "insert-license" not in raw:
        return FAIL, "no insert-license hook"
    # The stamp template must not BE the LICENSE — insert-license's default is
    # LICENSE.txt, which both collides with GitHub's detection and would prefix
    # every source file with the full notice.
    if "--license-filepath" not in raw:
        return FAIL, "insert-license does not set --license-filepath (defaults to LICENSE.txt)"
    # Pull the VALUE rather than pattern-matching one spelling. All of these are
    # ordinary YAML and argparse, and an earlier line-anchored regex caught only
    # the first: `- --license-filepath=X`, `args: [--license-filepath=X, ...]`,
    # `- "--license-filepath=X"`, and the split `- --license-filepath` / `- X`.
    # `(?:-\s+)?` absorbs the YAML list dash in the split form, where the value
    # sits on the NEXT line as its own item.
    values = re.findall(
        r"--license-filepath[=\s]+(?:-\s+)?[\"\']?([^\"\',\]\s]+)", raw)
    for v in values:
        if re.fullmatch(r"LICEN[SC]E(\.[A-Za-z]+)?|COPYING", pathlib.Path(v).name):
            return FAIL, f"insert-license stamps {v}, the repo LICENSE; use a separate header template"
    if not values:
        return MANUAL, "could not read --license-filepath's value"
    # --use-current-year, chosen over Chromium's "never touch the year".
    # That convention prevents annual churn but freezes whatever year a file
    # was first stamped with, and this family's 414 headers said 2024 for code
    # whose earliest commit is 2026. A frozen wrong year beats an annual diff
    # only if the frozen year was right. (--use-current-year implies
    # --allow-past-years, so accept either spelling.)
    if not ("--use-current-year" in raw or "--allow-past-years" in raw):
        return FAIL, "insert-license sets neither --use-current-year nor --allow-past-years"
    return PASS, ""


# LIC-02 judges only OUR OWN stamp. Scoping by holder rather than by path is
# what keeps the check safe across repos: a vendored or generated file may
# legitimately carry `Copyright (c) 2016 Google Inc.`, and a check that called
# that a stale year would demand someone rewrite a third party's copyright to
# go green.
_LIC_HOLDER = r"A\.I\. Hero, Inc\."

# A cheap skip-list for paths nothing of ours should be stamped in. It is a
# narrowing convenience, NOT a correctness guarantee: it does not detect drift
# from the hook's own excludes in either direction, and it is this repo's
# layout. The holder match above is what makes the check correct elsewhere.
_LIC_SKIP = ("schema/gen/", "ui/src/gen/", "ui/src/routeTree.gen.ts",
             "ui/src/components/ui/", "ui/src/components/blocks/",
             ".claude/hooks/", "node_modules/", "ui/.output/", ".venv/")


@check("LIC-02")
def _(r):
    if not any((r / n).is_file() for n in
               ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING")):
        return NA, "no LICENSE (LIC-01 owns the wiring)"
    rc, out = sh(r, r"git ls-files '*.go' '*.ts' '*.tsx' '*.py' '*.sh'")
    if rc != 0:
        return MANUAL, "git ls-files failed"
    year = str(datetime.now().year)
    stale = []
    for rel in out.splitlines():
        if not rel or any(rel.startswith(x) or f"/{x}" in rel for x in _LIC_SKIP):
            continue
        f = r / rel
        try:
            head = f.read_text(errors="replace")[:400]
        except OSError:
            continue
        m = re.search(
            rf"Copyright \(c\) (\d{{4}}(?:\s*-\s*\d{{4}})?) {_LIC_HOLDER}", head)
        # A file with no stamp of OURS is LIC-01's problem (no hook, or the hook
        # has not run); this check only judges the year of stamps that exist.
        if m and m.group(1) != year:
            stale.append(f"{rel}:{m.group(1)}")
    if not stale:
        return PASS, ""
    shown = ", ".join(stale[:3])
    more = f" (+{len(stale) - 3} more)" if len(stale) > 3 else ""
    return FAIL, f"{len(stale)} file(s) not {year}: {shown}{more}"


@check("ARCH-01")
def _(r):
    if (r / "DESIGN.md").is_file():
        return PASS, ""
    # Distinguish "never written" from "written under the pre-rename name".
    # Both FAIL, but they are different jobs: one is a bootstrap, the other a
    # git mv. Collapsing them sends someone to `sync` to author a file that
    # already exists, and the duplicate is what actually lands.
    #
    # Kept after the fleet migrated, for a repo that joins later carrying the
    # old name. Such a repo now also fails PLACE-04, since ARCHITECTURE is no
    # longer an allowlisted root document — that pair is expected, and THIS
    # message is the authoritative remedy. Renaming satisfies both.
    if (r / "ARCHITECTURE.md").is_file():
        return FAIL, "still ARCHITECTURE.md — git mv to DESIGN.md (H1 too)"
    return FAIL, "missing — run wayfare:wayfare-sync-architecture"


@check("ARCH-02")
def _(r):
    f = r / "DESIGN.md"
    if not f.is_file():
        return NA, "no DESIGN.md (ARCH-01 owns existence)"
    try:
        lines = f.read_text().splitlines()
    except UnicodeDecodeError:
        # The grammar's required '·' is the exact byte a Latin-1 round-trip
        # breaks — this mojibake IS a malformed anchor, not a checker error.
        return FAIL, "not valid UTF-8 — the anchor's '·' must be UTF-8 encoded"
    # Line 3, fixed grammar, strict on purpose — see ARCH-02's why.
    if len(lines) < 3 or not (
        m := re.match(
            r"^> Last updated: \d{4}-\d{2}-\d{2} · Source ref: ([0-9a-f]{40})$",
            lines[2],
        )
    ):
        return FAIL, "missing/malformed anchor on line 3"
    # Bind git to THIS directory before trusting its answer: upward .git
    # discovery from a non-clone would resolve the SHA against an ancestor
    # repo and report a false PASS.
    rc, top = sh(r, "git rev-parse --show-toplevel")
    if rc != 0 or pathlib.Path(top) != r.resolve():
        return MANUAL, "not a git clone — anchor unverifiable"
    rc, _out = sh(r, f"git cat-file -e {m.group(1)}^{{commit}}")
    if rc != 0:
        return MANUAL, "anchor SHA does not resolve to a commit in this clone (see ARCH-02's why)"
    return PASS, ""


# The skill's section contract. Order is not checked — only membership: a
# reordered file still gives every consumer the section it navigates by, and
# failing on order would make a cosmetic edit look like a structural defect.
_ARCH_CORE = ("Overview", "Tech stack", "Codemap", "Boundaries", "Invariants",
              "Decisions")
_ARCH_PRODUCT = ("Users", "Flows", "Interaction standards")


@check("ARCH-03")
def _(r):
    f = r / "DESIGN.md"
    if not f.is_file():
        return NA, "no DESIGN.md (ARCH-01 owns existence)"
    try:
        text = f.read_text()
    except UnicodeDecodeError:
        return FAIL, "not valid UTF-8"
    # Same spelling as DOC-01 (\s+, then strip), not `^## (.+?)\s*$`: CommonMark
    # allows a tab or several spaces after the hashes, and the tighter pattern
    # reports "missing section(s): Tech stack" against a file where the heading
    # is plainly there — the failure that sends someone hunting the checker.
    have = {h.strip() for h in re.findall(r"^##\s+(.+)$", text, re.M)}
    missing = [s for s in _ARCH_CORE if s not in have]
    # A user-facing surface is what makes the product sections required, and
    # the family spells it two ways: an app repo puts the front end in `ui/`,
    # while a repo that IS the front end (design-system) has `src/routes/` at
    # the top. Keying on `ui/` alone silently exempted the second shape —
    # design-system ships a registry site with routes and would have been
    # told it needs no Users or Flows.
    stray = []
    if (r / "ui").is_dir() or (r / "src" / "routes").is_dir():
        missing += [s for s in _ARCH_PRODUCT if s not in have]
    else:
        # Present at all is the failure, filled or empty: a repo with no
        # surface carrying `## Users` claims one, and every consumer that
        # navigates by the skeleton believes it.
        stray = [s for s in _ARCH_PRODUCT if s in have]
    # Report both causes in one pass. Returning early on stray discarded an
    # already-computed `missing`, so deleting the stray heading surfaced five
    # core sections nobody had been told about — a second full round trip for
    # evidence the first run was holding.
    detail = "; ".join(
        d for d in (
            f"missing section(s): {', '.join(missing)}" if missing else "",
            f"no user-facing surface, so drop: {', '.join(stray)}" if stray else "",
        ) if d
    )
    return (FAIL, detail) if detail else (PASS, "")


# The register has two homes — the engine in the wayfare plugin, the
# overlay in the fleet's register checkout (FLEET.md `register:`) — and any
# other repo carrying one of these is carrying a copy. The template still
# carries the pre-move copy until its removal PR lands: that is a real FAIL,
# not a reason to exempt it.
# The checkout directory name, not the GitHub slug: r.name is a directory.
_PLUGIN_REPO = "wayfare-skills"
# Presence list — deliberately NOT REGISTER_FILES, which is the content-grep
# exclusion set. The two overlap but answer different questions, and merging
# them would put a file in one job because it belonged in the other.
_REGISTER_ARTIFACTS = ("CONTROLS.yaml", "CHECKS.yaml", "CONSISTENCY.md",
                       "scripts/audit.py", "scripts/consistency.py",
                       ".claude/skills/consistency-audit")


@check("REG-01")
def _(r):
    if r.name == _PLUGIN_REPO:
        return NA, "the engine's home"
    # is_symlink() as well as exists(): a broken symlink is still a copy this
    # repo declares it owns, and exists() alone reads it as clean.
    found = [p for p in _REGISTER_ARTIFACTS
             if (r / p).exists() or (r / p).is_symlink()]
    if not found:
        return PASS, ""
    home = f"{_PLUGIN_REPO} (engine) and {REGISTER or 'the fleet register checkout'} (overlay)"
    return FAIL, f"carries register copy: {', '.join(found)} — the register lives in {home}"


# ── The protobuf wire contract ───────────────────────────────────────────────
# Gated on .proto sources existing, NOT on has_go: the question is whether the
# repo HAS a generated contract, and a repo could carry one without Go (or Go
# without protos). applies_to only resolves FLEET.md groups; a capability
# gate has to live in the checker.


def _has_protos(repo):
    return bool(list((repo / "schema").glob("**/*.proto"))) if (repo / "schema").is_dir() else False


def _bufgen(repo):
    """schema/buf.gen.yaml text, or "". Read as text, not parsed: the check is
    about how a plugin reference is SPELLED (bare `remote:` vs tagged vs
    `local:`), and yaml.safe_load normalises away exactly that distinction."""
    f = repo / "schema" / "buf.gen.yaml"
    return f.read_text() if f.is_file() else ""


@check("SCHEMA-01")
def _(r):
    if not _has_protos(r):
        return NA, "no .proto sources"
    missing = [n for n in ("buf.yaml", "buf.gen.yaml") if not (r / "schema" / n).is_file()]
    if missing:
        return FAIL, "missing " + ", ".join("schema/" + n for n in missing)
    stale = [
        n
        for n in ("buf.yaml", "buf.gen.yaml")
        if not re.search(r"^version:\s*v2\s*$", (r / "schema" / n).read_text(), re.M)
    ]
    return (PASS, "") if not stale else (FAIL, "not version: v2 — " + ", ".join(stale))


def _regenerates(repo, text):
    """Does this workflow text trigger codegen — directly or through `just`?

    Matching only a literal `buf generate` would fail the repos doing it right.
    JUST-01 requires CI to invoke gates through the Justfile precisely so CI and
    the runner cannot spell them differently and drift, so hero-template's job
    says `just proto-gen`. A checker that demands the raw command rewards
    restating it in the workflow — pushing repos toward the duplication another
    control exists to prevent.
    """
    if "buf generate" in text:
        return True
    just = repo / "Justfile"
    if not just.is_file():
        return False
    body = just.read_text()
    for recipe in set(re.findall(r"\bjust\s+([a-z][a-z0-9-]*)", text)):
        # Recipe body = the header line through the last indented line under it.
        m = re.search(rf"^{re.escape(recipe)}:.*?(?=^\S|\Z)", body, re.M | re.S)
        if m and "buf generate" in m.group(0):
            return True
    return False


@check("SCHEMA-02")
def _(r):
    if not _has_protos(r):
        return NA, "no .proto sources"
    # Both halves must appear in the SAME workflow file: a repo that regenerates
    # in one job and happens to diff something unrelated in another has no
    # freshness gate, and matching across files would pass it.
    regen = False
    for f in workflows(r):
        text = uncommented(f.read_text())
        if not _regenerates(r, text):
            continue
        regen = True
        if re.search(r"git diff\b.*(--quiet|--exit-code)", text):
            return PASS, f.name
    if regen:
        return FAIL, "regenerates the contract but never diffs the committed output"
    return FAIL, "no workflow regenerates the contract to check it is in sync"


@check("SCHEMA-03")
def _(r):
    if not _has_protos(r):
        return NA, "no .proto sources"
    text = _bufgen(r)
    if not text:
        return NA, "no schema/buf.gen.yaml (SCHEMA-01 owns existence)"
    # ANY remote ref, tagged or not. A tag looks like a pin and is not one: the
    # BSR publishes revisions underneath a version tag and buf.lock does not
    # cover plugins, so the ref still names something that can change. And
    # `remote:` executes off-machine, which no tag addresses at all. Matching
    # only untagged refs (what this did until 2026-07-25) blessed hiro's
    # `:v1.36.11` as compliant while it still shipped the descriptor set to
    # buf.build on the path that generates code compiled into the service.
    remotes = re.findall(r"^\s*-?\s*remote:\s*(\S+)", text, re.M)
    return (PASS, "") if not remotes else (FAIL, "remote plugin (use local:): " + ", ".join(remotes))


@check("SCHEMA-04")
def _(r):
    if not _has_protos(r):
        return NA, "no .proto sources"
    text = _bufgen(r)
    if not text:
        return NA, "no schema/buf.gen.yaml (SCHEMA-01 owns existence)"
    outs = re.findall(r"^\s*out:\s*(\S+)", text, re.M)
    if not outs:
        return MANUAL, "no `out:` found — verify by hand"
    ts = [o for o in outs if "ui/src/gen" in o]
    if ts:
        return PASS, ""
    # No TS plugin at all is a different shape from one aimed elsewhere, and
    # only the latter is what this check is about.
    if not re.search(r"protoc-gen-es|connect-(es|query)", text):
        return NA, "no TypeScript plugin configured"
    return FAIL, "TS generated outside the UI tree: " + ", ".join(o for o in outs if "gen" in o)


_SHARED_WORKFLOW_OWNER = "wayfare-skills"
# The env var name is a contract with whoever sets it, so it keeps its
# spelling; the default path is not, and it moved with the folder. A wrong
# default here does NOT fail loudly: _matches_reference returns MANUAL for an
# absent reference, and MANUAL cells are not printed in --json, so VNDR-02
# would simply stop reporting drift.
_PLUGIN_HOME = pathlib.Path(os.path.expanduser("~/.claude/plugins/wayfare-skills"))
_PLUGIN_REMOTE, _PLUGIN_BRANCH = "origin", "main"
_PLUGIN_ASSETS = pathlib.Path("<assets unbound: run checks inside reference_assets()>")


# Set in the child of run_at_origin(): the note naming the commit it was
# extracted from. Its presence is what stops the child re-executing again.
_ENGINE_MARKER = "WAYFARE_ENGINE_AT"
_ENGINE_NOTE = f"working tree {HERE} (engine not yet resolved)"


def engine_note():
    """The report header's `engine:` text: where the running engine came from."""
    return _ENGINE_NOTE


def run_at_origin(script):
    """Re-run `scripts/<script>` from the plugin checkout's origin/main as a
    child process and return its exit code, or None when this process should
    carry on as the engine.

    Register and checkers have to come from one commit: loading origin/main's
    register under a stale engine pairs new ids with old checkers. The child
    finds its own tree via HERE, so engine, register and assets cannot
    straddle two fetches. HERO_SKILLS_PLUGIN or an existing marker means
    no re-exec; so does a plugin home with no resolvable origin/main, where the
    invoked engine runs and the header says it may be stale."""
    global _ENGINE_NOTE
    override = os.environ.get("HERO_SKILLS_PLUGIN")
    if override:
        _ENGINE_NOTE = f"working tree {HERE} (HERO_SKILLS_PLUGIN override; assets from {override})"
        return None
    if os.environ.get(_ENGINE_MARKER):
        _ENGINE_NOTE = os.environ[_ENGINE_MARKER]
        return None
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="audit-engine-"))
    try:
        sha, note = _plugin_at_origin(_PLUGIN_HOME, tmp, ("scripts/audit.py", "scripts/consistency.py", "assets"),
                                      "engine")
        if not sha:
            _ENGINE_NOTE = f"working tree {HERE} ({note}; register and checkers may be stale)"
            return None
        print(f"engine: {_PLUGIN_REMOTE}/{_PLUGIN_BRANCH} @ {sha}, not the invoked tree {HERE}", file=sys.stderr)
        rc = subprocess.run([sys.executable, str(tmp / "scripts" / script), *sys.argv[1:]],
                            env={**os.environ, _ENGINE_MARKER: note}).returncode
        return rc if rc >= 0 else 128 - rc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@contextlib.contextmanager
def reference_assets():
    """Bind _PLUGIN_ASSETS for one audit run and yield a note naming where the
    assets came from, for the report header.

    The reference is the plugin checkout's origin/main, never its working
    tree. The repos are read at origin/main, and the checkout is on whatever
    branch the last session left it: a feature branch cut before a caller
    change inverted CI-20 fleet-wide (the repos that took the change failed,
    the rest passed). HERO_SKILLS_PLUGIN=<checkout> reads that checkout's
    working tree instead, which is how an unmerged asset is tested. Inside the
    child of run_at_origin() the assets are the ones extracted beside the
    running engine."""
    global _PLUGIN_ASSETS
    saved, tmp = _PLUGIN_ASSETS, None
    try:
        override = os.environ.get("HERO_SKILLS_PLUGIN")
        if override:
            _PLUGIN_ASSETS = pathlib.Path(override) / "assets"
            note = f"working tree {override} (HERO_SKILLS_PLUGIN override)"
        elif os.environ.get(_ENGINE_MARKER):
            _PLUGIN_ASSETS = HERE / "assets"
            note = os.environ[_ENGINE_MARKER]
        else:
            tmp = pathlib.Path(tempfile.mkdtemp(prefix="audit-assets-"))
            _sha, note = _plugin_at_origin(_PLUGIN_HOME, tmp, ("assets",), "assets")
            _PLUGIN_ASSETS = tmp / "assets"
        yield note
    finally:
        _PLUGIN_ASSETS = saved
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def _plugin_at_origin(plugin, dest, paths, label):
    """(sha, note) for `plugin`'s origin/main, with `paths` extracted under
    `dest`; sha is None, and nothing extracted, when there is no origin/main to
    read. A failed fetch is reported under `label`, what the fetch was for, and
    the last-fetched origin/main is used: falling back to the working tree is
    the defect reference_assets() fixes."""
    ref = f"{_PLUGIN_REMOTE}/{_PLUGIN_BRANCH}"
    if not (plugin / ".git").exists():
        return None, f"absent ({plugin} is not a git checkout; asset checks read MANUAL)"
    # A hung fetch or a credential prompt must fall back like any failed fetch,
    # not end the audit in a TimeoutExpired traceback.
    try:
        rc, _out, err = sh3(plugin, "GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -o BatchMode=yes' "
                                    f"git fetch -q {_PLUGIN_REMOTE} {_PLUGIN_BRANCH}")
    except subprocess.TimeoutExpired as e:
        rc, err = 124, f"timed out after {e.timeout:g}s"
    stale = ""
    if rc:
        stale = f"  (fetch failed: {err or f'rc={rc}'}; {ref} as last fetched)"
        print(f"{label}: git fetch in {plugin} failed: {err or f'rc={rc}'}", file=sys.stderr)
    rc, sha, _err = sh3(plugin, f"git rev-parse --verify -q --short {ref}^{{commit}}")
    if rc or not sha:
        return None, f"absent ({ref} does not resolve in {plugin}; asset checks read MANUAL){stale}"
    p = subprocess.run(["git", "archive", "--format=tar", sha, "--", *paths],
                       cwd=plugin, capture_output=True, env=_ENV, timeout=60)
    if p.returncode:
        raise RuntimeError(f"git archive {ref} in {plugin} failed: {p.stderr.decode().strip()}")
    _extract_tar(p.stdout, dest, f"git archive {ref} in {plugin}")
    return sha, f"{ref} @ {sha} in {plugin}{stale}"


def _extract_tar(data, dest, origin):
    """Extract the tar `data` under `dest`, refusing anything but regular files
    and directories with relative names that stay inside `dest`.

    The member check is the guard on every Python: `filter="data"` exists only
    on 3.12+ and late 3.9-3.11 patch releases, and macOS's /usr/bin/python3 is
    3.9.6, where passing it raises TypeError. Do not replace the member loop
    with the filter: 3.9.6 would be unguarded. `members=` is passed so semgrep
    sees the extraction is vetted. Links are refused on purpose, so a symlink
    added under assets/ or the scripts makes every audit raise."""
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        members = t.getmembers()
        for m in members:
            parts = pathlib.PurePosixPath(m.name).parts
            if not (m.isreg() or m.isdir()) or m.name.startswith("/") or ".." in parts:
                raise RuntimeError(f"{origin} holds an unsafe member {m.name!r}; nothing extracted")
        t.extractall(dest, members=members,
                     **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))


class Unreadable(Exception):
    """A file a checker must read cannot be parsed — the verdict is MANUAL
    naming the file, never a PASS built on an empty document."""


def _wf_doc(path):
    try:
        doc = yaml.safe_load(path.read_text())
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as e:
        raise Unreadable(f"{path.name}: {e}") from e
    if not isinstance(doc, dict):
        raise Unreadable(f"{path.name}: top level is {type(doc).__name__}")
    return doc


def _wf_on(doc):
    """The `on:` block as a dict. PyYAML 1.1 reads a bare `on` key as boolean
    True, so doc.get("on") sees nothing and passes every repo; GitHub also
    accepts `on: push` and `on: [push, pull_request]`."""
    on = doc.get("on") or doc.get(True) or {}
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return on if isinstance(on, dict) else {}


def _hook_segment(pc, hook_id):
    """The text of one pre-commit hook entry, from its `id:` to the next hook
    or repo. Matching the whole config attributes another hook's args to
    this one."""
    m = re.search(rf"id:\s*{re.escape(hook_id)}\b.*?(?=\n\s*-\s*id:|\n-\s*repo:|\Z)", pc, re.S)
    return m.group(0) if m else ""


def _matches_reference(mine, ref, extract=None):
    """A vendored artifact equals its source. MANUAL when the source is not
    on this machine (nothing to compare against is not a pass); FAIL when the
    artifact is missing or differs. `extract` pulls the vendored part out of a
    larger file (a section of AGENTS.md)."""
    if not ref.is_file():
        return MANUAL, f"reference absent: {ref}"
    if not mine.is_file():
        return FAIL, f"missing {mine.name}"
    if extract is None:
        return (PASS, "") if mine.read_bytes() == ref.read_bytes() else (FAIL, f"differs from {ref.name}")
    got = extract(mine.read_text())
    if got is None:
        return FAIL, "section absent"
    return (PASS, "") if got.strip() == ref.read_text().strip() else (FAIL, "differs from the installed asset")


_FROM_RE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", re.I | re.M)
_IMAGE_RE = re.compile(r"^\s*image:\s*['\"]?(\S+?)['\"]?\s*$", re.M)


def _image_refs(path):
    """(name, tag) for every pullable image reference in a Dockerfile or
    compose file — name is the last path segment, tag "" when absent. Stage
    names, scratch, variables and digest-pinned refs are not references to a
    tag and are dropped."""
    text = path.read_text()
    if path.name.startswith("Dockerfile"):
        from_lines = list(_FROM_RE.finditer(text))
        stages = {m.group(2) for m in from_lines if m.group(2)}
        refs = [m.group(1) for m in from_lines]
    else:
        stages = set()
        refs = _IMAGE_RE.findall(uncommented(text))
    out = []
    for ref in refs:
        if ref in stages or ref == "scratch" or "$" in ref or "@sha256:" in ref:
            continue
        name, _, tag = ref.rsplit("/", 1)[-1].partition(":")
        out.append((name, tag))
    return out


def _is_dockerfile_name(name):
    """Dependabot's docker ecosystem updates any `*dockerfile*` (any case)
    plus `Containerfile`, not only files named exactly `Dockerfile*`."""
    return "dockerfile" in name.lower() or name.lower() == "containerfile"


def _ref_is_digest_only(ref):
    """A digest-only ref is `@sha256:` with no `:` in the last path segment
    of the name — `node@sha256:…`, not `node:26-alpine@sha256:…` (tag+digest
    still gets tag bumps) and not `node:26-alpine` (no digest at all)."""
    if "@sha256:" not in ref:
        return False
    name = ref.split("@sha256:", 1)[0]
    return ":" not in name.rsplit("/", 1)[-1]


def _docker_entry_digest_pinned(r, entry):
    """True only when every FROM across the entry's directories is pinned by
    digest alone (no :tag). A bare `$` check stays ahead of
    `_ref_is_digest_only`, not folded into it: `${BASE}@sha256:x` has no `:`
    before its `@sha256:`, so the digest test alone would read it as
    digest-pinned instead of failing closed on the unresolved variable."""
    repo_root = r.resolve()
    has_digest = False
    for d in _entry_dirs(entry):
        d = str(d)
        if any(c in d for c in "*?["):
            return False
        base = (r / d.lstrip("/")).resolve()
        try:
            base.relative_to(repo_root)
        except ValueError:
            return False
        if not base.is_dir():
            return False
        dockerfiles = [p for p in base.iterdir() if p.is_file() and _is_dockerfile_name(p.name)]
        if not dockerfiles:
            return False
        for yml_path in list(base.glob("*.yml")) + list(base.glob("*.yaml")):
            if _IMAGE_RE.search(uncommented(yml_path.read_text())):
                return False
        for df in dockerfiles:
            stages = set()
            for m in _FROM_RE.finditer(df.read_text()):
                ref, stage_name = m.groups()
                if ref != "scratch" and ref not in stages:
                    if "$" in ref or not _ref_is_digest_only(ref):
                        return False
                    has_digest = True
                if stage_name:
                    stages.add(stage_name)
    return has_digest


def _image_files(r):
    return list(r.glob("Dockerfile*")) + list(r.glob("docker-compose*.y*ml"))


def _json_file(path):
    """JSON with `//` line comments stripped — VS Code reads its own files as
    JSONC, so a commented extensions.json is valid to the editor."""
    text = re.sub(r"^\s*//.*$", "", path.read_text(), flags=re.M)
    return json.loads(text)


@check("STRUCT-10")
def _(r):
    if not yml(r, "docker-compose.dev").is_file():
        return NA, "no dev stack"
    return (PASS, "") if tracked(r, ".env.example") else (FAIL, "root .env.example not tracked")


_GENERATED = ("schema/gen", "ui/src/gen", "ui/src/routeTree.gen.ts")


@check("STRUCT-11")
def _(r):
    present = [g for g in _GENERATED if (r / g).exists()]
    if not present:
        return NA, "no generated code"
    f = r / ".claude" / "settings.json"
    if not f.is_file():
        return FAIL, "no .claude/settings.json"
    try:
        deny = _json_file(f).get("permissions", {}).get("deny", [])
    except (json.JSONDecodeError, OSError, AttributeError) as e:
        return FAIL, f"settings.json: {e}"
    # Only a single-slash path is anchored to the settings source (the repo
    # root). `Read(./x)` is relative to the session's cwd, so it denies
    # nothing once an agent has cd'd into ui/ — the form the template
    # shipped for a month.
    anchored = [d for d in deny if re.match(r"Read\(/[^/]", d)]
    missing = [g for g in present if not any(g in d for d in anchored)]
    relative = [d for d in deny if d.startswith("Read(./")]
    if missing:
        why = " (cwd-relative `./` entries do not count)" if relative else ""
        return FAIL, "no root-anchored deny for " + ", ".join(missing) + why
    return PASS, ""


@check("CI-20")
def _(r):
    # Compared against the vendored caller the installer actually ships, not
    # against whatever the template repo happens to hold today. Reading it from
    # a repo made one member the silent definition of correct: when its copy
    # drifted, every other repo was judged against the drift and the template
    # itself could never fail, because a file always equals itself. It also
    # meant the check went MANUAL for anyone whose fleet named no template.
    # assets/auto-approve/caller.yaml is the same bytes install-auto-approve.sh
    # writes, so this compares a vendored artifact with its source.
    mine = r / ".github" / "workflows" / "auto-approve.yaml"
    if not mine.is_file():
        return NA, "no auto-approve caller"
    # The owner is recognised by what its file IS, not by what its folder is
    # called. `r.name` is the directory on disk, and a checkout of the plugin
    # under any other name — `hero-skills` after the rename, or a second clone
    # — read as an ordinary consumer, so its shared LOGIC was compared against
    # the CALLER template and failed on every line that differs between the
    # two, which is most of them.
    if r.name == _SHARED_WORKFLOW_OWNER:
        return NA, "shared workflow owner"
    try:
        doc = _wf_doc(mine)
    except Unreadable as e:
        return MANUAL, str(e)
    # `workflow_call` ALONE is not the test, and must not become it. This file
    # belongs to the repo being audited, GitHub accepts extra triggers, and NA
    # is not printed by --json — so a repo whose caller had drifted could add
    # one line, keep the drift, and erase the finding rather than fix it.
    # A caller still delegates: it has a job whose `uses:` is the shared
    # workflow. The callee cannot, because that would be itself. Requiring
    # both means the only way out of this check is to stop being a consumer.
    delegates = any(
        _SHARED_WORKFLOW_OWNER in str((job or {}).get("uses") or "")
        for job in (doc.get("jobs") or {}).values()
    )
    if "workflow_call" in _wf_on(doc) and not delegates:
        return NA, "shared workflow owner (declares workflow_call, delegates to nobody)"
    return _matches_reference(mine, _PLUGIN_ASSETS / "auto-approve" / "caller.yaml")


_EXPIRY_GATE = "check-exception-expiry.sh"
_EXCEPTION_INPUTS = {"vex-location", "trivyignores"}
_GATE_CMD = re.compile(r"^\s*(?:bash\s+)?(?:\./)?scripts/check-exception-expiry\.sh(?:\s+(.*))?$")


def _plain_trivyignore_entries(r):
    p = r / ".trivyignore"
    if not p.is_file():
        return []
    return [l.split()[0] for l in p.read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")]


def _gate_args(step, job):
    """The argument string of a gate invocation that can fail the job, else
    None. A substring match counted `echo check-exception-expiry.sh`, a
    `|| true` and a continue-on-error step as gates that could never fail."""
    if step.get("continue-on-error") or job.get("continue-on-error"):
        return None
    for line in str(step.get("run") or "").splitlines():
        m = _GATE_CMD.match(line.split(" #")[0])
        if m and "||" not in line:
            return (m.group(1) or "").split()
    return None


@check("SCAN-01")
def _(r):
    vex = r / ".vex"
    has_vex = vex.is_dir() and any(p.is_file() for p in vex.rglob("*"))
    has_trivy = (r / ".trivyignore.yaml").is_file()
    plain = _plain_trivyignore_entries(r)
    if not (has_vex or has_trivy or plain):
        return NA, "no .vex/, .trivyignore.yaml or .trivyignore entries"
    problems = []
    # The gate reads only .trivyignore.yaml for dates; a plain-format entry
    # suppresses in Trivy with no date anything checks.
    if plain:
        problems.append(".trivyignore entries the gate cannot date (move them to .trivyignore.yaml): " + ", ".join(plain))
    status, detail = _matches_reference(r / "scripts" / _EXPIRY_GATE,
                                        _PLUGIN_ASSETS / "exception-expiry" / _EXPIRY_GATE)
    if status == MANUAL:
        return status, f"scripts/{_EXPIRY_GATE}: {detail}"
    if status != PASS:
        problems.append(f"scripts/{_EXPIRY_GATE}: {detail}")
    ungated, unnamed, elsewhere, on_pr = [], [], [], False
    for wf in workflows(r):
        try:
            doc = _wf_doc(wf)
        except Unreadable as e:
            return MANUAL, str(e)
        pairs = [(s, job) for job in (doc.get("jobs") or {}).values() if isinstance(job, dict)
                 for s in (job.get("steps") or []) if isinstance(s, dict)]
        gates = [a for a in (_gate_args(s, job) for s, job in pairs) if a is not None]
        inputs = [s["with"] for s, _ in pairs if isinstance(s.get("with"), dict)]
        if any(_EXCEPTION_INPUTS & set(w) for w in inputs) and not gates:
            ungated.append(wf.name)
        # The gate reads .vex/ by default; a scanner pointed elsewhere applies
        # statements the gate never opens.
        if any(os.path.normpath(str(w.get("vex-location", ".vex"))) != ".vex" for w in inputs):
            elsewhere.append(wf.name)
        # Called with no argument the gate skips the Trivy half, so a repo
        # with a .trivyignore.yaml would pass this check while its Trivy
        # exceptions went unread.
        if has_trivy and any(".trivyignore.yaml" not in a for a in gates):
            unnamed.append(wf.name)
        if gates and "pull_request" in _wf_on(doc):
            on_pr = True
    if ungated:
        problems.append("applies exceptions without the gate: " + ", ".join(ungated))
    if unnamed:
        problems.append("gate not given .trivyignore.yaml: " + ", ".join(unnamed))
    if elsewhere:
        problems.append("vex-location other than .vex: " + ", ".join(elsewhere))
    if not on_pr:
        problems.append("no pull_request workflow runs the gate")
    return (FAIL, "; ".join(problems)) if problems else (PASS, "")


@check("CI-21")
def _(r):
    wfs = workflows(r)
    if not wfs:
        return NA, "no workflows"
    bad = []
    try:
        for w in wfs:
            pr = _wf_on(_wf_doc(w)).get("pull_request")
            if isinstance(pr, dict) and ("paths" in pr or "paths-ignore" in pr):
                bad.append(w.name)
    except Unreadable as e:
        return MANUAL, str(e)
    return (FAIL, "paths filter on pull_request: " + ", ".join(bad)) if bad else (PASS, "")


_FLEET = {}   # family-wide caches; cleared on snapshot entry and exit
_USES_RE = re.compile(r"uses:\s*([\w.-]+/[\w./-]+)@([0-9a-f]{40})\s*#\s*(v?[\d.]+)")


def _action_pins():
    """(action, comment) -> {sha: set(repos)} across the family."""
    if "pins" not in _FLEET:
        pins = {}
        for rn in FAMILY:
            for w in workflows(repo_path(rn)):
                for m in _USES_RE.finditer(w.read_text()):
                    action, sha, ver = m.groups()
                    action = action.split("/.github/")[0]
                    pins.setdefault((action, ver), {}).setdefault(sha, set()).add(rn)
        _FLEET["pins"] = pins
    return _FLEET["pins"]


@check("CI-22")
def _(r):
    if not workflows(r):
        return NA, "no workflows"
    bad = []
    for (action, ver), shas in _action_pins().items():
        if len(shas) < 2:
            continue
        top = max(len(v) for v in shas.values())
        for sha, repos in shas.items():
            if r.name in repos and len(repos) < top:
                bad.append(f"{action} {ver}@{sha[:7]} (majority differs)")
    return (FAIL, "; ".join(bad)) if bad else (PASS, "")


@check("CI-23")
def _(r):
    if not _ships_image(r):
        return NA, "no image"
    try:
        for w in workflows(r):
            text = w.read_text()
            if "schedule" in _wf_on(_wf_doc(w)) and ("trivy-action" in text or "scout-action" in text):
                return PASS, w.name
    except Unreadable as e:
        return MANUAL, str(e)
    return FAIL, "no scheduled scan workflow"


@check("GATE-07")
def _(r):
    if not has_go(r):
        return NA, "no Go"
    hits = [w.name for w in workflows(r) if "tidy -diff" in uncommented(w.read_text())]
    return (PASS, ", ".join(hits)) if hits else (FAIL, "no workflow runs go mod tidy -diff")


@check("GATE-08")
def _(r):
    seg = _hook_segment(uncommented(precommit(r)), "markdownlint")
    if not seg:
        return NA, "no markdownlint hook"
    cfg = [f for f in (".markdownlint.yaml", ".markdownlint.yml", ".markdownlint.json",
                       ".markdownlint-cli2.yaml", ".markdownlint-cli2.jsonc") if (r / f).is_file()]
    if not cfg:
        return FAIL, "no .markdownlint config"
    if "--disable" in seg:
        return FAIL, f"{cfg[0]} exists but rules are also disabled inline"
    return PASS, cfg[0]


@check("GATE-09")
def _(r):
    if not has_ui(r):
        return NA, "no UI"
    root = r / "ui" if (r / "ui" / "tsconfig.json").is_file() else r
    tsconfig = root / "tsconfig.json"
    if not tsconfig.is_file():
        return NA, "no tsconfig"
    if '"references"' not in tsconfig.read_text():
        return NA, "single-project tsconfig; --noEmit is fine here"
    blob = "\n".join(f.read_text() for f in (r / "Justfile", root / "package.json") if f.is_file())
    cmds = re.findall(r"\btsc\b[^\n\"&|;]*", uncommented(blob))
    if not cmds:
        return NA, "no tsc invocation found"
    bad = [c.strip() for c in cmds if not re.search(r"\s(-b|--build)\b", c)]
    return (FAIL, "solution file but: " + "; ".join(bad)) if bad else (PASS, "")


@check("CTR-09")
def _(r):
    if not _ships_image(r):
        return NA, "no image"
    bad = [f"{f.name}: {name}:{tag or '<untagged>'}" for f in _image_files(r)
           for name, tag in _image_refs(f) if not tag or tag == "latest"]
    return (FAIL, "; ".join(bad)) if bad else (PASS, "")


@check("CTR-10")
def _(r):
    f = r / "dev.sh"
    if not f.is_file():
        return NA, "no dev.sh"
    return (PASS, "") if re.search(r"^die\(\)", f.read_text(), re.M) else (FAIL, "no die(); wait loops fall through")


@check("CTR-11")
def _(r):
    majors = {re.match(r"\d*", tag).group(0) for f in _image_files(r)
              for name, tag in _image_refs(f) if name == "mongo"}
    if not majors:
        return NA, "no mongo"
    if len(majors) > 1:
        return FAIL, "mongo majors " + "/".join(sorted(majors))
    units = {f.name: uncommented(f.read_text()) for f in (r / "dev.sh", yml(r, "docker-compose.prod")) if f.is_file()}
    units = {n: t for n, t in units.items() if "mongod" in t or "mongo:" in t}
    if not units:
        return NA, "no mongod run by dev.sh or the prod compose"
    missing = [n for n, t in units.items() if "--replSet" not in t]
    if missing:
        return FAIL, "no --replSet in " + ", ".join(missing)
    return PASS, f"mongo:{majors.pop()} x{len(units)}"


@check("UI-04")
def _(r):
    if not has_ui(r) or not _ships_image(r):
        return NA, "no UI image"
    f = r / ".dockerignore"
    if not f.is_file():
        return NA, "no .dockerignore (STRUCT-01)"
    return (PASS, "") if "version.json" in uncommented(f.read_text()) else (FAIL, "version.json not excluded")


_SEMGREP_CONFIG = re.compile(r"--config(?:=|[ \t,\"']+|[ \t\"']*\n\s*-\s+)(?!-)[^\s,\"'\]]")


@check("PRE-06")
def _(r):
    seg = _hook_segment(uncommented(precommit(r)), "semgrep")
    if not seg:
        return NA, "no semgrep hook"
    # Any --config value names a ruleset: `auto` is one spelling and an
    # explicit pack list is another (`auto` refuses --metrics=off, so a repo
    # that turns metrics off has to list packs). The hook needs one.
    missing = [w for w in ("--error", "--skip-unknown-extensions") if w not in seg]
    if not _SEMGREP_CONFIG.search(seg):
        missing.insert(0, "--config=<ruleset>")
    return (FAIL, "missing " + " ".join(missing)) if missing else (PASS, "")


def _hook_revs():
    """hook repo URL -> {repo: rev} across the family, plus the repos whose
    config could not be parsed (they are not voters, and PRE-07 says so)."""
    if "revs" not in _FLEET:
        revs, broken = {}, {}
        for rn in FAMILY:
            text = precommit(repo_path(rn))
            if not text:
                continue
            try:
                for rep in (yaml.safe_load(text) or {}).get("repos", []):
                    if isinstance(rep, dict) and rep.get("rev"):
                        revs.setdefault(rep["repo"], {})[rn] = rep["rev"]
            except (yaml.YAMLError, AttributeError) as e:
                broken[rn] = str(e).splitlines()[0]
        _FLEET["revs"], _FLEET["revs-broken"] = revs, broken
    return _FLEET["revs"], _FLEET["revs-broken"]


@check("PRE-07")
def _(r):
    if not precommit(r):
        return NA, "no pre-commit"
    revs, broken = _hook_revs()
    if r.name in broken:
        return MANUAL, f".pre-commit-config.yaml unparsable: {broken[r.name]}"
    behind = []
    for url, by_repo in revs.items():
        if r.name not in by_repo or len(by_repo) < 3:
            continue
        counts = {}
        for rev in by_repo.values():
            counts[rev] = counts.get(rev, 0) + 1
        majority = max(counts, key=lambda k: (counts[k], _semver(k) or ()))
        mine, top = _semver(by_repo[r.name]), _semver(majority)
        if mine and top and mine < top:
            behind.append(f"{url.rsplit('/', 1)[-1]} {by_repo[r.name]} < {majority}")
    note = f" (not voting: {', '.join(sorted(broken))})" if broken else ""
    return (FAIL, "; ".join(behind) + note) if behind else (PASS, note.strip())


@check("JUST-05")
def _(r):
    jf = r / "Justfile"
    if not jf.is_file() or not yml(r, "docker-compose.dev").is_file():
        return NA, "no dev stack"
    # Raw text: uncommented() would blank the recipe's shebang line and the
    # body regex, which needs an indented first line, would see no recipe.
    m = re.search(r"^health[^\n]*:\n((?:[ \t]+[^\n]*\n?)+)", jf.read_text(), re.M)
    if not m:
        return NA, "no health recipe"
    body = "\n".join(l for l in m.group(1).splitlines() if not l.lstrip().startswith("#"))
    return (PASS, "") if re.search(r'\.status|"ok"', body) else (FAIL, "checks HTTP code only")


@check("REL-01")
def _(r):
    hits = tracked(r, "CHANGELOG*", "changelog*", "VERSION", "VERSION.*", "version.md")
    return (FAIL, ", ".join(hits)) if hits else (PASS, "")


# Which extension a repo needs, by what it runs. One row per tool; the
# predicate is the same signal the hooks/CI checks already use.
_IDE_FLOOR = (
    (lambda r, pc: True, "johnpapa.vscode-cloak"),
    (lambda r, pc: True, "redhat.vscode-yaml"),
    (lambda r, pc: has_go(r), "golang.go"),
    (lambda r, pc: has_node(r), "dbaeumer.vscode-eslint"),
    (lambda r, pc: "tailwindcss" in _npm_versions(r), "bradlc.vscode-tailwindcss"),
    (lambda r, pc: (r / "schema" / "buf.yaml").is_file(), "bufbuild.vscode-buf"),
    (lambda r, pc: _ships_image(r), "ms-azuretools.vscode-containers"),
    (lambda r, pc: "hadolint" in pc, "exiasr.hadolint"),
    (lambda r, pc: "shellcheck" in pc or (r / "dev.sh").is_file() or (r / ".claude" / "hooks").is_dir(),
     "timonwong.shellcheck"),
    (lambda r, pc: "markdownlint" in pc, "davidanson.vscode-markdownlint"),
    (lambda r, pc: bool(workflows(r)), "github.vscode-github-actions"),
    (lambda r, pc: (r / "Justfile").is_file(), "skellock.just"),
    (lambda r, pc: "ruff" in pc or has_python(r), "ms-python.python"),
    (lambda r, pc: "ruff" in pc or has_python(r), "charliermarsh.ruff"),
)


@check("IDE-01")
def _(r):
    f = r / ".vscode" / "extensions.json"
    if not tracked(r, ".vscode/extensions.json"):
        gi = (r / ".gitignore").read_text() if (r / ".gitignore").is_file() else ""
        why = "; .gitignore excludes the .vscode/ directory" if re.search(r"^\.vscode/?\s*$", gi, re.M) else ""
        return FAIL, "no tracked .vscode/extensions.json" + why
    try:
        recs = set(_json_file(f).get("recommendations", []))
    except (json.JSONDecodeError, OSError, AttributeError) as e:
        return FAIL, f"extensions.json: {e}"
    pc = uncommented(precommit(r))
    if "prettier" not in pc and "esbenp.prettier-vscode" in recs:
        return FAIL, "recommends prettier, which no hook runs here"
    missing = sorted({ext for pred, ext in _IDE_FLOOR if pred(r, pc)} - recs)
    return (FAIL, "missing " + " ".join(missing)) if missing else (PASS, "")


def _fleet_section(text):
    i = text.find("\n## Fleet\n")
    if i < 0:
        return None
    j = text.find("\n## ", i + 1)
    return text[i + 1:] if j < 0 else text[i + 1:j]


@check("VNDR-02")
def _(r):
    doc = r / "AGENTS.md" if (r / "AGENTS.md").is_file() else r / "CLAUDE.md"
    return _matches_reference(doc, _PLUGIN_ASSETS / "fleet" / "agents-md-fleet-section.md", _fleet_section)


def _register_file(base, name):
    """One register file as a mapping, or {} when absent. Every malformed
    shape exits naming the FILE: these are edited by hand in a private
    checkout the engine reads at a computed path, and a bare traceback does
    not say which of the four files was at fault."""
    f = base / name
    if not f.is_file():
        return {}
    try:
        doc = yaml.safe_load(f.read_text())
    except yaml.YAMLError as e:
        sys.exit(f"{f}: not valid YAML: {e}")
    if doc is None:
        return {}
    if not isinstance(doc, dict):
        sys.exit(f"{f}: top level must be a mapping with `controls:` or `checks:`")
    for key in ("controls", "checks"):
        recs = doc.get(key)
        if recs is None:
            continue
        if not isinstance(recs, list):
            sys.exit(f"{f}: `{key}:` must be a list")
        ids = []
        for i, r in enumerate(recs, 1):
            if not isinstance(r, dict) or not r.get("id"):
                sys.exit(f"{f}: {key} record #{i} is not a mapping with an id")
            ids.append(r["id"])
        dup = sorted({x for x in ids if ids.count(x) > 1})
        if dup:
            sys.exit(f"{f}: duplicate {key} id(s): {dup} — last-wins would hide one silently")
    return doc


def load_register():
    """(controls by id, checks): the baseline merged with the fleet's overlay
    by id — an overlay record's fields replace the baseline record's, and an
    overlay record with a new id is added. Referential integrity holds on
    the merged result: a check naming an unknown control is a broken row; a
    control no check tests is an objective nothing verifies — the GATE-01
    failure, one level up."""
    base_c = _register_file(BASELINE, "CONTROLS.yaml")
    base_k = _register_file(BASELINE, "CHECKS.yaml")
    over_c = _register_file(REGISTER, "CONTROLS.yaml") if REGISTER else {}
    over_k = _register_file(REGISTER, "CHECKS.yaml") if REGISTER else {}
    ctrl = {c["id"]: dict(c) for c in base_c.get("controls") or []}
    for c in over_c.get("controls") or []:
        ctrl.setdefault(c["id"], {}).update(c)
    by_id = {k["id"]: dict(k) for k in base_k.get("checks") or []}
    for k in over_k.get("checks") or []:
        base = by_id.get(k["id"])
        # Re-parenting a baseline check under another control makes --json's
        # `control` lie to whoever groups items by it; say so instead.
        if base and k.get("control") and k["control"] != base.get("control"):
            sys.exit(f"overlay check {k['id']} moves control {base.get('control')} -> {k['control']}; the overlay may add fields, not re-parent")
        by_id.setdefault(k["id"], {}).update(k)
    checks = list(by_id.values())
    # The merged result is what runs, so it is what gets validated: a record
    # missing a field the renderers index would crash AFTER the whole matrix
    # ran; a severity outside the enum would silently never match --fail-on;
    # an overlay id that matches no checker and is not declared manual is a
    # gate that silently does not run — the register's own definition of high.
    sev_ok = {"high", "medium", "low"}
    unimplemented = []
    exampleless = []
    # A rule may not name a repo. `reference:` and `known_violations` are
    # rejected rather than ignored: silently dropping them would leave an
    # overlay author believing an exemption is in force while every repo in it
    # is being audited. Both encoded one fleet on one day inside a rule meant
    # to outlive it, and went stale invisibly when a named repo left the fleet.
    def _no_repo_names(kind, d):
        for f in ("reference", "known_violations"):
            if d.get(f) not in (None, "none", [], ""):
                sys.exit(
                    f"{kind} {d.get('id', '?')}: `{f}` is retired — a check states what "
                    f"consistent means, not who currently passes. Delete the field; who "
                    f"passes is this run's output, derived from the repos FLEET.md lists."
                )
    for c in ctrl.values():
        for f in ("id", "title", "severity", "intent"):
            if not c.get(f):
                sys.exit(f"control {c.get('id', '?')} lacks `{f}`")
        if c["severity"] not in sev_ok:
            sys.exit(f"control {c['id']}: severity {c['severity']!r} is not one of high|medium|low")
        _no_repo_names("control", c)
    for k in checks:
        for f in ("id", "control", "title", "scope"):
            if not k.get(f):
                sys.exit(f"check {k.get('id', '?')} lacks `{f}`")
        if k.get("severity") is not None and k["severity"] not in sev_ok:
            sys.exit(f"check {k['id']}: severity {k['severity']!r} is not one of high|medium|low")
        _no_repo_names("check", k)
        manual = ((k.get("detect") or {}).get("method") == "manual")
        if k["id"] not in CHECKS and not manual:
            unimplemented.append(k["id"])
        # A manual check is verified by a person reading it. With no checker
        # and no exemplar repo to diff against, an `example:` is the only thing
        # left that says what the correct shape IS — prose alone leaves two
        # readers to infer two different rules. Named, not fatal: an overlay
        # written before examples existed still audits, it just says what it
        # is missing every load.
        if manual and not k.get("example"):
            exampleless.append(k["id"])
        want = k.get("applies_to") or "all"
        for n in ([want] if isinstance(want, str) else list(want)):
            n = str(n).lower()
            if GROUP_REPOS and n != "all" and n not in GROUP_REPOS and n not in CAPABILITIES:
                sys.exit(f"check {k['id']}: applies_to names '{n}', which is neither a FLEET.md group ({', '.join(sorted(GROUP_REPOS))}) nor a capability ({', '.join(sorted(CAPABILITIES))})")
    # A check with no checker reports MANUAL by design (a person verifies it),
    # but a check that does not SAY so is indistinguishable from a typo'd
    # overlay id — the gate that silently never runs. Name them every load.
    if unimplemented:
        print(f"load_register: {len(unimplemented)} check(s) have no checker and are not declared "
              f"`detect: method: manual` — reported MANUAL: {', '.join(unimplemented)}", file=sys.stderr)
    if exampleless:
        print(f"load_register: {len(exampleless)} manual check(s) carry no `example:`, so nothing "
              f"states the correct shape: {', '.join(exampleless)}", file=sys.stderr)
    if not ctrl or not checks:
        sys.exit(f"no register: baseline {BASELINE} holds no controls or checks"
                 + (f" and overlay {REGISTER} adds none" if REGISTER else ""))
    orphans = [k["id"] for k in checks if k.get("control") not in ctrl]
    if orphans:
        sys.exit(f"checks with unknown control: {orphans}")
    untested = [c for c in ctrl if not any(k.get("control") == c for k in checks)]
    if untested:
        sys.exit(f"controls with no checks: {untested}")
    order = {c: i for i, c in enumerate(ctrl)}
    checks.sort(key=lambda k: (order.get(k["control"], 99), k["id"]))
    return ctrl, checks


def family_repos():
    return [n for n in FAMILY if (repo_path(n) / ".git").exists()]


def sev_of(check, ctrl):
    """A check's OWN severity, falling back to its control's.

    Both levels carry one and they disagree for roughly a third of the
    checks — by design: C-GATES is high because a gate that does not run is
    a hole, while GATE-03 under it is cosmetic. The check is the thing being
    reported, so the check's severity is the one that describes the row.

    Reading the control's instead made --fail-on high wrong in both
    directions at once — firing on cosmetic checks under a high control and
    silent on high checks under a medium one. Over-firing trains people to
    ignore the gate; under-firing is the hole it exists to close. Keep the
    fallback: a check added without a severity must inherit one, never read
    as unset.
    """
    return check.get("severity") or ctrl[check["control"]]["severity"]


@contextlib.contextmanager
def snapshot_family(ref, repos=()):
    """Audit a detached worktree of `ref` for every family repo and every
    repo in `repos`; the checkout as it sits only when the ref does not
    resolve (a clone with no remote). A worktree that cannot be created is a
    hard error: silently auditing the checkout instead is the drift this
    exists to stop. Family-wide caches live exactly as long as the snapshot."""
    _FLEET.clear()
    snap_root = pathlib.Path(tempfile.mkdtemp(prefix="audit-"))
    try:
        for rn in dict.fromkeys(list(family_repos()) + [x for x in repos if (repo_path(x) / ".git").exists()]):
            REPO_PATH[rn], note = _snapshot(repo_path(rn), ref, snap_root / rn)
            print(f"{rn:<16} {note}", file=sys.stderr)
        print(file=sys.stderr)
        yield
    finally:
        for rn, path in list(REPO_PATH.items()):
            home = REPO_DIR.get(rn, ROOT / rn)
            if path == home:
                continue
            # sh3 raises on a missing cwd; inside this finally that would skip
            # every later repo's removal and leave worktrees behind.
            try:
                rc, _out, err = sh3(home, f"git worktree remove --force {shlex.quote(str(path))}")
                if rc:
                    sh3(home, "git worktree prune")
                    print(f"{rn}: worktree remove failed ({err}); ran `git worktree prune` — "
                          f"check `git -C {home} worktree list`", file=sys.stderr)
            except Exception as e:
                print(f"{rn}: could not remove worktree {path}: {e} — remove it by hand", file=sys.stderr)
        REPO_PATH.clear()
        _FLEET.clear()
        shutil.rmtree(snap_root, ignore_errors=True)


def _snapshot(repo, ref, dest):
    # The worktree's basename must stay the repo name: a dozen checkers
    # dispatch on r.name, and CI-22/PRE-07 key the fleet maps by it.
    rc, sha, _err = sh3(repo, f"git rev-parse --verify -q --short {shlex.quote(ref)}")
    if rc or not sha:
        return repo, f"checkout as-is ({ref} does not resolve)"
    rc, _out, err = sh3(repo, f"git worktree add --detach {shlex.quote(str(dest))} {shlex.quote(ref)}")
    if rc or not (dest / ".git").exists():
        raise RuntimeError(f"{repo.name}: git worktree add failed: {err or f'rc={rc}'}")
    rc, status, _err = sh3(repo, "git status --porcelain --branch")
    lines = status.splitlines() if not rc else []
    branch = lines[0].removeprefix("## ").split("...")[0] if lines else "?"
    dirty = max(len(lines) - 1, 0)
    _rc, lr, _err = sh3(repo, f"git rev-list --left-right --count {shlex.quote(ref)}...HEAD")
    behind, ahead = (lr.split() + ["?", "?"])[:2]
    note = f"{ref} @ {sha}"
    if branch != "main" or dirty or behind != "0" or ahead != "0":
        note += f"  (checkout is on {branch}, {behind} behind / {ahead} ahead, {dirty} dirty)"
    return dest, note


def run_matrix(checks, repos):
    """rows of (check, [(status, detail) per repo]), the FAIL cells, and the
    ERROR cells — a checker that raised. Errors are printed as they happen;
    a broken checker must read as broken, never as PASS or as a by-design
    MANUAL."""
    rows, fails, errors = [], [], []
    for c in checks:
        cells = []
        for rn in repos:
            fn = CHECKS.get(c["id"])
            if not applies(c, rn):
                want = c.get("applies_to")
                cells.append((NA, f"applies_to: {want if isinstance(want, str) else ', '.join(want)}"))
                continue
            if not fn:
                cells.append((MANUAL, ""))
                continue
            try:
                st, detail = fn(repo_path(rn))
                if st not in STATUSES:
                    raise ValueError(f"checker returned status {st!r}")
            except Exception as e:
                st, detail = ERROR, f"{type(e).__name__}: {e}"
                print(f"{c['id']} {rn}: {detail}", file=sys.stderr)
                errors.append((c, rn, detail))
            cells.append((st, detail))
            if st == FAIL:
                fails.append((c, rn, detail))
        rows.append((c, cells))
    return rows, fails, errors


MARK = {PASS: "✅", FAIL: "❌", NA: "–", MANUAL: "?", ERROR: "💥"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append")
    ap.add_argument("--control", action="append")
    ap.add_argument("--md", action="store_true", help="markdown table")
    ap.add_argument("--fail-on", default="", help="comma severities that exit non-zero, e.g. high")
    ap.add_argument("--ref", default="origin/main",
                    help="audit this ref of every repo via a detached worktree (default origin/main)")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="audit the checkouts as they sit, whatever branch or dirt they carry")
    ap.add_argument("--fleet", default="", help="the fleet root (default: found by walking up from cwd)")
    ap.add_argument("--json", action="store_true", help="one JSON object per failing (check x repo) cell, for skills")
    a = ap.parse_args()

    rc = run_at_origin("audit.py")
    if rc is not None:
        sys.exit(rc)
    configure(a.fleet or None)
    # --repo is a FLEET.md ROW NAME inside a fleet. `.` (or a path) resolves the
    # checkout it names to its row, so a skill can say "this repo" without
    # knowing the row — a basename is not the row when a row carries `path:`.
    if a.repo:
        resolved = []
        for x in a.repo:
            if x in REPO_DIR:
                resolved.append(x)
                continue
            p = pathlib.Path(x).resolve() if (x == "." or "/" in x) else None
            hit = next((k for k, v in REPO_DIR.items() if p and v == p), None)
            if hit:
                resolved.append(hit)
            elif REGISTER is not None:
                sys.exit(f"--repo {x}: not a FLEET.md row (rows: {', '.join(REPO_DIR) or 'none'}); pass the row name or `.`")
            else:
                sys.exit(f"--repo {x}: outside a fleet only the current repo ({', '.join(REPO_DIR)}) can be audited")
        a.repo = resolved
    ctrl, checks = load_register()
    if a.control:
        want = set(a.control)
        checks = [k for k in checks if k["id"] in want or k.get("control") in want]
    repos = [x for x in (a.repo or family_repos()) if repo_path(x).is_dir()]
    if not repos:
        sys.exit("no repos to audit: every FLEET.md row is `group: none` or missing on disk"
                 if REGISTER is not None else
                 "no repos to audit: not inside a fleet and not inside a git repo")

    with reference_assets() as assets_note:
        if a.no_snapshot:
            rows, fails, errors = run_matrix(checks, repos)
        else:
            with snapshot_family(a.ref, repos):
                rows, fails, errors = run_matrix(checks, repos)

    w = max(len(r) for r in repos) + 2
    print(f"engine: {engine_note()}\nassets: {assets_note}\n", file=sys.stderr if a.json else sys.stdout)
    if a.json:
        # ERROR cells go out too, flagged: a consumer that only saw FAILs would
        # read a broken checker as a passing one.
        for status, cells in ((FAIL, fails), (ERROR, errors)):
            for c, rn, detail in cells:
                # `example` replaces the old `reference` key: a consumer fixing
                # a finding needed the correct shape, and used to get a repo
                # name to go and read. The shape now travels with the finding.
                print(json.dumps({"status": status, "check": c["id"], "control": c["control"], "repo": rn,
                                  "severity": sev_of(c, ctrl), "title": c["title"],
                                  "example": c.get("example") or None,
                                  "detail": detail, "rule": " ".join((c.get("rule") or "").split())}))
    elif a.md:
        print("| Control | Check | Sev | " + " | ".join(repos) + " |")
        print("| --- | --- | --- | " + " | ".join("---" for _ in repos) + " |")
        for c, cells in rows:
            print(
                f"| {c.get('control','?')} | **{c['id']}** {c['title']} "
                f"({c.get('scope','?')}) | {sev_of(c, ctrl)[0].upper()} | "
                + " | ".join(
                    MARK[s] + (f" {d}" if s in (FAIL, ERROR) and d else "") for s, d in cells
                )
                + " |"
            )
    else:
        print(f"{'CONTROL':<13}{'CHECK':<12} {'SCOPE':<10}{'SEV':<7}"
              + "".join(f"{r:<{w}}" for r in repos))
        print("-" * (42 + w * len(repos)))
        last = None
        for c, cells in rows:
            cid = c["control"]
            shown = cid if cid != last else ""
            last = cid
            print(
                f"{shown:<13}{c['id']:<12} {c.get('scope',''):<10}"
                f"{sev_of(c, ctrl):<7}"
                + "".join(f"{st:<{w}}" for st, _ in cells)
            )

    hi = [f for f in fails if sev_of(f[0], ctrl) == "high"]
    ctrls_touched = {k["control"] for k in checks}
    failing_ctrls = {f[0]["control"] for f in fails}
    # Under --json stdout is one object per line and nothing else; the
    # summary still prints, on stderr, so a consumer parsing stdout never
    # meets prose.
    out = sys.stderr if a.json else sys.stdout
    print(f"\n{len(fails)} failing (check x repo) results ({len(hi)} high) "
          f"across {len(repos)} repos" + (f"; {len(errors)} checker errors" if errors else ""), file=out)
    print(f"{len(checks)} checks under {len(ctrls_touched)} controls; "
          f"{len(failing_ctrls)} controls have at least one failing check", file=out)
    if errors:
        return 2
    if a.fail_on:
        want = set(a.fail_on.split(","))
        if any(sev_of(f[0], ctrl) in want for f in fails):
            return 1
    return 0


# Bind once at import so tests and consistency.py get a usable module; main()
# re-binds, and loads the overlay, once run_at_origin() has picked the engine.
# A broken cwd (unreadable FLEET.md, a mapped
# register that is not cloned) must not sink `--help` or an explicit --fleet,
# so the import-time call swallows the exit and leaves the module unbound.
try:
    configure(load_overlay=False)
except SystemExit as _e:
    print(f"audit: not configured from cwd ({_e}); pass --fleet or run inside a fleet", file=sys.stderr)

if __name__ == "__main__":
    sys.exit(main())
