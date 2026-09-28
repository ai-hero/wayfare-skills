"""Every name a wayfare skill has had, mapped to the skill that carries its job today.

Built by hand from `git log -M --name-status -- 'skills/*/SKILL.md'` and the commit
messages of the three renaming waves (#9 on 5 May, #16 on 5 Jul, #106 on 22 Sep) and the
merges in between. A skill whose job was folded into another maps to the one that
absorbed it (commit-changes → push-pr), so usage stays continuous across renames.
"""

CURRENT = {
    # push: commit, branch, test and CI status were all folded into push-pr (#16, #36)
    "wayfare-push-pr": ["hero-push", "push", "push-pr", "hero-commit", "commit", "commit-changes",
                        "hero-branch", "branch", "create-branch", "hero-test", "test", "test-changes",
                        "smoke-ui", "hero-cicd", "hero-health", "check", "check-ci", "hero-pr-create"],
    "wayfare-ship-pr": ["hero-auto-approve", "ship", "ship-pr"],
    "wayfare-review-pr": ["hero-pr-review", "hero-review-pr", "hero-self-review", "review", "review-pr"],
    "wayfare-respond-pr": ["hero-pr-respond", "hero-respond-to-pr", "respond", "respond-to-pr",
                           "respond-to-comments", "hero-pr-resolve"],
    "wayfare-build-task": ["one-shot", "wayfare-run-task", "hero-plan", "plan", "plan-work", "hero-implement"],
    "wayfare-drop-item": ["hero-reset", "reset", "reset-branch", "abandon-branch", "abandon"],
    "wayfare-init-repo": ["hero-init", "init-hero", "hero-new", "hero-new-project", "create-project"],
    "wayfare-recalibrate-config": ["hero-update", "hero-reflect"],
    "wayfare-sync-plan": ["wayfare", "wayfare-hero"],
    "wayfare-audit-security": ["hero-secure", "scan", "scan-vulns", "harden"],
    "wayfare-review-architecture": ["hero-architect", "document-arch", "architecture"],
    "wayfare-setup-dev": ["hero-setup", "setup", "setup-dev"],
    "wayfare-audit-plugin": ["hero-meta", "audit", "audit-plugin"],
    "wayfare-create-skill": ["hero-skill", "hero-new-skill", "create-skill", "create"],
    "wayfare-grill-idea": ["relentless", "think-it-through"],
    "wayfare-write-handoff": ["handoff"],
    "wayfare-recomponentize-ui": ["recomponentize-ui"],
    "wayfare-sync-fleet": ["fleet"],
    "wayfare-humanize-prose": ["my-humanizer"],
    "wayfare-check-preflight": ["preflight"],
}
for cur in ["wayfare-advance-item", "wayfare-audit-compliance", "wayfare-review-fleet", "wayfare-start-goal",
            "wayfare-sync-architecture"]:
    CURRENT.setdefault(cur, [])

OLD_TO_CURRENT = {old: cur for cur, olds in CURRENT.items() for old in olds}
OLD_TO_CURRENT.update({cur: cur for cur in CURRENT})

# Families for charts: the pipeline skills separately, the rest grouped.
FAMILY = {
    "wayfare-push-pr": "push-pr", "wayfare-review-pr": "review-pr", "wayfare-ship-pr": "ship-pr",
    "wayfare-respond-pr": "respond-pr", "wayfare-build-task": "build-task (one-shot)",
    "wayfare-sync-plan": "plan & goal verbs", "wayfare-start-goal": "plan & goal verbs",
    "wayfare-advance-item": "plan & goal verbs", "wayfare-grill-idea": "plan & goal verbs",
    "wayfare-drop-item": "plan & goal verbs",
}
FAMILIES = ["push-pr", "review-pr", "ship-pr", "respond-pr", "build-task (one-shot)", "plan & goal verbs", "other"]

# The dates each naming scheme took over (merge day on main).
WAVES = [
    ("2026-05-05", "Verb-object names (#9)"),
    ("2026-07-05", "20 → 15 skills (#16)"),
    ("2026-09-22", "wayfare- prefix (#106)"),
]


def canonical(name):
    """A typed command or Skill-tool name → (current skill, bare name typed), or (None, bare)."""
    if not name:
        return None, None
    n = name.strip().lstrip("/")
    prefix = None
    if ":" in n:
        prefix, n = n.split(":", 1)
        if prefix not in ("hero-skills", "wayfare"):
            return None, n
    # Bare one-word names collide with Claude Code built-ins (/init, /review), so they count
    # only when typed with the plugin prefix.
    if prefix is None and n in SHORT:
        return None, n
    return OLD_TO_CURRENT.get(n), n


SHORT = {"push", "commit", "branch", "test", "check", "plan", "review", "respond", "reset", "scan", "setup",
         "audit", "create", "ship"}


def family(cur):
    return FAMILY.get(cur, "other")


def name_scheme(name):
    """Which naming the typed name belongs to: its current name, or a retired one."""
    cur, bare = canonical(name)
    return None if cur is None else ("current" if bare == cur else "retired")
