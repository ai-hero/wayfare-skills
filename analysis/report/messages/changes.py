"""One change across many repos: commits in different repos grouped into cross-repo changes.

Two commits are the same change when they land the same content at the same path (same
blob id, from messages.sqlite `blobs`, see gitscan.py) or carry the same normalized subject
(detectors/d7_duplicates.normalize) within 14 days. Groups are merged transitively, but a
merge that would stretch a group past 45 days is refused: without that guard, commits that
touch several shared files chain unrelated sweeps into one group spanning months.

Excluded: a repo's first 3 days (a clone copying the template is inheritance, report/compliance's),
commits touching more than 150 files, the empty blob, and subjects under 3 tokens.
"""
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]
from detectors.d7_duplicates import normalize  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE  # noqa: E402

PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
DB = os.path.join(PLUGIN, ".analysis", "data", "messages.sqlite")
LATEST = "2026-09-24"
UPSTREAM = ("wayfare-skills", "hero-template", "design-system", "auth")
LINK_DAYS, SPAN_DAYS, CREATION_DAYS = 14, 45, 3
PR_RE = re.compile(r"\(#(\d+)\)\s*$|Merge pull request #(\d+)")


def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def is_bot(author, subject):
    return "bot" in (author or "").lower() or bool(re.match(r"^(build|chore)\(deps[^)]*\): bump ", subject, re.I))


@lru_cache(maxsize=None)
def commits():
    con = sqlite3.connect(DB)
    first = {r: d for r, d in con.execute("SELECT repo, MIN(day) FROM blobs GROUP BY repo")}
    meta, files = {}, defaultdict(list)
    for repo, sha, ts, day, subject, author, path, blob, n in con.execute(
            "SELECT repo, sha, ts, day, subject, author, path, new_blob, n_files FROM blobs WHERE day <= ?", (LATEST,)):
        if repo in OUT_OF_SCOPE:
            continue
        m = PR_RE.search(subject)
        meta[(repo, sha)] = dict(repo=repo, sha=sha, ts=ts, day=day, subject=subject, author=author, n=n,
                                 pr=int(m.group(1) or m.group(2)) if m else None,
                                 bot=is_bot(author, subject), creation=days(first[repo], day) < CREATION_DAYS)
        files[(repo, sha)].append((path, blob))
    return meta, files


@lru_cache(maxsize=None)
def clusters():
    meta, files = commits()
    par, span = {}, {}

    def find(x):
        while par.setdefault(x, x) != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        la, lb = span.get(ra, (meta[a]["day"],) * 2), span.get(rb, (meta[b]["day"],) * 2)
        lo, hi = min(la[0], lb[0]), max(la[1], lb[1])
        if days(lo, hi) > SPAN_DAYS:
            return
        par[ra], span[rb] = rb, (lo, hi)

    usable = {k for k, m in meta.items() if not m["creation"] and m["n"] <= 150}
    by_blob = defaultdict(list)
    for k in usable:
        for path, blob in files[k]:
            if not blob.startswith(("0000000", "e69de29")):
                by_blob[(path, blob)].append(k)
    by_sig = defaultdict(list)
    for k in usable:
        s = normalize(meta[k]["subject"])
        if len(s.split()) >= 3:
            by_sig[s].append(k)
    for groups in (by_blob.values(), by_sig.values()):
        for ks in groups:
            if len({r for r, _ in ks}) < 2:
                continue
            ks = sorted(ks, key=lambda k: meta[k]["ts"])
            for a, b in zip(ks, ks[1:]):
                if days(meta[a]["day"], meta[b]["day"]) <= LINK_DAYS:
                    union(a, b)
    groups = defaultdict(list)
    for k in usable:
        if k in par:
            groups[find(k)].append(meta[k])
    out = []
    for members in groups.values():
        repos = {m["repo"] for m in members}
        if len(repos) < 2:
            continue
        members.sort(key=lambda m: m["ts"])
        arrival = {}
        for m in members:
            arrival.setdefault(m["repo"], m)
        first = members[0]
        bot = sum(m["bot"] for m in members) > len(members) / 2
        origin = ("Dependabot bumps" if bot else
                  "Upstream first" if first["repo"] in UPSTREAM else
                  "Upstream later" if any(r in UPSTREAM for r in repos) else "App to app")
        out.append(dict(members=members, repos=sorted(repos), n_repos=len(repos), first=first, arrival=arrival,
                        day=first["day"], last_day=members[-1]["day"], spread_days=days(first["day"], members[-1]["day"]),
                        origin=origin, bot=bot))
    out.sort(key=lambda c: c["first"]["ts"])
    return out


if __name__ == "__main__":
    cs = clusters()
    print(len(cs), "cross-repo changes")
    for c in sorted(cs, key=lambda c: -c["n_repos"])[:30]:
        print(c["n_repos"], len(c["members"]), c["day"], c["spread_days"], c["origin"], "|", c["first"]["repo"], "|",
              c["first"]["subject"][:80])
