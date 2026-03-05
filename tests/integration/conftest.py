"""Shared fixtures for check_cep integration tests.

Each test gets isolated test and result directories (via tmp_path).
The container image is taken from CEP_IMAGE env var or defaults to
localhost/check_cep:latest.
"""
import os
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CEP_IMAGE = os.environ.get("CEP_IMAGE", "localhost/check_cep:latest")
CEP_PLUGIN = Path(__file__).parent.parent.parent / "src" / "check_cep"

# Standard playwright.config.ts placed into every test directory.
# Per-test timeout is generous (30 s) — check_cep's --timeout controls the
# hard wall-clock limit from the outside.
PLAYWRIGHT_CONFIG = """\
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_env(tmp_path):
    """Provide isolated test-input and result directories.

    Returns a dict with:
      test_dir   — parent dir containing playwright.config.ts + tests/
      tests_dir  — tests/ subdir where *.test.ts files are placed
      result_dir — empty dir for check_cep results
    """
    test_dir = tmp_path / "test_input"
    tests_dir = test_dir / "tests"
    result_dir = tmp_path / "results"

    test_dir.mkdir()
    tests_dir.mkdir()
    result_dir.mkdir(mode=0o777)

    (test_dir / "playwright.config.ts").write_text(PLAYWRIGHT_CONFIG)

    return {
        "test_dir": test_dir,
        "tests_dir": tests_dir,
        "result_dir": result_dir,
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run_check_cep(test_dir, result_dir, extra_args=None, proc_timeout=180):
    """Run check_cep as a subprocess and return (combined_output, returncode).

    combined_output is stdout + stderr joined for easy assertion.
    proc_timeout is the Python subprocess timeout (should exceed check_cep's
    own --timeout to avoid a race).
    """
    cmd = [
        "python3", str(CEP_PLUGIN),
        "--host-name", "testhost",
        "--service-description", "pytest_test",
        "--image", CEP_IMAGE,
        "--probe-location", "local",
        "--test-source", "local",
        "--result-dest", "local",
        "--test-dir", str(test_dir),
        "--result-dir", str(result_dir),
    ]
    if extra_args:
        cmd.extend(extra_args)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=proc_timeout,
    )
    combined = proc.stdout + proc.stderr
    return combined, proc.returncode
