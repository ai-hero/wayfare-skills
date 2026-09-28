"""The compliance register's own history, read from git (read-only) in the checkouts.

The ingest sees the register only from 13 Sep. Before that it lived in hero-template, and
every audit committed a generated CONSISTENCY.md: a check x repo matrix plus a "Was broken
in" column (the repos failing a check when it was written). Those committed files are the
audit series this chapter is built on:

    hero-template  CONTROLS.yaml / CHECKS.yaml / CONSISTENCY.md   17 Jul - 13 Sep
    .fleet         the same three files (local repo, no remote)    13 Sep - now
    wayfare-skills assets/compliance/ (the plugin baseline)        13 Sep - now
    clones         their own CONTROLS.yaml copy, frozen at clone time
"""
import os
import re
import subprocess
from functools import lru_cache

FLEET = os.path.expanduser(os.environ.get("WAYFARE_FLEET_ROOT", "~/workspaces/aihero"))
SKILLS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Column headers in CONSISTENCY.md, short names before 13 Sep.
SHORT = {"template": "hero-template", "design-sys": "design-system", "wayfare": "aihero-wayfare",
         "elevate": "elevate-commons", "skills": "wayfare-skills", "hero-skills": "wayfare-skills"}
REPO_DIRS = {"wayfare-skills": SKILLS}
MARKS = {"✅": "pass", "❌": "fail", "–": "na", "?": "manual"}


def repo_dir(repo):
    return REPO_DIRS.get(repo, os.path.join(FLEET, repo))


# Exit 1 (git grep: no match) and 128 (path absent at that revision) read as empty; a missing mirror or
# ref must not, or a broken checkout reports as a repo with nothing in it.
GIT_BROKEN = ("not a git repository", "cannot change to", "unknown revision", "bad object")


def git(repo_path, *args):
    p = subprocess.run(["git", "-C", repo_path, *args], capture_output=True, text=True)
    if p.returncode not in (0, 1, 128) or any(s in p.stderr for s in GIT_BROKEN):
        raise RuntimeError(f"git {' '.join(args)} in {repo_path}: {p.stderr.strip()}")
    return p.stdout if p.returncode == 0 else ""


def norm_repo(name):
    name = name.strip()
    return SHORT.get(name, name)


@lru_cache(maxsize=None)
def file_versions(path_in_repo, where):
    """[(sha, iso ts, subject, author, has_claude_trailer, text)] oldest first; empty text if the file was deleted."""
    out = []
    log = git(where, "log", "--reverse", "--format=%H%x1f%aI%x1f%s%x1f%an%x1f%b%x1e", "--", path_in_repo)
    for rec in log.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, ts, subj, author, body = (rec.split("\x1f") + [""] * 5)[:5]
        text = git(where, "show", f"{sha}:{path_in_repo}")
        out.append((sha, ts, subj, author, "Co-Authored-By: Claude" in body, text))
    return out


def ids(text):
    return re.findall(r"^- id:\s*(\S+)", text, re.M)


def yaml_blocks(text):
    """id -> the raw text of its '- id:' block (enough for severity, why, detect method)."""
    parts = re.split(r"(?m)^(?=- id:)", text)
    out = {}
    for p in parts:
        m = re.match(r"- id:\s*(\S+)", p)
        if m:
            out[m.group(1)] = p
    return out


def field(block, name):
    m = re.search(rf"(?m)^  {name}:\s*(.*)$", block)
    if not m:
        return None
    v = m.group(1).strip()
    if v in (">", "|", ">-", "|-"):
        lines = []
        for ln in block[m.end():].split("\n")[1:]:
            if ln.startswith("    ") or not ln.strip():
                lines.append(ln.strip())
            else:
                break
        v = " ".join(l for l in lines if l).strip()
    return v


def parse_consistency(text):
    """{'repos': [...], 'rows': [{check, control, severity, title, broken_in: set|None, cells: {repo: mark}}],
        'header': (fixed, failing, checks, controls)}"""
    repos, rows, control, sev = [], [], None, None
    has_was = False
    for ln in text.splitlines():
        m = re.match(r"^## (C-[A-Z0-9-]+)\s+—\s+.*\*\((\w+)\)\*", ln)
        if m:
            control, sev = m.group(1), m.group(2)
            continue
        if ln.startswith("| Check"):
            cols = [c.strip() for c in ln.strip("|").split("|")]
            has_was = cols[1] == "Was broken in"
            repos = [norm_repo(c) for c in cols[(2 if has_was else 1):-1]]
            continue
        m = re.match(r"^\| \*\*([A-Z0-9]+-[0-9A-Z]+)\*\*", ln)
        if m and repos:
            cols = [c.strip() for c in ln.strip().strip("|").split("|")]
            was = None
            if has_was:
                w = cols[1]
                was = (None if "not recorded" in w else set() if "none" in w else
                       {norm_repo(x) for x in w.split(",") if x.strip()})
                cells = cols[2:2 + len(repos)]
            else:
                cells = cols[1:1 + len(repos)]
            rows.append({"check": m.group(1), "control": control, "severity": sev, "broken_in": was,
                         "cells": {r: MARKS.get(c, c) for r, c in zip(repos, cells)}})
    h = re.search(r"\*\*(\d+) \(check × repo\) results (fixed|failing)\.(?: (\d+) still failing\.)?\*\* (\d+) checks under (\d+) controls", text)
    header = None
    if h:
        fixed = int(h.group(1)) if h.group(2) == "fixed" else None
        failing = int(h.group(3)) if h.group(2) == "fixed" else int(h.group(1))
        header = (fixed, failing, int(h.group(4)), int(h.group(5)))
    return {"repos": list(dict.fromkeys(r for row in rows for r in row["cells"])), "rows": rows, "header": header}


@lru_cache(maxsize=None)
def audits():
    """Every committed CONSISTENCY.md, oldest first: dict(sha, ts, day, where, subject, **parsed)."""
    out = []
    for where, path in (("hero-template", os.path.join(FLEET, "hero-template")), (".fleet", os.path.join(FLEET, ".fleet"))):
        for sha, ts, subj, author, claude, text in file_versions("CONSISTENCY.md", path):
            if not text.strip():
                continue
            p = parse_consistency(text)
            if not p["rows"]:
                continue
            out.append({"sha": sha[:7], "ts": ts, "day": ts[:10], "where": where, "subject": subj, **p})
    out.sort(key=lambda a: a["ts"])
    return out


@lru_cache(maxsize=None)
def register_versions():
    """Every version of the canonical register: (day, where, sha, subject, author, claude, n_controls, n_checks, blocks)."""
    out = []
    for where, path in (("hero-template", os.path.join(FLEET, "hero-template")), (".fleet", os.path.join(FLEET, ".fleet"))):
        ctl = {sha: (ts, s, a, c, t) for sha, ts, s, a, c, t in file_versions("CONTROLS.yaml", path)}
        chk = {sha: (ts, s, a, c, t) for sha, ts, s, a, c, t in file_versions("CHECKS.yaml", path)}
        shas = sorted(set(ctl) | set(chk), key=lambda s: (ctl.get(s) or chk.get(s))[0])
        last_ctl = last_chk = ""
        for sha in shas:
            ts, subj, author, claude, _ = ctl.get(sha) or chk.get(sha)
            if sha in ctl:
                last_ctl = ctl[sha][4]
            if sha in chk:
                last_chk = chk[sha][4]
            if not last_ctl.strip() or not last_chk.strip():
                continue
            out.append({"ts": ts, "day": ts[:10], "where": where, "sha": sha[:7], "subject": subj, "author": author,
                        "claude": claude, "controls": yaml_blocks(last_ctl), "checks": yaml_blocks(last_chk),
                        "touched": ("CONTROLS" if sha in ctl else "") + ("CHECKS" if sha in chk else "")})
    out.sort(key=lambda v: v["ts"])
    return out


# Clones that carried a copy of the register (found by `git log -- CONTROLS.yaml` in each checkout).
COPY_REPOS = ["aihero-wayfare", "elevate-commons", "ah-cozy", "aihero-dokyu", "aihero-mehr", "aihero-steadfast"]


@lru_cache(maxsize=None)
def copies():
    """{repo: [(day, sha, subject, set(control ids) or None when removed)]}"""
    out = {}
    for repo in COPY_REPOS:
        vs = []
        for sha, ts, subj, author, claude, text in file_versions("CONTROLS.yaml", repo_dir(repo)):
            vs.append((ts[:10], sha[:7], subj, set(ids(text)) if text.strip() else None))
        out[repo] = vs
    return out
