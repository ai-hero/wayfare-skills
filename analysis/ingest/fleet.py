"""The fleet, read from FLEET.md, and each repo's generic role (GLOSSARY.md).

Generic across installations, on purpose (this file is committed to the
shared wayfare-skills plugin, not fleet-specific tooling):

- PLUGIN is found the same way every wayfare skill finds its own root
  (CLAUDE_PLUGIN_ROOT, then WAYFARE_ROOT -- see scripts/hero-lib.sh's own
  header comment), not a hardcoded path.
- ROOT is found the same way scripts/hero-lib.sh's hero_fleet_root finds
  it: the nearest ancestor of the current directory holding FLEET.md with
  no sibling HERO.md and outside any git work tree (a repo that committed
  its own FLEET.md is not a fleet folder). WAYFARE_FLEET_ROOT overrides it,
  for a script run from outside any repo.
- Facts FLEET.md/HERO.md don't carry at all -- a baseline before/after
  cutoff date, which repos have no roadmap yet, which app IS the design
  system, role labels finer than a FLEET.md group -- come from
  .analysis/config.json (gitignored, per-installation; WAYFARE_ANALYSIS_CONFIG
  names another file, for a test fixture), not from this file. See analysis/config.example.json for the shape. A fleet with no
  config file just gets empty defaults; every question that reads one of
  these should handle that (e.g. BASELINE_CUTOFF is None, not a guess).
"""
import glob, json, os, re, sys, datetime as dt


def _plugin_root():
    return (os.environ.get("CLAUDE_PLUGIN_ROOT")
            or os.environ.get("WAYFARE_ROOT")
            or os.path.expanduser("~/.claude/plugins/wayfare-skills"))


# Mirrors scripts/audit.py's in_git_worktree rather than importing it:
# importing audit.py runs its configure(), which shells out to git and parses
# FLEET.md at import time.
def _in_git_worktree(d):
    home = os.path.realpath(os.path.expanduser("~"))
    while True:
        if d != home and os.path.exists(os.path.join(d, ".git")):
            return True
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent


def _fleet_root():
    env = os.environ.get("WAYFARE_FLEET_ROOT")
    if env:
        return os.path.abspath(env)
    d = os.path.realpath(os.getcwd())
    while True:
        if os.path.isfile(os.path.join(d, "FLEET.md")) and not os.path.isfile(os.path.join(d, "HERO.md")):
            if not _in_git_worktree(d):
                return d
            print(f"ingest/fleet.py: passing over {d}; a folder inside a git work tree is never a fleet root", file=sys.stderr)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    sys.exit(
        "ingest/fleet.py: no FLEET.md found walking up from the current directory, and "
        "WAYFARE_FLEET_ROOT isn't set. Run analysis scripts from inside the fleet folder "
        "(or a repo beneath it), or export WAYFARE_FLEET_ROOT=/path/to/fleet."
    )


PLUGIN = _plugin_root()
ROOT = _fleet_root()
# analysis/ingest/fleet.py -> repo root's gitignored .analysis/data (large, personal, rebuildable)
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".analysis", "data")

_CONFIG_PATH = os.environ.get("WAYFARE_ANALYSIS_CONFIG") or os.path.join(os.path.dirname(OUT), "config.json")
# A missing default config means empty defaults, but a missing override is a typo: read as empty, it
# would put every repo in APP with no error.
if os.environ.get("WAYFARE_ANALYSIS_CONFIG") and not os.path.isfile(_CONFIG_PATH):
    sys.exit(f"ingest/fleet.py: WAYFARE_ANALYSIS_CONFIG={_CONFIG_PATH} does not exist")


def _load_config():
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    return {}


_config = _load_config()
NO_ROADMAP_YET = set(_config.get("no_roadmap_yet", []))
BASELINE_CUTOFF = _config.get("baseline_cutoff")  # None if unset -- callers must handle that, not assume a date
DESIGN_SYSTEM_REPO = _config.get("design_system_repo")
ROLE_OVERRIDES = _config.get("role_overrides", {})  # e.g. {"auth": "shared service", "website": "product"}
# historical renames (a repo or the plugin itself), for matching old
# ~/.claude/projects/* directory names in transcripts predating the rename
REPO_ALIASES = _config.get("repo_aliases", {})


def _fleet_field(key):
    """A `- key: value` line under FLEET.md's `## Fleet` section (mirrors
    scripts/hero-lib.sh's hero_fleet_field), e.g. `register: .fleet/`."""
    in_section = False
    for line in open(os.path.join(ROOT, "FLEET.md")):
        if re.match(r"^## Fleet\s*$", line):
            in_section = True; continue
        if in_section and re.match(r"^## ", line):
            break
        if in_section:
            m = re.match(rf"^- {re.escape(key)}:\s*(\S+)", line)
            if m:
                return m.group(1).split("#")[0].strip()
    return None


def _groups():
    groups, name = {}, None
    for line in open(os.path.join(ROOT, "FLEET.md")):
        m = re.match(r"### (\S+)", line)
        if m: name = m.group(1); continue
        m = re.match(r"- group: (\w+)", line)
        if m and name: groups[name] = m.group(1)
    return groups


GROUPS = _groups()
FLEET_REPOS = sorted(r for r, g in GROUPS.items() if g in ("template", "apps", "infra") and os.path.isdir(os.path.join(ROOT, r)))
# the design exports are group none, but they are the design-source corner of each product
DESIGN_REPOS = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "*-design")))
PLUGIN_REPO_NAME = os.path.basename(PLUGIN.rstrip(os.sep))
EXTRA_REPOS = [r for r in _config.get("extra_repos", []) if os.path.isdir(os.path.join(ROOT, r))]
OUT_OF_SCOPE = set(_config.get("out_of_scope_repos", []))
ALL_REPOS = FLEET_REPOS + DESIGN_REPOS + [PLUGIN_REPO_NAME] + EXTRA_REPOS

APP = "app"
APP_NO_FEATURES = "app, no features yet"
ALLIED = "allied"
OUT_OF_SCOPE_CATEGORY = "out of scope"
CATEGORIES = (APP, APP_NO_FEATURES, ALLIED, OUT_OF_SCOPE_CATEGORY)
APP_CATEGORIES = (APP, APP_NO_FEATURES)

# The repo with FLEET.md group: template -- None if the fleet has none
# declared (a fleet with no template-and-clones shape, or FLEET.md not yet
# updated). Detectors that need "the template" must handle None, not assume
# a name.
TEMPLATE_REPO = next((r for r, g in GROUPS.items() if g == "template"), None)

# The compliance register overlay's path, from FLEET.md's own `register:`
# field (its README: "FLEET.md names it, so nothing has to guess the path").
# None if the fleet declares no register.
_register_rel = _fleet_field("register")
FLEET_REGISTER = os.path.join(ROOT, _register_rel.rstrip("/")) if _register_rel else None


def path_of(repo): return PLUGIN if repo == PLUGIN_REPO_NAME else os.path.join(ROOT, repo)


def role_of(repo):
    if repo == PLUGIN_REPO_NAME: return "process plugin"
    if repo in DESIGN_REPOS: return "design source"
    if repo == DESIGN_SYSTEM_REPO: return "design system"
    if repo in ROLE_OVERRIDES: return ROLE_OVERRIDES[repo]
    g = GROUPS.get(repo)
    if g == "template": return "template repo"
    if g == "infra": return "infrastructure repo"
    return "clone"


def category_of(repo):
    """APP (what the factory builds), APP_NO_FEATURES (config's no_roadmap_yet), ALLIED (what it
    builds with: the plugin, the template, infrastructure), or OUT_OF_SCOPE_CATEGORY (config's
    out_of_scope_repos), in that reverse order of precedence."""
    if repo in OUT_OF_SCOPE: return OUT_OF_SCOPE_CATEGORY
    if repo == PLUGIN_REPO_NAME or GROUPS.get(repo) in ("template", "infra"): return ALLIED
    if repo in NO_ROADMAP_YET: return APP_NO_FEATURES
    return APP


def dims(ts):
    """ts: datetime or ISO string → the shared time keys."""
    d = ts if isinstance(ts, dt.datetime) else dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
    d = d.astimezone(dt.timezone.utc); y, w, _ = d.isocalendar()
    return {"ts": d.isoformat(), "day": d.date().isoformat(), "week": f"{y}-W{w:02d}", "month": d.strftime("%Y-%m")}


if __name__ == "__main__":
    for r in ALL_REPOS: print(f"{r:32} {role_of(r):20} {os.path.isdir(path_of(r))}")
