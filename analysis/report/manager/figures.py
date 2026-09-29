"""Drawn figure for the manager deck's book card 7.3: the five plugin restructures and the rename's incident timeline."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import figure_lib as F  # noqa: E402

T0 = datetime(2026, 9, 21, 21, 0, tzinfo=timezone.utc)


def _h(ts):
    """Hours since 21 Sep 21:00 UTC."""
    return (datetime.fromisoformat(ts.replace("Z", "+00:00")) - T0).total_seconds() / 3600


def fig_7_3(x):
    from datetime import date
    import matplotlib.ticker as mt
    ev = x["events"]
    fig, (ax, bx) = F.fig(nrows=2, gridspec_kw={"height_ratios": [1, 1.6]})
    # Top: the five events side by side.
    labels = [date.fromisoformat(e["day"]).strftime("%-d %b") for e in ev]
    idx = list(range(len(ev)))
    w = 0.26
    series = [("Skills renamed or removed", [e["renamed"] + e["deleted"] for e in ev], F.GREY_DARK),
              ("Plugin fixes in 14 days", [e["plugin_fixes_14d"] for e in ev], F.GREY),
              ("Consumer PRs re-pointing at the plugin in 14 days", [e["repair_commits_14d"] for e in ev], F.PINK)]
    for j, (name, vals, col) in enumerate(series):
        xs = [i + (j - 1) * w for i in idx]
        ax.bar(xs, vals, width=w, color=col, label=name)
        for xx, v in zip(xs, vals):
            if v:
                ax.text(xx, v + 0.6, str(v), ha="center", va="bottom", fontsize=8.5, color=F.BODY)
    ax.set_xticks(idx)
    ax.set_xticklabels([f"{l}\n{e['repair_repos']} of {e['exposed_caller_repos']} exposed\nrepos re-pointed" for l, e in zip(labels, ev)],
                       fontsize=8.5)
    ax.set_ylim(0, max(v for _, vals, _ in series for v in vals) * 1.6)
    ax.set_ylabel("Count")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", ncol=2, fontsize=8.5)
    ax.set_title("Five restructures of the shared plugin, 2026", loc="left", fontsize=10.5, color=F.BODY)

    # Bottom: the rename, hour by hour. One lane for the plugin, one per consumer.
    waves = list(x["waves"].items())
    consumers = sorted({p["repo"] for _, ps in waves for p in ps}, key=lambda r: min(_h(p["created_ts"]) for _, ps in waves for p in ps if p["repo"] == r))
    names = ["wayfare-skills (the plugin)"] + consumers
    ys = list(range(len(names)))[::-1]
    for y, name in zip(ys, names):
        if name.startswith("wayfare-skills"):
            for p in x["plugin_prs"]:
                bx.plot([_h(p["created_ts"]), _h(p["merged_ts"])], [y, y], color=F.GREY_DARK, linewidth=6, solid_capstyle="butt")
                bx.text(_h(p["merged_ts"]) + 0.05, y + 0.32, f"#{p['number']}", fontsize=7.5, color=F.GREY_DARK, ha="left", va="center")
            continue
        for (label, ps), col in zip(waves, (F.PINK_LIGHT, F.PINK)):
            for p in ps:
                if p["repo"] == name:
                    bx.plot([_h(p["created_ts"]), _h(p["merged_ts"])], [y, y], color=col, linewidth=6, solid_capstyle="butt")
                    bx.plot([_h(p["merged_ts"])], [y], "|", color=col, markersize=9, markeredgewidth=1.5)
    rename = next(p for p in x["plugin_prs"] if p["number"] == 108)
    bx.axvline(_h(rename["merged_ts"]), color=F.PINK_DARK, linewidth=0.9, linestyle=(0, (3, 3)))
    bx.text(_h(rename["merged_ts"]) - 0.05, ys[0] + 0.9, "repository renamed (#108 merged)", fontsize=8, color=F.PINK_DARK, ha="right")
    last = max(_h(p["merged_ts"]) for _, ps in waves for p in ps)
    bx.axvline(last, color=F.PINK_DARK, linewidth=0.9, linestyle=(0, (3, 3)))
    bx.text(last - 0.05, ys[0] + 0.9, f"last consumer merged, {last - _h(rename['merged_ts']):.1f} h later", fontsize=8, color=F.PINK_DARK, ha="right")
    for (label, _), col in zip(waves, (F.PINK_LIGHT, F.PINK)):
        bx.plot([], [], color=col, linewidth=6, label=label)
    bx.plot([], [], color=F.GREY_DARK, linewidth=6, label="Plugin PR (#106 plugin renamed, #108 repo renamed, #115 caller fix)")
    bx.legend(loc="lower left", fontsize=8)
    bx.set_yticks(ys)
    bx.set_yticklabels(names, fontsize=8)
    bx.set_ylim(-0.7, len(names) + 0.6)
    bx.set_xlim(0, 8)
    bx.xaxis.set_major_locator(mt.MultipleLocator(1))
    bx.xaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: (T0.replace(hour=21) + __import__("datetime").timedelta(hours=v)).strftime("%H:%M")))
    bx.grid(axis="y", visible=False)
    bx.set_xlabel("UTC, 21 Sep 21:00 to 22 Sep 05:00: PR opened (bar start) to merged (bar end)")
    bx.set_title("The 21 September rename: every exposed consumer needed two PRs", loc="left", fontsize=10.5, color=F.BODY)
    png = F.save(fig, F.asset("7.3"))
    F.summary("7.3", question="Across all shared-plugin restructures, what downstream repair work, simultaneous breakage and recovery "
                              "time followed, and which properties distinguished the high-blast-radius rename?",
              params={"restructure": "a day on which four or more skills were renamed or removed (knowledge.skill_versions)",
                      "plugin_fixes": "wayfare-skills commits in the next 14 days whose message names a specific failure "
                                      "(manager.labels ws_reason.incident; 25 audited by hand, 25 agree)",
                      "repointing": "merged PRs in consumer repos in the next 14 days whose title names the plugin (hero-skills, "
                                    "wayfare-skills), a multi-word skill renamed or removed that day, the caller or a re-vendor; "
                                    "bodies are not searched (agents name the skill they ran)",
                      "exposed": "consumer repos whose history holds an auto-approve caller (or HERO.md) by that day, in scope",
                      "recovery": "from the repository rename (#108 merged) to the last consumer's second PR merged"},
              columns=["day", "subject", "renamed", "deleted", "added", "plugin_fixes_14d", "repair_commits_14d", "repair_repos",
                       "exposed_caller_repos", "exposed_skills_repos", "repos_repaired_within_1d", "unrepaired_caller_repos", "repairs_first_day"],
              table=[{k: e[k] for k in ("day", "subject", "renamed", "deleted", "added", "plugin_fixes_14d", "repair_commits_14d",
                                       "repair_repos", "exposed_caller_repos", "exposed_skills_repos", "repos_repaired_within_1d",
                                       "unrepaired_caller_repos", "repairs_first_day")} for e in ev],
              notes=f"Rename PRs: {[(p['number'], p['created_ts'], p['merged_ts']) for p in x['plugin_prs']]}. Consumer waves: "
                    + "; ".join(f"{k}: {len(v)} PRs, opened {min(p['created_ts'] for p in v)[11:16]} to {max(p['created_ts'] for p in v)[11:16]}, "
                                f"merged by {max(p['merged_ts'] for p in v)[11:16]} UTC" for k, v in waves)
                    + f". Consumers with both PRs: {x['consumers_both_waves']}. Plugin fixes after the rename: {x['fixes_after_rename']}. "
                    f"Auto Approve runs 21-23 Sep by conclusion: {x['aa_runs']} (a caller whose uses: path no longer resolves starts no run, "
                    "so the outage leaves no run record). Re-pointing titles per event: "
                    + "; ".join(f"{e['day']}: {e['repair_subjects']}" for e in ev),
              sources=["knowledge.skill_versions", "git.commits (wayfare-skills)", "manager.labels ws_reason", "github.prs", "github.ci_runs",
                       "git.commit_files (HERO.md, auto-approve caller first seen)"])
    return png
