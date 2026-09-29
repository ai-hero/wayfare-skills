"""Drawn figures for the book's Chapter 2 cards in this deck: 2.3 (Q work-sources) and 2.4 (Q goal-duration-and-scope).

Each function takes the deck's data, draws the figure with figure_lib, writes its summary table and returns
the PNG path the answer slide places with F.picture. Run through deck.py with /tmp/pptxenv/bin/python3.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import deck_lib as L  # noqa: E402
import figure_lib as F  # noqa: E402

ITEMS_FROM_WEEK = "2026-W30"
SOURCE_GROUP = {"Found in other work": "Discovered", "Roadmap sync": "Policy", "Security audit": "Policy",
                "Owner asked": "Requested", "Another repo's message": "Requested", "Not recorded": "Not recorded"}


def fig_2_3(x):
    """Left: items opened and closed per week with the open backlog at each week's end. Right: items by source,
    split by what became of them, with the longest discovery chain named."""
    b = x["backlog"]
    weeks = [w for w in b["weeks"] if w >= ITEMS_FROM_WEEK]
    idx = [b["weeks"].index(w) for w in weeks]
    opened = [b["series"]["Opened"][i] or 0 for i in idx]
    closed = [b["series"]["Closed"][i] or 0 for i in idx]
    open_end = [b["open_end"][i] for i in idx]
    fig, (ax1, ax2) = F.fig(ncols=2, gridspec_kw={"width_ratios": [1.15, 1]})

    xs = list(range(len(weeks)))
    ax1.bar([i - 0.2 for i in xs], opened, width=0.4, color=F.GREY, label=f"Opened ({sum(opened)})")
    ax1.bar([i + 0.2 for i in xs], closed, width=0.4, color=F.PINK, label=f"Closed ({sum(closed)})")
    ax1.plot(xs, open_end, color=F.GREY_DARK, marker="o", markersize=4, linewidth=1.6, label="Open at week end")
    peak_i = open_end.index(max(open_end))
    ax1.annotate(f"peak {open_end[peak_i]}", (peak_i, open_end[peak_i]), xytext=(0, 8), textcoords="offset points",
                 ha="center", fontsize=9, color=F.GREY_DARK)
    ax1.annotate(str(open_end[0]), (0, open_end[0]), xytext=(0, 8), textcoords="offset points", ha="center",
                 fontsize=9, color=F.GREY_DARK)
    ax1.set_xticks(xs)
    ax1.set_xticklabels([L.wlabel(w) for w in weeks], rotation=60, ha="right", fontsize=8.5)
    ax1.set_ylabel("Work items")
    ax1.set_xlabel("Week of 2026 (from 23 Jul; last week partial)")
    ax1.set_title("Opened, closed and open at week end", loc="left")
    ax1.legend(loc="upper left")
    ax1.grid(axis="x", visible=False)

    sources = x["sources"]
    names = x["outcome_names"]
    cols = {"Completed": F.PINK, "Still open": F.GREY, "Abandoned": F.GREY_DARK}
    ys = list(range(len(sources)))[::-1]
    left = [0] * len(sources)
    for name in names:
        vals = [x["outcomes"][s].get(name, 0) for s in sources]
        ax2.barh(ys, vals, left=left, color=cols[name], edgecolor="white", linewidth=1, height=0.62, label=name)
        for y, v, l, s in zip(ys, vals, left, sources):
            tot = sum(x["outcomes"][s].values())
            if name == "Completed" and tot and v >= 60:
                ax2.text(l + v / 2, y, f"{v / tot:.0%}", ha="center", va="center", fontsize=8.5, color="white")
        left = [a + v for a, v in zip(left, vals)]
    for y, s, tot in zip(ys, sources, left):
        ax2.text(tot + 4, y, f"n={tot}", va="center", fontsize=8.5, color=F.MUTED)
    ax2.set_yticks(ys)
    ax2.set_yticklabels([f"{s}\n({SOURCE_GROUP[s].lower()})" if SOURCE_GROUP[s] != "Not recorded" else s for s in sources],
                        fontsize=8.5)
    ax2.set_xlim(0, max(left) * 1.25)
    chain = x["chain_example"]
    first, last = (chain[0].split(":")[0], chain[-1].split(":")[0]) if chain else ("", "")
    ax2.set_xlabel(f"n={x['n']} items since 23 Jul; completed = shipped or delivered upstream\n"
                   f"Longest chain: {x['max_depth']} hops, {len(chain)} items ({first} → … → {last.split()[-1]})",
                   fontsize=9, loc="right")
    ax2.set_title("Items by source and outcome", loc="left")
    ax2.legend(loc="lower right", ncol=1, fontsize=8.5)
    ax2.grid(axis="y", visible=False)
    png = F.save(fig, F.asset("2.3"))

    rows = [[w, o, c, e] for w, o, c, e in zip(weeks, opened, closed, open_end)]
    rows2 = [[s, SOURCE_GROUP[s]] + [x["outcomes"][s].get(n, 0) for n in names] + [sum(x["outcomes"][s].values())]
             for s in sources]
    F.summary("2.3", question="How much work did the factory discover while building, how often was discovered work "
                              "completed and did intake and closure keep pace well enough to prevent the open backlog from growing?",
              params={"items_from": "2026-07-23", "weeks": [weeks[0], weeks[-1]], "completed": ["Shipped", "Delivered upstream"],
                      "abandoned": ["Dropped", "Obsolete / rejected"], "found": "discovered_from edge to a real item, or origin self-review",
                      "security_audit": "origin harden, or an old-schema discovered_from naming the harden audit",
                      "open_today": b["open_now"], "open_today_undated": b["open_now"] - (open_end[-1] or 0)},
              columns=["week", "opened", "closed", "open_at_week_end"], table=rows,
              extra={"by_source": {"columns": ["source", "group"] + names + ["n"], "table": rows2},
                     "chain_depth": x["depth"], "n_found_chain": x["n_found"], "roots": x["roots"],
                     "longest_chain": chain, "peak_open": b["peak_open"], "peak_week": b["peak_week"],
                     "weeks_closed_ge_opened": b["weeks_closed_ge_opened"], "n_weeks": b["n_weeks"]},
              notes="Left panel: items created and ended per ISO week (day-level dates from the item's log); open at week end = "
                    "created on or before the Sunday and not ended by it. Goals excluded. Items with no dated log line count in "
                    "'open today' but not in the weekly line. Right panel: every non-goal item since 23 Jul by source and outcome; "
                    "the per-source outcome is the item's ending today, so recent items are more often open whatever their source.",
              sources=["plans.plan_items", "plans.item_edges (discovered_from)", "detectors.found_work", "github.prs"])
    return png


def _hist(ax, dist, cap=None, color=F.PINK, xlabel=None, title=None, median=None, p80=None):
    keys = sorted(dist)
    if cap is not None:
        vals = {k: 0 for k in range(cap + 1)}
        for k, v in dist.items():
            vals[min(k, cap)] += v
        keys = list(range(cap + 1))
        labels = [str(k) if k < cap else f"{cap}+" for k in keys]
    else:
        vals = dist
        labels = [str(k) for k in keys]
    ax.bar(range(len(keys)), [vals[k] for k in keys], color=color, width=0.7)
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels(labels)
    ax.grid(axis="x", visible=False)
    if xlabel:
        ax.set_xlabel(xlabel)
    if title:
        ax.set_title(title, loc="left")
    top = max(vals[k] for k in keys)
    ax.set_ylim(0, top * 1.18)
    top = top * 1.16
    if median is not None:
        ax.axvline(keys.index(min(median, cap) if cap is not None else median), color=F.GREY_DARK, linewidth=1,
                   linestyle=(0, (2, 3)))
        ax.text(keys.index(min(median, cap) if cap is not None else median) + 0.15, top, f"median {median:g}",
                fontsize=8.5, color=F.GREY_DARK, va="top")
    if p80 is not None:
        ax.text(0.98, 0.95, f"80th pct {p80:g}", transform=ax.transAxes, ha="right", va="top", fontsize=8.5, color=F.MUTED)


def fig_2_4(g, p):
    """Four small multiples: items per goal, days to done, items added after the goal started, and work items per
    merged PR before and after 'one commit per feature' (18 Sep)."""
    fig, axs = F.fig(ncols=2, nrows=2)
    (a, b), (c, d) = axs
    _hist(a, {int(k): v for k, v in g["members_dist"].items()}, cap=8, xlabel=f"Work items in the goal ({g['n']} goals)",
          title="Goal size", median=g["median_members_all"])
    a.set_ylabel("Goals")
    _hist(b, {int(k): v for k, v in g["days_dist"].items()}, cap=10, color=F.GREY_DARK,
          xlabel=f"Days from created to done ({g['n_done']} finished goals)", title="Goal duration", median=g["median_days"],
          p80=g["p80_days"])
    later = {int(k): v for k, v in g["later_dist"].items()}
    _hist(c, later, cap=3, color=F.PINK_LIGHT, xlabel=f"Items filed after the goal started ({g['n']} goals)",
          title="Scope growth after the start")
    c.set_ylabel("Goals")
    lo, hi = F.wilson(g["grew"], g["n"])
    c.text(0.98, 0.95, f"{g['grew']} of {g['n']} grew ({g['grew_share']:.0%}; 95% CI {lo:.0%}–{hi:.0%}),\n"
                       f"{g['grew_how']['Log says items joined']} of them known only from a log line",
           transform=c.transAxes, ha="right", va="top", fontsize=8.5, color=F.MUTED)
    dist = p["ipp_dist"]
    cats = [1, 2, 3, 4]
    def bucket(dd):
        out = {k: 0 for k in cats}
        for k, v in dd.items():
            out[min(int(k), 4)] += v
        return out
    bef, aft = bucket(dist["before"]), bucket(dist["after"])
    nb, na = sum(bef.values()), sum(aft.values())
    xs = list(range(len(cats)))
    d.bar([i - 0.2 for i in xs], [bef[k] / nb for k in cats], width=0.4, color=F.GREY_DARK,
          label=f"Before 18 Sep ({nb} PRs, mean {p['ipp_before_after'][0]})")
    d.bar([i + 0.2 for i in xs], [aft[k] / na for k in cats], width=0.4, color=F.PINK,
          label=f"From 18 Sep ({na} PRs, mean {p['ipp_before_after'][1]})")
    d.set_xticks(xs)
    d.set_xticklabels(["1", "2", "3", "4+"])
    d.yaxis.set_major_formatter(F.matplotlib.ticker.PercentFormatter(1.0))
    d.set_ylabel("Share of PRs")
    d.set_xlabel("Shipped work items reaching the merged PR")
    d.set_title("Work items per pull request", loc="left")
    d.legend(loc="upper right", fontsize=8.5)
    d.grid(axis="x", visible=False)
    png = F.save(fig, F.asset("2.4"))
    F.summary("2.4", question="How did goals change the relationship among work items, change sets and pull requests, and "
                              "what do the distributions of goal size, duration and scope growth show beyond the medians?",
              params={"goals_from": "2026-08-28", "bundling_change": "2026-09-18", "n_goals": g["n"], "n_done": g["n_done"],
                      "grew": "a member created after the goal's day, or a goal log line saying items joined or were re-cut"},
              columns=["panel", "value", "count"],
              table=[["items_per_goal", k, v] for k, v in sorted(g["members_dist"].items())] +
                    [["days_to_done", k, v] for k, v in sorted(g["days_dist"].items())] +
                    [["items_added_after_start", k, v] for k, v in sorted(g["later_dist"].items())] +
                    [["items_per_pr_before", k, v] for k, v in sorted(dist["before"].items())] +
                    [["items_per_pr_after", k, v] for k, v in sorted(dist["after"].items())],
              extra={"median_items": g["median_members_all"], "median_items_done_goals": g["median_members"],
                     "median_days": g["median_days"], "p80_days": g["p80_days"], "grew": g["grew"], "grew_share": g["grew_share"],
                     "grew_ci95": [lo, hi], "grew_how": g["grew_how"], "later_members": g["later_members"],
                     "all_members": g["all_members"], "items_per_pr_mean": p["ipp_before_after"]},
              notes="Descriptive: the before/after split is a calendar cut at the 'one commit per feature' change, not a "
                    "controlled comparison; goals, the bundling rule and the September clones arrived together. Items per PR counts "
                    "distinct shipped items reaching a merged PR (its recorded PR or branch, its goal's PR, or a commit naming it).",
              sources=["plans.plan_items", "plans.goals", "plans.item_logs", "github.prs", "git.commits"])
    return png
