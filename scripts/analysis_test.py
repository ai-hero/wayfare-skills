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


if __name__ == "__main__":
    unittest.main()
