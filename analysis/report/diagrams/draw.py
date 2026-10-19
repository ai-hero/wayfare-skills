"""Draw the book's diagrams in both editions: `python3 draw.py [d_01_04 ...]` (all when none named).

The technical edition prefers `.analysis/diagrams/paper/`, so a diagram redrawn for the book alone
leaves the paper printing the old one.
"""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main(names):
    mods = sorted(glob.glob(os.path.join(HERE, "d_*.py")))
    if names:
        mods = [m for m in mods if any(os.path.basename(m).startswith(n) for n in names)]
    failed = []
    for mod in mods:
        for edition in ("book", "paper"):
            r = subprocess.run([sys.executable, mod], cwd=HERE, env={**os.environ, "DIAGRAM_EDITION": edition})
            if r.returncode:
                failed.append(f"{os.path.basename(mod)} ({edition})")
    if failed:
        raise SystemExit("draw: failed " + ", ".join(failed))


if __name__ == "__main__":
    main(sys.argv[1:])
