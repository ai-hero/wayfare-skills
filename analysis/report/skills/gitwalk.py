# Exit 1 (git grep: no match) and 128 (path absent at that revision) read as empty; a missing mirror or
# ref must not, or a broken checkout reports as a repo with nothing in it.
GIT_BROKEN = ("not a git repository", "cannot change to", "unknown revision", "bad object")


"""Read-only snapshots of a git checkout: the tree on a given day, and blob contents.

Only `rev-list`, `ls-tree`, `cat-file` and `log` are run; nothing checks out, fetches or writes.
"""
import os
import subprocess
from datetime import date, timedelta
from functools import lru_cache

PLUGIN = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
FLEET = os.path.expanduser(os.environ.get("WAYFARE_FLEET_ROOT", "~/workspaces/aihero"))


def git(repo, *args):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=False)
    if p.returncode not in (0, 1, 128) or any(s in p.stderr for s in GIT_BROKEN):
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {p.stderr.strip()}")
    return p.stdout


def repo_path(name):
    return PLUGIN if name in ("wayfare-skills", "hero-skills") else os.path.join(FLEET, name)


def week_end(week):
    y, w = int(week[:4]), int(week[6:])
    return date.fromisocalendar(y, w, 7)


@lru_cache(maxsize=None)
def sha_at(repo, day):
    """Last first-parent commit on HEAD dated on or before `day` (ISO date), or None."""
    nxt = (date.fromisoformat(day) + timedelta(1)).isoformat()
    out = git(repo, "rev-list", "-1", "--first-parent", f"--before={nxt}T00:00:00", "HEAD").strip()
    return out or None


@lru_cache(maxsize=None)
def tree(repo, sha):
    """{path: blob id} at a commit."""
    out = {}
    for line in git(repo, "ls-tree", "-r", sha).splitlines():
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if parts[1] == "blob":
            out[path] = parts[2]
    return out


_BLOBS = {}


def blobs(repo, ids):
    """{blob id: text} for many blobs, cached across calls."""
    want = [i for i in dict.fromkeys(ids) if (repo, i) not in _BLOBS]
    if want:
        p = subprocess.run(["git", "-C", repo, "cat-file", "--batch"], input="\n".join(want).encode() + b"\n",
                           capture_output=True, check=False)
        data, pos = p.stdout, 0
        for i in want:
            nl = data.index(b"\n", pos)
            head = data[pos:nl].split()
            if len(head) < 3:
                _BLOBS[(repo, i)] = ""
                pos = nl + 1
                continue
            size = int(head[2])
            _BLOBS[(repo, i)] = data[nl + 1:nl + 1 + size].decode("utf-8", "replace")
            pos = nl + 1 + size + 1
    return {i: _BLOBS[(repo, i)] for i in ids}


def blame_origins(repo, sha, paths_prefix=("skills/", "references/", "docs/", "scripts/", ".github/", "assets/")):
    """{origin commit sha: lines} for the lines `sha` removed or rewrote, blamed in its first parent.

    Pure additions blame nothing, so a fix that only adds a guard has no traceable origin.
    """
    import re
    diff = git(repo, "diff", "-U0", "--no-color", f"{sha}^1", sha)
    out, path = {}, None
    for line in diff.splitlines():
        if line.startswith("--- "):
            path = line[6:] if line.startswith("--- a/") else None
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+", line)
        if m and path and path.startswith(paths_prefix):
            start, n = int(m.group(1)), int(m.group(2) or 1)
            if n == 0:
                continue
            b = git(repo, "blame", "--porcelain", "-L", f"{start},{start + n - 1}", f"{sha}^1", "--", path)
            for bl in b.splitlines():
                mm = re.match(r"([0-9a-f]{40}) \d+ \d+", bl)
                if mm:
                    out[mm.group(1)] = out.get(mm.group(1), 0) + 1
    return out


def file_history(repo, path_glob):
    """[(sha, iso day, subject)] of first-parent commits touching the paths, oldest first."""
    out = git(repo, "log", "--first-parent", "--reverse", "--format=%H\t%cs\t%s", "--", path_glob)
    return [tuple(l.split("\t", 2)) for l in out.splitlines() if l.count("\t") >= 2]
