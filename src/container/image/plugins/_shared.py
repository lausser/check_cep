"""Shared utilities for container-side plugins."""

# Directories skipped when walking test trees.
# These are shared-utility folders that never hold test entry points.
SKIP_DIRS = {"functions", "variables", "node_modules"}

# File names that mark a directory as a test directory in discovery mode
# (spec 023 FR-042).
TEST_FILE_SUFFIXES = (".test.ts", ".test.js")
