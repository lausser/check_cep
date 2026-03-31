"""Shared utilities for container-side plugins."""

# Directories skipped when walking test trees.
# These are shared-utility folders that never hold test entry points.
SKIP_DIRS = {"functions", "variables", "node_modules"}


def has_test_files(path: str) -> bool:
    """Return True if *path* contains at least one *.test.ts / *.test.js file."""
    import os
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(".test.ts") or f.endswith(".test.js"):
                return True
    return False
