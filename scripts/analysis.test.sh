#!/usr/bin/env bash

# Copyright (c) 2026 A.I. Hero, Inc.
# All Rights Reserved.

# Runs the research pipeline's Python tables (scripts/analysis_test.py) so they
# gate with the shell suites: both runners glob scripts/*.test.sh and neither
# knows about .py.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# The plugin root decides PLUGIN_REPO_NAME; an inherited one would make the
# fixture fleet's category cases depend on whoever runs the suite.
unset CLAUDE_PLUGIN_ROOT
WAYFARE_ROOT="$(pwd)" python3 -m unittest scripts/analysis_test.py
