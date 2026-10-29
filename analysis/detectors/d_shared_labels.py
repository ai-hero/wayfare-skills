"""Shared labels every chapter reads -> detectors.sqlite, tables prompt_intent and cs_worktype.

prompt_intent: every typed (non-slash) prompt the owner wrote, labelled with
  intent          new_work | continue | approve | correction | redirect | question | answer | meta | other
  target          app | factory | infra | none   (what the prompt is about)
  correction_kind error | taste | scope | none    (only for correction/redirect)
cs_worktype: every change set, labelled with
  work_type  feature | fix | security | refactor | test | docs | ci_build | dependency | design_ui | factory | chore
  theme      the study chapter it most belongs to (THEMES)

Both are cached by content hash; a re-run labels only what is new.
    python3 detectors/d_shared_labels.py [prompts|changesets]
"""
import hashlib, json, os, sqlite3, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import d1_changesets as D1
from ingest.fleet import OUT

DB = os.path.join(OUT, "detectors.sqlite")
THEMES = ["harness", "human_loop", "skills", "connectors", "knowledge", "architecture", "work_items", "rework",
          "security", "fleet_apps", "cross_repo", "compliance", "deploy_infra", "spend", "product"]

PROMPT_HEADER = """You label messages a software owner typed to their coding agent. For each message give:
- intent: new_work (asks for something new), continue (carry on / next step), approve (yes, go ahead, merge),
  correction (the agent did something wrong), redirect (change direction, taste or scope without a mistake),
  question (asks the agent something), answer (answers the agent's question), meta (about the process,
  tooling or the factory itself), other.
- target: app (the product being built), factory (skills, plugin, prompts, process), infra (deploy, cloud,
  CI), none.
- correction_kind: for correction or redirect only: error (a factual or technical mistake), taste (style,
  wording, design preference), scope (did too much or too little); otherwise none.

Reply with ONLY a JSON object, no prose, no fence:
{"<id>": {"intent": "...", "target": "...", "correction_kind": "..."}, ...}

Messages:
"""

CS_HEADER = """You label units of software work (change sets) from a fleet of repos. For each give:
- work_type: feature (new user-facing capability), fix (bug fix), security (hardening, CVE, auth, secrets),
  refactor, test, docs, ci_build (CI, build, tooling config), dependency (version bumps), design_ui
  (visual/UI polish, design tokens), factory (the agent process itself: skills, prompts, plans, rules,
  AGENTS.md, HERO.md), chore (other upkeep).
- theme: which of these the work most belongs to: """ + ", ".join(THEMES) + """
  (product = ordinary app work that fits none of the others).

Reply with ONLY a JSON object, no prose, no fence:
{"<id>": {"work_type": "...", "theme": "..."}, ...}

Change sets:
"""


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def run_batches(d, cache_table, items, header, per_batch, fields):
    """items: [(key_hash, text)]. Labels the uncached ones in parallel; returns total cost."""
    cached = {r[0] for r in d.execute(f"SELECT h FROM {cache_table}")}
    todo = list({k: t for k, t in items if k not in cached}.items())
    batches = [todo[i:i + per_batch] for i in range(0, len(todo), per_batch)]
    print(f"{cache_table}: {len(items)} items, {len(todo)} to label in {len(batches)} batches", file=sys.stderr)
    total = 0.0
    for round_ in range(2):
        with ThreadPoolExecutor(max_workers=D1.WORKERS) as pool:
            futs = {pool.submit(D1.call_haiku, [f"--- id={j} ---\n{t}" for j, (_, t) in enumerate(b)], header=header): b
                    for b in batches}
            for n, fut in enumerate(as_completed(futs), 1):
                b = futs[fut]
                reply, cost = fut.result()
                total += cost
                for j, (k, _) in enumerate(b):
                    v = reply.get(str(j)) if isinstance(reply, dict) else None
                    if isinstance(v, dict):
                        d.execute(f"INSERT OR REPLACE INTO {cache_table} VALUES (?,{','.join('?' * len(fields))})",
                                  (k, *[str(v.get(f, "")) for f in fields]))
                d.commit()
                if n % 20 == 0:
                    print(f"  round {round_ + 1} {n}/{len(batches)} ${total:.2f}", file=sys.stderr)
        cached = {r[0] for r in d.execute(f"SELECT h FROM {cache_table}")}
        missed = [(k, t) for k, t in todo if k not in cached]
        batches = [missed[i:i + max(5, per_batch // 4)] for i in range(0, len(missed), max(5, per_batch // 4))]
        if not missed:
            break
    if missed:
        print(f"  ! {cache_table}: {len(missed)} items still unlabelled after 2 rounds; rerun to retry them",
              file=sys.stderr)
    return total


WORK_TYPES = ["feature", "fix", "security", "refactor", "test", "docs", "ci_build", "dependency", "design_ui",
              "factory", "chore"]
# The model sometimes answers a theme with a work-type word; map those onto the nearest theme.
THEME_FIX = {"factory": "skills", "ci_build": "deploy_infra", "design_ui": "product", "dependency": "security"}
INTENTS = ["new_work", "continue", "approve", "correction", "redirect", "question", "answer", "meta", "other"]


def normalise(d, table):
    """Coerce off-list model answers onto the closed lists in place; the raw_* columns keep what the model said."""
    changed = {}

    def upd(what, sql, args=()):
        changed[what] = changed.get(what, 0) + d.execute(sql, args).rowcount

    if table == "prompt_intent":
        upd("intent", f"UPDATE prompt_intent SET intent='other' WHERE intent NOT IN ({','.join('?' * len(INTENTS))})", INTENTS)
        upd("target", "UPDATE prompt_intent SET target='none' WHERE target NOT IN ('app', 'factory', 'infra', 'none')")
        upd("correction_kind", "UPDATE prompt_intent SET correction_kind='none' "
                               "WHERE correction_kind NOT IN ('error', 'taste', 'scope', 'none')")
    print(f"{table}: normalise changed " + ", ".join(f"{n} {what}" for what, n in changed.items()), file=sys.stderr)


def normalise_worktype(work_type, theme, dependabot):
    """Coerce a cached cs_worktype label onto WORK_TYPES and THEMES -> (work_type, theme, what changed)."""
    changed = []
    w = "feature" if work_type in ("feat", "features") else work_type
    w = w if w in WORK_TYPES else "chore"
    if w != work_type:
        changed.append("work_type")
    t = THEME_FIX.get(theme, theme)
    t = t if t in THEMES else "product"
    if t != theme:
        changed.append("theme")
    # Dependabot bumps are supply-chain upkeep whatever the model guessed from the package name.
    if dependabot and (w, t) != ("dependency", "security"):
        w, t = "dependency", "security"
        changed.append("dependabot override")
    return w, t, changed


def _in(values):
    return ", ".join(f"'{v}'" for v in values)


# The CHECKs hold at INSERT, so a label is normalised before it is written, not by an UPDATE after.
CS_WORKTYPE_SCHEMA = f"""
    DROP TABLE IF EXISTS cs_worktype;
    CREATE TABLE cs_worktype ({D1.UNIT_COLS}, set_idx INTEGER NOT NULL CHECK (set_idx >= 0),
                              work_type TEXT NOT NULL CHECK (work_type IN ({_in(WORK_TYPES)})),
                              theme TEXT NOT NULL CHECK (theme IN ({_in(THEMES)})),
                              raw_work_type TEXT, raw_theme TEXT, PRIMARY KEY (repo, unit_kind, unit_id, set_idx));
"""


def prompts(con, d):
    d.execute("CREATE TABLE IF NOT EXISTS prompt_intent_cache (h TEXT PRIMARY KEY, intent TEXT, target TEXT, correction_kind TEXT)")
    rows = con.execute("SELECT ts, day, week, repo, text_redacted t FROM harness.prompts "
                       "WHERE is_slash_command = 0 AND LENGTH(TRIM(text_redacted)) > 0").fetchall()
    items = [(h(r["t"].strip()[:600]), r["t"].strip()[:600]) for r in rows]
    cost = run_batches(d, "prompt_intent_cache", items, PROMPT_HEADER, 50, ["intent", "target", "correction_kind"])
    tags = {r[0]: r[1:] for r in d.execute("SELECT * FROM prompt_intent_cache")}
    d.execute("DROP TABLE IF EXISTS prompt_intent")
    d.execute("CREATE TABLE prompt_intent (ts TEXT, day TEXT, week TEXT, repo TEXT, prompt_hash TEXT, chars INTEGER, "
              "intent TEXT, target TEXT, correction_kind TEXT, raw_intent TEXT, raw_target TEXT, raw_correction_kind TEXT)")
    unlabelled = 0
    for r, (k, _) in zip(rows, items):
        if k in tags:
            d.execute("INSERT INTO prompt_intent VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (r["ts"], r["day"], r["week"], r["repo"], k, len(r["t"]), *tags[k], *tags[k]))
        else:
            unlabelled += 1
    normalise(d, "prompt_intent")
    d.commit()
    if unlabelled:
        print(f"  ! prompt_intent: {unlabelled} prompts have no label and no row", file=sys.stderr)
    print(f"prompt_intent: {d.execute('SELECT COUNT(*) FROM prompt_intent').fetchone()[0]} rows, ${cost:.2f}")


def changesets(con, d):
    d.execute("CREATE TABLE IF NOT EXISTS cs_worktype_cache (h TEXT PRIMARY KEY, work_type TEXT, theme TEXT)")
    subjects = {}
    for r in con.execute("SELECT repo, sha, subject FROM pr_commits.pr_commits"):
        subjects[(r["repo"], r["sha"])] = r["subject"]
    for r in con.execute("SELECT repo, sha, subject FROM git.commits"):
        subjects.setdefault((r["repo"], r["sha"]), r["subject"])
    rows = con.execute("SELECT repo, unit_kind, unit_id, set_idx, label, shas_json FROM detectors.cs_sets").fetchall()
    items = []
    for r in rows:
        subs = [subjects.get((r["repo"], s), "") for s in json.loads(r["shas_json"])][:3]
        text = f"repo {r['repo']}: {r['label']} | commits: " + " ; ".join(x[:120] for x in subs if x)
        items.append((h(text), text))
    cost = run_batches(d, "cs_worktype_cache", items, CS_HEADER, 60, ["work_type", "theme"])
    tags = {r[0]: r[1:] for r in d.execute("SELECT * FROM cs_worktype_cache")}
    dependabot = {tuple(r) for r in d.execute("SELECT repo, unit_kind, unit_id FROM cs_units WHERE method='dependabot'")}
    d.executescript(CS_WORKTYPE_SCHEMA)
    unlabelled, changed = 0, {}
    for r, (k, _) in zip(rows, items):
        if k in tags:
            raw_w, raw_t = tags[k]
            w, t, what = normalise_worktype(raw_w, raw_t, (r["repo"], r["unit_kind"], r["unit_id"]) in dependabot)
            for x in what:
                changed[x] = changed.get(x, 0) + 1
            d.execute("INSERT INTO cs_worktype VALUES (?,?,?,?,?,?,?,?)",
                      (r["repo"], r["unit_kind"], r["unit_id"], r["set_idx"], w, t, raw_w, raw_t))
        else:
            unlabelled += 1
    print("cs_worktype: normalise changed " + ", ".join(f"{n} {what}" for what, n in changed.items()), file=sys.stderr)
    d.commit()
    if unlabelled:
        print(f"  ! cs_worktype: {unlabelled} change sets have no label and no row", file=sys.stderr)
    print(f"cs_worktype: {d.execute('SELECT COUNT(*) FROM cs_worktype').fetchone()[0]} rows, ${cost:.2f}")


if __name__ == "__main__":
    from cube.db import connect
    con = connect()
    d = sqlite3.connect(DB)
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("changesets", "both"):
        changesets(con, d)
    if which in ("prompts", "both"):
        prompts(con, d)
