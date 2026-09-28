"""Who really acted on GitHub: the owner, an agent using the owner's account, a bot, or another person.

Agents post reviews, approvals and thread replies through `gh` with the owner's token, so
GitHub credits `rparundekar` for work no human did. Rules, per review:

- A bot account (reviewer_is_bot) is a bot.
- A review under the owner's account with a body is an agent's: every such body is a
  skill's template (a "## Review Summary", "## Self-review", a Dependabot verdict) and none
  is a short human note. Checked by reading them all (there are 124).
- An empty COMMENTED review on a PR the owner's account opened is a reply in a comment
  thread (GitHub files a thread reply as a review; an author can't review their own PR).
  It is an agent's when a respond/review/ship/one-shot/goal/push command ran in the same
  repo in the 3 hours before; otherwise it is unclear.
- An empty review under the owner's account on someone else's PR (the second human's) is
  the owner's own: the GitHub UI's approve button, with no text.
- Any other non-bot account is a human.

    human_reviews(con) -> {(repo, number): True if a person reviewed that merged PR}
"""
import bisect
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from functools import lru_cache

OWNER = "rparundekar"
AGENT_CMD = re.compile(r"respond|review|ship|one-shot|goal|push|wayfare|build-task|advance")
WINDOW_S = 3 * 3600


def _t(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


@lru_cache(maxsize=None)
def _agent_commands(con):
    out = defaultdict(list)
    for r in con.execute("SELECT repo, ts, command FROM harness.prompts WHERE is_slash_command = 1"):
        if r[2] and AGENT_CMD.search(r[2]):
            out[r[0]].append(_t(r[1]))
    for v in out.values():
        v.sort()
    return out


def _command_before(cmds, repo, ts):
    v = cmds.get(repo, [])
    i = bisect.bisect_right(v, ts)
    return i > 0 and ts - v[i - 1] <= WINDOW_S


@lru_cache(maxsize=None)
def review_actors(con):
    """Every review with `actor` in owner / agent / bot / human / unclear and the rule that decided it."""
    cmds = _agent_commands(con)
    out = []
    for r in con.execute("""SELECT r.repo, r.number, r.reviewer, r.reviewer_is_bot, r.state, r.submitted_ts,
                                   COALESCE(r.body_redacted, '') body, p.author, p.merged_ts
                            FROM github.pr_reviews r JOIN github.prs p ON p.repo = r.repo AND p.number = r.number"""):
        r = dict(r)
        if r["reviewer_is_bot"]:
            actor, why = "bot", "bot account"
        elif r["reviewer"] != OWNER:
            actor, why = "human", "another person's account"
        elif r["body"].strip():
            actor, why = "agent", "skill template body"
        elif r["author"] == OWNER:
            if _command_before(cmds, r["repo"], _t(r["submitted_ts"])):
                actor, why = "agent", "thread reply after an agent command"
            else:
                actor, why = "unclear", "thread reply, no agent command in 3 h"
        elif r["author"] and "dependabot" in r["author"]:
            ok = _command_before(cmds, r["repo"], _t(r["submitted_ts"]))
            actor, why = ("agent", "empty, after an agent command") if ok else ("unclear", "empty, on a bot PR")
        else:
            actor, why = "owner", "empty review on another person's PR"
        out.append({**r, "actor": actor, "why": why})
    return out


def human_reviews(con):
    """{(repo, number): bool} for every merged PR: True when the owner or another person reviewed it.
    Unclear reviews count as not human; `human_reviews_upper(con)` counts them as human."""
    return _flags(con, {"owner", "human"})


def human_reviews_upper(con):
    return _flags(con, {"owner", "human", "unclear"})


def _flags(con, humans):
    got = defaultdict(bool)
    for r in review_actors(con):
        if r["merged_ts"]:
            got[(r["repo"], r["number"])] |= r["actor"] in humans
    for r in con.execute("SELECT repo, number FROM github.prs WHERE merged_ts IS NOT NULL"):
        got.setdefault((r[0], r[1]), False)
    return dict(got)


def merge_actors(con):
    """{(repo, number): actor} for merged PRs: 'human' when another person merged, 'agent' when the owner's
    account merged within 3 h of an agent command in that repo, else 'unclear' (the owner or an agent)."""
    cmds = _agent_commands(con)
    out = {}
    for r in con.execute("""SELECT p.repo, p.number, p.merged_ts, t.actor FROM github.prs p
                            LEFT JOIN github.pr_timeline t ON t.repo = p.repo AND t.number = p.number AND t.event = 'merged'
                            WHERE p.merged_ts IS NOT NULL"""):
        if r[3] and r[3] != OWNER and not r[3].endswith("[bot]"):
            out[(r[0], r[1])] = "human"
        elif _command_before(cmds, r[0], _t(r[2])):
            out[(r[0], r[1])] = "agent"
        else:
            out[(r[0], r[1])] = "unclear"
    return out


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from collections import Counter
    from cube.db import connect
    con = connect()
    print(Counter((r["reviewer"] if r["reviewer"] == OWNER else "other", r["actor"], r["why"]) for r in review_actors(con)))
    h = human_reviews(con)
    print("merged PRs", len(h), "with a human review", sum(h.values()), "upper", sum(human_reviews_upper(con).values()))
    print(Counter(merge_actors(con).values()))
