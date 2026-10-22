"""Build the editions. `./publish all` runs every target in order; each target can run alone
once `source` has run, and `all` always rebuilds `source` first so no edition reads a stale one."""
import importlib
import sys
import time

# Literal names, never import_module(name): semgrep's non-literal-import rule blocks the pre-push
# gate, and this table is the allow-list of what `./publish` may load.
EDITIONS = {
    "source": lambda: importlib.import_module("source"),
    "book": lambda: importlib.import_module("book"),
    "technical": lambda: importlib.import_module("technical"),
    "web": lambda: importlib.import_module("web"),
    "slides": lambda: importlib.import_module("slides"),
    "cover": lambda: importlib.import_module("cover"),
    "kindle": lambda: importlib.import_module("kindle"),
}
# `book` draws the cover itself (the wrap's spine needs the page count); `cover` redraws it alone.
# `kindle` is not in `all`: the store edition is built only when a KDP upload is being prepared.
TARGETS = ["source", "book", "technical", "web", "slides"]


def run(name):
    t = time.time()
    EDITIONS[name]().main()
    print(f"{name}: done in {time.time() - t:.1f}s")


def main(argv):
    names = argv or ["all"]
    if names[0] == "qa":
        import qa
        return qa.main(names[1:])
    if names == ["all"]:
        names = TARGETS
    bad = [n for n in names if n not in EDITIONS]
    if bad:
        sys.exit(f"unknown target {', '.join(bad)}; choose from all, {', '.join(EDITIONS)}, or qa [edition] [pages]")
    for n in names:
        run(n)


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    main(sys.argv[1:])
