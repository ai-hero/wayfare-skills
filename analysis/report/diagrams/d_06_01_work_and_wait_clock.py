"""Diagram 6.1: elapsed time decomposed, with measured session states separated from queue time and from
states the logs cannot tell apart."""
import svg_lib as S

c = S.Canvas(1400, 900)

# Band 1: the work item's queue, measured from .plans dates, not sessions.
q = c.group(40, 40, 1320, 190, "Work item queue · from .plans dates, days only")
ready = c.node(60, 100, 300, 100, "record", "Ready, not started", "picked up in a mean 1.43 days; 47% the same day")
built = c.node(420, 100, 300, 100, "agent", "Built", "sessions on its branch; the band below")
shipped = c.node(780, 100, 260, 100, "delivery", "Shipped", "median 1 day from filed; 65% within a day")
tail = c.node(1100, 100, 240, 100, "evidence", "The slow fifth", "80th percentile 1.2 days in July, 4 in September")
c.arrow(ready, built, "flow")
c.arrow(built, shipped, "flow")

# Band 2: open session hours, drawn to scale from Figure 6.3's summary, so the two cannot disagree.
import json, os
_sum = json.load(open(os.path.join(S.ROOT, ".analysis", "data", "figures", "6.3.json"), encoding="utf-8"))
_all = next(r for r in _sum["table"] if r[0] == "All weeks")
_h = _all[1]
_share = dict(zip(_sum["columns"][2:], _all[2:]))
_agent = _share["Agent working"]
_tool = _share["Agent's tool or subagent running (no main-thread turn)"]
_wait = _share["Waiting on the owner: ask tool"] + _share["Waiting on the owner: question in prose"]
_limit = _share["Stopped by a usage limit"]
_away = _share["Owner reading or away (ended by a typed prompt)"]
_rest = _share["Scheduled loop tick or session continuation"] + _share["Unclassified"]
HOURS = {k: round(_h * v) for k, v in (("agent", _agent), ("tool", _tool), ("wait", _wait), ("limit", _limit), ("away", _away))}
band = c.group(40, 290, 1320, 270, f"Open session time · {_h:,} hours · 25 Aug to 24 Sep 2026 · 10 to 24 Aug unlogged")
shares = [("working", _agent, HOURS["agent"], "agent", "Agent working", f"{_agent:.0%}"),
          ("tool", _tool, HOURS["tool"], "agent", "Tool or subagent running", f"{_tool:.0%}"),
          ("waiting_human", _wait, HOURS["wait"], "person", "Waiting on the owner", f"{_wait:.0%}"),
          ("limited", _limit, HOURS["limit"], "policy", "Usage limit", f"{_limit:.0%}"),
          ("away", _away, HOURS["away"], "plain", "Owner reading or away", f"{_away:.0%}")]
x, y0, h, W = 60, 350, 120, 1280
for key, share, hours, kind, label, pct in shares:
    w = round(W * share)
    if kind == "plain":
        c.rect(x, y0, w, h, "none", S.MUTED, 1.5, r=8)
        c.text(x + w / 2, y0 + 14, label, size=S.LABEL, weight=500, anchor="middle", color=S.MUTED, width=w - 24)
        c.text(x + w / 2, y0 + 72, f"{pct} · {hours} h · ends when the owner types", size=S.SMALL, anchor="middle",
               color=S.MUTED, width=w - 24)
    else:
        c.node(x, y0, w, h, kind, label, f"{pct} · {hours} h")
    x += w
c.text(60, 490, f"Gaps between logged turns of interactive sessions; a gap over 8 hours counts as the session closed and is "
                f"dropped. The last segment cannot tell reading a plan, reviewing on GitHub or being away apart. Waiting on the owner is an ask-tool stop ({_share['Waiting on the owner: ask tool']:.0%}) or a "
                f"question asked in prose ({_share['Waiting on the owner: question in prose']:.0%}). Loop ticks and "
                f"unclassified gaps are {_rest:.1%}. A hand audit of 17 judgeable gaps agreed with this classifier on 14.",
       size=S.SMALL, color=S.BODY, width=1280)

# Band 3: what the session logs do not hold.
nb = c.group(40, 620, 1320, 200, "Not measured on its own")
ciw = c.node(60, 680, 400, 110, "check", "CI wait", "folded into working or idle above", target=True)
dep = c.node(500, 680, 400, 110, "delivery", "Deployment", "runs are logged, but not against the session", target=True)
close = c.node(940, 680, 400, 110, "record", "Closure", "review, approval, merge: a PR merges a median 30 min after it opens", target=True)

c.legend(60, 840, kinds=("agent", "person", "policy", "evidence"), target=True, cols=5, cell=250)

S.finish(
    c, id="6.1", name="diagram-06-01-work-and-wait-clock",
    caption=f"Less than half of the open session clock is an agent or its tools working; a fifth is waiting on the owner, "
            f"a further {_away:.0%} ends only when the owner types and cannot be classified, and CI, deployment and closure "
            "are not measured on their own at all.",
    alt=f"Three bands: a work item's queue from ready to shipped, an open-session bar of {_h:,} hours split to scale "
        f"into agent working {_agent:.0%}, tool or subagent running {_tool:.0%}, waiting on the owner {_wait:.0%}, "
        f"usage limit {_limit:.0%} and owner reading or away {_away:.0%} marked as indistinguishable, and a dashed band "
        "of states not measured on their own: CI wait, deployment and closure.",
    source="Replaces D08 HOW MUCH OF THE CLOCK DOES WORK. Session shares and hours from Figure 6.3's summary "
           "(.analysis/data/figures/6.3.json: report/efficiency/data.py, gaps between logged turns of interactive "
           "sessions 25 Aug to 24 Sep 2026, 10 to 24 Aug unlogged; Q session-clock). "
           "Concurrency (median 1, p90 4) and 80% of limit hours in one week: chapter 6. Queue (mean 1.43 days, 47% "
           "same day): Q pickup-wait. Lead time (median 1 day, 65% within a day; p80 1.2 to 4 days): Q "
           "item-lead-time. PR merge 30 min after opening: Q item-lead-time, PR and item view. CI folded into "
           "session states: the Origin entry's Shows line.",
)
