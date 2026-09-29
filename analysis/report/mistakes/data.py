"""Mistakes and rework: one function per question, each returning what its slides plot.

    cd analysis && WAYFARE_FLEET_ROOT=~/workspaces/aihero python3 report/mistakes/data.py   # prints every answer

Inputs beyond the shared databases: mistakes.sqlite, written by label.py (Haiku labels: commit_labels,
mistake_labels, persona_findings, persona_sessions) and szz.py (szz, szz_hits).
"""
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))]
from cube.db import connect as _connect  # noqa: E402
from record import STAGES, adoption, changeset_facts, commit_facts, rows, stage_of, week_of  # noqa: E402
from ingest.fleet import OUT_OF_SCOPE  # noqa: E402
from facts import fix_changesets, fix_method  # noqa: E402

WEEKS = [f"2026-W{w:02d}" for w in range(1, 40)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
# No Claude Code sessions were logged 10-24 Aug. Session-derived series (tool calls, subagent runs)
# show those weeks as "data not available" (None), never 0, and leave them out of every average.
# Typed prompts come from another log and continue through the gap.
NO_DATA_WEEKS = {"2026-W33", "2026-W34"}
NO_DATA_EVENT = ("2026-08-10", "Session data not available")
MISTAKE_LOG_EVENT = ("2026-09-19", "Mistake log (#104)")
DATA_END = date(2026, 9, 25)     # last day in git.commits; a fix window is complete only if it ends by then
ITEMS_FROM, SESSIONS_FROM = "2026-W30", "2026-W32"
RENAMES = {"hero-skills": "wayfare-skills"}
APPS = ("app", "app, no features yet")

THEME_NAMES = {
    "logic_bug": "Logic bug", "incomplete": "Left something out", "docs_prose": "Docs, comments or PR text",
    "env_assumption": "Wrong assumption (tool, API, host)", "test_gap": "Weak or missing test",
    "security": "Security weakness", "format_lint": "Lint, format, syntax", "unverified_claim": "Claimed without checking",
    "plan_gap": "Plan was wrong", "git_process": "Git or process step", "ci_config": "CI or build config",
    "subagent": "Subagent failure", "other": "Other",
}
CATCHER_NAMES = {"review_agent": "Review agents", "self": "The agent itself", "ci": "CI", "copilot": "Copilot",
                 "judge": "Auto-approve judge", "owner": "The owner", "hook": "Pre-commit hook", "test": "A test",
                 "unknown": "Unknown"}
GUARD_EVENTS = [
    ("2026-05-04", "Prior-review gate"),
    ("2026-09-18", "Draft until self-review (#93)"),
    ("2026-09-23", "Judge fails closed (#118)"),
]
JUDGE_EVENTS = [
    ("2026-05-04", "Prior-review gate"),
    ("2026-07-18", "Reusable workflow"),
    ("2026-08-29", "Scripted gates first (#65)"),
    ("2026-09-18", "Verdict says what it verified (#97)"),
    ("2026-09-23", "Fails closed (#118)"),
]


def con_():
    return _connect("mistakes")


def iso_monday(w):
    return date.fromisocalendar(int(w[:4]), int(w[6:]), 1)


def weekly_count(pairs, weeks=WEEKS, start=None, no_data=False):
    """pairs: iterable of (week, value). None before `start` week and, if no_data, in NO_DATA_WEEKS."""
    acc = defaultdict(float)
    for w, v in pairs:
        acc[w] += v
    out = []
    for w in weeks:
        if (start and w < start) or (no_data and w in NO_DATA_WEEKS):
            out.append(None)
        else:
            out.append(round(acc.get(w, 0), 3))
    return out


def share(num, den, min_n=5):
    return [round(n / d, 3) if d and d >= min_n and n is not None else None for n, d in zip(num, den)]


def mean_known(v):
    v = [x for x in v if x is not None]
    return round(statistics.mean(v), 3) if v else None


def repo_ok(con, repo):
    return repo in adoption(con)


@lru_cache(maxsize=None)
def cs_nondep(con):
    return tuple(f for f in changeset_facts(con) if not f["dependabot"])


# ------------------------------------------------------------------ labelled facts

@lru_cache(maxsize=None)
def fixup_commits(con):
    """Every labelled non-first original commit of a merged, non-Dependabot PR, with its merge week.
    The trigger is overridden when the subject names it (Haiku sometimes answered `self` on
    "address self-review findings")."""
    merged = {(r["repo"], r["pr_number"]): r["day"] for r in rows(con, "SELECT repo, pr_number, day FROM git.commits "
                                                                        "WHERE pr_number IS NOT NULL")}
    subj = {(r["repo"], r["sha"]): r["subject"] or "" for r in rows(con, "SELECT repo, sha, subject FROM pr_commits.pr_commits")}
    out = []
    for r in rows(con, "SELECT * FROM mistakes.commit_labels"):
        if not repo_ok(con, r["repo"]) or (r["repo"], r["pr"]) not in merged:
            continue
        s = subj.get((r["repo"], r["sha"]), "")
        trig = r["trigger"]
        if r["fixup"]:
            if re.search(r"self-review|review findings|review agents?", s, re.I):
                trig = "review_agent"
            elif re.search(r"copilot", s, re.I):
                trig = "copilot"
        md = merged[(r["repo"], r["pr"])]
        out.append({**r, "trigger": trig, "subject": s, "merged_day": md, "week": week_of(md),
                    "stage": stage_of(con, r["repo"], md), "category": adoption(con)[r["repo"]]["category"]})
    return tuple(out)


@lru_cache(maxsize=None)
def logged_mistakes(con):
    out = []
    for r in rows(con, "SELECT * FROM mistakes.mistake_labels WHERE source IN ('mistake_log', 'note')"):
        if repo_ok(con, r["repo"]) and r["day"]:
            out.append({**r, "week": week_of(r["day"])})
    return tuple(out)


@lru_cache(maxsize=None)
def pr_units(con):
    """Merged non-bot PRs: {(repo, pr): {day, week, n_commits, n_sets}}."""
    sets = Counter((f["repo"], f["pr"]) for f in cs_nondep(con) if f["pr"])
    ncom = Counter((r["repo"], r["pr_number"]) for r in rows(con, "SELECT repo, pr_number FROM pr_commits.pr_commits "
                                                                   "WHERE is_merge = 0"))
    out = {}
    for r in rows(con, "SELECT repo, number, day, author, author_is_bot FROM github.prs WHERE merged_ts IS NOT NULL"):
        if not repo_ok(con, r["repo"]) or r["author_is_bot"] or "dependabot" in (r["author"] or "").lower():
            continue
        out[(r["repo"], r["number"])] = {"day": r["day"], "week": week_of(r["day"]), "n_commits": ncom.get((r["repo"], r["number"]), 1),
                                         "n_sets": sets.get((r["repo"], r["number"]), 0),
                                         "stage": stage_of(con, r["repo"], r["day"]),
                                         "category": adoption(con)[r["repo"]]["category"]}
    return out


# ------------------------------------------------------------------ Q mistake-records

def q_mistake_records(con):
    """Mistakes recorded per week, by the channel that recorded them."""
    lm = logged_mistakes(con)
    fx = [f for f in fixup_commits(con) if f["fixup"]]
    ci = rows(con, "SELECT repo, day FROM github.ci_runs WHERE conclusion = 'failure' AND event = 'pull_request'")
    judge = rows(con, "SELECT repo, submitted_ts ts FROM github.pr_reviews WHERE reviewer = 'github-actions' "
                      "AND state = 'CHANGES_REQUESTED'")
    corr = owner_corrections(con)
    series = {
        "In-PR fix-up commits": weekly_count((f["week"], 1) for f in fx),
        "Failed CI runs on PRs": weekly_count((week_of(r["day"]), 1) for r in ci if repo_ok(con, r["repo"])),
        "Judge: changes requested": weekly_count((week_of(r["ts"][:10]), 1) for r in judge if repo_ok(con, r["repo"])),
        "Owner corrections": weekly_count((w, n) for w, n in corr.items()),
        "Mistakes in work-item notes": weekly_count(((m["week"], 1) for m in lm if m["source"] == "note" and m["is_mistake"]),
                                                    start=ITEMS_FROM),
        "Mistake log entries": weekly_count(((m["week"], 1) for m in lm if m["source"] == "mistake_log" and m["is_mistake"]),
                                            start="2026-W38"),
    }
    started = {"In-PR fix-up commits": "whole period (original PR commits)", "Failed CI runs on PRs": "whole period",
               "Judge: changes requested": "5 May (prior-review gate)", "Mistakes in work-item notes": "23 Jul (.plans notes)",
               "Owner corrections": "whole period (typed prompts)",
               "Mistake log entries": "18 Sep (#104 made it a convention on 19 Sep)"}
    totals = {k: int(sum(v for v in s if v)) for k, s in series.items()}
    totals["In-PR fix-up commits"] = len(fx)
    by_repo = Counter(m["repo"] for m in lm if m["source"] == "mistake_log" and m["is_mistake"])
    note_repo = Counter(m["repo"] for m in lm if m["source"] == "note" and m["is_mistake"])
    active = {r for r in adoption(con) if adoption(con)[r]["last"] >= "2026-09-18"}
    return {"weeks": WEEKS, "series": series, "totals": totals, "started": started,
            "log_repos": dict(by_repo.most_common()), "note_repos": dict(note_repo.most_common()),
            "active_since_log": sorted(active), "silent_repos": sorted(active - set(by_repo)),
            "log_entries": sum(1 for m in lm if m["source"] == "mistake_log"),
            "log_not_mistake": sum(1 for m in lm if m["source"] == "mistake_log" and not m["is_mistake"])}


@lru_cache(maxsize=None)
def owner_corrections(con):
    """Typed prompts per week labelled correction or redirect. Uses the lead's detectors.prompt_intent when
    present, else detectors.prompt_kind (report/owner owns the correction rate itself)."""
    from facts import has_table
    out = Counter()
    if has_table(con, "detectors", "prompt_intent"):
        cols = {r[1] for r in con.execute("PRAGMA detectors.table_info(prompt_intent)")}
        ts = "ts" if "ts" in cols else None
        if ts and "intent" in cols:
            for r in rows(con, "SELECT ts, intent FROM detectors.prompt_intent"):
                if r["intent"] in ("correction", "redirect") and r["ts"]:
                    out[week_of(r["ts"][:10])] += 1
            return out
    kind = {r["content_hash"]: r["kind"] for r in rows(con, "SELECT content_hash, kind FROM detectors.prompt_kind")}
    for r in rows(con, "SELECT ts, content_hash FROM detectors.prompt_kind_by_prompt"):
        if kind.get(r["content_hash"]) in ("correction", "redirect") and r["ts"]:
            out[week_of(r["ts"][:10])] += 1
    return out


# ------------------------------------------------------------------ Q readable-gate-verdicts

def q_readable_gate_verdicts(con):
    """Weekly recorded outcomes per gate, and whether each gate records a verdict or only that it ran."""
    ci = rows(con, "SELECT repo, day, conclusion FROM github.ci_runs WHERE conclusion IS NOT NULL")
    rv = rows(con, "SELECT repo, reviewer, state, submitted_ts ts FROM github.pr_reviews")
    pr_runs = rows(con, "SELECT ts_start ts FROM harness.subagent_runs WHERE subagent_type LIKE 'pr-review-toolkit:%'")
    checks = rows(con, "SELECT repo, as_of FROM knowledge.check_results")
    judge = [r for r in rv if r["reviewer"] == "github-actions" and r["state"] in ("APPROVED", "CHANGES_REQUESTED")]
    cop = [r for r in rv if r["reviewer"].startswith("copilot")]
    wk = lambda it, f: weekly_count((week_of(f(r)[:10]), 1) for r in it if f(r))
    series = {
        "CI runs (pass/fail)": wk([r for r in ci if repo_ok(con, r["repo"])], lambda r: r["day"]),
        "Judge verdicts": wk([r for r in judge if repo_ok(con, r["repo"])], lambda r: r["ts"]),
        "Copilot reviews": wk([r for r in cop if repo_ok(con, r["repo"])], lambda r: r["ts"]),
        "Review persona runs (no verdict)": weekly_count(((week_of(r["ts"][:10]), 1) for r in pr_runs if r["ts"]),
                                                         start=SESSIONS_FROM, no_data=True),
    }
    inventory = [
        ("CI", "verdict per run", len(ci)),
        ("Auto-approve judge", "verdict per PR + reasons (partly)", len(judge)),
        ("Copilot reviewer", "comments, no verdict", len(cop)),
        ("Review personas", "run recorded, findings only in transcript prose", len(pr_runs)),
        ("Compliance checks", "verdict per check, latest state only", len(checks)),
        ("Pre-commit hooks", "nothing recorded", 0),
    ]
    judged_with_reasons = sum(1 for r in rows(con, "SELECT body_redacted b FROM github.pr_reviews WHERE reviewer='github-actions' "
                                                   "AND state='CHANGES_REQUESTED'") if re.search(r"^##\s*.+?:\s*❌", r["b"] or "", re.M))
    check_dates = sorted({r["as_of"][:10] for r in checks if r["as_of"]})
    return {"weeks": WEEKS, "series": series, "inventory": inventory, "judge_reasons": judged_with_reasons,
            "judge_rejections": sum(1 for r in judge if r["state"] == "CHANGES_REQUESTED"), "check_dates": check_dates}


# ------------------------------------------------------------------ Q in-pr-fix-share

FIXUP_RE_CH2 = re.compile(r"\b(address|review|self-review|copilot|lint|format|nit|fixup|typo|feedback|findings)\b", re.I)


def q_in_pr_fix_share_fixups(con):
    """Share of merged PRs (with 2+ commits and all) that carry at least one in-PR fix-up, weekly and by stage."""
    fx = fixup_commits(con)
    has_fix = defaultdict(int)
    labelled = defaultdict(int)
    for f in fx:
        labelled[(f["repo"], f["pr"])] += 1
        has_fix[(f["repo"], f["pr"])] += f["fixup"]
    prs = pr_units(con)
    multi = {k: v for k, v in prs.items() if k in labelled}
    w_all = weekly_count((v["week"], 1) for v in prs.values())
    w_fix = weekly_count((v["week"], 1) for k, v in prs.items() if has_fix.get(k))
    w_multi = weekly_count((v["week"], 1) for v in multi.values())
    sets_w = weekly_count((f["week"], 1) for f in cs_nondep(con))
    fix_w = weekly_count((f["week"], f["fixup"]) for f in fx)
    per100 = [round(100 * a / b, 1) if b and b >= 5 else None for a, b in zip(fix_w, sets_w)]
    series = {"Merged PRs with an in-PR fix-up": share(w_fix, w_all),
              "Merged PRs with 2+ commits": share(w_multi, w_all)}
    by_stage = {}
    for s in STAGES:
        ks = [k for k, v in prs.items() if v["stage"] == s]
        if len(ks) >= 20:
            by_stage[s] = (round(sum(1 for k in ks if has_fix.get(k)) / len(ks), 3), len(ks))
    by_trigger = Counter(f["trigger"] for f in fx if f["fixup"])
    # evolution.py's q_where_rework_is_caught regex against the Haiku label, on the same commits.
    agree = Counter((bool(FIXUP_RE_CH2.search(f["subject"])), bool(f["fixup"])) for f in fx)
    by_repo = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for k, v in prs.items():
        m = v["day"][:7]
        by_repo[k[0]][m][1] += 1
        by_repo[k[0]][m][0] += 1 if has_fix.get(k) else 0
    top = sorted(by_repo, key=lambda r: -sum(x[1] for x in by_repo[r].values()))[:8]
    repo_series = {r: [round(by_repo[r][m][0] / by_repo[r][m][1], 3) if by_repo[r][m][1] >= 5 else None for m in MONTHS]
                   for r in top}
    n_fix = sum(f["fixup"] for f in fx)
    return {"weeks": WEEKS, "series": series, "per100": per100, "by_stage": by_stage, "by_trigger": dict(by_trigger.most_common()),
            "agree": {f"regex={a},haiku={b}": n for (a, b), n in agree.items()}, "n_labelled": len(fx), "n_fixups": n_fix,
            "n_prs": len(prs), "n_prs_fix": sum(1 for k in prs if has_fix.get(k)), "n_multi": len(multi),
            "unlabelled": unlabelled_commits(con),
            "months": MONTHS, "by_repo": repo_series,
            "recent": mean_known(series["Merged PRs with an in-PR fix-up"][-6:]),
            "early": mean_known(series["Merged PRs with an in-PR fix-up"][:18])}


def unlabelled_commits(con):
    """Non-first original commits of in-scope, non-Dependabot PRs that got no label (unparsable replies)."""
    import label
    have = {(r["repo"], r["pr"], r["sha"]) for r in rows(con, "SELECT repo, pr, sha FROM mistakes.commit_labels")}
    return sum(1 for k, _ in label.commit_items(con) if (k[0], k[1], k[2]) not in have)


# ------------------------------------------------------------------ Q fix-forwards

NOISE_FILE_RE = re.compile(r"(^|/)(package-lock\.json|package\.json|pnpm-lock\.yaml|yarn\.lock|go\.sum|go\.mod|"
                           r"uv\.lock|poetry\.lock|Cargo\.lock|VERSION\.md|CHANGELOG\.md|HERO\.md|AGENTS\.md|"
                           r"CLAUDE\.md|CONSISTENCY\.md|PLAN\.md)$|^\.plans/")


def parse_ts(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@lru_cache(maxsize=None)
def same_file_followups(con, days=7):
    """Filtered D5, the same definition report/conclusion uses: non-bot PRs whose own files (lockfiles,
    manifests and bookkeeping excluded) a later non-bot commit from another PR touches by half or more
    within `days` of the merge."""
    prs = rows(con, "SELECT repo, number, merged_ts, author, author_is_bot FROM github.prs WHERE merged_ts IS NOT NULL")
    files = defaultdict(set)
    for r in rows(con, "SELECT c.repo, c.pr_number pr, cf.path FROM git.commits c JOIN git.commit_files cf "
                       "ON cf.repo=c.repo AND cf.sha=c.sha WHERE c.pr_number IS NOT NULL"):
        if not NOISE_FILE_RE.search(r["path"]):
            files[(r["repo"], r["pr"])].add(r["path"])
    later = defaultdict(list)
    for r in rows(con, "SELECT repo, sha, committed_ts ts, pr_number pr, is_bot FROM git.commits "
                       "WHERE committed_ts IS NOT NULL AND is_merge = 0"):
        if not r["is_bot"]:
            later[r["repo"]].append((parse_ts(r["ts"]), r["pr"], r["sha"]))
    cfiles = defaultdict(set)
    for r in rows(con, "SELECT repo, sha, path FROM git.commit_files"):
        if not NOISE_FILE_RE.search(r["path"]):
            cfiles[(r["repo"], r["sha"])].add(r["path"])
    for v in later.values():
        v.sort(key=lambda x: x[0])
    out = []
    for p in prs:
        if not repo_ok(con, p["repo"]) or p["author_is_bot"] or "dependabot" in (p["author"] or "").lower():
            continue
        base = files.get((p["repo"], p["number"]))
        if not base:
            continue
        m = parse_ts(p["merged_ts"])
        for ts, pr, sha in later[p["repo"]]:
            dd = (ts - m).total_seconds() / 86400
            if dd <= 0 or pr == p["number"]:
                continue
            if dd > days:
                break
            if len(cfiles[(p["repo"], sha)] & base) / len(base) >= 0.5:
                out.append((p["repo"], p["number"]))
                break
    return tuple(out)


@lru_cache(maxsize=None)
def szz_rows(con):
    return tuple(r for r in rows(con, "SELECT * FROM mistakes.szz") if repo_ok(con, r["repo"]))


def q_fix_forwards_fixforward(con):
    """Weekly share of merged PRs whose lines a later fix change set repaired within 3 / 7 days (SZZ)."""
    prs = pr_units(con)
    fixed_in = defaultdict(lambda: 10 ** 6)
    for r in szz_rows(con):
        if r["outcome"] == "traced" and r["intro_unit"].startswith("pr:"):
            k = (r["repo"], int(r["intro_unit"][3:]))
            fixed_in[k] = min(fixed_in[k], r["lifetime_days"])
    w_all = weekly_count((v["week"], 1) for v in prs.values())
    w3 = weekly_count((v["week"], 1) for k, v in prs.items() if fixed_in.get(k, 1e9) <= 3)
    w7 = weekly_count((v["week"], 1) for k, v in prs.items() if fixed_in.get(k, 1e9) <= 7)
    series = {"Fixed forward within 7 days": share(w7, w_all), "Within 3 days": share(w3, w_all)}
    by_cat = {}
    for c in ("app", "app, no features yet", "allied"):
        ks = [k for k, v in prs.items() if v["category"] == c]
        if ks:
            by_cat[c] = (round(sum(1 for k in ks if fixed_in.get(k, 1e9) <= 7) / len(ks), 3), len(ks))
    by_repo = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for k, v in prs.items():
        by_repo[k[0]][v["day"][:7]][1] += 1
        by_repo[k[0]][v["day"][:7]][0] += 1 if fixed_in.get(k, 1e9) <= 7 else 0
    top = sorted(by_repo, key=lambda r: -sum(x[1] for x in by_repo[r].values()))[:8]
    repo_series = {r: [round(by_repo[r][m][0] / by_repo[r][m][1], 3) if by_repo[r][m][1] >= 5 else None for m in MONTHS]
                   for r in top}
    sff = same_file_followups(con)
    raw = rows(con, "SELECT COUNT(*) n FROM detectors.followups WHERE followup_within_7d_days IS NOT NULL")[0]["n"]
    n7 = sum(1 for k in prs if fixed_in.get(k, 1e9) <= 7)
    # Figure 4.6: a PR is eligible for a window only when the data end lies at least that many days after its
    # merge, so the last weeks stop reading as an improvement they have not had time to earn.
    age = lambda k: (DATA_END - date.fromisoformat(prs[k]["day"])).days
    windows = {}
    for w in (3, 7, 14, 30):
        elig = [k for k in prs if age(k) >= w]
        windows[w] = {"eligible": len(elig), "fixed": sum(1 for k in elig if fixed_in.get(k, 1e9) <= w)}
    elig7 = [k for k in prs if age(k) >= 7]
    monthly = {}
    for w in (7, 14, 30):
        acc = defaultdict(lambda: [0, 0])
        for k in prs:
            if age(k) >= w:
                acc[prs[k]["day"][:7]][1] += 1
                acc[prs[k]["day"][:7]][0] += fixed_in.get(k, 1e9) <= w
        monthly[w] = {m: tuple(v) for m, v in sorted(acc.items()) if m >= "2026-01"}
    elig30 = [k for k in prs if age(k) >= 30]
    lifetimes30 = sorted(fixed_in[k] for k in elig30 if fixed_in.get(k, 1e9) <= 30)
    repo7 = defaultdict(lambda: [0, 0])
    for k in elig7:
        repo7[k[0]][1] += 1
        repo7[k[0]][0] += fixed_in.get(k, 1e9) <= 7
    cat7 = defaultdict(lambda: [0, 0])
    for k in elig7:
        cat7[prs[k]["category"]][1] += 1
        cat7[prs[k]["category"]][0] += fixed_in.get(k, 1e9) <= 7
    periods = {}
    for name, lo, hi in (("Jan–Jun", "2026-01-01", "2026-06-30"), ("Jul", "2026-07-01", "2026-07-31"),
                         ("Aug–18 Sep", "2026-08-01", "2026-09-18")):
        ks = [k for k in elig7 if lo <= prs[k]["day"] <= hi]
        periods[name] = (sum(1 for k in ks if fixed_in.get(k, 1e9) <= 7), len(ks))
    return {"weeks": WEEKS, "series": series, "by_cat": by_cat, "months": MONTHS, "by_repo": repo_series,
            "n_prs": len(prs), "n7": n7, "n3": sum(1 for k in prs if fixed_in.get(k, 1e9) <= 3),
            "same_file_7d": len(sff), "d5_raw_7d": raw,
            "early": mean_known(series["Fixed forward within 7 days"][:26]),
            "recent": mean_known(series["Fixed forward within 7 days"][-8:]),
            "data_end": DATA_END.isoformat(), "windows": windows, "monthly": monthly,
            "u7_within_3": sum(1 for k in elig7 if fixed_in.get(k, 1e9) <= 3),
            "u7_within_1": sum(1 for k in elig7 if fixed_in.get(k, 1e9) <= 1),
            "n_elig30": len(elig30), "lifetimes30": lifetimes30,
            "repo7": {r: tuple(v) for r, v in sorted(repo7.items(), key=lambda kv: -kv[1][1])},
            "cat7": {c: tuple(v) for c, v in cat7.items()}, "periods": periods,
            "n_traced_prs": len(fixed_in)}


# ------------------------------------------------------------------ Q reverts-and-reopens

def q_reverts_and_reopens_reverts(con):
    """Every revert on main, every PR reopened after merge or close, and reverts inside PRs."""
    events = []
    for r in rows(con, "SELECT repo, day, subject, pr_number FROM git.commits WHERE is_revert = 1 OR subject LIKE 'Revert%'"):
        if repo_ok(con, r["repo"]):
            events.append({"kind": "Revert on main", "repo": r["repo"], "day": r["day"], "what": r["subject"]})
    for r in rows(con, "SELECT t.repo, t.number, t.ts, p.title FROM github.pr_timeline t JOIN github.prs p "
                       "ON p.repo=t.repo AND p.number=t.number WHERE t.event = 'reopened'"):
        if repo_ok(con, r["repo"]):
            events.append({"kind": "PR reopened", "repo": r["repo"], "day": r["ts"][:10], "what": f"#{r['number']} {r['title']}"})
    in_pr = [r for r in rows(con, "SELECT repo, pr_number, ts, subject FROM pr_commits.pr_commits WHERE subject LIKE 'Revert%'")
             if repo_ok(con, r["repo"])]
    prs = pr_units(con)
    w_prs = weekly_count((v["week"], 1) for v in prs.values())
    w_inpr = weekly_count((week_of(r["ts"][:10]), 1) for r in in_pr)
    return {"weeks": WEEKS, "series": {"Merged PRs": w_prs}, "in_pr": w_inpr, "events": sorted(events, key=lambda e: e["day"]),
            "n_in_pr": len(in_pr), "n_prs": len(prs),
            "in_pr_examples": [f"{r['repo']}#{r['pr_number']}: {r['subject'][:90]}" for r in in_pr[:8]]}


# ------------------------------------------------------------------ Q defect-lifetime

LIFE_BINS = [("Same day", 0, 0), ("1–2 days", 1, 2), ("3–7 days", 3, 7), ("8–30 days", 8, 30), ("31–90 days", 31, 90),
             ("Over 90 days", 91, 10 ** 6)]


def pctl(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))] if v else None


def q_defect_lifetime(con):
    tr = [r for r in szz_rows(con) if r["outcome"] == "traced"]
    by_w = defaultdict(list)
    for r in tr:
        by_w[week_of(r["fix_day"])].append(r["lifetime_days"])
    med = [statistics.median(by_w[w]) if len(by_w[w]) >= 5 else None for w in WEEKS]
    p90 = [pctl(by_w[w], 0.9) if len(by_w[w]) >= 5 else None for w in WEEKS]
    hist = [sum(1 for r in tr if lo <= r["lifetime_days"] <= hi) for _, lo, hi in LIFE_BINS]
    long_ = [r for r in tr if r["lifetime_days"] > 30]
    long_by_repo = Counter(r["repo"] for r in long_)
    push_long = sum(1 for r in long_ if r["intro_unit"].startswith("push:"))
    outcomes = Counter(r["outcome"] for r in szz_rows(con))
    lt = [r["lifetime_days"] for r in tr]
    return {"weeks": WEEKS, "series": {"Median days": med, "90th percentile": p90},
            "bins": [b[0] for b in LIFE_BINS], "hist": hist, "n": len(tr), "median": statistics.median(lt) if lt else None,
            "p90": pctl(lt, 0.9), "within_7": sum(1 for x in lt if x <= 7), "over_30": len(long_),
            "long_by_repo": dict(long_by_repo.most_common(5)), "long_from_push": push_long, "outcomes": dict(outcomes),
            "fix_method": fix_method(con),
            "long_examples": [f"{r['repo']}: {r['label']} ({int(r['lifetime_days'])} d, from {r['intro_unit']})"
                              for r in sorted(long_, key=lambda r: -r["lifetime_days"])[:6]]}


# ------------------------------------------------------------------ Q defect-origin

def q_defect_origin_origin(con):
    """Monthly: what put the repaired lines there."""
    cats = ["An earlier agent-written change", "An earlier human-written change", "The repo's first commit (inherited)",
            "Not traceable (additive or in-PR only)"]
    by_m = defaultdict(Counter)
    for r in szz_rows(con):
        m = r["fix_day"][:7]
        if r["outcome"] != "traced":
            by_m[m][cats[3]] += 1
        elif r["intro_is_first_commit"]:
            by_m[m][cats[2]] += 1
        elif r["intro_agent"]:
            by_m[m][cats[0]] += 1
        else:
            by_m[m][cats[1]] += 1
    tot = {m: sum(by_m[m].values()) for m in MONTHS}
    series = {c: [round(by_m[m][c] / tot[m], 3) if tot[m] >= 5 else None for m in MONTHS] for c in cats}
    counts = {c: sum(by_m[m][c] for m in MONTHS) for c in cats}
    by_stage = defaultdict(Counter)
    for r in szz_rows(con):
        if r["outcome"] == "traced":
            k = "agent" if (r["intro_agent"] and not r["intro_is_first_commit"]) else "other"
            by_stage[stage_of(con, r["repo"], r["fix_day"])][k] += 1
    return {"months": MONTHS, "series": series, "counts": counts, "n": sum(counts.values()),
            "by_stage": {s: dict(v) for s, v in by_stage.items()}}


# ------------------------------------------------------------------ Q mistake-kinds

TOP_THEMES = ["logic_bug", "incomplete", "docs_prose", "env_assumption", "test_gap", "security"]


def theme_key(t):
    return THEME_NAMES[t] if t in TOP_THEMES else "Everything else"


def q_mistake_kinds_themes(con):
    fx = [f for f in fixup_commits(con) if f["fixup"]]
    lm = [m for m in logged_mistakes(con) if m["is_mistake"]]
    cats = [THEME_NAMES[t] for t in TOP_THEMES] + ["Everything else"]
    acc = defaultdict(Counter)
    for f in fx:
        acc[theme_key(f["theme"])][f["week"]] += 1
    for m in lm:
        acc[theme_key(m["theme"])][m["week"]] += 1
    series = {c: [acc[c].get(w, 0) for w in WEEKS] for c in cats}
    fx_themes = Counter(f["theme"] for f in fx)
    lm_themes = Counter(m["theme"] for m in lm)
    all_t = sorted(set(fx_themes) | set(lm_themes), key=lambda t: -(fx_themes[t] / max(1, len(fx)) + lm_themes[t] / max(1, len(lm))))
    actors = Counter(m["actor"] for m in lm)
    recurring = Counter(m["summary"].lower()[:40] for m in lm)
    # Month-over-month share of the top two themes among fix-ups, to say whether the mix moved.
    mix = {}
    for t in ("logic_bug", "incomplete", "docs_prose"):
        mix[THEME_NAMES[t]] = [round(sum(1 for f in fx if f["theme"] == t and f["merged_day"][:7] == m) /
                                     max(1, sum(1 for f in fx if f["merged_day"][:7] == m)), 3)
                               if sum(1 for f in fx if f["merged_day"][:7] == m) >= 20 else None for m in MONTHS]
    return {"weeks": WEEKS, "series": series, "themes": [THEME_NAMES.get(t, t) for t in all_t],
            "fixup_share": [round(fx_themes[t] / len(fx), 3) for t in all_t],
            "log_share": [round(lm_themes[t] / len(lm), 3) for t in all_t], "n_fx": len(fx), "n_lm": len(lm),
            "fx_top": {THEME_NAMES.get(t, t): n for t, n in fx_themes.most_common(4)},
            "lm_top": {THEME_NAMES.get(t, t): n for t, n in lm_themes.most_common(4)},
            "subagent": actors.get("subagent", 0) + lm_themes.get("subagent", 0), "actors": dict(actors),
            "mix": mix, "months": MONTHS}


# ------------------------------------------------------------------ Q who-catches-mistakes

CATCH_ORDER = ["review_agent", "self", "ci", "copilot", "judge", "owner", "hook"]


def q_who_catches_mistakes_catchers(con):
    fx = [f for f in fixup_commits(con) if f["fixup"]]
    by_w = defaultdict(Counter)
    for f in fx:
        by_w[f["week"]][f["trigger"]] += 1
    tot = {w: sum(by_w[w].values()) for w in WEEKS}
    series = {CATCHER_NAMES[c]: [round(by_w[w][c] / tot[w], 3) if tot[w] >= 5 else None for w in WEEKS] for c in CATCH_ORDER}
    by_stage = {}
    for s in STAGES:
        c = Counter(f["trigger"] for f in fx if f["stage"] == s)
        if sum(c.values()) >= 20:
            by_stage[s] = {CATCHER_NAMES[k]: round(c[k] / sum(c.values()), 3) for k in CATCH_ORDER}
    lm = [m for m in logged_mistakes(con) if m["is_mistake"]]
    log_c = Counter(m["caught_by"] for m in lm)
    tot_fx = Counter(f["trigger"] for f in fx)
    return {"weeks": WEEKS, "series": series, "by_stage": by_stage,
            "fx_share": {CATCHER_NAMES[k]: round(tot_fx[k] / len(fx), 3) for k in CATCH_ORDER},
            "log_share": {CATCHER_NAMES.get(k, k): round(v / len(lm), 3) for k, v in log_c.most_common()},
            "n_fx": len(fx), "n_lm": len(lm),
            "review_recent": mean_known(series["Review agents"][-8:]), "review_early": mean_known(series["Review agents"][:18])}


# ------------------------------------------------------------------ Q where-fixes-land

SCOPES = [
    ("Tests", re.compile(r"(^|/)(tests?|__tests__|e2e|spec)/|[._-](test|spec)\.[a-z]+$|_test\.go$|\.test\.sh$")),
    ("CI and build", re.compile(r"^\.github/|(^|/)(Dockerfile[^/]*|docker-compose[^/]*|compose[^/]*\.ya?ml|Justfile|Makefile|"
                                r"\.pre-commit-config\.yaml|\.golangci\.yaml)$")),
    ("Agent instructions and skills", re.compile(r"(^|/)(AGENTS\.md|CLAUDE\.md|HERO\.md|SKILL\.md)$|^\.claude/|^skills/|^\.plans/")),
    ("Infrastructure and config", re.compile(r"\.(tf|tfvars|hcl)$|(^|/)(infra|deploy|terraform|k8s|helm)/|\.(ya?ml|toml|ini|env[^/]*)$")),
    ("Docs and prose", re.compile(r"\.(md|mdx|txt|rst)$|(^|/)docs/")),
]


def scope_of(path):
    for name, rx in SCOPES:
        if rx.search(path):
            return name
    return "Product code"


def q_where_fixes_land_scope(con):
    """Fix and security change sets by where their lines land, monthly, plus the security share."""
    files = defaultdict(list)
    for r in rows(con, "SELECT repo, sha, files_json FROM pr_commits.pr_commits"):
        try:
            fs = json.loads(r["files_json"] or "[]")
        except json.JSONDecodeError:
            fs = []
        files[(r["repo"], r["sha"])] = [f.get("path") if isinstance(f, dict) else str(f) for f in fs]
    for r in rows(con, "SELECT repo, sha, path FROM git.commit_files"):
        files.setdefault((r["repo"], r["sha"]), []).append(r["path"])
    lab = {(r["repo"], r["unit_kind"], r["unit_id"], r["set_idx"]): r["work_type"]
           for r in rows(con, "SELECT * FROM detectors.cs_worktype")}
    scopes = [s[0] for s in SCOPES] + ["Product code"]
    order = ["Product code", "Tests", "CI and build", "Infrastructure and config", "Agent instructions and skills", "Docs and prose"]
    by_m = defaultdict(Counter)
    by_stage = defaultdict(Counter)
    sec_m, fix_m = Counter(), Counter()
    n = 0
    for f in cs_nondep(con):
        wt = lab.get((f["repo"], f["unit_kind"], f["unit_id"], f["set_idx"]))
        if wt not in ("fix", "security"):
            continue
        paths = [p for sha in f["shas"] for p in files.get((f["repo"], sha), [])]
        if not paths:
            continue
        sc = Counter(scope_of(p) for p in paths).most_common(1)[0][0]
        n += 1
        by_m[f["month"]][sc] += 1
        by_stage[f["stage"]][sc] += 1
        (sec_m if wt == "security" else fix_m)[f["month"]] += 1
    series = {s: [by_m[m][s] for m in MONTHS] for s in order}
    stage_share = {s: {k: round(by_stage[s][k] / sum(by_stage[s].values()), 3) for k in order}
                   for s in STAGES if sum(by_stage[s].values()) >= 20}
    total = Counter()
    for m in MONTHS:
        total.update(by_m[m])
    return {"months": MONTHS, "series": series, "order": order, "stage_share": stage_share, "n": n,
            "total": {k: total[k] for k in order}, "security": sum(sec_m.values()), "fix": sum(fix_m.values()),
            "sec_share_m": [round(sec_m[m] / (sec_m[m] + fix_m[m]), 3) if sec_m[m] + fix_m[m] >= 10 else None for m in MONTHS]}


# ------------------------------------------------------------------ Q done-not-done

def q_done_not_done_overclaim(con):
    """Weekly evidence that "done" was not done: judge send-backs, logged overclaims, fix-ups of a claim."""
    judge = [r for r in rows(con, "SELECT repo, submitted_ts ts, body_redacted b FROM github.pr_reviews "
                                  "WHERE reviewer='github-actions' AND state='CHANGES_REQUESTED'") if repo_ok(con, r["repo"])]
    reasons = Counter()
    for r in judge:
        hs = re.findall(r"^##\s*(.+?):\s*❌", r["b"] or "", re.M)
        if not hs:
            reasons["Reason not recorded (in a comment not ingested)"] += 1
        for x in set(hs):
            reasons[{"Prior Review": "No prior review on the PR", "CI": "CI not green", "PR Description": "Description claims more than the diff",
                     "Tests": "Tests missing", "Completeness": "Work incomplete"}.get(x, x)] += 1
    lm = [m for m in logged_mistakes(con) if m["is_mistake"] and (m["overclaim"] or m["theme"] == "unverified_claim")]
    fx = [f for f in fixup_commits(con) if f["fixup"] and f["theme"] == "unverified_claim"]
    series = {"Judge sent the PR back": weekly_count((week_of(r["ts"][:10]), 1) for r in judge),
              "Agent logged an overclaim": weekly_count(((m["week"], 1) for m in lm), start=ITEMS_FROM),
              "Fix-up of an unverified claim": weekly_count((f["week"], 1) for f in fx)}
    judged = rows(con, "SELECT COUNT(*) n FROM github.pr_reviews WHERE reviewer='github-actions' AND state IN ('APPROVED','CHANGES_REQUESTED')")[0]["n"]
    # Figure 4.3 counts PRs, not verdicts: a PR sent back twice is one PR that did not survive checking.
    verdicts = [r for r in rows(con, "SELECT repo, number, state FROM github.pr_reviews WHERE reviewer='github-actions' "
                                     "AND state IN ('APPROVED','CHANGES_REQUESTED')") if repo_ok(con, r["repo"])]
    prs_judged = {(r["repo"], r["number"]) for r in verdicts}
    prs_back = {(r["repo"], r["number"]) for r in verdicts if r["state"] == "CHANGES_REQUESTED"}
    all_lm = [m for m in logged_mistakes(con) if m["is_mistake"]]
    # Overlap audit: an overclaim names its work item, never a PR; the item's recorded PR, branch or goal branch
    # leads to the merged PR, and that PR is checked against the judge's send-backs.
    ghprs = rows(con, "SELECT repo, number, head_ref FROM github.prs WHERE merged_ts IS NOT NULL")
    by_head = defaultdict(set)
    for r in ghprs:
        by_head[(r["repo"], r["head_ref"])].add(r["number"])
    items = {(r["repo"], r["item_id"]): r for r in rows(con, "SELECT repo, item_id, type, goal_id, raw_frontmatter_json j "
                                                              "FROM plans.plan_items")}
    goal_branch = {k: json.loads(v["j"] or "{}").get("branch") for k, v in items.items() if v["type"] == "goal"}

    def item_prs(repo, iid):
        it = items.get((repo, str(iid)))
        if not it:
            return set()
        fm = json.loads(it["j"] or "{}")
        got = set()
        for k in ("pr", "merged_pr", "merged_prs"):
            v = fm.get(k)
            for x in (v if isinstance(v, list) else [v]):
                m = re.search(r"(\d+)$", str(x)) if x is not None else None
                if m:
                    got.add(int(m.group(1)))
        if fm.get("branch"):
            got |= by_head.get((repo, fm["branch"]), set())
        if it["goal_id"] and goal_branch.get((repo, it["goal_id"])):
            got |= by_head.get((repo, goal_branch[(repo, it["goal_id"])]), set())
        return got
    linked = [m for m in lm if item_prs(m["repo"], m["item_id"])]
    overlap = [m for m in linked if any((m["repo"], n) in prs_back for n in item_prs(m["repo"], m["item_id"]))]
    themes = Counter(THEME_NAMES.get(m["theme"], m["theme"]) for m in lm)
    return {"weeks": WEEKS, "series": series, "reasons": dict(reasons.most_common()), "n_judge": len(judge), "judged": judged,
            "n_lm": len(lm), "n_fx": len(fx), "events": GUARD_EVENTS,
            "examples": [m["summary"] for m in lm if m["summary"]][:8],
            "prs_judged": len(prs_judged), "prs_back": len(prs_back), "n_all_lm": len(all_lm),
            "lm_first_day": min(m["day"] for m in all_lm) if all_lm else None,
            "lm_linked": len(linked), "lm_overlap": len(overlap), "themes": dict(themes.most_common()),
            "lm_caught_by": dict(Counter(CATCHER_NAMES.get(m["caught_by"], m["caught_by"]) for m in lm).most_common())}


# ------------------------------------------------------------------ Q reviewer-and-judge-changes

SECTIONS = ["Prior Review", "Unresolved Comments", "CI", "PR Description", "Tests", "Completeness"]


def q_reviewer_and_judge_changes(con):
    rv = [r for r in rows(con, "SELECT repo, reviewer, state, submitted_ts ts, body_redacted b FROM github.pr_reviews")
          if repo_ok(con, r["repo"]) and r["ts"]]
    judge = [r for r in rv if r["reviewer"] == "github-actions" and r["state"] in ("APPROVED", "CHANGES_REQUESTED")]
    cr = weekly_count((week_of(r["ts"][:10]), 1) for r in judge if r["state"] == "CHANGES_REQUESTED")
    al = weekly_count((week_of(r["ts"][:10]), 1) for r in judge)
    cop = weekly_count((week_of(r["ts"][:10]), 1) for r in rv if r["reviewer"].startswith("copilot"))
    prs = pr_units(con)
    w_prs = weekly_count((v["week"], 1) for v in prs.values())
    by_m = defaultdict(Counter)
    tot_m = Counter()
    for r in judge:
        m = r["ts"][:7]
        tot_m[m] += 1
        for s in SECTIONS:
            if re.search(rf"^##\s*{re.escape(s)}\s*:", r["b"] or "", re.M):
                by_m[s][m] += 1
    sections = {s: [round(by_m[s][m] / tot_m[m], 3) if tot_m[m] >= 10 else None for m in MONTHS] for s in SECTIONS}
    first_seen = {s: min((r["ts"][:10] for r in judge if re.search(rf"^##\s*{re.escape(s)}\s*:", r["b"] or "", re.M)), default=None)
                  for s in SECTIONS}
    rate = share(cr, al)
    return {"weeks": WEEKS, "series": {"Judge send-back rate": rate,
                                       "Copilot reviews per merged PR": [round(c / p, 2) if p and p >= 5 else None for c, p in zip(cop, w_prs)]},
            "sections": sections, "first_seen": first_seen, "months": MONTHS, "events": JUDGE_EVENTS,
            "n_judge": len(judge), "n_cr": sum(1 for r in judge if r["state"] == "CHANGES_REQUESTED"),
            "rate_all": round(sum(1 for r in judge if r["state"] == "CHANGES_REQUESTED") / len(judge), 3),
            "rate_recent": mean_known(rate[-6:]), "rate_mid": mean_known(rate[26:33])}


# ------------------------------------------------------------------ Q review-persona-value

PERSONA_TYPES = ["code-reviewer", "silent-failure-hunter", "pr-test-analyzer", "comment-analyzer", "type-design-analyzer"]


def q_review_persona_value(con):
    runs = rows(con, "SELECT ts_start ts, subagent_type t, cost_usd_est c FROM harness.subagent_runs WHERE subagent_type LIKE 'pr-review-toolkit:%'")
    by_t = defaultdict(Counter)
    cost = Counter()
    for r in runs:
        t = r["t"].split(":", 1)[1]
        if r["ts"]:
            by_t[t][week_of(r["ts"][:10])] += 1
        cost[t] += r["c"] or 0
    series = {t: [None if (w in NO_DATA_WEEKS or w < SESSIONS_FROM) else by_t[t].get(w, 0) for w in WEEKS] for t in PERSONA_TYPES}
    f = rows(con, "SELECT * FROM mistakes.persona_findings")
    stats = {}
    for t in PERSONA_TYPES + ["security"]:
        mine = [x for x in f if x["persona"] == t]
        uniq = [x for x in mine if x["also"] in ("[]", None, "")]
        stats[t] = {"findings": len(mine), "unique": len(uniq), "high": sum(1 for x in uniq if x["severity"] == "high"),
                    "fixed": sum(1 for x in mine if x["disposition"] == "fixed"),
                    "deferred": sum(1 for x in mine if x["disposition"] == "deferred"),
                    "disputed": sum(1 for x in mine if x["disposition"] == "disputed"),
                    "runs": sum(by_t[t].values()), "cost": round(cost[t], 2),
                    "per_unique": round(cost[t] / len(uniq), 2) if uniq and cost[t] else None}
    sess = rows(con, "SELECT * FROM mistakes.persona_sessions")
    clean = Counter()
    ran = Counter()
    for s in sess:
        for p in json.loads(s["ran"] or "[]"):
            ran[p] += 1
        for p in json.loads(s["clean"] or "[]"):
            clean[p] += 1
    return {"weeks": WEEKS, "series": series, "stats": stats, "n_sessions": len(sess), "n_findings": len(f),
            "ran": dict(ran), "clean": dict(clean), "n_runs": len(runs)}


# ------------------------------------------------------------------ Q hollow-checks

GBE_RX = re.compile(r"could not fail|cannot fail|couldn't fail|proves? nothing|proving nothing|silent(ly)? pass|false[- ]clean|"
                    r"never ran|ran nothing|green but|passes? (against|on) (both|the old)|always pass|vacuous|no-op check|"
                    r"swallow(s|ed)? (its|the) exit", re.I)


def q_hollow_checks(con):
    """Cases where a test, check or gate reported success without checking, and who noticed."""
    lm = [m for m in logged_mistakes(con) if m["is_mistake"] and m["green_but_empty"]]
    subj = [f for f in fixup_commits(con) if GBE_RX.search(f["subject"])]
    main = [r for r in rows(con, "SELECT repo, day, subject, body_redacted b FROM git.commits WHERE is_merge = 0")
            if repo_ok(con, r["repo"]) and GBE_RX.search((r["subject"] or "") + " " + (r["b"] or "")[:600])]
    cases = [("log", m["repo"], m["day"], m["summary"], m["caught_by"]) for m in lm]
    cases += [("fix-up", f["repo"], f["merged_day"], f["subject"][:100], f["trigger"]) for f in subj]
    seen_prs = {(f["repo"], f["merged_day"]) for f in subj}
    cases += [("main", r["repo"], r["day"], r["subject"][:100], "unknown") for r in main if (r["repo"], r["day"]) not in seen_prs]
    who = Counter(CATCHER_NAMES.get(c[4], c[4]) for c in cases)
    series = {"Found in a log": weekly_count((week_of(c[2]), 1) for c in cases if c[0] == "log"),
              "Found in a commit": weekly_count((week_of(c[2]), 1) for c in cases if c[0] != "log")}
    return {"weeks": WEEKS, "series": series, "n": len(cases), "who": dict(who.most_common()),
            "by_repo": dict(Counter(c[1] for c in cases).most_common(6)),
            "examples": [f"{c[1]} {c[2]}: {c[3]}" for c in sorted(cases, key=lambda c: c[2])[-10:]]}


# ------------------------------------------------------------------ Q found-problem-follow-up

def q_found_problem_follow_up(con):
    """Work items filed from found work (discovered_from), weekly by current status, and open-item ages."""
    items = {(r["repo"], r["item_id"]): r for r in rows(con, "SELECT repo, item_id, title, type, status, origin, created_ts, "
                                                              "done_ts FROM plans.plan_items WHERE type != 'goal'")}
    found = {(r["repo"], r["item_id"]) for r in rows(con, "SELECT repo, item_id FROM detectors.found_work WHERE depth >= 1")}
    harden = {k for k, v in items.items() if v["origin"] == "harden"}
    today = date(2026, 9, 25)
    grp = lambda s: "Done" if s in ("done", "delivered", "committed", "accepted") else "Dropped" if s == "dropped" else "Still open"
    src = {"Found while building": found, "Hardening sweep": harden - found}
    series = {}
    for name, keys in src.items():
        for st in ("Done", "Still open"):
            series[f"{name}: {st.lower()}"] = weekly_count(((week_of(items[k]["created_ts"][:10]), 1) for k in keys
                                                           if k in items and items[k]["created_ts"] and grp(items[k]["status"]) == st),
                                                           start=ITEMS_FROM)
    open_ages = []
    for k, v in items.items():
        if grp(v["status"]) == "Still open" and v["created_ts"] and repo_ok(con, k[0]):
            open_ages.append((( today - date.fromisoformat(v["created_ts"][:10])).days, k, v))
    open_ages.sort(key=lambda x: -x[0])
    bins = [("Under 7 days", 0, 6), ("7–13", 7, 13), ("14–29", 14, 29), ("30–59", 30, 59), ("60+", 60, 10 ** 6)]
    kinds = {"Found while building": lambda k: k in found, "Hardening sweep": lambda k: k in harden and k not in found,
             "Other": lambda k: k not in found and k not in harden}
    age_hist = {n: [sum(1 for a, k, _ in open_ages if f(k) and lo <= a <= hi) for _, lo, hi in bins] for n, f in kinds.items()}
    done_rate = {n: (round(sum(1 for k in keys if k in items and grp(items[k]["status"]) == "Done") / max(1, len(keys & items.keys())), 3),
                     len(keys & items.keys())) for n, keys in src.items()}
    pf = rows(con, "SELECT disposition, COUNT(*) n FROM mistakes.persona_findings GROUP BY 1")
    return {"weeks": WEEKS, "series": series, "bins": [b[0] for b in bins], "age_hist": age_hist, "done_rate": done_rate,
            "n_open": len(open_ages), "oldest": [(a, k[0], v["item_id"], v["title"], v["origin"]) for a, k, v in open_ages[:5]],
            "persona_disposition": {r["disposition"]: r["n"] for r in pf}}


# ------------------------------------------------------------------ Q replanning-after-ready

REPLAN_RX = re.compile(r"re-?plan|re-?grill|plan (was|is) wrong|premise (was )?wrong|scope (changed|grew)|re-?scoped|"
                       r"back to planning|un-?ready|not ready after all|reopen", re.I)


def q_replanning_after_ready(con):
    """Ready-marked work items: how they were readied, and whether they later needed replanning."""
    logs = defaultdict(list)
    for r in rows(con, "SELECT repo, item_id, ts, kind, text_redacted t FROM plans.item_logs"):
        logs[(r["repo"], r["item_id"])].append(r)
    ml = defaultdict(list)
    for m in logged_mistakes(con):
        if m["is_mistake"] and m["item_id"]:
            ml[(m["repo"], m["item_id"])].append(m)
    items = [r for r in rows(con, "SELECT repo, item_id, status, origin, ready_ts, body_chars FROM plans.plan_items "
                                  "WHERE type != 'goal' AND ready_ts IS NOT NULL") if repo_ok(con, r["repo"])]
    res = []
    for it in items:
        k = (it["repo"], it["item_id"])
        rd = it["ready_ts"][:10]
        text = " ".join((x["t"] or "") for x in logs[k])
        grilled = bool(re.search(r"grill", text, re.I)) and not re.search(r"skipped the grill|no grill", text, re.I)
        path = ("Grilled, then ready" if grilled else "Harden recipe or bot PR as the plan"
                if (it["origin"] == "harden" or re.search(r"recipe|bot's PR", text, re.I)) else "Ready without a grill")
        after = [x for x in logs[k] if (x["ts"] or "")[:10] >= rd]
        replan = any(REPLAN_RX.search(x["t"] or "") for x in after) or any(
            m["theme"] in ("plan_gap",) and m["day"] >= rd for m in ml[k])
        res.append({"path": path, "replan": replan, "week": week_of(rd), "dropped": it["status"] == "dropped"})
    paths = ["Grilled, then ready", "Ready without a grill", "Harden recipe or bot PR as the plan"]
    by_path = {p: (round(sum(1 for r in res if r["path"] == p and r["replan"]) / max(1, sum(1 for r in res if r["path"] == p)), 3),
                   sum(1 for r in res if r["path"] == p)) for p in paths}
    w_all = weekly_count(((r["week"], 1) for r in res), start=ITEMS_FROM)
    w_rep = weekly_count(((r["week"], 1) for r in res if r["replan"]), start=ITEMS_FROM)
    return {"weeks": WEEKS, "series": {"Needed replanning after the ready-mark": share(w_rep, w_all, min_n=5)},
            "counts": {"Ready-marked items": w_all}, "by_path": by_path, "n": len(res), "n_replan": sum(r["replan"] for r in res),
            "n_dropped": sum(r["dropped"] for r in res)}


# ------------------------------------------------------------------ Q errors-vs-corrections

def q_errors_vs_corrections(con):
    """Tool-call error rate and owner correction rate, weekly, from session logs."""
    calls = rows(con, "SELECT ts, tool, is_error FROM harness.tool_calls WHERE ts IS NOT NULL")
    n, e, ag, age = Counter(), Counter(), Counter(), Counter()
    by_tool = defaultdict(lambda: [0, 0])
    for r in calls:
        w = week_of(r["ts"][:10])
        n[w] += 1
        e[w] += r["is_error"] or 0
        by_tool[r["tool"]][0] += r["is_error"] or 0
        by_tool[r["tool"]][1] += 1
        if r["tool"] == "Agent":
            ag[w] += 1
            age[w] += r["is_error"] or 0
    corr = owner_corrections(con)
    from facts import has_table
    if has_table(con, "detectors", "prompt_intent"):
        prompts = Counter(week_of(r["ts"][:10]) for r in rows(con, "SELECT ts FROM detectors.prompt_intent WHERE ts IS NOT NULL"))
    else:
        prompts = Counter(week_of(r["ts"][:10]) for r in rows(con, "SELECT ts FROM harness.prompts WHERE ts IS NOT NULL "
                                                                  "AND is_slash_command = 0"))
    ok = lambda w: w >= SESSIONS_FROM and w not in NO_DATA_WEEKS
    err = [round(100 * e[w] / n[w], 2) if ok(w) and n[w] >= 200 else None for w in WEEKS]
    cor = [round(100 * corr[w] / prompts[w], 1) if prompts[w] >= 20 else None for w in WEEKS]
    top = sorted(((t, v[0] / v[1], v[1]) for t, v in by_tool.items() if v[1] >= 150), key=lambda x: -x[1])[:8]
    return {"weeks": WEEKS, "series": {"Tool calls that errored, per 100": err, "Owner corrections per 100 prompts": cor},
            "by_tool": [(t, round(100 * r, 2), c) for t, r, c in top], "n_calls": sum(n.values()), "n_err": sum(e.values()),
            "agent_err": (sum(age.values()), sum(ag.values())),
            "err_first": next((v for v in err if v is not None), None), "err_last": next((v for v in reversed(err) if v is not None), None),
            "cor_first": next((v for v in cor if v is not None), None), "cor_last": next((v for v in reversed(cor) if v is not None), None),
            "known_weeks": [w for w, v in zip(WEEKS, err) if v is not None],
            "err_min": min(v for v in err if v is not None), "err_max": max(v for v in err if v is not None),
            "cor_early": mean_known(cor[:26]), "cor_recent": mean_known(cor[31:]),
            "n_corr": sum(corr.values()), "n_prompts": sum(prompts.values())}


def all_data():
    con = con_()
    out = {}
    for name, fn in list(globals().items()):
        if name.startswith("q_") and callable(fn) and getattr(fn, "__module__", None) == __name__:
            out[name] = fn(con)
    return out


if __name__ == "__main__":
    d = all_data()
    for k, v in d.items():
        print("=" * 10, k)
        for kk, vv in v.items():
            if kk in ("weeks", "months"):
                continue
            s = json.dumps(vv, default=str)
            print(f"  {kk}: {s[:600]}")
