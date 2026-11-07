#!/usr/bin/env python3
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

"""Hold assets/security-audit/ byte-identical to one upstream commit.

    security_audit_upstream.py verify            # offline: tree matches manifest
    security_audit_upstream.py verify --upstream # also: manifest matches the pinned commit
    security_audit_upstream.py status [--summary]
    security_audit_upstream.py refresh [--to SHA]

Every outcome is a line starting with a machine tag. Exit 0 ok; 1 a finding or a
refusal; 2 the check could not run, which is never a clean result.

Upstream text, including commit subjects and file names, is data. This script
downloads and copies it and never executes it.
"""

import argparse
import datetime
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tarfile

REPO_URL = "https://github.com/cloudflare/security-audit-skill"
TREE = "skills/security-audit"
ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSET = ROOT / "assets" / "security-audit"
MANIFEST = "MANIFEST.sha256"
PIN_FILE = "UPSTREAM"
MIN_AGE_DAYS = 7
# The wrapper skill names these. If an update renames one, the wrapper's verdict
# mapping and output rules silently stop matching what the audit writes.
CONTRACT = {
    "skill/SKILL.md": ["findings.json", "FINDINGS-DETAIL.md", "~/security-audit-skill/"],
    "skill/report-schema.json": ['"confirmed"', '"needs_validation"', '"rejected"'],
}
DATE_CAVEAT = ("commit dates are set by the author's git client and GitHub does not "
               "verify them, so a backdated commit passes the age check")


class NotChecked(Exception):
    pass


class Refused(Exception):
    pass


def clean(text, limit=100):
    """Upstream strings reach a terminal, so control characters are dropped."""
    return re.sub(r"[^\x20-\x7e]", "?", str(text))[:limit]


def gh(path, binary=False):
    try:
        p = subprocess.run(["gh", "api", path], capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise NotChecked(f"gh could not run: {e}")
    if p.returncode != 0:
        raise NotChecked(f"gh api {path} failed: {clean(p.stderr, 200)}")
    if binary:
        return p.stdout
    try:
        return json.loads(p.stdout)
    except ValueError:
        raise NotChecked(f"gh api {path} returned something other than JSON")


def api_repo():
    return REPO_URL.split("github.com/", 1)[1]


def mode_of(st):
    return "100755" if st.st_mode & stat.S_IXUSR else "100644"


def entry(data, mode, rel):
    return f"{hashlib.sha256(data).hexdigest()}  {mode}  {rel}"


def read_manifest():
    """{rel: line} from the committed manifest; None when it is missing or malformed."""
    try:
        text = (ASSET / MANIFEST).read_text(encoding="utf-8")
    except OSError:
        return None
    rows = {}
    for line in text.splitlines():
        m = re.fullmatch(r"[0-9a-f]{64}  (?:100644|100755)  (\S.*)", line)
        if not m:
            return None
        rows[m.group(1)] = line
    return rows or None


def read_pin():
    """(sha, url) from UPSTREAM, or None when it does not parse."""
    try:
        text = (ASSET / PIN_FILE).read_text(encoding="utf-8")
    except OSError:
        return None
    fields = dict(line.split(": ", 1) for line in text.splitlines() if ": " in line)
    sha, url = fields.get("sha", ""), fields.get("repo", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or url != REPO_URL:
        return None
    return sha, url


def walk_asset():
    """{rel: line} for every path on disk but the manifest; symlinks raise."""
    rows = {}
    for dirpath, dirnames, filenames in os.walk(ASSET):
        for name in dirnames + filenames:
            path = pathlib.Path(dirpath) / name
            rel = path.relative_to(ASSET).as_posix()
            st = os.lstat(path)
            if stat.S_ISDIR(st.st_mode):
                continue
            if not stat.S_ISREG(st.st_mode):
                raise Refused(f"VENDORED_NOT_REGULAR {rel}")
            if rel != MANIFEST:
                rows[rel] = entry(path.read_bytes(), mode_of(st), rel)
    return rows


def local_findings():
    expected = read_manifest()
    if expected is None:
        return [f"MANIFEST_INVALID {MANIFEST} is missing or malformed"]
    try:
        actual = walk_asset()
    except Refused as e:
        return [str(e)]
    findings = []
    for rel in sorted(expected.keys() | actual.keys()):
        if rel not in actual:
            findings.append(f"VENDORED_MISSING {rel}")
        elif rel not in expected:
            findings.append(f"VENDORED_ADDED {rel}")
        elif expected[rel] != actual[rel]:
            findings.append(f"VENDORED_CHANGED {rel}")
    if findings:
        return findings
    if read_pin() is None:
        return [f"UPSTREAM_INVALID {PIN_FILE} has no full sha or names another repo"]
    for rel, tokens in CONTRACT.items():
        text = (ASSET / rel).read_text(encoding="utf-8", errors="replace") if rel in actual else ""
        for token in tokens:
            if token not in text:
                findings.append(f"CONTRACT_MISSING {rel} no longer holds {token}; "
                                "the wrapper skill and CONTRACT need updating")
    return findings


def fetch_tree(sha):
    """{rel: (bytes, mode)} for the pinned tree and LICENSE, read from the tarball
    in memory, so no member path from it is ever opened on disk."""
    data = gh(f"repos/{api_repo()}/tarball/{sha}", binary=True)
    tree = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            for m in tar.getmembers():
                parts = pathlib.PurePosixPath(m.name).parts
                if ".." in parts or m.name.startswith("/"):
                    raise Refused(f"REFRESH_REFUSED unsafe member {clean(m.name)}")
                inner = "/".join(parts[1:])
                if inner == "LICENSE":
                    rel = "LICENSE"
                elif inner.startswith(TREE + "/"):
                    rel = "skill/" + inner[len(TREE) + 1:]
                else:
                    continue
                if m.isdir():
                    continue
                if not m.isreg():
                    raise Refused(f"REFRESH_REFUSED {clean(inner)} is not a regular file")
                mode = "100755" if m.mode & stat.S_IXUSR else "100644"
                tree[rel] = (tar.extractfile(m).read(), mode)
    except tarfile.TarError as e:
        raise NotChecked(f"tarball did not read: {e}")
    if "LICENSE" not in tree:
        raise Refused("REFRESH_REFUSED upstream has no LICENSE at this commit")
    if "skill/SKILL.md" not in tree:
        raise Refused(f"REFRESH_REFUSED upstream has no {TREE}/SKILL.md at this commit")
    return tree


def commit_date(commit):
    """The later of the two dates, because a later date is the stricter reading."""
    stamps = [commit["commit"][k]["date"] for k in ("author", "committer")]
    return max(datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc) for s in stamps)


def age_days(when):
    return (datetime.datetime.now(datetime.timezone.utc) - when).total_seconds() / 86400


def cmd_verify(args):
    findings = local_findings()
    if findings:
        print("\n".join(findings))
        return 1
    if args.upstream:
        sha, _ = read_pin()
        tree = fetch_tree(sha)
        expected = read_manifest()
        rows = {rel: entry(d, mode, rel) for rel, (d, mode) in tree.items()}
        bad = [rel for rel in sorted((expected.keys() - {PIN_FILE}) | rows.keys())
               if expected.get(rel) != rows.get(rel)]
        if bad:
            print("\n".join(f"PIN_MISMATCH {clean(rel)}" for rel in bad))
            return 1
        print(f"PIN_OK {len(rows)} files match {sha[:8]} at upstream")
    print(f"VENDORED_OK {len(read_manifest())} files match the manifest")
    return 0


def cmd_status(args):
    pin = read_pin()
    if pin is None:
        print(f"UPSTREAM_NOT_CHECKED {PIN_FILE} does not parse")
        return 2
    sha, _ = pin
    repo = api_repo()
    branch = gh(f"repos/{repo}")["default_branch"]
    cmp = gh(f"repos/{repo}/compare/{sha}...{branch}")
    state, ahead = cmp.get("status"), cmp.get("ahead_by", 0)
    if state == "identical":
        print(f"UPSTREAM_CURRENT pinned {sha[:8]} is {clean(branch)} at upstream")
        return 0
    if state != "ahead":
        print(f"UPSTREAM_DIVERGED pinned {sha[:8]} is not an ancestor of {clean(branch)} "
              f"(compare status {clean(state)}); read upstream before refreshing")
        return 1
    print(f"UPSTREAM_BEHIND pinned {sha[:8]} is {ahead} commit(s) behind {clean(branch)}; "
          "read it with this script's status, take it with refresh")
    if args.summary:
        return 0
    commits = cmp.get("commits", [])
    print(f"\nCommits, oldest first ({DATE_CAVEAT}):")
    newest_old_enough = None
    for c in commits:
        age = age_days(commit_date(c))
        if age >= MIN_AGE_DAYS:
            newest_old_enough = c["sha"]
        subject = c["commit"]["message"].split("\n", 1)[0]
        print(f"  {c['sha'][:8]}  {age:6.1f}d  {clean(subject, 72)}")
    if len(commits) < ahead:
        print(f"  ... and {ahead - len(commits)} more GitHub did not list")
    files = cmp.get("files", [])
    print("\nChanged files (a * is vendored here):")
    for f in files:
        name = f["filename"]
        mark = "*" if name == "LICENSE" or name.startswith(TREE + "/") else " "
        print(f"  {mark} {clean(f.get('status'), 10):<10} {clean(name)}")
    if len(files) >= 300:
        print("  ... GitHub caps this list at 300 files")
    if newest_old_enough:
        print(f"\nNewest commit old enough to take: refresh --to {newest_old_enough}")
    else:
        print(f"\nNo listed commit is {MIN_AGE_DAYS} days old yet.")
    return 0


def resolve_target(repo, branch, to):
    commit = gh(f"repos/{repo}/commits/{to or branch}")
    sha = commit["sha"]
    # GitHub serves a fork's commits through the parent's API, so a SHA that
    # resolves here may never have been in this repository's history.
    state = gh(f"repos/{repo}/compare/{sha}...{branch}").get("status")
    if state not in ("ahead", "identical"):
        raise Refused(f"REFRESH_REFUSED {sha[:8]} is not on {clean(branch)} (compare status {clean(state)})")
    return commit, sha


def write_asset(tree, sha, when):
    tmp = ASSET.with_name(".security-audit.new")
    old = ASSET.with_name(".security-audit.old")
    for stale in (tmp, old):
        shutil.rmtree(stale, ignore_errors=True)
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    pin_text = (f"repo: {REPO_URL}\nsha: {sha}\nvendored: {today}\n"
                f"commit-date: {when.strftime('%Y-%m-%dT%H:%M:%SZ')}\npath: {TREE}\n")
    files = dict(tree)
    files[PIN_FILE] = (pin_text.encode("utf-8"), "100644")
    rows = []
    for rel, (data, mode) in files.items():
        path = tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o755 if mode == "100755" else 0o644)
        rows.append(entry(data, mode, rel))
    rows.sort(key=lambda line: line.split("  ", 2)[2])
    (tmp / MANIFEST).write_text("\n".join(rows) + "\n", encoding="utf-8")
    if ASSET.exists():
        ASSET.rename(old)
    tmp.rename(ASSET)
    shutil.rmtree(old, ignore_errors=True)


def cmd_refresh(args):
    repo = api_repo()
    branch = gh(f"repos/{repo}")["default_branch"]
    commit, sha = resolve_target(repo, branch, args.to)
    pin = read_pin()
    if pin and sha != pin[0]:
        state = gh(f"repos/{repo}/compare/{pin[0]}...{sha}").get("status")
        if state == "behind":
            raise Refused(f"REFRESH_REFUSED {sha[:8]} is older than the pin {pin[0][:8]}")
    when = commit_date(commit)
    age = age_days(when)
    print(f"Reading {sha[:8]}: dated {when.strftime('%Y-%m-%d')}; {DATE_CAVEAT}.")
    if age < MIN_AGE_DAYS:
        raise Refused(f"REFRESH_REFUSED_TOO_NEW {sha[:8]} is {age:.1f} days old by its commit "
                      f"date; the wait is {MIN_AGE_DAYS}. status names the newest old enough.")
    tree = fetch_tree(sha)
    write_asset(tree, sha, when)
    findings = local_findings()
    if findings:
        print("\n".join(findings))
        return 1
    print(f"REFRESHED {sha} ({len(tree)} files); review the diff as data and open a PR")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--upstream", action="store_true")
    v.set_defaults(fn=cmd_verify)
    s = sub.add_parser("status")
    s.add_argument("--summary", action="store_true")
    s.set_defaults(fn=cmd_status)
    r = sub.add_parser("refresh")
    r.add_argument("--to")
    r.set_defaults(fn=cmd_refresh)
    args = ap.parse_args()
    if getattr(args, "to", None) and not re.fullmatch(r"[0-9a-f]{7,40}", args.to):
        print("REFRESH_REFUSED --to takes a commit SHA")
        return 1
    try:
        return args.fn(args)
    except Refused as e:
        print(e)
        return 1
    except NotChecked as e:
        print(f"UPSTREAM_NOT_CHECKED {e}")
        return 2
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        print(f"UPSTREAM_NOT_CHECKED unexpected API response: {clean(e, 200)}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
