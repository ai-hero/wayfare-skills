"""Run one or all answered question files against the cube.

Usage:
    python3 questions/runner.py                 # run every question module
    python3 questions/runner.py RQ-h1-042        # run one, by rq_id

Each questions/RQ_<id>.py module declares:
    RQ_ID    = "RQ-h1-042"          # matches bank/questions.csv rq_id
    QUESTION = "..."                # human-readable, for the printed header
    def answer(con): -> list[dict]  # con is the connected cube (cube.db.connect())

A question file never opens its own sqlite connection or re-reads a repo --
everything it needs is a query over the cube's attached sources and views.
"""
import csv, importlib, os, pkgutil, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bank.generate_human_stubs import module_name
from cube.db import connect

HERE = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(os.path.dirname(HERE), "bank", "questions.csv")
QUESTIONS_MD = os.path.join(os.path.dirname(HERE), "QUESTIONS.md")
SLUG = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")
QUESTION_LINE = re.compile(r"- \*\*Q (" + SLUG.pattern + r")\*\* \S.*")


def bank_row(rq_id):
    with open(BANK) as f:
        for row in csv.DictReader(f):
            if row["rq_id"] == rq_id:
                return row
    return None


def check_modules(mods):
    """Raise ValueError unless every module declares a string QUESTION, a callable answer, and an RQ_ID
    that is its own filename (module_name's spelling, STUB_ prefix optional) and no other module's.
    A stub left beside its real module would otherwise make `runner.py RQ_ID` run both."""
    errors, seen = [], {}
    for m in mods:
        name, rq_id = m.__name__.rsplit(".", 1)[-1], getattr(m, "RQ_ID", None)
        if not isinstance(getattr(m, "QUESTION", None), str) or not callable(getattr(m, "answer", None)):
            errors.append(f"{name}.py lacks a QUESTION string or an answer(con) function")
        if not isinstance(rq_id, str) or name not in (module_name(rq_id), module_name(rq_id).removeprefix("STUB_")):
            errors.append(f"{name}.py declares RQ_ID {rq_id!r}, which does not match its filename")
        elif rq_id in seen:
            errors.append(f"{name}.py and {seen[rq_id]}.py both declare RQ_ID {rq_id!r}")
        else:
            seen[rq_id] = name
    if errors:
        raise ValueError("questions/: " + "; ".join(errors))


def check_slugs(lines):
    """Raise ValueError unless every line holding `**Q ` is `- **Q slug** question`, its slug lower-case words
    joined by hyphens that no other line declares. The hyphen is what makes a slug citable: deck_html.Q_RE needs
    one, so a book's `Q gaps` would never resolve to its question. Lines are found loosely and checked strictly,
    so a malformed declaration fails instead of going unseen."""
    errors, seen = [], set()
    for n, line in enumerate(lines, 1):
        if "**Q " not in line:
            continue
        m = QUESTION_LINE.fullmatch(line.rstrip("\n"))
        if not m:
            errors.append(f"line {n}: {line.strip()[:60]!r} is not `- **Q slug** question` "
                          "with a slug of lower-case words joined by hyphens")
        elif m.group(1) in seen:
            errors.append(f"line {n}: Q {m.group(1)} is declared twice")
        else:
            seen.add(m.group(1))
    if errors:
        raise ValueError("QUESTIONS.md: " + "; ".join(errors))


def discover():
    with open(QUESTIONS_MD, encoding="utf-8") as f:
        check_slugs(f)
    mods = [importlib.import_module(f"questions.{name}")
            for _, name, _ in pkgutil.iter_modules([HERE]) if name not in ("runner", "__init__")]
    check_modules(mods)
    return mods


def run_one(mod, con):
    row = bank_row(mod.RQ_ID)
    status = row["status"] if row else "?"
    print(f"\n=== {mod.RQ_ID} [{status}] {mod.QUESTION}")
    result = mod.answer(con)
    for r in result:
        print(" ", dict(r) if hasattr(r, "keys") else r)
    return result


def main():
    con = connect()
    target = sys.argv[1] if len(sys.argv) > 1 else None
    mods = discover()
    if target:
        mods = [m for m in mods if m.RQ_ID == target]
        if not mods:
            sys.exit(f"no question module for {target}")
    for mod in mods:
        run_one(mod, con)


if __name__ == "__main__":
    main()
