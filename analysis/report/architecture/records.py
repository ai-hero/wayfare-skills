"""Every version of every repo's design record, re-read from the git mirrors.

`knowledge.doc_versions` has no hiro rows and keeps only counts, so the chapter reads
DESIGN.md (and its predecessor ARCHITECTURE.md) at every default-branch commit that
touched it, and parses sections, the Source ref anchor and each Decisions entry.
"""
import os
import re
import subprocess
from datetime import datetime, timezone
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
MIRRORS = os.path.join(HERE, "..", "..", "..", ".analysis", "data", "mirrors")
RECORD_PATHS = ("DESIGN.md", "ARCHITECTURE.md")
ANCHOR_RE = re.compile(r"Source ref:\s*([0-9a-f]{7,40})")
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*[—–-]+\s*(.*)$")


def utc_day(ts):
    return datetime.fromisoformat(ts).astimezone(timezone.utc).date().isoformat()


def git(repo, *args):
    p = subprocess.run(["git", "-C", os.path.join(MIRRORS, f"{repo}.git"), *args], capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def mirror_repos():
    return sorted(f[:-4] for f in os.listdir(MIRRORS) if f.endswith(".git"))


def norm_heading(h):
    """Decision identity: the heading without its date and without a trailing '(superseded …)' note."""
    m = DATE_RE.match(h.strip())
    t = m.group(2) if m else h
    t = re.sub(r"\((?:superseded|supersedes)[^)]*\)", "", t, flags=re.I)
    t = re.sub(r"[`*_\"'“”]", "", t).lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def norm_body(b):
    return re.sub(r"\s+", " ", re.sub(r"[`*_]", "", b)).strip()


def parse(text):
    lines = text.splitlines()
    sections = [l[3:].strip() for l in lines if l.startswith("## ")]
    anchor = next((m.group(1) for l in lines[:8] for m in [ANCHOR_RE.search(l)] if m), None)
    decisions, cur, in_dec = [], None, False
    for l in lines:
        if l.startswith("## "):
            in_dec = l[3:].strip().lower().startswith("decision")
            cur = None
            continue
        if in_dec and l.startswith("### "):
            h = l[4:].strip()
            m = DATE_RE.match(h)
            cur = {"heading": h, "key": norm_heading(h), "date": m.group(1) if m else None, "body": []}
            decisions.append(cur)
        elif cur is not None:
            cur["body"].append(l)
    for d in decisions:
        d["body"] = "\n".join(d["body"]).strip()
        d["norm"] = norm_body(d["body"])
    return {"sections": sections, "anchor": anchor, "decisions": decisions, "lines": len(lines)}


@lru_cache(maxsize=None)
def versions(repo):
    """Default-branch versions of the record, oldest first: {sha, ts, day, path, text, parsed}."""
    out = []
    log = git(repo, "log", "--first-parent", "--format=%x01%H\t%cI", "--name-status", "HEAD", "--", *RECORD_PATHS)
    if not log:
        return out
    for chunk in reversed(log.split("\x01")):
        chunk = chunk.strip()
        if not chunk:
            continue
        head, *files = chunk.splitlines()
        sha, ts = head.split("\t")
        present = [p for p in RECORD_PATHS if git(repo, "cat-file", "-e", f"{sha}:{p}") is not None]
        path = present[0] if present else None
        text = git(repo, "show", f"{sha}:{path}") if path else None
        out.append({"sha": sha, "ts": ts, "day": utc_day(ts), "path": path, "text": text,
                    "parsed": parse(text) if text else None})
    return out


@lru_cache(maxsize=None)
def main_commits(repo):
    """[(sha, day)] first-parent history, oldest first."""
    log = git(repo, "log", "--first-parent", "--format=%H %cI", "HEAD") or ""
    return [(l.split()[0], utc_day(l.split()[1])) for l in reversed(log.splitlines()) if l.strip()]


@lru_cache(maxsize=None)
def commit_day(repo, sha):
    """Committer day of any commit the mirror holds, or None if it does not resolve."""
    out = git(repo, "log", "-1", "--format=%cI", sha)
    return utc_day(out.strip()) if out and out.strip() else None


def head_text(repo, path):
    return git(repo, "show", f"HEAD:{path}")


@lru_cache(maxsize=None)
def file_versions(repo, path):
    """[(sha, day, text)] first-parent versions of any file, oldest first (text None when deleted)."""
    log = git(repo, "log", "--first-parent", "--format=%H %cI", "HEAD", "--", path) or ""
    out = []
    for l in reversed(log.splitlines()):
        if l.strip():
            sha, ts = l.split()
            out.append((sha, utc_day(ts), git(repo, "show", f"{sha}:{path}")))
    return out
