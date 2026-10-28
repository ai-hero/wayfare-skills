#!/usr/bin/env python3
# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

"""Generate CONSISTENCY.md — the before/after view of the harness sweep.

    scripts/consistency.py            # write CONSISTENCY.md
    scripts/consistency.py --stdout   # print instead

GENERATED, deliberately. A hand-maintained status table is a stored result,
and a stored result is a copy — the exact thing this register exists to stamp
out.

Every column comes from data that already exists:

    per-repo mark    <- scripts/audit.py, computed live against origin/main
                        of each repo (--ref; --no-snapshot for the checkouts).
    "How it's made   <- the merged register's rule, which IS the standard.
     consistent"

    There is no "Was broken in" column and no "Reference" note: the register
    names no repos, so a check no longer carries a before-state or an
    exemplar. Everything about WHO is computed this run.

So the table cannot drift from the register: regenerate it and it re-derives.

The one thing a run cannot derive is how long a cell has been failing, so that
alone is kept, in FIRST_SEEN.json beside CONSISTENCY.md (see first_seen). A
failing cell's age is checked against its check's severity deadline, which is
register content (CONTROLS.yaml `deadlines:`).
"""

import argparse
import datetime
import importlib.util
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent   # the wayfare plugin


# Columns, ordering and results all come from audit.py at run time — never a
# copy here. A five-repo list once lived in this file and dropped three repos.
def short(name):
    """A column header that fits: the fleet's org prefix (FLEET.md `org`, plus
    its `hero-`/`aihero-` style variants) dropped, then truncated. Derived, so
    a new repo needs no entry anywhere; a collision falls back to full names
    in main()."""
    for pre in _prefixes():
        if name.startswith(pre) and len(name) > len(pre):
            name = name[len(pre):]
            break
    return name if len(name) <= 10 else name[:9] + "…"


def _prefixes():
    org = (_ORG or "").lower()
    out = []
    for o in ([org, org.replace("-", "")] if org else []) + ["hero"]:
        out += [o + "-", o + "_"]
    return [p for p in dict.fromkeys(out) if len(p) > 1]


_ORG = None



def load_audit():
    spec = importlib.util.spec_from_file_location("audit", HERE / "scripts" / "audit.py")
    m = importlib.util.module_from_spec(spec)
    # Registered under `audit`: the fleet's checkers.py, loaded by main()'s
    # configure(), does `import audit`, and without this entry that import
    # loads a second copy whose registry nobody reads.
    sys.modules["audit"] = m
    spec.loader.exec_module(m)
    return m


def condense(text, limit=200):
    """One-line summary of a rule block."""
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    cut = t[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def first_seen(path, cells, today):
    """(started, {check: {repo: iso date}}) from `cells`, {(check, repo):
    status} for this run. A FAIL keeps its date from `path`, or is seen
    `today`. Only a PASS, or a cell gone from the table, clears a date: a
    cell reading MANUAL or n/a this run (an unreviewed register turns overlay
    checks MANUAL) has not been seen fixed, and clearing it would restart a
    late failure's clock at zero. `started` is when the file began, so an age
    that reaches back to it may be older still.

    A file that does not parse stops the run rather than starting over:
    starting over would reset every age to zero, and the table would show a
    fleet with nothing past its deadline."""
    started, seen = today.isoformat(), {}
    if path.is_file():
        try:
            doc = json.loads(path.read_text())
            started, seen = doc["started"], doc["seen"]
            datetime.date.fromisoformat(started)
            for repos in seen.values():
                for d in repos.values():
                    datetime.date.fromisoformat(d)
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            sys.exit(f"{path}: unreadable first-seen state ({type(e).__name__}: {e}). "
                     "Restore it from the register's history; deleting it resets every age to today")
    out = {}
    for (cid, repo), st in sorted(cells.items()):
        d = (seen.get(cid) or {}).get(repo)
        if st == "FAIL":
            d = d or today.isoformat()
        elif st == "PASS":
            d = None
        if d:
            out.setdefault(cid, {})[repo] = d
    return started, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true")
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--no-snapshot", action="store_true")
    ap.add_argument("--fleet", default="", help="the fleet root (default: found by walking up from cwd)")
    a = ap.parse_args()

    global _ORG
    audit = load_audit()
    rc = audit.run_at_origin("consistency.py")
    if rc is not None:
        sys.exit(rc)
    audit.configure(a.fleet or None)
    _ORG = audit.read_fleet(audit.ROOT)[0].get("org") if audit.REGISTER is not None else None
    if audit.REGISTER is None:
        sys.exit("not inside a fleet: CONSISTENCY.md is the fleet's table and lives in its register checkout")
    if not audit.REGISTER.is_dir():
        sys.exit(f"register checkout missing: {audit.REGISTER} — clone it before regenerating its table")
    OUT = audit.REGISTER / "CONSISTENCY.md"
    controls, checks = audit.load_register()
    deadlines = audit.load_deadlines()
    _src, reviewed, register_note = audit.register_source()
    repos = audit.family_repos()
    with audit.reference_assets() as assets_note:
        print(f"engine: {audit.engine_note()}", file=sys.stderr)
        print(f"assets: {assets_note}", file=sys.stderr)
        print(f"register: {register_note}", file=sys.stderr)
        if a.no_snapshot:
            matrix, _fails, errors = audit.run_matrix(checks, repos)
        else:
            with audit.snapshot_family(a.ref):
                matrix, _fails, errors = audit.run_matrix(checks, repos)
    if errors:
        sys.exit(f"{len(errors)} checker errors (printed above) — not writing a table built on them")
    rows = [(c, [st for st, _d in cells]) for c, cells in matrix]
    today = datetime.date.today()
    STATE = audit.REGISTER / "FIRST_SEEN.json"
    started, seen = first_seen(
        STATE, {(c["id"], r): x for c, cells in rows for r, x in zip(repos, cells)}, today)

    def deadline(c):
        return deadlines[audit.sev_of(c, controls)]

    age = {(c["id"], r): (today - datetime.date.fromisoformat(seen[c["id"]][r])).days
           for c, cells in rows for r, x in zip(repos, cells) if x == audit.FAIL}
    by_id = {c["id"]: c for c, _cells in rows}
    late = sorted((k for k, days in age.items() if days > deadline(by_id[k[0]])),
                  key=lambda k: (deadline(by_id[k[0]]) - age[k], k))
    overdue = set(late)
    MARK = audit.MARK

    def cell(c, x, repo):
        if x != audit.FAIL:
            return MARK[x]
        k = (c["id"], repo)
        return f"{MARK[x]} {age[k]}d" + (" overdue" if k in overdue else "")

    # Two repos rendering to one header would read as one repo; use full
    # names for the whole table rather than let a column lie.
    if len({short(r) for r in repos}) != len(repos):
        globals()["short"] = lambda n: n

    L = []
    L.append("# Consistency — what drifted, and what it looks like now")
    L.append("")
    L.append("<!-- GENERATED by scripts/consistency.py. Do not edit by hand:")
    L.append("     every column is derived, so regenerating re-reads reality.")
    L.append("     A hand-maintained status table is a stored result, and a")
    L.append("     stored result is a copy — the exact failure this register")
    L.append("     exists to stamp out. Run: scripts/consistency.py -->")
    L.append("")
    L.append("Rows are checks. Columns are repos. Regenerate any time:")
    L.append("")
    L.append("```bash")
    L.append("$WAYFARE_ROOT/scripts/consistency.py     # rewrite this file  (WAYFARE_ROOT = the plugin checkout)")
    L.append("$WAYFARE_ROOT/scripts/audit.py --md      # the same results, no history")
    L.append("```")
    L.append("")
    L.append("| | Meaning |")
    L.append("| --- | --- |")
    L.append("| ✅ | complies today |")
    L.append("| ❌ 12d | still drifting, first seen failing 12 days ago |")
    L.append("| ❌ 40d overdue | past its severity's deadline: "
             + ", ".join(f"{s} {deadlines[s]} days" for s in audit.SEVERITIES) + " |")
    L.append("| – | doesn't apply (no Go, no UI, no image — or `applies_to` names a group this repo is not in) |")
    L.append("| ? | no automated checker, or the register is unreviewed — needs a human, not a guess |")
    L.append("")
    L.append("The repo columns are computed live, this run. No check names a")
    L.append("repo, so no mark is remembered from a previous sweep — a cell is")
    L.append("what the checker found just now. Only a failure's age is kept:")
    L.append("FIRST_SEEN.json, beside this file, records the first regeneration")
    L.append(f"that saw each cell fail. It started on {started}, so an age that")
    L.append("reaches back to that day may be older.")
    L.append("")
    if not reviewed:
        L.append(f"**Register unreviewed:** {register_note.split('UNREVIEWED: ', 1)[-1]}.")
        L.append("")

    total = len(age)
    L.append(f"**{total} (check × repo) results failing, {len(late)} past their deadline.** "
             f"{len(checks)} checks under {len(controls)} controls.")
    L.append("")
    if late:
        L.append("## Past deadline")
        L.append("")
        for cid, r in late:
            c = by_id[cid]
            L.append(f"- **{cid}** in {r}: failing {age[cid, r]} days, "
                     f"{audit.sev_of(c, controls)} deadline {deadline(c)} days")
        L.append("")

    last = None
    for c, cells in rows:
        cid = c["control"]
        if cid != last:
            ctl = controls[cid]
            L.append("")
            L.append(f"## {cid} — {ctl['title']} *({ctl['severity']})*")
            L.append("")
            L.append(f"> {condense(ctl.get('intent'), 260)}")
            L.append("")
            L.append("| Check | " + " | ".join(short(r) for r in repos) + " | How it's made consistent |")
            L.append("| --- | " + " | ".join("---" for _ in repos) + " | --- |")
            last = cid

        # No "Was broken in" column and no "Reference:" suffix: the register
        # names no repos, so both had exactly one source and it is gone. Left
        # in, they printed "*(none)*" and "No reference yet — needs a decision"
        # on every row — a column of nothing, and 128 rows each demanding a
        # decision nobody owes. The per-repo cells below already say who fails
        # today, computed this run rather than remembered from the last one.
        how = condense(c.get("rule"), 180)

        L.append(
            f"| **{c['id']}** {c['title']} *({c['scope']}, {audit.sev_of(c, controls)})* | "
            + " | ".join(cell(c, x, r) for x, r in zip(cells, repos))
            + f" | {how} |"
        )

    L.append("")
    L.append("---")
    L.append("")
    L.append("## Reading this honestly")
    L.append("")
    L.append("A `?` is not a pass. It means no checker exists, so the answer is")
    L.append("unknown — reported as unknown rather than guessed.")
    L.append("")
    L.append("**No check names a repo.** A check states what consistent means;")
    L.append("who passes it is this table, computed per run from the repos")
    L.append("FLEET.md lists. Where a consumer got it right first, the fix is")
    L.append("still a backport INTO the template — never a change to the repo")
    L.append("that is already right.")
    L.append("")

    # Emit what this repo's own hooks accept: no run of blank lines
    # (markdownlint MD012) and exactly one trailing newline (end-of-file-fixer).
    # Otherwise every regeneration lands dirty, the hooks rewrite the file, and
    # the generator and its output disagree forever — a drift between the map
    # and the territory, in the one file whose entire purpose is not drifting.
    lines = []
    for line in L:
        if line == "" and lines and lines[-1] == "":
            continue
        lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()

    out = "\n".join(lines) + "\n"
    if a.stdout:
        print(out)
    else:
        OUT.write_text(out)
        STATE.write_text(json.dumps({"started": started, "seen": seen}, indent=2, sort_keys=True) + "\n")
        print(f"wrote {OUT} and {STATE.name}  ({len(checks)} checks, {total} failing, {len(late)} past deadline)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
