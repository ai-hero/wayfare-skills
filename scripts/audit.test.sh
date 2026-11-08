#!/usr/bin/env bash

# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Runs the compliance engine's Python tables so they gate with the shell
# suites: both runners glob scripts/*.test.sh and neither knows about .py.
# No skip when uv is missing: a suite that skips prints the same as one that
# passed.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
uv run --quiet scripts/audit_test.py
