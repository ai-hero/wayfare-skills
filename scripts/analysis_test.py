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
from detectors import d1_changesets as D1
from detectors.d1_changesets import clean_sets, dependabot_sets
sys.path.insert(0, os.path.join(ANALYSIS, "detectors"))
import d_shared_labels as L
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

    def test_stale_change_set_tables_stop_the_cube(self):
        sqlite3.connect(os.path.join(self.data, "detectors.sqlite")).execute(
            "CREATE TABLE changesets_by_commit (repo TEXT, sha TEXT, content_hash TEXT)")
        with self.assertRaisesRegex(SystemExit, "d1_changesets.py, then .*d_shared_labels.py changesets"):
            self.connect()
        with contextlib.redirect_stderr(io.StringIO()):
            db.connect(check_changesets=False)

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


class ChangeSetSchema(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.executescript(D1.SCHEMA)
        self.con.executescript(L.CS_WORKTYPE_SCHEMA)
        self.addCleanup(self.con.close)

    INSERTS = {
        "cs_units": "INSERT INTO cs_units VALUES (?,?,?,?,?,?,?)",
        "cs_sets": "INSERT INTO cs_sets VALUES (?,?,?,?,?,?)",
        "cs_worktype": "INSERT INTO cs_worktype VALUES (?,?,?,?,?,?,?,?)",
        "changesets_by_commit": "INSERT INTO changesets_by_commit VALUES (?,?,?,?,?)",
    }

    def insert(self, table, *row):
        self.con.execute(self.INSERTS[table], row)

    def test_primary_keys_reject_a_duplicate_set(self):
        rows = {"cs_sets": ("app1", "pr", "12", 0, "label", "[]"),
                "cs_worktype": ("app1", "pr", "12", 0, "fix", "product", "fix", "product")}
        for table, row in rows.items():
            with self.subTest(table):
                self.insert(table, *row)
                with self.assertRaisesRegex(sqlite3.IntegrityError, "UNIQUE"):
                    self.insert(table, *row)

    def test_checks_reject_a_bad_row(self):
        good = ("app1", "pr", "12", 0)
        bad = {"unit kind": ("app1", "merge", "12", 0), "empty repo": ("", "pr", "12", 0),
               "empty unit id": ("app1", "pr", "", 0), "negative set": ("app1", "pr", "12", -1),
               "no set": ("app1", "pr", "12", None), "no repo": (None, "pr", "12", 0)}
        for name, key in bad.items():
            for table, rest in (("cs_sets", ("label", "[]")), ("cs_worktype", ("fix", "product", "", ""))):
                with self.subTest(name, table=table), self.assertRaises(sqlite3.IntegrityError):
                    self.insert(table, *key, *rest)
        for name, rest in {"work type": ("feat", "product"), "theme": ("fix", "factory")}.items():
            with self.subTest(name), self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK"):
                self.insert("cs_worktype", *good, *rest, "", "")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK"):
            self.insert("changesets_by_commit", "app1", "abc", "app1#pr12", "merge", "12")

    def test_every_unit_kind_and_label_the_code_writes_is_accepted(self):
        for i, kind in enumerate(D1.UNIT_KINDS):
            self.insert("cs_sets", "app1", kind, "1", i, "label", "[]")
        for i, (w, t) in enumerate(zip(L.WORK_TYPES * 2, L.THEMES)):
            self.insert("cs_worktype", "app1", "pr", "1", i, w, t, w, t)

    def test_normalised_labels_satisfy_the_checks(self):
        cases = {
            ("feat", "factory", False): ("feature", "skills", ["work_type", "theme"]),
            ("nonsense", "nonsense", False): ("chore", "product", ["work_type", "theme"]),
            ("", "", False): ("chore", "product", ["work_type", "theme"]),
            ("fix", "harness", False): ("fix", "harness", []),
            ("fix", "harness", True): ("dependency", "security", ["dependabot override"]),
            ("dependency", "security", True): ("dependency", "security", []),
        }
        for i, (args, want) in enumerate(cases.items()):
            with self.subTest(args=args):
                got = L.normalise_worktype(*args)
                self.assertEqual(got, want)
                self.insert("cs_worktype", "app1", "pr", "1", i, got[0], got[1], args[0], args[1])

    def test_commits_join_their_unit_on_typed_columns(self):
        self.insert("cs_units", "app1", "pr", "12", "aaa", 2, 2, "haiku")
        self.insert("cs_units", "app1", "push", "bbb", "bbb", 1, 1, "single-line")
        self.insert("cs_units", "app1", "pr", "13", None, 1, 1, "single-line")
        for i in range(2):
            self.insert("cs_sets", "app1", "pr", "12", i, f"set {i}", "[]")
            self.insert("cs_worktype", "app1", "pr", "12", i, "fix", "product", "fix", "product")
        self.insert("changesets_by_commit", "app1", "aaa", "app1#pr12", "pr", "12")
        self.insert("changesets_by_commit", "app1", "bbb", "app1#pushbbb", "push", "bbb")
        self.insert("changesets_by_commit", "app1", None, "app1#pr13", "pr", "13")
        got = self.con.execute("""SELECT lk.sha, u.n_sets, COUNT(w.set_idx) FROM changesets_by_commit lk
                                  JOIN cs_units u USING (repo, unit_kind, unit_id)
                                  LEFT JOIN cs_worktype w USING (repo, unit_kind, unit_id)
                                  GROUP BY lk.repo, lk.unit_kind, lk.unit_id ORDER BY lk.unit_id""").fetchall()
        self.assertEqual(got, [("aaa", 2, 2), (None, 1, 0), ("bbb", 1, 0)])

    def test_unit_checks_reject_a_bad_unit(self):
        bad = {"method": ("app1", "pr", "12", "a", 1, 1, "guess"),
               "no sets": ("app1", "pr", "12", "a", 1, 0, "haiku"),
               "no commits": ("app1", "pr", "12", "a", 0, 1, "haiku"),
               "leading zero": ("app1", "pr", "012", "a", 1, 1, "haiku"),
               "not a number": ("app1", "pr-squash", "abc", "a", 1, 1, "haiku")}
        for name, row in bad.items():
            with self.subTest(name), self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK"):
                self.insert("cs_units", *row)
        self.insert("cs_units", "app1", "push", "abc", "abc", 1, 1, "unlabelled: one per commit")

    def test_one_pr_cannot_be_both_pr_and_pr_squash(self):
        self.insert("cs_units", "app1", "pr", "12", "a", 1, 1, "haiku")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "UNIQUE"):
            self.insert("cs_units", "app1", "pr-squash", "12", "b", 1, 1, "single-line")
        self.insert("cs_units", "app2", "pr-squash", "12", "b", 1, 1, "single-line")


def commit(sha, subject, body=""):
    return {"sha": sha, "subject": subject, "body": body, "files_json": "[]"}


class WriteUnits(unittest.TestCase):
    """build()'s write loop against the real SCHEMA, one unit of each kind of source."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = sqlite3.connect(os.path.join(tmp.name, "detectors.sqlite"))
        self.addCleanup(self.d.close)
        bump = {**commit("s5", "bump a"), "dependabot_sets": ["minor/patch bumps: a", "major bump: b 1 → 2"]}
        cached = ("app1#pr8", "app1", "pr", "8", "m8", 'PR #8 "cache"', [commit("p8a", "feat"), commit("p8b", "test")])
        self.units = [
            ("app1#pr-squash5", "app1", "pr-squash", "5", "s5", "commit on main for PR #5", [bump], "dependabot"),
            ("app1#pr7", "app1", "pr", "7", "m7", 'PR #7 "typo"', [commit("p7", "fix typo")], "single-line"),
            (*cached, None),
            ("app1#pushabc", "app1", "push", "abc", "abc", "commit on main", [commit("abc", "two things", "a / b")], None),
            ("app1#pr9", "app1", "pr", "9", None, 'PR #9 "off main"', [commit("p9", "gone")], "single-line"),
            ("app1#pr10", "app1", "pr", "10", None, 'PR #10 "off main"', [commit("p10", "gone too")], "single-line"),
        ]
        h = D1.sha256(D1.PROMPT_VERSION + D1.unit_text(cached[0], cached[5], cached[6]))
        self.cache = {h: ([("feature", [0, 1])], "haiku")}

    def table(self, sql):
        return self.d.execute(sql).fetchall()

    def test_each_kind_of_unit_is_written(self):
        D1.write_units(self.d, self.units, self.cache)
        self.assertEqual(self.table("SELECT unit_kind, unit_id, main_sha, n_commits, n_sets, method FROM cs_units "
                                    "ORDER BY unit_kind, unit_id"), [
            ("pr", "10", None, 1, 1, "single-line"), ("pr", "7", "m7", 1, 1, "single-line"),
            ("pr", "8", "m8", 2, 1, "haiku"), ("pr", "9", None, 1, 1, "single-line"),
            ("pr-squash", "5", "s5", 1, 2, "dependabot"), ("push", "abc", "abc", 1, 1, "unlabelled: one per commit")])
        self.assertEqual(self.table("SELECT unit_id, set_idx, label, shas_json FROM cs_sets WHERE unit_id IN ('5', '8') "
                                    "ORDER BY unit_id, set_idx"), [
            ("5", 0, "minor/patch bumps: a", '["s5"]'), ("5", 1, "major bump: b 1 → 2", '["s5"]'),
            ("8", 0, "feature", '["p8a", "p8b"]')])
        self.assertEqual(self.table("SELECT unit_id FROM changesets_by_commit WHERE sha IS NULL ORDER BY unit_id"),
                         [("10",), ("9",)])

    def test_a_duplicate_unit_is_named_and_nothing_is_written(self):
        D1.write_units(self.d, self.units, self.cache)
        before = self.table("SELECT * FROM cs_sets ORDER BY 1, 2, 3, 4")
        again = ("app1#pr7", "app1", "pr", "7", "m7b", 'PR #7 "typo"', [commit("p7", "fix typo")], "single-line")
        with self.assertRaisesRegex(ValueError, "app1 pr 7 from main commits m7, m7b"):
            D1.write_units(self.d, self.units[:2] + [again], self.cache)
        self.assertEqual(self.table("SELECT * FROM cs_sets ORDER BY 1, 2, 3, 4"), before)

    def test_a_failed_write_keeps_the_last_good_tables(self):
        D1.write_units(self.d, self.units, self.cache)
        before = {t: self.table(f"SELECT * FROM {t} ORDER BY 1, 2, 3") for t in ("cs_units", "changesets_by_commit")}
        bad = ("app1#pr07", "app1", "pr", "07", "m07", 'PR #07 "zero"', [commit("p07", "zero")], "single-line")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK"):
            D1.write_units(self.d, self.units[:1] + [bad], self.cache)
        for t, rows in before.items():
            self.assertEqual(self.table(f"SELECT * FROM {t} ORDER BY 1, 2, 3"), rows)


STUBS = {
    "git": ["CREATE TABLE commits (repo, sha, day, week, month, pr_number, plan_item_ref, is_bot, is_merge, subject, "
            "insertions, deletions)",
            "INSERT INTO commits VALUES ('app1', 'm8', '2026-08-03', '2026-W32', '2026-08', 8, NULL, 0, 0, 'feat', 3, 1)",
            "INSERT INTO commits VALUES ('app1', 'x1', '2026-08-04', '2026-W32', '2026-08', NULL, NULL, 0, 0, 'x', 1, 1)"],
    "github": ["CREATE TABLE prs (repo, number, month, day, additions, deletions, changed_files, merged_ts, review_count, "
               "head_ref)",
               "INSERT INTO prs VALUES ('app1', 8, '2026-08', '2026-08-03', 3, 1, 2, '2026-08-03T00:00:00Z', 1, 'goal-1')",
               "CREATE TABLE ci_runs (repo, head_branch)"],
    "plans": ["CREATE TABLE plan_items (repo, item_id, type, goal_id, day, raw_frontmatter_json)",
              "CREATE TABLE goals (repo, goal_id, members)",
              "INSERT INTO goals VALUES ('app1', '1', '[\"1\", \"2\"]')"],
    "harness": ["CREATE TABLE sessions (day, pr_links)"],
    "pr_commits": ["CREATE TABLE pr_commits (repo, pr_number, sha, subject)"],
    "detectors": ["CREATE TABLE session_spend (repo, cost_usd)", "INSERT INTO session_spend VALUES ('app1', 2.0)",
                  "CREATE TABLE duplicate_fixes (cluster_id, repo)"],
}
CHANGE_SET_QUESTIONS = ("RQ_h4_015", "RQ_h6_040", "RQ_h1_033", "NEW_A_02", "RQ_h2_004", "RQ_h2_020", "NEW_A_03",
                        "RQ_h2_010", "RQ_h7_030", "NEW_A_05", "RQ_h1_045", "RQ_h1_014")


class ChangeSetQueries(unittest.TestCase):
    """Every query that joins the change-set tables runs against the real SCHEMA, so a column typo fails here."""

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.addCleanup(self.con.close)
        for name, stmts in STUBS.items():
            self.con.execute(f"ATTACH DATABASE ':memory:' AS {name}")
            for stmt in stmts:
                self.con.execute(stmt.replace("CREATE TABLE ", f"CREATE TABLE {name}.").replace(
                    "INSERT INTO ", f"INSERT INTO {name}."))
        for stmt in D1.SCHEMA.split(";"):
            if stmt.strip():
                self.con.execute(stmt.replace("TABLE IF EXISTS ", "TABLE IF EXISTS detectors.")
                                 .replace("CREATE TABLE ", "CREATE TABLE detectors.")
                                 .replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX detectors."))
        self.con.execute("INSERT INTO detectors.cs_units VALUES ('app1', 'pr', '8', 'm8', 2, 3, 'haiku')")
        self.con.execute("INSERT INTO detectors.changesets VALUES ('app1#pr8', 3, '[]', 'haiku')")
        self.con.execute("INSERT INTO detectors.changesets_by_commit VALUES ('app1', 'm8', 'app1#pr8', 'pr', '8')")

    def test_the_questions_run(self):
        import importlib
        for name in CHANGE_SET_QUESTIONS:
            with self.subTest(name):
                importlib.import_module(f"questions.{name}").answer(self.con)
        with mock.patch.dict(sys.modules, _stubs), mock.patch.object(fleet, "BASELINE_CUTOFF", "2026-05-01"):
            import links
        self.assertEqual(links.sets_by_sha(self.con), {("app1", "m8"): 3})
        got = links.q_change_set_work_item_links(self.con)
        self.assertEqual((got["goal_merges"], got["d1_sets_in_goal_merges"]), (1, 3))

    def test_a_link_to_a_missing_unit_raises(self):
        self.con.execute("INSERT INTO detectors.changesets_by_commit VALUES ('app1', 'x1', 'app1#pr99', 'pr', '99')")
        with self.assertRaisesRegex(ValueError, "app1 pr 99.*d1_changesets.py"):
            db.commit_sets(self.con)
        for name in ("RQ_h1_045", "RQ_h1_014", "RQ_h4_015"):
            with self.subTest(name), self.assertRaisesRegex(ValueError, "missing from cs_units"):
                __import__(f"questions.{name}", fromlist=["answer"]).answer(self.con)

    def test_an_unlinked_commit_counts_as_one_set(self):
        from questions import RQ_h1_014
        [row] = RQ_h1_014.answer(self.con)
        self.assertEqual((row["commits"], row["change_sets"]), (2, 4))


class WorktypeWrite(unittest.TestCase):
    def test_a_dependabot_set_is_written_as_dependency_security(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "detectors.sqlite")
        d = sqlite3.connect(path)
        self.addCleanup(d.close)
        bump = {**commit("s5", "bump a"), "dependabot_sets": ["minor/patch bumps: a"]}
        D1.write_units(d, [("app1#pr-squash5", "app1", "pr-squash", "5", "s5", "h", [bump], "dependabot"),
                           ("app1#pr7", "app1", "pr", "7", "m7", "h", [commit("p7", "fix typo")], "single-line")], {})
        d.execute("CREATE TABLE cs_worktype_cache (h TEXT PRIMARY KEY, work_type TEXT, theme TEXT)")
        for label in ("minor/patch bumps: a", "fix typo"):
            d.execute("INSERT INTO cs_worktype_cache VALUES (?, 'feature', 'product')",
                      (L.h(f"repo app1: {label} | commits: "),))
        d.commit()
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        con.execute("ATTACH DATABASE ? AS detectors", (path,))
        for name, table in (("pr_commits", "pr_commits"), ("git", "commits")):
            con.execute(f"ATTACH DATABASE ':memory:' AS {name}")
            con.execute(f"CREATE TABLE {name}.{table} (repo, sha, subject)")
        err = io.StringIO()
        with mock.patch.object(L.D1, "call_haiku", side_effect=AssertionError("no model calls")), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            L.changesets(con, d)
        self.assertEqual(d.execute("SELECT unit_id, work_type, theme, raw_work_type, raw_theme FROM cs_worktype "
                                   "ORDER BY unit_id").fetchall(),
                         [("5", "dependency", "security", "feature", "product"),
                          ("7", "feature", "product", "feature", "product")])


class QuestionSlugs(unittest.TestCase):
    def lines(self, *slugs):
        return ["# Research questions", ""] + [f"- **Q {s}** A question?" for s in slugs]

    def test_committed_slugs_pass(self):
        with open(runner.QUESTIONS_MD, encoding="utf-8") as f:
            lines = f.readlines()
        self.assertGreater(sum(1 for line in lines if runner.QUESTION_LINE.fullmatch(line.rstrip("\n"))), 0)
        runner.check_slugs(lines)

    def test_rejected(self):
        shape = "is not `- \\*\\*Q slug\\*\\* question`"
        cases = {"no hyphen": (["gaps"], shape),
                 "upper case": (["Check-Gaps"], shape),
                 "trailing hyphen": (["gaps-"], shape),
                 "underscore": (["check_gaps"], shape),
                 "space": (["check gaps"], shape),
                 "declared twice": (["check-gaps", "check-gaps"], "declared twice")}
        for name, (slugs, reason) in cases.items():
            with self.subTest(name), self.assertRaisesRegex(ValueError, reason):
                runner.check_slugs(self.lines(*slugs))
        for name, line in {"indented": "  - **Q check-gaps** A question?",
                           "star bullet": "* **Q check-gaps** A question?",
                           "no question": "- **Q check-gaps**"}.items():
            with self.subTest(name), self.assertRaisesRegex(ValueError, shape):
                runner.check_slugs(["# Research questions", line])

    def test_a_valid_slug_is_one_the_book_can_cite(self):
        for slug in ("work-sources", "review-gap-2", "rq-h1-024"):
            with self.subTest(slug=slug):
                runner.check_slugs(self.lines(slug))
                self.assertEqual(D.qkey(f"Q {slug}"), f"Q {slug}")
        self.assertIsNone(D.qkey("Q gaps"))

    def test_the_book_cites_the_same_slug_shape(self):
        self.assertIn(runner.SLUG.pattern, D.Q_RE.pattern)


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
