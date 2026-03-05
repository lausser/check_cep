"""source_local.py - Test source plugin: local mount.

Validates ~/tests directory exists and contains test files.
When test-source=local, the host mounts the test directory at ~/tests.
"""

import os


def acquire_tests(test_name: str, dest_path: str) -> None:
    """Validate that test files are present at dest_path.

    Args:
        test_name: TESTNAME — symbolic identifier (not a filesystem path)
        dest_path: Container-side path where tests must be ("~/tests")

    Raises:
        RuntimeError: If dest_path doesn't exist or contains no test files
    """
    if not os.path.isdir(dest_path):
        raise RuntimeError(f"Test directory '{dest_path}' does not exist")

    # Walk to find *.test.ts files
    has_tests = False
    for root, dirs, files in os.walk(dest_path):
        dirs[:] = [d for d in dirs if d not in {"variables", "functions", "node_modules"}]
        for f in files:
            if f.endswith(".test.ts") or f.endswith(".test.js"):
                has_tests = True
                break
        if has_tests:
            break

    if not has_tests:
        raise RuntimeError(f"No test files (*.test.ts, *.test.js) found in '{dest_path}'")
