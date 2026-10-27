# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

"""Tables for the research pipeline's pure functions. Run: bash scripts/analysis.test.sh

Everything runs against a temp fleet folder and a temp data dir. Nothing here
calls a detector's build(): .analysis/data is irreplaceable, and build() opens
it for writing."""

import ast
import atexit
import contextlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ANALYSIS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "analysis")
sys.path.insert(0, ANALYSIS)

FIXTURE = tempfile.mkdtemp()
atexit.register(shutil.rmtree, FIXTURE, True)
FLEET_DIR = os.path.join(FIXTURE, "fleet")
GROUPS = {"tmpl": "template", "app1": "apps", "fresh": "apps", "gone": "apps", "infra1": "infra"}
os.makedirs(FLEET_DIR)
with open(os.path.join(FLEET_DIR, "FLEET.md"), "w") as f:
    f.write("# Fleet\n\n## Fleet\n\n## Repos\n\n")
    for repo, group in GROUPS.items():
        os.makedirs(os.path.join(FLEET_DIR, repo))
        f.write(f"### {repo}\n\n- group: {group}\n\n")
CONFIG = os.path.join(FIXTURE, "config.json")
with open(CONFIG, "w") as f:
    json.dump({"out_of_scope_repos": ["gone"], "no_roadmap_yet": ["fresh", "tmpl"]}, f)
os.environ["WAYFARE_FLEET_ROOT"] = FLEET_DIR
os.environ["WAYFARE_ANALYSIS_CONFIG"] = CONFIG

from ingest import fleet
from ingest.redact import redact
from cube import db
from detectors.d1_changesets import clean_sets, dependabot_sets
from questions import runner

# python-pptx and lxml are not installed where the suites run. build() takes its decks as dicts and never
# opens a .pptx or a views file, so stubs only have to satisfy the imports.
sys.path.append(os.path.join(ANALYSIS, "report"))
_stubs = {name: types.ModuleType(name) for name in ("pptx", "pptx.enum", "pptx.enum.shapes", "html_views")}
_stubs["pptx"].Presentation = None
_stubs["pptx.enum.shapes"].MSO_SHAPE_TYPE = None
with mock.patch.dict(sys.modules, _stubs):
    import book_pages
    import deck_html as D


class Redact(unittest.TestCase):
    SECRETS = [
        "sk-ant-api03-" + "x" * 24,
        "sk_live_" + "x" * 24,
        "ghp_" + "A" * 36,
        "github_pat_" + "x" * 24,
        "glpat-" + "x" * 20,
        "xoxb-" + "x" * 12,
        "AKIA" + "X" * 16,
    ]

    def test_secrets_are_replaced(self):
        for s in self.SECRETS:
            with self.subTest(s=s[:8]):
                out = redact(f"leaked {s} here")
                self.assertNotIn(s, out)
                self.assertIn("<secret>", out)

    def test_other_identifiers_are_replaced(self):
        cases = [
            ("eyJ" + "x" * 12 + "." + "y" * 12 + "." + "z" * 8, "<jwt>", "xxxxxxxxxxxx"),
            ("-----BEGIN RSA " + "PRIVATE KEY-----\nMIIE\n-----END RSA " + "PRIVATE KEY-----", "<private-key>", "MIIE"),
            ("password: hunter2", "password=<redacted>", "hunter2"),
            ("API_KEY=abc123", "API_KEY=<redacted>", "abc123"),
            ("mail someone@example.com now", "<email>", "someone"),
            ("id 123e4567-e89b-12d3-a456-426614174000", "<uuid>", "426614174000"),
            ("blob " + "aB3" * 14, "<blob>", "aB3aB3"),
        ]
        for text, marker, value in cases:
            with self.subTest(marker=marker):
                out = redact(text)
                self.assertIn(marker, out)
                self.assertNotIn(value, out)

    def test_shas_and_ordinary_words_are_kept(self):
        kept = [
            "fixes 3f786850e387550fdab836ed7e6dc881de23001b",
            "image " + "0123456789abcdef" * 4,
            "skip_validation and sketch the skeleton",
            "the token bucket refills; a secret garden",
            "version 2026-10-27 of task-runner",
        ]
        for text in kept:
            with self.subTest(text=text):
                self.assertEqual(redact(text), text)

    def test_empty_passes_through(self):
        self.assertIsNone(redact(None))
        self.assertEqual(redact(""), "")


class Dependabot(unittest.TestCase):
    def test_minor_and_patch_bumps_are_one_set(self):
        text = "Updates `lodash` from 4.17.20 to 4.17.21\nUpdates `axios` from 1.6.0 to 1.7.2"
        self.assertEqual(dependabot_sets(text), ["minor/patch bumps: lodash, axios"])

    def test_each_major_bump_is_its_own_set(self):
        text = ("Bumps [react](https://github.com/facebook/react) from 17.0.2 to 18.2.0.\n"
                "Bumps [vite](https://github.com/vitejs/vite) from 4.5.0 to 5.0.1.\n"
                "Updates `zod` from 3.22.0 to 3.23.0")
        self.assertEqual(dependabot_sets(text), [
            "minor/patch bumps: zod",
            "major bump: react 17.0.2 → 18.2.0",
            "major bump: vite 4.5.0 → 5.0.1",
        ])

    def test_majors_alone_add_no_empty_minor_set(self):
        self.assertEqual(dependabot_sets("Bump actions/checkout from v3 to v4"),
                         ["major bump: actions/checkout v3 → v4"])

    def test_the_title_form_with_a_directory(self):
        self.assertEqual(dependabot_sets("Bump lodash from 4.17.20 to 4.17.21 in /web"),
                         ["minor/patch bumps: lodash"])

    def test_a_package_named_twice_counts_once(self):
        text = "Bumps [left-pad](u) from 1.0.0 to 1.0.1.\nUpdates `left-pad` from 1.0.0 to 1.0.1"
        self.assertEqual(dependabot_sets(text), ["minor/patch bumps: left-pad"])

    def test_an_unparsed_pr_is_still_one_set(self):
        self.assertEqual(dependabot_sets("chore(deps): group update"), ["minor/patch bumps: "])
        self.assertEqual(dependabot_sets(None), ["minor/patch bumps: "])


class CleanSets(unittest.TestCase):
    def covered(self, sets, n):
        return sorted({i for _, idx in sets for i in idx}) == list(range(n))

    def test_unusable_replies_are_none(self):
        for raw in (None, {}, "text", [], [{"label": "x", "commits": [0, 9, "a"]}],
                    ["a"], [{"commits": None}], [{"label": "x", "commits": "12"}]):
            with self.subTest(raw=raw):
                self.assertIsNone(clean_sets(raw, 3))

    def test_an_uncovered_commit_joins_the_set_before_it(self):
        raw = [{"label": "feature", "commits": [1]}, {"label": "fix", "commits": [3]}]
        self.assertEqual(clean_sets(raw, 4), [("feature", [0, 1]), ("fix", [2, 3])])

    def test_every_commit_is_covered(self):
        raws = [
            [{"label": "late", "commits": [3]}],
            [{"label": "a", "commits": ["2"]}, {"label": "b", "commits": [5, 5]}],
            [{"label": "one", "commits": [1, 2, 3, 4, 5]}],
        ]
        for raw in raws:
            with self.subTest(raw=raw):
                self.assertTrue(self.covered(clean_sets(raw, 5), 5))

    def test_out_of_range_and_non_numeric_commits_are_dropped(self):
        raw = [{"label": "x", "commits": [0, "1", "two", 2, 7]}]
        self.assertEqual(clean_sets(raw, 2), [("x", [0, 1])])

    def test_label_is_capped(self):
        [(label, _)] = clean_sets([{"label": "y" * 500, "commits": [1]}], 1)
        self.assertEqual(len(label), 200)


class Connect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        self.report = os.path.join(self.tmp.name, "report")
        os.makedirs(self.data)
        os.makedirs(os.path.join(self.report, "skills"))
        os.makedirs(os.path.join(self.tmp.name, "cube"))
        with open(os.path.join(self.tmp.name, "cube", "views.sql"), "w") as f:
            f.write("-- needs: git\nCREATE TEMP VIEW v_git AS SELECT * FROM git.commits;\n"
                    "-- needs: nowhere\nCREATE TEMP VIEW v_nowhere AS SELECT 1;\n"
                    "CREATE TEMP VIEW v_free AS SELECT 1;\n")
        for name in db.SHARED:
            self.db(name)
        sqlite3.connect(os.path.join(self.data, "git.sqlite")).execute("CREATE TABLE commits (sha TEXT)")
        for p in (mock.patch.object(db, "DATA", self.data), mock.patch.object(db, "REPORT", self.report),
                  mock.patch.object(db, "HERE", self.tmp.name), mock.patch.object(db, "_warned", set())):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def db(self, name):
        open(os.path.join(self.data, f"{name}.sqlite"), "w").close()

    def connect(self, *topics):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            con = db.connect(*topics)
        return {r[1] for r in con.execute("PRAGMA database_list")} - {"main", "temp"}, err.getvalue(), con

    def test_shared_sources_attach(self):
        attached, err, _ = self.connect()
        self.assertEqual(attached, set(db.SHARED))
        self.assertEqual(err, "cube: skipped view v_nowhere: missing nowhere\n")

    def test_a_topic_cache_attaches_only_when_named(self):
        self.db("skills")
        attached, err, _ = self.connect()
        self.assertNotIn("skills", attached)
        self.assertNotIn("skills.sqlite", err)
        attached, _, _ = self.connect("skills")
        self.assertIn("skills", attached)

    def test_an_unlisted_file_is_skipped_with_a_warning(self):
        self.db("stray")
        attached, err, _ = self.connect()
        self.assertNotIn("stray", attached)
        self.assertIn("skipped stray.sqlite: neither in SHARED nor a topic's label cache", err)

    def test_stray_files_cannot_reach_the_attach_limit(self):
        for i in range(12):
            self.db(f"stray{i}")
        attached, _, _ = self.connect()
        self.assertEqual(attached, set(db.SHARED))

    def test_a_named_file_that_is_not_an_identifier_is_skipped(self):
        self.db("git commits")
        attached, err, _ = self.connect("git commits")
        self.assertEqual(attached, set(db.SHARED))
        self.assertIn("is not an SQL identifier", err)

    def test_a_named_cache_that_is_missing_warns(self):
        _, err, _ = self.connect("mistakes")
        self.assertIn("label cache mistakes.sqlite not found", err)

    def test_views_apply_only_when_their_sources_attached(self):
        _, _, con = self.connect()
        views = {r[0] for r in con.execute("SELECT name FROM temp.sqlite_master WHERE type='view'")}
        self.assertEqual(views, {"v_git", "v_free"})


class Categories(unittest.TestCase):
    def test_precedence(self):
        cases = {
            "gone": fleet.OUT_OF_SCOPE_CATEGORY,
            "tmpl": fleet.ALLIED,
            "infra1": fleet.ALLIED,
            fleet.PLUGIN_REPO_NAME: fleet.ALLIED,
            "fresh": fleet.APP_NO_FEATURES,
            "app1": fleet.APP,
            "unknown": fleet.APP,
        }
        for repo, want in cases.items():
            with self.subTest(repo=repo):
                self.assertEqual(fleet.category_of(repo), want)

    def test_out_of_scope_beats_allied(self):
        with mock.patch.object(fleet, "OUT_OF_SCOPE", {"tmpl", fleet.PLUGIN_REPO_NAME}):
            self.assertEqual(fleet.category_of("tmpl"), fleet.OUT_OF_SCOPE_CATEGORY)
            self.assertEqual(fleet.category_of(fleet.PLUGIN_REPO_NAME), fleet.OUT_OF_SCOPE_CATEGORY)

    def test_a_missing_config_override_stops_the_import(self):
        env = {**os.environ, "WAYFARE_ANALYSIS_CONFIG": os.path.join(FIXTURE, "nope.json")}
        p = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, sys.argv[1]); import ingest.fleet",
                            ANALYSIS], env=env, capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("WAYFARE_ANALYSIS_CONFIG", p.stderr)

    def test_every_category_is_declared(self):
        self.assertEqual({fleet.category_of(r) for r in fleet.ALL_REPOS + ["unknown"]}, set(fleet.CATEGORIES))


def module(name, rq_id, question="Q?", answer=lambda con: []):
    return types.SimpleNamespace(__name__=f"questions.{name}", RQ_ID=rq_id, QUESTION=question, answer=answer)


class QuestionModules(unittest.TestCase):
    def test_matching_modules_pass(self):
        runner.check_modules([module("RQ_h1_001", "RQ-h1-001"), module("STUB_NEW_A_15", "NEW-A-15"),
                              module("NEW_C07_A", "NEW-C07-A")])

    def test_rejected(self):
        cases = {
            "mismatched id": ([module("RQ_h1_001", "RQ-h1-002")], "does not match its filename"),
            "missing id": ([module("RQ_h1_001", None)], "does not match its filename"),
            "stub and module share an id": (
                [module("RQ_h1_024", "RQ-h1-024"), module("STUB_RQ_h1_024", "RQ-h1-024")], "both declare"),
            "no question": ([module("RQ_h1_001", "RQ-h1-001", question=None)], "lacks a QUESTION"),
            "no answer": ([module("RQ_h1_001", "RQ-h1-001", answer=None)], "lacks a QUESTION"),
        }
        for name, (mods, reason) in cases.items():
            with self.subTest(name), self.assertRaisesRegex(ValueError, reason):
                runner.check_modules(mods)

    def test_committed_modules_pass(self):
        # Parsed, not imported: importing a question module could open the real .analysis/data.
        mods = []
        for fname in sorted(os.listdir(runner.HERE)):
            if fname.endswith(".py") and fname not in ("runner.py", "__init__.py"):
                with open(os.path.join(runner.HERE, fname)) as f:
                    tree = ast.parse(f.read())
                consts, answer = {}, None
                for node in tree.body:
                    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                        for t in node.targets:
                            if isinstance(t, ast.Name):
                                consts[t.id] = node.value.value
                    elif isinstance(node, ast.FunctionDef) and node.name == "answer":
                        answer = lambda con: []
                mods.append(module(fname[:-3], consts.get("RQ_ID"), consts.get("QUESTION"), answer))
        self.assertTrue(mods)
        runner.check_modules(mods)


class QKey(unittest.TestCase):
    def test_ids_in_either_case_round_trip(self):
        cases = {
            "Q work-sources": "Q work-sources",
            "Q WORK-SOURCES · QUESTION": "Q work-sources",
            "see Q Review-Gap-2 here": "Q review-gap-2",
            "Q rq-h1-024 · By repo": "Q rq-h1-024",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(D.qkey(text), want)
                self.assertEqual(D.qkey(D.qkey(text)), want)

    def test_old_and_malformed_ids_are_rejected(self):
        for text in ("Q 2.01", "Q 12", "Q 2-01", "Q worksources", "Qwork-sources", "", None):
            with self.subTest(text=text):
                self.assertIsNone(D.qkey(text))


def block(key, *labels):
    return {"key": key, "question": {"question": "?"}, "statements": [],
            "views": [{"label": label, "title": f"{key} {label}"} for label in labels or ("ANSWER",)]}


def build(text, own=(), questions=None, deck_known=None):
    warnings = []
    with mock.patch.object(D, "warn", warnings.append):
        out, _ = book_pages.build({"n": 4, "questions": list(own)}, text, questions or {}, [], deck_known or {})
    return out, warnings


def flagged(warnings):
    return [w.split("book number ", 1)[1].split(" is not", 1)[0].strip("'") for w in warnings if "book number" in w]


def layout(out):
    return [(b["kind"], b.get("key"), b.get("number")) if b["kind"] != "p" else ("p", b["text"])
            for s in out for b in s["blocks"]]


class BookNumbers(unittest.TestCase):
    QUESTIONS = {"Q own-q": {"block": block("Q own-q"), "deck": "a"},
                 "Q other-q": {"block": block("Q other-q"), "deck": "b"}}
    KNOWN = {"a": {"77", "1200", "695450"}, "b": {"412"}}

    def check(self, text):
        _, warnings = build(text, ["own-q"], self.QUESTIONS, self.KNOWN)
        return flagged(warnings)

    def test_numbers_a_reader_can_check_are_exempt(self):
        cases = [
            "the report at https://example.com/runs/4123 says so",
            "as Q rq-412-split shows",
            "as Q RQ-412-SPLIT shows",
            "Chapters 3, 5 and 17 make the case",
            "Ch 12 and Part 14",
            "Figures 6.2 to 6.14",
            "on 27 Oct the run stopped",
            "on September 30 the run stopped",
            "in 2026, as in the 1990s",
            "Opus 4.1 and Sonnet 4 and Claude 3.5 Sonnet",
            "8090 and 8090.ai",
            "3 repos and 10 reasons",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(self.check(text), [])

    def test_numbers_in_the_chapters_data_pass(self):
        cases = ["77 runs", "$1,200 spent", "about 695,000 tokens", "about 700,000 tokens"]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(self.check(text), [])

    def test_findings_not_in_the_data_warn(self):
        cases = {
            "$1,300 spent": ["$1,300"],
            "90% of runs": ["90%"],
            "412 runs": ["412"],
            "as Q 2.01 found": ["2.01"],
            "11 repos": ["11"],
            "about 690,000 tokens": ["690,000"],
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.check(text), want)

    def test_a_figure_from_another_deck_vouches_for_its_numbers(self):
        self.assertEqual(self.check("Q own-q saw 412 runs."), ["412"])
        self.assertEqual(self.check("[[Q other-q]]\n\nQ own-q saw 412 runs."), [])


class BookCards(unittest.TestCase):
    QUESTIONS = {"Q own-q": {"block": block("Q own-q", "ANSWER", "BY REPO"), "deck": "a"},
                 "Q never-q": {"block": block("Q never-q"), "deck": "a"}}

    def build(self, text, own=("own-q",)):
        return build(text, own, self.QUESTIONS, {"a": set()})

    def test_a_card_follows_the_paragraph_that_first_cites_it(self):
        out, _ = self.build("## One\n\nNothing yet.\n\nFirst Q own-q.\n\nAgain Q own-q.")
        self.assertEqual(layout(out), [("p", "Nothing yet."), ("p", "First Q own-q."), ("card", "Q own-q", "4.1"),
                                       ("p", "Again Q own-q.")])

    def test_a_drawn_card_sits_at_its_figure_not_at_an_earlier_citation(self):
        out, _ = self.build("Cited as Q own-q.\n\n[[Q own-q · By repo | caption]]\n\n[[Q own-q]]")
        self.assertEqual(layout(out), [("p", "Cited as Q own-q."), ("card", "Q own-q", "4.1"),
                                       ("figure", "Q own-q", "4.2")])
        self.assertEqual(out[0]["blocks"][1]["block"]["views"][0]["label"], "BY REPO")

    def test_a_figure_that_fails_does_not_keep_its_card_off_the_page(self):
        out, warnings = self.build("Cited as Q own-q.\n\n[[Q own-q · Missing]]")
        self.assertEqual(layout(out), [("p", "Cited as Q own-q."), ("card", "Q own-q", "4.1")])
        self.assertTrue(any("matches no view" in w for w in warnings))
        self.assertFalse(any("never cites" in w for w in warnings))

    def test_an_uncited_question_is_left_off_with_a_warning(self):
        out, warnings = self.build("Only Q own-q.", own=("own-q", "never-q"))
        self.assertEqual(layout(out), [("p", "Only Q own-q."), ("card", "Q own-q", "4.1")])
        self.assertIn("ch04: 1 question(s) the text never cites, left off the page: Q never-q", warnings)

    def test_a_question_in_no_deck_warns(self):
        _, warnings = self.build("Text.", own=("gone-q",))
        self.assertIn("ch04: Q gone-q is in no deck", warnings)


if __name__ == "__main__":
    unittest.main()
