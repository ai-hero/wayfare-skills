"""Open the cube: one in-memory SQLite connection with the shared data/*.sqlite ATTACHed under their source
names (SHARED), any label caches the caller names, and cube/views.sql applied."""
import glob, os, re, sqlite3, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(os.path.dirname(HERE), ".analysis", "data")
_warned = set()


def _warn(msg):
    if msg not in _warned:
        _warned.add(msg)
        print(f"cube: {msg}", file=sys.stderr)


# The ingest and detector databases every query can use. Any other *.sqlite is one topic's label
# cache, attached only when named: SQLite attaches at most 10 databases to one connection.
# A topic folder must never take a SHARED name (hence agent_harness, not harness): its label cache
# would be the same file as the shared source, and writing labels would clobber the ingest.
REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "report")
SHARED = ("detectors", "git", "github", "harness", "knowledge", "plans", "pr_commits")


def connect(*topics):
    """topics: label caches to attach as well, e.g. connect("skills", "mistakes")."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    for p in sorted(glob.glob(os.path.join(DATA, "*.sqlite"))):
        stem = os.path.basename(p)[:-7]
        if stem not in SHARED and stem not in topics:
            # A topic's own cache is skipped on purpose; anything else is a source nobody listed in SHARED.
            if not os.path.isdir(os.path.join(REPORT, stem)):
                _warn(f"skipped {os.path.basename(p)}: neither in SHARED nor a topic's label cache")
            continue
        # A mistyped `sqlite3 "<db> <table>.sqlite"` creates a stray file whose name is not an
        # identifier; attaching it would break every connect(), so it is skipped.
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", stem):
            _warn(f"skipped {os.path.basename(p)!r}: its name is not an SQL identifier")
            continue
        con.execute("ATTACH DATABASE ? AS " + stem, (p,))
    views = os.path.join(HERE, "cube", "views.sql")
    attached = {r[1] for r in con.execute("PRAGMA database_list")}
    # Warn, never raise: some topics ask for a database they never write, or read it before labelling creates it.
    for name in topics:
        if name not in attached:
            _warn(f"label cache {name}.sqlite not found in {DATA}; queries on {name}.* will fail")
    # a view over a source that isn't ingested yet would fail the whole script, so each view names its sources
    block, needs = [], set()
    for line in open(views):
        if line.startswith("-- needs:"): needs = set(line[9:].split())
        block.append(line)
        if line.rstrip().endswith(";"):
            if needs <= attached:
                con.executescript("".join(block))
            else:
                view = re.search(r"CREATE\s+TEMP\s+VIEW\s+(\w+)", "".join(block), re.I)
                _warn(f"skipped view {view.group(1) if view else '?'}: missing {', '.join(sorted(needs - attached))}")
            block, needs = [], set()
    return con

if __name__ == "__main__":
    con = connect()
    for r in con.execute("PRAGMA database_list"): print("attached", r[1])
    for r in con.execute("SELECT name FROM temp.sqlite_master WHERE type='view' ORDER BY name"): print("view", r[0])
