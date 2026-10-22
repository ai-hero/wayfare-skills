# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

"""Tables for audit.py's parsers. Run: python3 -m unittest scripts/audit_test.py

Each parser here has the failure mode the Justfile names for the hook tests:
matching nothing is indistinguishable from a clean input, so a regression
reads as a fleet that got better."""

import contextlib
import importlib.util
import io
import os
import pathlib
import json
import shutil
import site
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("audit", HERE / "audit.py")
audit = importlib.util.module_from_spec(spec)
sys.modules["audit"] = audit  # the fleet's checkers.py does `import audit`
CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
# Without the override, every audit.py / consistency.py subprocess below runs
# `git fetch` in the developer's real plugin checkout.
CLEAN_ENV["HERO_SKILLS_PLUGIN"] = str(HERE.parent)
spec.loader.exec_module(audit)


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def git(cwd, *args):
    # Strip GIT_* from the environment: under a pre-commit hook (and in a
    # linked worktree) GIT_DIR/GIT_INDEX_FILE point at the repo being
    # committed, and every fixture `git init`/`commit` would hit it instead.
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=CLEAN_ENV)


def git_repo(root, name):
    """A committed repo with one file, so ls-files / worktree add work."""
    r = root / name
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "t")
    write(r, "README.md", "x\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "init")
    return r


class WorkflowOn(unittest.TestCase):
    def test_forms(self):
        cases = {
            "on:\n  push:\n": {"push": None},
            "on: [push, pull_request]\n": {"push": None, "pull_request": None},
            "on: push\n": {"push": None},
            '"on":\n  push:\n': {"push": None},
        }
        for text, want in cases.items():
            with tempfile.TemporaryDirectory() as d:
                w = write(pathlib.Path(d), "ci.yaml", text)
                self.assertEqual(audit._wf_on(audit._wf_doc(w)), want, text)

    def test_unreadable_is_manual_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, ".github/workflows/ci.yaml", "on:\n  pull_request:\n    paths: [x]\n\tbad\n")
            st, detail = audit.CHECKS["CI-21"](r)
            self.assertEqual(st, audit.MANUAL)
            self.assertIn("ci.yaml", detail)

    def test_list_form_passes_ci21(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, ".github/workflows/ci.yaml", "on: [push, pull_request]\njobs: {}\n")
            self.assertEqual(audit.CHECKS["CI-21"](r), (audit.PASS, ""))


class ImageRefs(unittest.TestCase):
    def test_dockerfile(self):
        text = (
            "FROM --platform=$BUILDPLATFORM golang:1.22 AS build\n"
            "FROM node:20-alpine as ui\nFROM ui\nFROM scratch\nFROM ${BASE}\n"
            "FROM alpine@sha256:abc\nFROM redis:latest\nFROM mongo\n"
            "FROM myreg:5000/mongo:8.0\n"
        )
        with tempfile.TemporaryDirectory() as d:
            f = write(pathlib.Path(d), "Dockerfile.dev", text)
            self.assertEqual(audit._image_refs(f), [
                ("golang", "1.22"), ("node", "20-alpine"), ("redis", "latest"),
                ("mongo", ""), ("mongo", "8.0"),
            ])

    def test_compose_ignores_comments(self):
        text = "services:\n  a:\n    image: 'minio/minio:latest'\n  b:\n    image: mongo:8\n  # image: bad:latest\n  c:\n    image: ${IMG}\n"
        with tempfile.TemporaryDirectory() as d:
            f = write(pathlib.Path(d), "docker-compose.dev.yaml", text)
            self.assertEqual(audit._image_refs(f), [("minio", "latest"), ("mongo", "8")])

    def test_ctr09_and_ctr11(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile.dev", "FROM mongo:8\nFROM redis:latest\nFROM golang:1.22 AS build\nFROM build\n")
            write(r, "docker-compose.prod.yaml", "services:\n  mongo:\n    image: mongo:8.0\n    command: [--replSet, rs0]\n")
            write(r, "dev.sh", "mongod --replSet rs0\n")
            st, detail = audit.CHECKS["CTR-09"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("redis:latest", detail)
            self.assertNotIn("golang", detail)
            self.assertEqual(audit.CHECKS["CTR-11"](r)[0], audit.PASS, "8 and 8.0 are one major")


class VersionPins(unittest.TestCase):
    """CTR-01/CTR-02 key every pin by file:line, so two pins in one file
    both survive instead of one overwriting the other."""

    def test_ctr02_two_job_workflow_fails_and_names_both(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "lib/go.mod", "go 1.21\n")
            write(
                r,
                ".github/workflows/ci.yaml",
                "jobs:\n"
                "  a:\n"
                "    steps:\n"
                "      - uses: actions/setup-go@v5\n"
                "        with:\n"
                "          go-version: '1.26'\n"
                "  b:\n"
                "    steps:\n"
                "      - uses: actions/setup-go@v5\n"
                "        with:\n"
                "          go-version: '1.21'\n",
            )
            st, detail = audit.CHECKS["CTR-02"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertEqual(detail.count("ci.yaml:"), 2, detail)
            self.assertIn("1.26", detail)
            self.assertIn("lib/go.mod=1.21", detail)

    def test_ctr01_two_job_workflow_fails_and_names_both(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(
                r,
                ".github/workflows/ci.yaml",
                "jobs:\n"
                "  a:\n"
                "    steps:\n"
                "      - uses: actions/setup-node@v4\n"
                "        with:\n"
                "          node-version: '20'\n"
                "  b:\n"
                "    steps:\n"
                "      - uses: actions/setup-node@v4\n"
                "        with:\n"
                "          node-version: '18'\n",
            )
            st, detail = audit.CHECKS["CTR-01"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertEqual(detail.count("ci.yaml:"), 2, detail)
            self.assertIn("=20", detail)
            self.assertIn("=18", detail)

    def test_ctr01_double_quoted_node_version_disagrees_with_nvmrc(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, ".nvmrc", "20\n")
            write(
                r,
                ".github/workflows/ci.yaml",
                "jobs:\n"
                "  a:\n"
                "    steps:\n"
                "      - uses: actions/setup-node@v4\n"
                '        with:\n'
                '          node-version: "22"\n',
            )
            st, detail = audit.CHECKS["CTR-01"](r)
            self.assertEqual(st, audit.FAIL, detail)
            self.assertIn("=20", detail)
            self.assertIn("=22", detail)

    def test_ctr02_double_quoted_go_version_disagrees_with_go_mod(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "lib/go.mod", "go 1.21\n")
            write(
                r,
                ".github/workflows/ci.yaml",
                "jobs:\n"
                "  a:\n"
                "    steps:\n"
                "      - uses: actions/setup-go@v5\n"
                '        with:\n'
                '          go-version: "1.26"\n',
            )
            st, detail = audit.CHECKS["CTR-02"](r)
            self.assertEqual(st, audit.FAIL, detail)
            self.assertIn("1.21", detail)
            self.assertIn("1.26", detail)

    def test_ctr02_two_from_golang_fails_and_names_both(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "lib/go.mod", "go 1.21\n")
            write(r, "Dockerfile", "FROM golang:1.26 AS build\nFROM golang:1.21 AS test\n")
            st, detail = audit.CHECKS["CTR-02"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("Dockerfile:1=1.26", detail)
            self.assertIn("Dockerfile:2=1.21", detail)

    def test_ctr01_two_from_node_fails_and_names_both(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM node:20-alpine AS build\nFROM node:18-alpine AS test\n")
            st, detail = audit.CHECKS["CTR-01"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("Dockerfile:1:node=20", detail)
            self.assertIn("Dockerfile:2:node=18", detail)

    def test_agreeing_two_job_workflow_still_passes(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "lib/go.mod", "go 1.21\n")
            write(
                r,
                ".github/workflows/ci.yaml",
                "jobs:\n"
                "  a:\n"
                "    steps:\n"
                "      - uses: actions/setup-go@v5\n"
                "        with:\n"
                "          go-version: '1.21'\n"
                "  b:\n"
                "    steps:\n"
                "      - uses: actions/setup-go@v5\n"
                "        with:\n"
                "          go-version: '1.21'\n",
            )
            st, detail = audit.CHECKS["CTR-02"](r)
            self.assertEqual(st, audit.PASS)
            self.assertEqual(detail, "go 1.21 everywhere")


class CI14(unittest.TestCase):
    """See CI-14's own comment in audit.py for the two traps these pin."""

    def _dependabot(self, r, updates_yaml):
        write(r, ".github/dependabot.yaml", f"version: 2\nupdates:\n{updates_yaml}")

    def test_digest_pinned_docker_unfiltered_passes(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM alpine@sha256:abc\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.PASS, detail)

    def test_tag_pinned_docker_unfiltered_fails(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM alpine:3.19\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("docker@/: catch-all batches majors", detail)

    def test_docker_with_arg_base_unfiltered_fails(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM ${BASE}\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("docker@/: catch-all batches majors", detail)

    def test_unfiltered_then_decorative_group_on_npm_fails(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            self._dependabot(
                r,
                "- package-ecosystem: npm\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    all:\n"
                "      patterns: ['*']\n"
                "    decorative:\n"
                "      patterns: ['*']\n"
                "      update-types: [minor, patch]\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("npm@/: catch-all batches majors", detail)

    def test_minor_patch_group_first_passes(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            self._dependabot(
                r,
                "- package-ecosystem: npm\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    minor-patch:\n"
                "      patterns: ['*']\n"
                "      update-types: [minor, patch]\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.PASS, detail)

    def test_directories_with_one_tagged_dir_fails(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "a/Dockerfile", "FROM alpine@sha256:abc\n")
            write(r, "b/Dockerfile", "FROM alpine:3.19\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directories: ['/a', '/b']\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("docker@/a,/b: catch-all batches majors", detail)

    def test_no_catch_all_group_names_missing(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            self._dependabot(
                r,
                "- package-ecosystem: gomod\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("gomod@/: no catch-all group", detail)

    def test_tag_digest_docker_unfiltered_fails(self):
        """A tag+digest FROM still gets tag bumps, so an unfiltered catch-all
        still batches majors. Only a digest-only ref (no :tag) is exempt."""
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM node:26-alpine@sha256:abc\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("docker@/: catch-all batches majors", detail)

    def test_tag_digest_docker_ignore_major_passes(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM node:26-alpine@sha256:abc\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  ignore:\n"
                "    - dependency-name: '*'\n"
                "      update-types: ['version-update:semver-major']\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.PASS, detail)

    def test_minor_patch_then_later_unfiltered_fails(self):
        """A major that skips the [minor, patch] group falls through to the
        later unfiltered one — judging only the first group misses this."""
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            self._dependabot(
                r,
                "- package-ecosystem: npm\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    mp:\n"
                "      patterns: ['*']\n"
                "      update-types: [minor, patch]\n"
                "    majors:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("npm@/: catch-all batches majors", detail)

    def test_major_minor_patch_fails(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            self._dependabot(
                r,
                "- package-ecosystem: npm\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    all:\n"
                "      patterns: ['*']\n"
                "      update-types: [major, minor, patch]\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("npm@/: catch-all batches majors", detail)

    def test_security_updates_group_ignored_passes(self):
        """A first `["*"]` group scoped to security-updates is not a
        version-update catch-all, so it must not be picked as the judged
        group and hide the real one that follows it."""
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            self._dependabot(
                r,
                "- package-ecosystem: npm\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    sec:\n"
                "      applies-to: security-updates\n"
                "      patterns: ['*']\n"
                "    mp:\n"
                "      patterns: ['*']\n"
                "      update-types: [minor, patch]\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.PASS, detail)

    def test_dev_minor_patch_then_unfiltered_prod_fails(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            self._dependabot(
                r,
                "- package-ecosystem: npm\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    dev:\n"
                "      dependency-type: development\n"
                "      patterns: ['*']\n"
                "      update-types: [minor, patch]\n"
                "    prod:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("npm@/: catch-all batches majors", detail)

    def test_dollar_ref_after_digest_stage_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM alpine@sha256:abc AS a\nFROM ${BASE}\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("docker@/: catch-all batches majors", detail)

    def test_digest_pinned_dockerfile_but_npm_entry_fails(self):
        """The digest exemption is docker-only: a digest-pinned Dockerfile
        sitting in the repo must not exempt an unrelated npm entry."""
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM alpine@sha256:abc\n")
            self._dependabot(
                r,
                "- package-ecosystem: npm\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("npm@/: catch-all batches majors", detail)

    def test_missing_directory_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM alpine@sha256:abc\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directories: ['/', '/gone']\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("catch-all batches majors", detail)

    def test_glob_directory_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM alpine@sha256:abc\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directories: ['/', '/svc/*']\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("catch-all batches majors", detail)

    def test_alternate_dockerfile_name_with_tag_fails_closed(self):
        """Dependabot's docker ecosystem also updates `prod.dockerfile`
        beside a digest-only `Dockerfile`, so a tagged ref in it must not be
        skipped by name."""
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM alpine@sha256:abc\n")
            write(r, "prod.dockerfile", "FROM alpine:3.19\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("docker@/: catch-all batches majors", detail)

    def test_k8s_yaml_image_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM alpine@sha256:abc\n")
            write(r, "deploy.yaml", "image: nginx:1.25\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("docker@/: catch-all batches majors", detail)

    def test_stage_name_used_before_defined_fails_closed(self):
        """A stage name only counts after the FROM … AS name that defines
        it; recognizing it anywhere in the file would let this Dockerfile's
        second FROM read as digest-pinned by treating the first FROM's
        untagged image name as an already-known stage."""
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            write(r, "Dockerfile", "FROM ubuntu\nFROM alpine@sha256:abc AS ubuntu\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directory: /\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("docker@/: catch-all batches majors", detail)

    def test_directory_escapes_repo_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d) / "repo"
            r.mkdir()
            write(r, "Dockerfile", "FROM alpine:3.19\n")
            write(pathlib.Path(d) / "x", "Dockerfile", "FROM alpine@sha256:abc\n")
            self._dependabot(
                r,
                "- package-ecosystem: docker\n"
                "  directory: /../x\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    docker-all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("catch-all batches majors", detail)

    def test_two_failing_npm_entries_named_apart(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            self._dependabot(
                r,
                "- package-ecosystem: npm\n"
                "  directory: /a\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    all:\n"
                "      patterns: ['*']\n"
                "- package-ecosystem: npm\n"
                "  directory: /b\n"
                "  schedule: {interval: weekly}\n"
                "  groups:\n"
                "    all:\n"
                "      patterns: ['*']\n",
            )
            st, detail = audit.CHECKS["CI-14"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("npm@/a: catch-all batches majors", detail)
            self.assertIn("npm@/b: catch-all batches majors", detail)


class HookSegments(unittest.TestCase):
    PC = "repos:\n- repo: a\n  hooks:\n  - id: markdownlint\n    args: [--fix]\n  - id: codespell\n    args: [--disable=x]\n- repo: b\n  hooks:\n  - id: semgrep\n    # a comment\n    args:\n    - --config=auto\n    - --error\n"

    def test_segment_scopes_args(self):
        seg = audit._hook_segment(self.PC, "markdownlint")
        self.assertIn("--fix", seg)
        self.assertNotIn("--disable", seg)
        self.assertIn("--config=auto", audit._hook_segment(self.PC, "semgrep"))
        self.assertEqual(audit._hook_segment(self.PC, "ruff"), "")


class References(unittest.TestCase):
    def test_three_outcomes(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            ref = write(r, "ref.md", "## Fleet\nbody\n")
            self.assertEqual(audit._matches_reference(r / "x", r / "absent")[0], audit.MANUAL)
            self.assertEqual(audit._matches_reference(r / "absent", ref)[0], audit.FAIL)
            same = write(r, "same.md", "## Fleet\nbody\n")
            self.assertEqual(audit._matches_reference(same, ref)[0], audit.PASS)
            doc = write(r, "AGENTS.md", "# A\n\n## Fleet\nbody\n\n## Next\nz\n")
            self.assertEqual(audit._matches_reference(doc, ref, audit._fleet_section)[0], audit.PASS)
            nodoc = write(r, "B.md", "# A\n")
            self.assertEqual(audit._matches_reference(nodoc, ref, audit._fleet_section), (audit.FAIL, "section absent"))

    def test_fleet_section_slices(self):
        self.assertIsNone(audit._fleet_section("# A\n"))
        self.assertEqual(audit._fleet_section("x\n## Fleet\nb\n"), "## Fleet\nb\n")
        self.assertEqual(audit._fleet_section("x\n## Fleet\nb\n## C\nd\n"), "## Fleet\nb")


class HookRevs(unittest.TestCase):
    def tearDown(self):
        audit._FLEET.clear()

    def run_pre07(self, mine, by_repo):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d) / "fx"
            write(r, ".pre-commit-config.yaml", "repos: []\n")
            audit._FLEET["revs"] = {"https://h/hooks": {**by_repo, "fx": mine}}
            audit._FLEET["revs-broken"] = {}
            return audit.CHECKS["PRE-07"](r)

    def test_majority(self):
        self.assertEqual(self.run_pre07("v0.9.0", {"a": "v1.0.0", "b": "v1.0.0"})[0], audit.FAIL)
        self.assertEqual(self.run_pre07("v1.5.0", {"a": "v1.0.0", "b": "v2.0.0"})[0], audit.FAIL, "tie goes to newest")
        self.assertEqual(self.run_pre07("v0.9.0", {"a": "v1.0.0"})[0], audit.PASS, "under three voters")


class Snapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        # FAMILY is bound by configure() from FLEET.md (or the lone repo), so
        # the fixture binds its own: the snapshot walks family_repos().
        self.saved = audit.ROOT, audit.FAMILY, dict(audit.REPO_DIR)
        audit.ROOT, audit.FAMILY = self.root, ("hero-template",)
        audit.REPO_DIR.clear()
        # Mapped under a subdirectory, so cleanup must go through REPO_DIR: a
        # regression to `ROOT / rn` would leave the worktree behind and the
        # count below would still read 1 only by accident of the fallback.
        audit.REPO_DIR["hero-template"] = self.root / "sub" / "hero-template"
        (self.root / "sub").mkdir()
        git_repo(self.root / "sub", "hero-template")

    def tearDown(self):
        audit.ROOT, audit.FAMILY, saved_dirs = self.saved
        audit.REPO_DIR.clear()
        audit.REPO_DIR.update(saved_dirs)
        self.tmp.cleanup()

    def worktrees(self):
        out = subprocess.run(["git", "worktree", "list"], cwd=self.root / "sub" / "hero-template",
                             capture_output=True, text=True, env=CLEAN_ENV).stdout
        return out.strip().splitlines()

    def test_cleanup_on_exception(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(RuntimeError):
                with audit.snapshot_family("HEAD"):
                    self.assertNotEqual(audit.repo_path("hero-template"), self.root / "sub" / "hero-template")
                    self.assertEqual(audit.repo_path("hero-template").name, "hero-template")
                    raise RuntimeError("boom")
        self.assertEqual(audit.REPO_PATH, {})
        self.assertEqual(audit._FLEET, {})
        self.assertEqual(len(self.worktrees()), 1)

    def test_unknown_ref_audits_checkout(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with audit.snapshot_family("no-such-ref"):
                self.assertEqual(audit.repo_path("hero-template"), self.root / "sub" / "hero-template")
        self.assertEqual(len(self.worktrees()), 1)


class AppliesTo(unittest.TestCase):
    """applies_to resolves FLEET.md groups and leaves every other name to
    the checkers. A capability name must never exempt a repo on its own:
    the explicit lists it used to resolve to went stale and hid three
    template clones from every Go and Node check."""
    def setUp(self):
        self.saved = dict(audit.GROUP_REPOS)
        audit.GROUP_REPOS.clear()
        audit.GROUP_REPOS.update({"apps": {"a", "b"}, "infra": {"tf"}})

    def tearDown(self):
        audit.GROUP_REPOS.clear(); audit.GROUP_REPOS.update(self.saved)

    def test_groups(self):
        self.assertTrue(audit.applies({"applies_to": "all"}, "tf"))
        self.assertTrue(audit.applies({}, "tf"))
        self.assertTrue(audit.applies({"applies_to": ["template", "apps"]}, "a"))
        self.assertFalse(audit.applies({"applies_to": ["template", "apps"]}, "tf"))
        self.assertTrue(audit.applies({"applies_to": "go"}, "tf"), "a capability is the checker's call")
        self.assertTrue(audit.applies({"applies_to": ["go", "apps"]}, "a"))
        self.assertFalse(audit.applies({"applies_to": ["go", "apps"]}, "tf"), "the group half still decides")

    def test_no_fleet_reaches_everyone(self):
        audit.GROUP_REPOS.clear()
        self.assertTrue(audit.applies({"applies_to": ["apps"]}, "anything"))


def fleet_fixture(root, fleet_md, overlay=None, checkers=None):
    """A fleet folder: FLEET.md, a `.fleet/` register with the given overlay
    text (or an empty one), and repos named by the caller."""
    write(root, "FLEET.md", fleet_md)
    reg = root / ".fleet"
    reg.mkdir(exist_ok=True)
    if overlay is not None:
        write(root, ".fleet/CHECKS.yaml", overlay)
    if checkers is not None:
        write(root, ".fleet/checkers.py", checkers)
    return root


class Configured(unittest.TestCase):
    """configure() binds every module global from FLEET.md; each test rebinds
    from a fixture and tearDown restores what the import-time call found."""
    def setUp(self):
        self.saved = (audit.ROOT, audit.FAMILY, audit.REGISTER, audit.TEMPLATE,
                      dict(audit.REPO_DIR), {k: set(v) for k, v in audit.GROUP_REPOS.items()})
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name).resolve()

    def tearDown(self):
        audit.ROOT, audit.FAMILY, audit.REGISTER, audit.TEMPLATE, dirs, groups = self.saved
        audit.REPO_DIR.clear(); audit.REPO_DIR.update(dirs)
        audit.GROUP_REPOS.clear(); audit.GROUP_REPOS.update(groups)
        audit._OVERLAY_LOADED.clear()
        self.tmp.cleanup()

    FLEET = """# Fleet
## Fleet

- name: fx
- org: acme
- template: tpl
- register: .fleet/ # a trailing comment must not reach the path

## Groups

- apps: the apps
- infra: deployments

## Repos

### tpl

- group: template
- port: 33099

### alpha

- group: apps
- path: "apps/alpha" # quoted, nested

### tf

- group: infra

### parked

- group: none

### blank

- group:

### escapee

- group: apps
- path: ../outside

### ../evil

- group: apps

```markdown
### fenced

- group: apps
```
"""

    def test_read_fleet_and_configure(self):
        fleet_fixture(self.root, self.FLEET)
        for name in ("tpl", "apps/alpha", "tf", "parked", "blank"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            audit.configure(self.root)
        self.assertEqual(audit.ROOT, self.root)
        self.assertEqual(audit.REGISTER, self.root / ".fleet")
        self.assertEqual(audit.TEMPLATE, "tpl")
        self.assertEqual(audit.FAMILY, ("tpl", "alpha", "tf"), "none, blank, escapee, ../evil and fenced are out")
        self.assertEqual(audit.REPO_DIR["alpha"], self.root / "apps" / "alpha", "path: honoured, quotes and comment stripped")
        self.assertEqual(audit.GROUP_REPOS, {"template": {"tpl"}, "apps": {"alpha"}, "infra": {"tf"}})
        self.assertIn("skipping 'escapee'", err.getvalue())
        self.assertIn("skipping '../evil'", err.getvalue())
        self.assertEqual(audit.repo_path("alpha"), self.root / "apps" / "alpha")

    def test_absolute_path_outside_is_trusted_relative_escape_is_not(self):
        outside = pathlib.Path(tempfile.mkdtemp()).resolve()
        home = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, outside, True)
        self.addCleanup(shutil.rmtree, home, True)
        (home / ".plug" / "tilde").mkdir(parents=True)
        (self.root / "inside").mkdir()
        (self.root / "linked").symlink_to(outside)
        fleet_fixture(self.root, f"""## Fleet

- name: fx

## Repos

### inside

- group: apps

### abs

- path: {outside}
- group: apps

### tilde

- path: ~/.plug/tilde
- group: apps

### linked

- group: apps

### dotdot

- path: ../{outside.name}
- group: apps
""")
        with mock.patch.dict(os.environ, {"HOME": str(home)}), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            audit.configure(self.root)
        self.assertEqual(audit.FAMILY, ("inside", "abs", "tilde"))
        self.assertEqual(audit.REPO_DIR["abs"], outside)
        self.assertEqual(audit.REPO_DIR["tilde"], home / ".plug" / "tilde")
        self.assertIn("skipping 'linked'", err.getvalue())
        self.assertIn("skipping 'dotdot'", err.getvalue())

    def test_fleet_root(self):
        fleet_fixture(self.root, "## Fleet\n- name: fx\n")
        inner = self.root / "repo" / "sub"
        inner.mkdir(parents=True)
        self.assertEqual(audit.fleet_root(inner), self.root)
        write(self.root, "HERO.md", "# HERO\n")
        self.assertIsNone(audit.fleet_root(inner), "FLEET.md beside HERO.md is a repo, not a fleet")

    def test_fleet_root_passes_over_a_git_work_tree(self):
        git_repo(self.root, "clone")
        clone = self.root / "clone"
        fleet_fixture(clone, "## Fleet\n- name: fx\n")
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertIsNone(audit.fleet_root(clone), "a committed FLEET.md is not a fleet")
        self.assertIn("inside a git work tree", err.getvalue())

    def test_fleet_root_ignores_a_git_register(self):
        fleet_fixture(self.root, "## Fleet\n- name: fx\n")
        git(self.root / ".fleet", "init", "-q")
        sub = self.root / "repo"
        sub.mkdir()
        self.assertEqual(audit.fleet_root(sub), self.root)

    def test_audit_in_a_clone_runs_no_committed_checkers(self):
        clone = git_repo(self.root, "clone")
        marker = self.root / "ran"
        fleet_fixture(clone, "## Fleet\n- name: fx\n", checkers=f"open({str(marker)!r}, 'w').close()\n")
        p = subprocess.run([sys.executable, str(HERE / "audit.py")], cwd=str(clone),
                           capture_output=True, text=True, env=CLEAN_ENV)
        self.assertFalse(marker.exists(), "the clone's .fleet/checkers.py executed")
        self.assertIn("inside a git work tree", p.stderr)

    def test_fleet_root_walks_ancestors_of_a_clone(self):
        clone = git_repo(self.root, "clone")
        docs = clone / "docs"
        fleet_fixture(docs, "## Fleet\n- name: fx\n")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(audit.fleet_root(docs), "a FLEET.md in a clone's subfolder is not a fleet")

    def test_audit_in_a_clone_subfolder_runs_no_committed_checkers(self):
        clone = git_repo(self.root, "clone")
        docs = clone / "docs"
        marker = self.root / "ran"
        fleet_fixture(docs, "## Fleet\n- name: fx\n", checkers=f"open({str(marker)!r}, 'w').close()\n")
        subprocess.run([sys.executable, str(HERE / "audit.py")], cwd=str(docs),
                       capture_output=True, text=True, env=CLEAN_ENV)
        self.assertFalse(marker.exists(), "the clone subfolder's .fleet/checkers.py executed")

    def test_fleet_root_passes_over_a_git_file(self):
        fleet_fixture(self.root, "## Fleet\n- name: fx\n")
        write(self.root, ".git", "gitdir: /nonexistent\n")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(audit.fleet_root(self.root))

    def test_git_dir_in_the_environment_does_not_hide_a_plain_fleet(self):
        fleet_fixture(self.root / "fleet", "## Fleet\n- name: fx\n")
        repo = git_repo(self.root, "other")
        with mock.patch.dict(os.environ, {"GIT_DIR": str(repo / ".git")}):
            self.assertEqual(audit.fleet_root(self.root / "fleet"), self.root / "fleet")

    def test_a_git_dir_at_home_is_not_a_work_tree_signal(self):
        home = self.root / "home"
        home.mkdir()
        git(home, "init", "-q")
        fleet_fixture(home / "fleet", "## Fleet\n- name: fx\n")
        clone = git_repo(home, "clone")
        fleet_fixture(clone, "## Fleet\n- name: fx\n")
        with mock.patch.dict(os.environ, {"HOME": str(home)}), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(audit.fleet_root(home / "fleet"), home / "fleet")
            self.assertIsNone(audit.fleet_root(clone), "a clone below a dotfiles $HOME is still passed over")

    def test_tilde_user_row_is_relative_as_in_the_shell(self):
        write(self.root, "FLEET.md", "## Fleet\n- name: fx\n## Repos\n### u\n- path: ~nobody/x\n- group: apps\n")
        (self.root / ".fleet").mkdir()
        (self.root / "~nobody" / "x").mkdir(parents=True)
        audit.configure(self.root)
        self.assertEqual(audit.REPO_DIR["u"], self.root / "~nobody" / "x")

    def test_missing_register_is_an_error(self):
        write(self.root, "FLEET.md", "## Fleet\n- name: fx\n- register: .flet/\n## Repos\n### a\n- group: apps\n")
        (self.root / "a").mkdir()
        with self.assertRaises(SystemExit) as cm:
            audit.configure(self.root)
        self.assertIn("register checkout missing", str(cm.exception))

    def test_register_must_stay_inside(self):
        write(self.root, "FLEET.md", "## Fleet\n- name: fx\n- register: ../elsewhere\n")
        with self.assertRaises(SystemExit) as cm:
            audit.configure(self.root)
        self.assertIn("outside the fleet", str(cm.exception))

    def test_explicit_fleet_without_fleet_md(self):
        with self.assertRaises(SystemExit):
            audit.configure(self.root)

    def test_lone_repo(self):
        r = git_repo(self.root, "solo")
        cwd = os.getcwd()
        try:
            os.chdir(r)
            audit.configure(None)
        finally:
            os.chdir(cwd)
        self.assertIsNone(audit.REGISTER)
        self.assertEqual(audit.FAMILY, ("solo",))
        self.assertEqual(audit.REPO_DIR["solo"], r.resolve())


class Register(unittest.TestCase):
    """load_register merges baseline + overlay by id and validates the
    RESULT: an overlay may add fields and records, never re-parent a check,
    hide a duplicate, or use a severity --fail-on would never match."""
    BASE = "\n".join([
        "controls:", "- id: C-A", "  title: A", "  severity: high", "  intent: a",
        "checks:", "- id: A-1", "  control: C-A", "  scope: repo", "  title: one", "  severity: low",
        "  detect: {method: manual}", ""])

    def setUp(self):
        self.saved = (audit.BASELINE, audit.REGISTER, {k: set(v) for k, v in audit.GROUP_REPOS.items()})
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "base").mkdir(); (self.root / "over").mkdir()
        write(self.root, "base/CONTROLS.yaml", self.BASE.split("checks:")[0])
        write(self.root, "base/CHECKS.yaml", "checks:" + self.BASE.split("checks:")[1])
        audit.BASELINE = self.root / "base"
        audit.REGISTER = self.root / "over"
        audit.GROUP_REPOS.clear()

    def tearDown(self):
        audit.BASELINE, audit.REGISTER, groups = self.saved
        audit.GROUP_REPOS.clear(); audit.GROUP_REPOS.update(groups)
        self.tmp.cleanup()

    def load(self, overlay_checks="", overlay_controls=""):
        if overlay_checks:
            write(self.root, "over/CHECKS.yaml", overlay_checks)
        if overlay_controls:
            write(self.root, "over/CONTROLS.yaml", overlay_controls)
        with contextlib.redirect_stderr(io.StringIO()):
            return audit.load_register()

    def test_overlay_fields_win_and_records_add(self):
        ctrl, checks = self.load(
            "checks:\n- id: A-1\n  severity: low\n"
            "- id: A-2\n  control: C-A\n  scope: ci\n  title: two\n  detect: {method: manual}\n")
        by = {k["id"]: k for k in checks}
        self.assertEqual(by["A-1"]["severity"], "low")
        self.assertEqual(by["A-1"]["title"], "one", "baseline field survives an overlay that did not set it")
        self.assertEqual(by["A-2"]["control"], "C-A")

    def test_a_check_may_not_name_a_repo(self):
        """Rejected, not ignored: dropping the field silently would leave an
        overlay author believing an exemption is in force while every repo in
        it is audited."""
        for field in ("reference: alpha", "known_violations: [alpha]"):
            with self.subTest(field=field):
                with self.assertRaises(SystemExit) as cm:
                    self.load(f"checks:\n- id: A-1\n  {field}\n")
                self.assertIn("retired", str(cm.exception))

    def test_no_overlay_files_is_baseline(self):
        ctrl, checks = self.load()
        self.assertEqual([k["id"] for k in checks], ["A-1"])

    def test_reparenting_rejected(self):
        with self.assertRaises(SystemExit) as cm:
            self.load("checks:\n- id: A-1\n  control: C-B\n", "controls:\n- id: C-B\n  title: B\n  severity: low\n  intent: b\n")
        self.assertIn("re-parent", str(cm.exception))

    def test_duplicate_id_rejected(self):
        with self.assertRaises(SystemExit) as cm:
            self.load("checks:\n- id: A-1\n  title: x\n- id: A-1\n  title: y\n")
        self.assertIn("duplicate", str(cm.exception))

    def test_bad_severity_rejected(self):
        with self.assertRaises(SystemExit) as cm:
            self.load("checks:\n- id: A-1\n  severity: High\n")
        self.assertIn("severity", str(cm.exception))

    def test_orphan_and_untested(self):
        with self.assertRaises(SystemExit):
            self.load("checks:\n- id: A-9\n  control: C-Z\n  scope: repo\n  title: z\n")
        with self.assertRaises(SystemExit):
            self.load("", "controls:\n- id: C-Q\n  title: Q\n  severity: low\n  intent: q\n")

    def test_malformed_yaml_names_the_file(self):
        with self.assertRaises(SystemExit) as cm:
            self.load("checks: [\n")
        self.assertIn("CHECKS.yaml", str(cm.exception))

    def test_applies_to_unknown_name_rejected_inside_a_fleet(self):
        audit.GROUP_REPOS.update({"apps": {"a"}})
        with self.assertRaises(SystemExit) as cm:
            self.load("checks:\n- id: A-1\n  applies_to: [aps]\n")
        self.assertIn("neither a FLEET.md group", str(cm.exception))
        ctrl, checks = self.load("checks:\n- id: A-1\n  applies_to: [Apps, go]\n")
        self.assertTrue(audit.applies(checks[0], "a"), "group names are case-insensitive")


class JsonOutput(unittest.TestCase):
    """The --json contract wayfare's compliance stage parses: one object per
    FAIL or ERROR cell on stdout, nothing else there, summary on stderr."""
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d).resolve()
            fleet_fixture(root, "## Fleet\n- name: fx\n## Repos\n### a\n- group: apps\n",
                          overlay="checks:\n- id: CI-02\n  applies_to: [apps]\n",
                          checkers="from audit import check, FAIL\n@check('ZZ-1')\ndef _(r):\n    raise RuntimeError('boom')\n")
            write(root, ".fleet/CONTROLS.yaml", "controls:\n- id: C-ZZ\n  title: z\n  severity: low\n  intent: z\n")
            write(root, ".fleet/CHECKS.yaml", "checks:\n- id: CI-02\n  applies_to: [apps]\n  example: |\n    version: 2\n- id: ZZ-1\n  control: C-ZZ\n  scope: repo\n  title: boom\n")
            git_repo(root, "a")
            p = subprocess.run([sys.executable, str(HERE / "audit.py"), "--fleet", str(root), "--no-snapshot", "--json", "--repo", "a"],
                               capture_output=True, text=True, env=CLEAN_ENV)
            lines = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
            self.assertTrue(lines, p.stderr)
            by = {(o["check"], o["status"]): o for o in lines}
            self.assertIn(("CI-02", "FAIL"), by, "no dependabot.yml in the fixture")
            self.assertEqual(by[("CI-02", "FAIL")]["example"], "version: 2\n",
                             "the correct shape travels with the finding, not a repo name")
            self.assertEqual(by[("CI-02", "FAIL")]["repo"], "a")
            self.assertIn(("ZZ-1", "ERROR"), by, "a raised checker is on stdout, flagged")
            self.assertIn("failing (check x repo)", p.stderr, "summary went to stderr")
            self.assertEqual(p.returncode, 2, "a checker error exits 2")

    def test_repo_dot_resolves_the_row(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d).resolve()
            fleet_fixture(root, "## Fleet\n- name: fx\n## Repos\n### svc\n- group: apps\n- path: services/svc\n", overlay="checks: []\n")
            (root / "services").mkdir()
            r = git_repo(root / "services", "svc")
            p = subprocess.run([sys.executable, str(HERE / "audit.py"), "--fleet", str(root), "--no-snapshot", "--repo", "."],
                               capture_output=True, text=True, cwd=r, env=CLEAN_ENV)
            self.assertIn("across 1 repos", p.stdout + p.stderr)
            p = subprocess.run([sys.executable, str(HERE / "audit.py"), "--fleet", str(root), "--no-snapshot", "--repo", "svc-typo"],
                               capture_output=True, text=True, cwd=r, env=CLEAN_ENV)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("not a FLEET.md row", p.stderr)


class IdeFloor(unittest.TestCase):
    def test_floor_and_gitignore_note(self):
        with tempfile.TemporaryDirectory() as d:
            r = git_repo(pathlib.Path(d), "fx")
            write(r, "lib/go.mod", "module x\n")
            write(r, ".vscode/extensions.json", '{\n  // jsonc\n  "recommendations": []\n}\n')
            git(r, "add", "-A")
            st, detail = audit.CHECKS["IDE-01"](r)
            self.assertEqual((st, detail), (audit.FAIL, "missing golang.go johnpapa.vscode-cloak redhat.vscode-yaml"))
            git(r, "rm", "-q", "--cached", ".vscode/extensions.json")
            write(r, ".gitignore", ".vscode/\n")
            st, detail = audit.CHECKS["IDE-01"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertTrue(detail.endswith("excludes the .vscode/ directory"), detail)


class DenyAnchoring(unittest.TestCase):
    def test_cwd_relative_deny_does_not_count(self):
        with tempfile.TemporaryDirectory() as d:
            r = pathlib.Path(d)
            (r / "schema" / "gen").mkdir(parents=True)
            write(r, ".claude/settings.json", '{"permissions": {"deny": ["Read(./schema/gen/**)"]}}')
            st, detail = audit.CHECKS["STRUCT-11"](r)
            self.assertEqual(st, audit.FAIL)
            self.assertIn("cwd-relative", detail)
            write(r, ".claude/settings.json", '{"permissions": {"deny": ["Read(/schema/gen/**)"]}}')
            self.assertEqual(audit.CHECKS["STRUCT-11"](r), (audit.PASS, ""))


class Runner(unittest.TestCase):
    def test_bad_status_is_error(self):
        audit.CHECKS["ZZ-00"] = lambda r: ("pass", "")
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                rows, fails, errors = audit.run_matrix([{"id": "ZZ-00", "control": "C"}], ["hero-template"])
        finally:
            del audit.CHECKS["ZZ-00"]
        self.assertEqual(rows[0][1][0][0], audit.ERROR)
        self.assertEqual(len(errors), 1)
        self.assertEqual(fails, [])


class Consistency(unittest.TestCase):
    """scripts/consistency.py, run as a SUBPROCESS.

    It had no coverage at all, and it is the script that regressed: #110
    deleted the `fixed` counter and left the name in the closing print, so a
    run wrote a correct table and then died on a NameError. Importing main()
    would not have caught that — the table is written first, so only the exit
    path is wrong. Every assertion here is therefore about what a real
    invocation leaves behind: the file, the exit status, and the summary.
    """
    def _fleet(self, root):
        # Two DIFFERENT groups, and an overlay check narrowed to one of them.
        # An overlay that restates the baseline is inert: it reads as though it
        # pins applies_to scoping and the overlay merge, and pins neither,
        # so a later change to either could not fail this suite.
        fleet_fixture(root, "## Fleet\n- name: fx\n- org: fx\n## Repos\n"
                            "### a\n- group: apps\n\n### b\n- group: infra\n",
                      overlay="checks:\n- id: CI-02\n  applies_to: [apps]\n")
        write(root, ".fleet/CONTROLS.yaml",
              "controls:\n- id: C-SUPPLY\n  title: s\n  severity: high\n  intent: s\n")
        for name in ("a", "b"):
            git_repo(root, name)
        return root

    def test_applies_to_narrows_the_row_to_its_group(self):
        """The overlay's `applies_to: [apps]` must actually scope CI-02: repo
        `a` (apps) gets a real verdict, repo `b` (infra) gets the not-applicable
        mark. This is what makes the fixture's overlay load-bearing."""
        with tempfile.TemporaryDirectory() as d:
            root = self._fleet(pathlib.Path(d).resolve())
            self.assertEqual(self._run(root).returncode, 0)
            body = (root / ".fleet" / "CONSISTENCY.md").read_text()
            row = [l for l in body.splitlines() if l.startswith("| **CI-02**")]
            self.assertTrue(row, "no CI-02 row in the table")
            cells = [c.strip() for c in row[0].split("|")]
            self.assertIn(audit.MARK[audit.NA], cells,
                          "CI-02 is scoped to apps, so the infra repo's cell must be n/a")

    def _run(self, root, *extra):
        return subprocess.run(
            [sys.executable, str(HERE / "consistency.py"), "--fleet", str(root),
             "--no-snapshot", *extra],
            capture_output=True, text=True, env=CLEAN_ENV)

    def test_writes_the_table_and_exits_clean(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._fleet(pathlib.Path(d).resolve())
            p = self._run(root)
            self.assertEqual(p.returncode, 0, p.stderr)
            out = (root / ".fleet" / "CONSISTENCY.md")
            self.assertTrue(out.is_file(), "no table written")
            body = out.read_text()
            # Both repos are columns, and neither is remembered from a field:
            # the register names no repo, so these come from FLEET.md this run.
            self.assertIn("| Check |", body)
            for name in ("a", "b"):
                self.assertRegex(body, r"\|\s*%s\s*\|" % name)
            self.assertIn("checks under", body)
            # The closing summary is the line that used to raise.
            self.assertIn("wrote", p.stdout)
            self.assertIn("failing", p.stdout)

    def test_no_retired_columns(self):
        """The register names no repo, so neither derived column may return."""
        with tempfile.TemporaryDirectory() as d:
            root = self._fleet(pathlib.Path(d).resolve())
            self.assertEqual(self._run(root).returncode, 0)
            body = (root / ".fleet" / "CONSISTENCY.md").read_text()
            self.assertNotIn("Was broken in", body)
            self.assertNotIn("Reference:", body)
            self.assertNotIn("needs a decision", body)

    def test_stdout_mode_writes_no_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._fleet(pathlib.Path(d).resolve())
            p = self._run(root, "--stdout")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("| Check |", p.stdout)
            self.assertFalse((root / ".fleet" / "CONSISTENCY.md").exists(),
                             "--stdout must not write the file")

    def test_outside_a_fleet_refuses(self):
        """CONSISTENCY.md is the fleet's table. With no FLEET.md there is no
        family to build columns from, and a one-repo table would read as one.

        Run from INSIDE the lonely repo with no --fleet, so fleet_root() walks
        up and finds nothing. Passing `--fleet <that repo>` instead dies in
        audit.configure's own argument validation ("no FLEET.md there"), which
        is a different refusal: delete consistency.py's guard entirely and that
        version still goes green, because the assertion matched the word
        "FLEET.md" in an unrelated message."""
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d).resolve()
            git_repo(root, "lonely")
            p = subprocess.run(
                [sys.executable, str(HERE / "consistency.py"), "--no-snapshot"],
                cwd=str(root / "lonely"), capture_output=True, text=True, env=CLEAN_ENV)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("not inside a fleet", p.stderr, p.stdout)
class CI20Owner(unittest.TestCase):
    """CI-20 must not be silenceable by the repo it is auditing.

    The owner exemption is a content test on `<repo>/.github/workflows/
    auto-approve.yaml`, which the audited repo controls. `workflow_call` alone
    was enough to claim it, GitHub accepts extra triggers at no cost, and NA is
    not emitted by --json — so a repo whose caller had drifted could add one
    line, keep the drift, and erase the finding instead of fixing it.
    """
    def _verdict(self, body):
        with tempfile.TemporaryDirectory() as d:
            repo = pathlib.Path(d) / "consumer"
            (repo / ".github" / "workflows").mkdir(parents=True)
            (repo / ".github" / "workflows" / "auto-approve.yaml").write_text(body)
            return audit.CHECKS["CI-20"](repo)[0]

    def setUp(self):
        # `_PLUGIN_ASSETS` is unbound outside reference_assets(), so without
        # this every asset-comparing case reads MANUAL and passes vacuously.
        # This repo IS the plugin, so its own assets/ is the right reference.
        self._saved_assets = audit._PLUGIN_ASSETS
        audit._PLUGIN_ASSETS = HERE.parent / "assets"
        self.asset = (HERE.parent / "assets" / "auto-approve" / "caller.yaml").read_text()

    def tearDown(self):
        audit._PLUGIN_ASSETS = self._saved_assets

    def test_pristine_caller_passes(self):
        self.assertEqual(self._verdict(self.asset), audit.PASS)

    def test_drifted_caller_fails(self):
        self.assertEqual(self._verdict(self.asset.replace("@main", "@some-branch")), audit.FAIL)

    def test_workflow_call_does_not_excuse_a_caller_that_still_delegates(self):
        drifted = self.asset.replace("@main", "@some-branch")
        spoof = drifted.replace("on:\n", "on:\n  workflow_call:\n", 1)
        self.assertEqual(self._verdict(spoof), audit.FAIL,
                         "adding workflow_call must not turn a drifted caller into NA")

    def test_the_real_shared_workflow_is_exempt(self):
        owner = (HERE.parent / ".github" / "workflows" / "auto-approve.yaml").read_text()
        self.assertEqual(self._verdict(owner), audit.NA)


class ReferenceAssets(unittest.TestCase):
    """The asset reference is the plugin checkout's origin/main, whatever
    branch the checkout is on: a stale branch's caller.yaml inverted CI-20
    for the whole fleet."""

    CALLER = ("on:\n  pull_request:\njobs:\n  approve:\n"
              "    uses: ai-hero/wayfare-skills/.github/workflows/auto-approve.yaml@main  # {}\n")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        upstream = git_repo(root, "upstream")
        self.commit(upstream, "v1")
        # Cloned before v2 lands, so only a fetch can see v2.
        git(root, "clone", "-q", str(upstream), "wayfare-skills")
        self.plugin = root / "wayfare-skills"
        git(self.plugin, "config", "user.email", "t@example.com")
        git(self.plugin, "config", "user.name", "t")
        git(self.plugin, "checkout", "-q", "-b", "stale")
        self.commit(self.plugin, "stale")
        self.commit(upstream, "v2")
        self.consumer = root / "consumer"
        self.saved = audit._PLUGIN_HOME, os.environ.pop("HERO_SKILLS_PLUGIN", None)
        audit._PLUGIN_HOME = self.plugin

    def tearDown(self):
        audit._PLUGIN_HOME, override = self.saved
        if override is not None:
            os.environ["HERO_SKILLS_PLUGIN"] = override
        else:
            os.environ.pop("HERO_SKILLS_PLUGIN", None)
        self.tmp.cleanup()

    def commit(self, repo, tag):
        write(repo, "assets/auto-approve/caller.yaml", self.CALLER.format(tag))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", tag)

    def ci20(self, tag):
        write(self.consumer, ".github/workflows/auto-approve.yaml", self.CALLER.format(tag))
        return audit.CHECKS["CI-20"](self.consumer)[0]

    def test_origin_main_not_the_checked_out_branch(self):
        with audit.reference_assets() as note:
            self.assertEqual(self.ci20("v2"), audit.PASS, "the caller on origin/main after a fetch")
            self.assertEqual(self.ci20("stale"), audit.FAIL, "the checked-out branch is not the reference")
            self.assertEqual(self.ci20("v1"), audit.FAIL, "origin/main as cloned, before the fetch")
        self.assertRegex(note, r"^origin/main @ [0-9a-f]+ in ")
        self.assertNotIn("fetch failed", note)
        self.assertEqual(self.ci20("v2"), audit.MANUAL, "unbound outside reference_assets()")

    def test_override_reads_the_working_tree(self):
        os.environ["HERO_SKILLS_PLUGIN"] = str(self.plugin)
        write(self.plugin, "assets/auto-approve/caller.yaml", self.CALLER.format("unmerged"))
        with audit.reference_assets() as note:
            self.assertEqual(self.ci20("unmerged"), audit.PASS)
        self.assertIn("override", note)

    def test_failed_fetch_is_reported_and_never_reads_the_working_tree(self):
        git(self.plugin, "remote", "set-url", "origin", str(self.plugin.parent / "gone"))
        with contextlib.redirect_stderr(io.StringIO()) as err:
            with audit.reference_assets() as note:
                self.assertEqual(self.ci20("v1"), audit.PASS, "origin/main as last fetched")
                self.assertEqual(self.ci20("stale"), audit.FAIL)
        self.assertIn("fetch failed", note)
        self.assertIn("fetch", err.getvalue())

    def test_hung_fetch_falls_back_like_a_failed_one(self):
        real = audit.sh3

        def hang(cwd, cmd):
            if " fetch " in f" {cmd} ":
                raise subprocess.TimeoutExpired(cmd, 60)
            return real(cwd, cmd)
        audit.sh3 = hang
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                with audit.reference_assets() as note:
                    self.assertEqual(self.ci20("v1"), audit.PASS, "origin/main as last fetched")
        finally:
            audit.sh3 = real
        self.assertIn("timed out after 60s", note)

    def test_absent_checkout_is_named(self):
        audit._PLUGIN_HOME = self.plugin.parent / "nowhere"
        with audit.reference_assets() as note:
            self.assertEqual(self.ci20("v2"), audit.MANUAL)
        self.assertIn("absent", note)


class EngineAtOrigin(unittest.TestCase):
    """The engine, register and assets run from the plugin checkout's
    origin/main, whatever branch it sits on. The fixture's origin/main carries
    one extra check and a line the stale branch's engine lacks."""

    NEW_CHECK = ("\n- id: ZZ-NEW\n  control: C-SUPPLY\n  scope: repo\n  title: only on main\n"
                 "  example: |\n    x\n  detect:\n    method: manual\n")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name).resolve()
        upstream = git_repo(self.root, "upstream")
        for rel in ("scripts/audit.py", "scripts/consistency.py",
                    "assets/compliance/CONTROLS.yaml", "assets/compliance/CHECKS.yaml"):
            write(upstream, rel, (HERE.parent / rel).read_text())
        git(upstream, "add", "-A")
        git(upstream, "commit", "-q", "-m", "v1")
        git(self.root, "clone", "-q", str(upstream), "home/.claude/plugins/wayfare-skills")
        self.plugin = self.root / "home/.claude/plugins/wayfare-skills"
        git(self.plugin, "config", "user.email", "t@example.com")
        git(self.plugin, "config", "user.name", "t")
        git(self.plugin, "checkout", "-q", "-b", "stale")
        write(upstream, "assets/compliance/CHECKS.yaml",
              (upstream / "assets/compliance/CHECKS.yaml").read_text() + self.NEW_CHECK)
        audit_py = upstream / "scripts/audit.py"
        audit_py.write_text(audit_py.read_text().replace(
            "def main():\n", "def main():\n    print('ran-origin-engine', file=sys.stderr)\n", 1))
        git(upstream, "add", "-A")
        git(upstream, "commit", "-q", "-m", "v2")
        self.fleet = self.root / "fleet"
        self.fleet.mkdir()
        fleet_fixture(self.fleet, "## Fleet\n- name: fx\n- org: fx\n## Repos\n### a\n- group: apps\n")
        git_repo(self.fleet, "a")

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, script, *args, **env):
        e = {k: v for k, v in CLEAN_ENV.items() if k != "HERO_SKILLS_PLUGIN"}
        # HOME moves so _PLUGIN_HOME is the fixture; the user site (where a
        # developer's pyyaml may live) is found through HOME, so pin it.
        e.update(HOME=str(self.root / "home"), PYTHONUSERBASE=site.getuserbase(), **env)
        return subprocess.run([sys.executable, str(self.plugin / "scripts" / script),
                               "--fleet", str(self.fleet), "--no-snapshot", *args],
                              capture_output=True, text=True, env=e)

    def test_stale_checkout_runs_origin_main(self):
        p = self.run_script("audit.py", "--md")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("ZZ-NEW", p.stdout, "a check added on origin/main is listed")
        self.assertIn("ran-origin-engine", p.stderr, "origin/main's engine code ran")
        self.assertRegex(p.stdout, r"engine: origin/main @ ([0-9a-f]+) in .*\nassets: origin/main @ \1 in ")

    def test_json_header_goes_to_stderr(self):
        p = self.run_script("audit.py", "--json")
        self.assertNotIn("engine:", p.stdout)
        self.assertIn("engine: origin/main @ ", p.stderr)

    def test_consistency_reads_origin_main_register(self):
        p = self.run_script("consistency.py")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("ZZ-NEW", (self.fleet / ".fleet" / "CONSISTENCY.md").read_text())
        self.assertIn("engine: origin/main @ ", p.stderr)

    def test_override_runs_the_invoked_tree(self):
        p = self.run_script("audit.py", "--md", HERO_SKILLS_PLUGIN=str(self.plugin))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("ZZ-NEW", p.stdout)
        self.assertNotIn("ran-origin-engine", p.stderr)
        self.assertIn("engine: working tree", p.stdout)
        self.assertIn("HERO_SKILLS_PLUGIN override", p.stdout)
        self.assertIn(f"assets from {self.plugin}", p.stdout, "the engine named is the one that ran")

    def test_marker_stops_a_second_reexec(self):
        p = self.run_script("audit.py", "--md", WAYFARE_ENGINE_AT="origin/main @ abc1234 in X")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("ZZ-NEW", p.stdout, "the invoked tree ran, nothing was extracted")
        self.assertIn("engine: origin/main @ abc1234 in X", p.stdout)

    def test_no_plugin_checkout_runs_the_invoked_engine(self):
        shutil.rmtree(self.plugin / ".git")
        p = self.run_script("audit.py", "--md")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("ZZ-NEW", p.stdout)
        self.assertRegex(p.stdout, r"engine: working tree .*is not a git checkout.*may be stale")

    def test_exit_code_is_the_childs(self):
        p = self.run_script("audit.py", "--md", "--fail-on", "high,medium,low")
        self.assertNotEqual(p.returncode, 0, "the bare fixture repo fails checks, and the child's code propagates")


class ExtractTar(unittest.TestCase):
    """_extract_tar is the only guard on 3.9.6, where `filter="data"` does not
    exist. Each case also runs with `data_filter` removed, so the 3.9 branch
    is exercised on whatever Python runs the suite."""

    def both_branches(self, fn):
        fn()
        if hasattr(tarfile, "data_filter"):
            saved = tarfile.data_filter
            del tarfile.data_filter
            try:
                for p in self.dest.iterdir():
                    shutil.rmtree(p) if p.is_dir() else p.unlink()
                fn()
            finally:
                tarfile.data_filter = saved

    @staticmethod
    def tar(*entries):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as t:
            for name, kind in entries:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.mode = 0o755 if kind == tarfile.DIRTYPE else 0o644
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    info.linkname = "/etc/passwd"
                data = b"x" if kind == tarfile.REGTYPE else b""
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.dest = self.root / "dest"
        self.dest.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_normal_assets_archive_extracts(self):
        data = self.tar(("assets/", tarfile.DIRTYPE), ("assets/a/", tarfile.DIRTYPE),
                        ("assets/a/caller.yaml", tarfile.REGTYPE))

        def run():
            audit._extract_tar(data, self.dest, "test")
            self.assertTrue((self.dest / "assets" / "a" / "caller.yaml").is_file())
        self.both_branches(run)

    def test_traversal_member_raises_and_writes_nothing(self):
        data = self.tar(("assets/ok.yaml", tarfile.REGTYPE), ("../escape.txt", tarfile.REGTYPE))

        def run():
            with self.assertRaisesRegex(RuntimeError, "escape.txt"):
                audit._extract_tar(data, self.dest, "test")
            self.assertFalse((self.root / "escape.txt").exists())
            self.assertEqual(list(self.dest.iterdir()), [], "validated before anything is written")
        self.both_branches(run)

    def test_absolute_and_link_members_raise(self):
        def run():
            for entry in (("/tmp/abs.txt", tarfile.REGTYPE), ("assets/link", tarfile.SYMTYPE),
                          ("assets/hard", tarfile.LNKTYPE)):
                with self.assertRaises(RuntimeError, msg=entry):
                    audit._extract_tar(self.tar(entry), self.dest, "test")
        self.both_branches(run)


class SCAN01(unittest.TestCase):
    """The expiry gate is the only thing that reads a VEX `expired_at`, so a
    repo holding exceptions without it running on PRs and in every scan that
    applies them must fail."""

    PR_GATE = ("on:\n  pull_request:\njobs:\n  lint:\n    steps:\n"
               "      - run: ./scripts/check-exception-expiry.sh{arg}\n")
    SCAN = ("on:\n  schedule:\n    - cron: '0 6 * * *'\njobs:\n  scan:\n    steps:\n"
            "{gate}"
            "      - uses: docker/scout-action@x\n        with:\n          vex-location: .vex\n")

    def setUp(self):
        self._saved_assets = audit._PLUGIN_ASSETS
        audit._PLUGIN_ASSETS = HERE.parent / "assets"
        self.asset = (HERE.parent / "assets" / "exception-expiry" / "check-exception-expiry.sh").read_text()
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name) / "consumer"
        write(self.repo, ".vex/x.openvex.json", '{"statements": []}')
        write(self.repo, "scripts/check-exception-expiry.sh", self.asset)

    def tearDown(self):
        audit._PLUGIN_ASSETS = self._saved_assets
        self.tmp.cleanup()

    def verdict(self):
        return audit.CHECKS["SCAN-01"](self.repo)

    def wf(self, name, text):
        write(self.repo, f".github/workflows/{name}", text)

    def gated_scan(self, arg=""):
        return self.SCAN.format(gate=f"      - run: ./scripts/check-exception-expiry.sh{arg}\n")

    def test_no_exceptions_is_na(self):
        (self.repo / ".vex" / "x.openvex.json").unlink()
        self.assertEqual(self.verdict()[0], audit.NA)

    def test_gated_pr_and_scan_passes(self):
        self.wf("build.yaml", self.PR_GATE.format(arg=""))
        self.wf("image-scan.yaml", self.gated_scan())
        self.assertEqual(self.verdict(), (audit.PASS, ""))

    def test_drifted_script_fails(self):
        write(self.repo, "scripts/check-exception-expiry.sh", self.asset.replace("90", "900"))
        self.wf("build.yaml", self.PR_GATE.format(arg=""))
        self.assertEqual(self.verdict()[0], audit.FAIL)

    def test_missing_script_fails(self):
        (self.repo / "scripts" / "check-exception-expiry.sh").unlink()
        self.wf("build.yaml", self.PR_GATE.format(arg=""))
        self.assertEqual(self.verdict()[0], audit.FAIL)

    def test_scan_applying_vex_without_gate_fails(self):
        self.wf("build.yaml", self.PR_GATE.format(arg=""))
        self.wf("image-scan.yaml", self.SCAN.format(gate=""))
        status, detail = self.verdict()
        self.assertEqual(status, audit.FAIL)
        self.assertIn("image-scan.yaml", detail)

    def test_scheduled_gate_alone_fails(self):
        self.wf("image-scan.yaml", self.gated_scan())
        status, detail = self.verdict()
        self.assertEqual(status, audit.FAIL)
        self.assertIn("pull_request", detail)

    def test_a_gate_that_cannot_fail_does_not_count(self):
        for run in ("./scripts/check-exception-expiry.sh || true",
                    "echo hi  # TODO wire check-exception-expiry.sh"):
            self.wf("build.yaml", "on:\n  pull_request:\njobs:\n  lint:\n    steps:\n"
                    f"      - run: {run}\n")
            self.assertEqual(self.verdict()[0], audit.FAIL, run)
        self.wf("build.yaml", "on:\n  pull_request:\njobs:\n  lint:\n    steps:\n"
                "      - run: ./scripts/check-exception-expiry.sh\n        continue-on-error: true\n")
        self.assertEqual(self.verdict()[0], audit.FAIL)

    def test_undated_plain_trivyignore_fails(self):
        write(self.repo, ".trivyignore", "# header\nCVE-2026-1\n")
        self.wf("build.yaml", self.PR_GATE.format(arg=""))
        status, detail = self.verdict()
        self.assertEqual(status, audit.FAIL)
        self.assertIn("CVE-2026-1", detail)
        write(self.repo, ".trivyignore", "# header only\n")
        self.assertEqual(self.verdict(), (audit.PASS, ""))

    def test_vex_location_elsewhere_fails(self):
        self.wf("build.yaml", self.PR_GATE.format(arg=""))
        self.wf("image-scan.yaml", self.gated_scan().replace("vex-location: .vex", "vex-location: security/vex"))
        self.assertEqual(self.verdict()[0], audit.FAIL)

    def test_trivyignore_yaml_must_be_named(self):
        write(self.repo, ".trivyignore.yaml", "vulnerabilities: []\n")
        self.wf("build.yaml", self.PR_GATE.format(arg=""))
        self.assertEqual(self.verdict()[0], audit.FAIL)
        self.wf("build.yaml", self.PR_GATE.format(arg=" .trivyignore.yaml"))
        self.assertEqual(self.verdict(), (audit.PASS, ""))


class RuleNotSpelling(unittest.TestCase):
    """Each pair: a repo following the rule by another spelling passes, and a
    true violation still fails."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)

    def repo(self, files):
        r = git_repo(self.root, "r")
        for rel, text in files.items():
            write(r, rel, text)
        git(r, "add", "-A")
        git(r, "commit", "-q", "-m", "x")
        return r

    def verdict(self, cid, r):
        return audit.CHECKS[cid](r)

    # PRE-06
    SEMGREP = "repos:\n- repo: b\n  hooks:\n  - id: semgrep\n    args:\n{args}"

    def pre06(self, args):
        r = self.root / "p"
        write(r, ".pre-commit-config.yaml", self.SEMGREP.format(args="".join(f"    - {a}\n" for a in args)))
        return self.verdict("PRE-06", r)[0]

    def test_pre06_any_config_value(self):
        flags = ["--error", "--skip-unknown-extensions"]
        self.assertEqual(self.pre06(["--config=auto"] + flags), audit.PASS)
        self.assertEqual(self.pre06(["--config=p/default", "--config=p/golang", "--metrics=off"] + flags), audit.PASS)
        self.assertEqual(self.pre06(["--config", "p/default"] + flags), audit.PASS)

    def test_pre06_still_fails_violations(self):
        self.assertEqual(self.pre06(["--error", "--skip-unknown-extensions"]), audit.FAIL)
        self.assertEqual(self.pre06(["--config=", "--error", "--skip-unknown-extensions"]), audit.FAIL)
        self.assertEqual(self.pre06(["--config", "--error", "--skip-unknown-extensions"]), audit.FAIL)
        self.assertEqual(self.pre06(["--config=p/default", "--skip-unknown-extensions"]), audit.FAIL)
        self.assertEqual(self.pre06(["--config=p/default", "--error"]), audit.FAIL)
        r = self.root / "p"
        write(r, ".pre-commit-config.yaml", self.SEMGREP.format(
            args="    - --error\n    - --skip-unknown-extensions\n    - --config\n") + "    stages: [pre-push]\n")
        self.assertEqual(self.verdict("PRE-06", r)[0], audit.FAIL, "a trailing bare --config has no value")

    # PLACE-04
    def test_place04_go_module_at_root(self):
        r = self.repo({"go.mod": "module x\n", "go.sum": "", "main.go": "package main\n"})
        self.assertEqual(self.verdict("PLACE-04", r)[0], audit.PASS)

    def test_place04_stray_go_file_without_go_mod_fails(self):
        r = self.repo({"main.go": "package main\n", "go.sum": ""})
        st, detail = self.verdict("PLACE-04", r)
        self.assertEqual(st, audit.FAIL)
        self.assertIn("main.go", detail)
        self.assertNotIn("go.sum", detail)

    def test_place04_other_stray_file_fails_beside_go_mod(self):
        r = self.repo({"go.mod": "module x\n", "notes.txt": "x\n"})
        st, detail = self.verdict("PLACE-04", r)
        self.assertEqual((st, detail), (audit.FAIL, "notes.txt"))

    # JUST-01
    BASE = "".join(f"{n}:\n    echo\n" for n in ("test", "lint", "typecheck", "clean", "format"))

    def test_just01_go_library_without_a_dev_stack(self):
        r = self.root / "j"
        write(r, "go.mod", "module x\n")
        write(r, "Justfile", self.BASE + "build:\n    go build\n")
        self.assertEqual(self.verdict("JUST-01", r), (audit.PASS, ""))

    def test_just01_dev_stack_demands_health_and_dev_stack(self):
        r = self.root / "j"
        write(r, "go.mod", "module x\n")
        write(r, "docker-compose.dev.yaml", "services: {}\n")
        write(r, "Justfile", self.BASE + "build:\n    go build\ndev-stack:\n    up\n")
        self.assertEqual(self.verdict("JUST-01", r), (audit.FAIL, "no health"))

    def test_just01_prod_image_demands_dev_stack(self):
        r = self.root / "j"
        write(r, "Dockerfile.prod", "FROM scratch\n")
        write(r, "Justfile", self.BASE + "build:\n    x\nhealth:\n    x\n")
        self.assertEqual(self.verdict("JUST-01", r), (audit.FAIL, "no dev-stack"))

    def test_just01_build_keeps_the_backend_predicate(self):
        r = self.root / "j"
        write(r, "go.mod", "module x\n")
        write(r, "Justfile", self.BASE)
        self.assertEqual(self.verdict("JUST-01", r), (audit.FAIL, "no build"))

    # CI-08
    def ci08(self, files):
        r = self.root / "c"
        for name, text in files.items():
            write(r, f".github/workflows/{name}", text)
        return self.verdict("CI-08", r)

    PUSH_JOB = "jobs:\n  b:\n{conc}    steps:\n      - run: docker push img\n"

    def test_ci08_signal_without_concurrency_fails(self):
        st, detail = self.ci08({"build.yaml": self.PUSH_JOB.format(conc="")})
        self.assertEqual((st, detail), (audit.FAIL, "build.yaml"))

    def test_ci08_every_concurrency_placement_passes(self):
        top = "concurrency:\n  group: g\n" + self.PUSH_JOB.format(conc="")
        job = self.PUSH_JOB.format(conc="    concurrency:\n      group: g\n")
        for text in (top, job):
            self.assertEqual(self.ci08({"build.yaml": text}), (audit.PASS, ""))

    def test_ci08_job_level_must_cover_every_racing_job(self):
        two = (
            "jobs:\n  a:\n    concurrency: {group: g}\n    steps:\n      - run: git push\n"
            "  b:\n    steps:\n      - run: git tag v1\n"
        )
        self.assertEqual(self.ci08({"build.yaml": two}), (audit.FAIL, "build.yaml"))

    def test_ci08_each_signal_races(self):
        for body in (
            "      - uses: docker/build-push-action@x\n        with:\n          push: true\n",
            "      - uses: docker/build-push-action@x\n        with:\n          cache-to: type=gha\n",
            "      - uses: actions/cache@x\n",
            "      - run: git tag v1\n",
            "      - uses: docker/build-push-action@x\n        with:\n"
            "          push: ${{ github.event_name != 'pull_request' }}\n",
            "      - uses: google-github-actions/deploy-cloudrun@v2\n",
            "      - run: gcloud run deploy svc\n",
            "      - run: npm publish\n",
            "      - run: gh release create v1\n",
            "      - run: kubectl apply -f k8s/\n",
        ):
            st, _ = self.ci08({"w.yaml": "jobs:\n  j:\n    steps:\n" + body})
            self.assertEqual(st, audit.FAIL, body)
        for head in ("    environment: prod\n", "    uses: org/repo/.github/workflows/deploy.yaml@x\n"):
            st, _ = self.ci08({"w.yaml": "jobs:\n  j:\n" + head})
            self.assertEqual(st, audit.FAIL, head)

    def test_ci08_read_only_workflows_are_not_applicable(self):
        st, _ = self.ci08({"ci.yaml": "jobs:\n  t:\n    steps:\n      - run: just test\n"})
        self.assertEqual(st, audit.NA)
        st, _ = self.ci08({"ci.yaml": "jobs:\n  t:\n    steps:\n      - uses: docker/build-push-action@x\n"
                           "        with:\n          push: false\n"})
        self.assertEqual(st, audit.NA)

    def test_ci08_concurrency_without_a_signal_keeps_its_pass(self):
        st, _ = self.ci08({"ci.yaml": "concurrency:\n  group: g\njobs:\n  t:\n    steps:\n      - run: just test\n"})
        self.assertEqual(st, audit.PASS)

    def test_ci08_a_comment_is_not_a_signal(self):
        st, _ = self.ci08({"ci.yaml": "# we used to git push here\njobs:\n  t:\n    steps:\n      - run: just test\n"})
        self.assertEqual(st, audit.NA)

    # CTR-01
    NODE_CI = (
        "jobs:\n  a:\n    steps:\n"
        "      - uses: actions/setup-node@v4\n        with:\n          node-version: '20'\n"
        "{extra}"
    )

    def ctr01(self, files, extra=""):
        r = self.root / "n"
        write(r, ".nvmrc", "20\n")
        write(r, ".github/workflows/ci.yaml", self.NODE_CI.format(extra=extra))
        for rel, text in files.items():
            write(r, rel, text)
        return self.verdict("CTR-01", r)

    ASSERT_SH = "#!/bin/sh\nwant=$(cat .nvmrc)\ngrep -q \"distroless/nodejs$want\" Dockerfile\n"

    def test_ctr01_script_run_by_ci_asserts(self):
        st, _ = self.ctr01({"scripts/check-node.sh": self.ASSERT_SH}, "      - run: scripts/check-node.sh\n")
        self.assertEqual(st, audit.PASS)

    def test_ctr01_just_recipe_run_by_ci_asserts(self):
        jf = "check-node:\n    sh scripts/check-node.sh\n\ntest:\n    echo\n"
        st, _ = self.ctr01({"Justfile": jf, "scripts/check-node.sh": self.ASSERT_SH}, "      - run: just check-node\n")
        self.assertEqual(st, audit.PASS)
        jf = "check-node:\n    grep distroless/nodejs20 Dockerfile && cat .nvmrc\n"
        st, _ = self.ctr01({"Justfile": jf}, "      - run: just check-node\n")
        self.assertEqual(st, audit.PASS)

    def test_ctr01_agreeing_but_unasserted_still_fails(self):
        st, detail = self.ctr01({"scripts/other.sh": "echo hi\n"}, "      - run: scripts/other.sh\n")
        self.assertEqual(st, audit.FAIL)
        self.assertIn("does not assert", detail)

    def test_ctr01_two_mentions_are_not_a_comparison(self):
        build = ("      - uses: actions/setup-node@v4\n        with:\n          node-version-file: .nvmrc\n"
                 "      - run: docker build --build-arg BASE=gcr.io/distroless/nodejs20 .\n")
        self.assertEqual(self.ctr01({}, build)[0], audit.FAIL)
        todo = "      # TODO: compare .nvmrc with distroless/nodejs\n      - run: echo\n"
        self.assertEqual(self.ctr01({}, todo)[0], audit.FAIL)
        commented = "#!/bin/sh\n# should read .nvmrc and grep distroless/nodejs\necho ok\n"
        st, _ = self.ctr01({"scripts/check-node.sh": commented}, "      - run: scripts/check-node.sh\n")
        self.assertEqual(st, audit.FAIL)

    def test_ctr01_recipe_name_is_matched_whole(self):
        jf = "check-node:\n    grep distroless/nodejs20 Dockerfile && cat .nvmrc\n\ncheck:\n    echo\n"
        st, _ = self.ctr01({"Justfile": jf}, "      - run: just check\n")
        self.assertEqual(st, audit.FAIL)

    def test_ctr01_an_assertion_ci_never_runs_does_not_count(self):
        st, _ = self.ctr01({"scripts/check-node.sh": self.ASSERT_SH, "Justfile": "check-node:\n    sh scripts/check-node.sh\n"})
        self.assertEqual(st, audit.FAIL)

    # UI-01
    HOOK = "export function useVersionCheck() { return false }\n"
    BANNER = "import { useVersionCheck } from '../hooks/use-version-check'\nexport function UpdateBanner() { useVersionCheck(); return null }\n"
    SHELL = "import { UpdateBanner } from './update-banner'\nexport function Shell() { return <UpdateBanner /> }\n"

    def ui01(self, files):
        base = {"package.json": "{}\n", "src/hooks/use-version-check.ts": self.HOOK}
        return self.verdict("UI-01", self.repo({**base, **files}))

    def test_ui01_gate_mounted_through_the_chain(self):
        st, detail = self.ui01({
            "src/components/update-banner.tsx": self.BANNER,
            "src/components/shell.tsx": self.SHELL,
            "src/routes/__root.tsx": "import { Shell } from '@/components/shell'\nexport const Route = { component: () => <Shell /> }\n",
        })
        self.assertEqual(st, audit.PASS, detail)
        self.assertIn("__root.tsx", detail)

    def test_ui01_chain_imported_but_never_rendered_fails(self):
        st, _ = self.ui01({
            "src/components/update-banner.tsx": self.BANNER,
            "src/components/shell.tsx": self.SHELL,
            "src/routes/__root.tsx": "import { Shell } from '@/components/shell'\nexport const Route = { shell: Shell }\n",
        })
        self.assertEqual(st, audit.FAIL)

    def test_ui01_chain_never_imported_by_the_app_fails(self):
        st, _ = self.ui01({
            "src/components/update-banner.tsx": self.BANNER,
            "src/components/shell.tsx": self.SHELL,
        })
        self.assertEqual(st, audit.FAIL)

    def test_ui01_chain_rendered_only_in_a_test_fails(self):
        st, _ = self.ui01({
            "src/components/update-banner.tsx": self.BANNER,
            "src/components/shell.test.tsx": self.SHELL,
            "src/routes/__root.tsx": "export const Route = {}\n",
        })
        self.assertEqual(st, audit.FAIL)

    def test_ui01_chain_longer_than_three_hops_fails(self):
        st, _ = self.ui01({
            "src/components/update-banner.tsx": self.BANNER,
            "src/components/a.tsx": "import { UpdateBanner } from './update-banner'\nexport function A() { return <UpdateBanner /> }\n",
            "src/components/b.tsx": "import { A } from './a'\nexport function B() { return <A /> }\n",
            "src/components/c.tsx": "import { B } from './b'\nexport function C() { return <B /> }\n",
            "src/routes/__root.tsx": "import { C } from '@/components/c'\nexport const Route = { component: () => <C /> }\n",
        })
        self.assertEqual(st, audit.FAIL)

    def test_ui01_component_folder_index_is_not_an_entry(self):
        st, _ = self.ui01({
            "src/components/update-banner.tsx": self.BANNER,
            "src/components/shell/index.tsx": "import { UpdateBanner } from '../update-banner'\n"
                                              "export function Shell() { return <UpdateBanner /> }\n",
        })
        self.assertEqual(st, audit.FAIL)

    def test_ui01_commented_out_render_fails(self):
        st, _ = self.ui01({
            "src/components/update-banner.tsx": self.BANNER,
            "src/routes/__root.tsx": "import { UpdateBanner } from '@/components/update-banner'\n"
                                     "// TODO render <UpdateBanner />\nexport const Route = {}\n",
        })
        self.assertEqual(st, audit.FAIL)

    def test_ui01_package_import_does_not_resolve_to_a_local_file(self):
        st, _ = self.ui01({
            "src/components/update-banner.tsx": self.BANNER,
            "src/lib/react.tsx": "import { UpdateBanner } from '../components/update-banner'\n"
                                 "export function R() { return <UpdateBanner /> }\n",
            "src/routes/__root.tsx": "import { R } from 'react'\nexport const Route = { component: () => <R /> }\n",
        })
        self.assertEqual(st, audit.FAIL)

    def test_ui01_literal_version_gate_still_passes(self):
        st, _ = self.ui01({
            "src/components/version-gate.tsx": "export function VersionGate() { return null }\n",
            "src/app.tsx": "import { VersionGate } from './components/version-gate'\nexport const A = () => <VersionGate />\n",
        })
        self.assertEqual(st, audit.PASS)


if __name__ == "__main__":
    unittest.main()
