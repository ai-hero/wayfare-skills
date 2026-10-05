"""Build the editions. `./publish all` runs every target in order; each target can run alone
once `source` has run, and `all` always rebuilds `source` first so no edition reads a stale one."""
import importlib
import sys
import time

TARGETS = ["source", "book", "technical", "web", "slides"]
# `book` draws the cover itself (the wrap's spine needs the page count); `cover` redraws it alone.
EXTRA = ["cover"]


def run(name):
    t = time.time()
    importlib.import_module(name).main()
    print(f"{name}: done in {time.time() - t:.1f}s")


def main(argv):
    names = argv or ["all"]
    if names[0] == "qa":
        import qa
        return qa.main(names[1:])
    if names == ["all"]:
        names = TARGETS
    bad = [n for n in names if n not in TARGETS + EXTRA]
    if bad:
        sys.exit(f"unknown target {', '.join(bad)}; choose from all, {', '.join(TARGETS + EXTRA)}, or qa [edition] [pages]")
    for n in names:
        run(n)


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    main(sys.argv[1:])
