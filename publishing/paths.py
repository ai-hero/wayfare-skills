"""Where the manuscript, its assets and the editions live. `PUBLISH_OUT` moves the output; the
default keeps it under `.analysis/`, which is gitignored because the editions carry the findings."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "publishing")
REPORT = os.path.join(ROOT, "analysis", "report")
ANALYSIS = os.path.join(ROOT, ".analysis")
# The editor's master: edited chapters in `book/`, the curated evidence appendix in `appendix/`.
# `.analysis/book` is the pre-edit working copy and must not be published from.
MANUSCRIPT = os.environ.get("MANUSCRIPT_DIR", os.path.join(ROOT, "analysis", "manuscript"))
BOOK = os.path.join(MANUSCRIPT, "book")
APPENDIX = os.path.join(MANUSCRIPT, "appendix")
DECKS = os.path.join(ANALYSIS, "decks")
DIAGRAMS = os.path.join(ANALYSIS, "diagrams", "book")
OUT = os.environ.get("PUBLISH_OUT", os.path.join(ANALYSIS, "publish"))
BUILD = os.path.join(OUT, "build")
SOURCE = os.path.join(BUILD, "book.json")
ASSETS = os.path.join(BUILD, "assets")
EDITIONS = os.path.join(OUT, "editions")
META = os.path.join(EDITIONS, "meta.json")
DIST = os.path.join(OUT, "dist")
QA = os.path.join(OUT, "qa")
WORKSPACE = os.environ.get("WAYFARE_FLEET_ROOT", os.path.expanduser("~/workspaces/aihero"))
DESIGN_SYSTEM = os.path.join(WORKSPACE, "design-system")
WEBSITE = os.environ.get("WEBSITE_DIR", os.path.join(WORKSPACE, "website"))
