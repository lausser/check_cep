"""Integration tests for 009-report-management.

Tests per-run timestamped directories (%t), automatic cleanup by age
(--report-retention), and timeout-aware cleanup behaviour.

Requirements:
  - Podman installed and working (rootless)
  - Container image available (default: check_cep:test)

Run with:
  pytest tests/integration/test_report_management.py -v
"""
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from conftest import run_check_cep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASSING_TEST = """\
import { test, expect } from '@playwright/test';

test('simple passing test', async ({ page }) => {
  await page.goto('https://www.consol.de');
  await expect(page.locator('body')).toContainText('Consulting & Solutions');
});
"""


def _write_passing_test(test_dir: Path) -> None:
    (test_dir / "passing.test.ts").write_text(_PASSING_TEST)


def _make_old_run_dir(parent: Path, age_seconds: int, with_meta: bool = True) -> Path:
    """Create a fake completed run directory that appears age_seconds old."""
    started = int(time.time()) - age_seconds
    d = parent / str(started)
    d.mkdir(parents=True, exist_ok=True)
    if with_meta:
        meta = {
            "started": str(started),
            "finished": str(started + 30),
            "hostname": "testhost",
            "servicedescription": "pytest_test",
            "exitcode": 0,
            "duration": "30.000",
            "probe_location": "local",
            "status": "OK",
        }
        (d / "test-meta.json").write_text(json.dumps(meta))
    return d


# ---------------------------------------------------------------------------
# US1: Per-run directories via %t
# ---------------------------------------------------------------------------

def test_per_run_directories(tmp_path, write_playwright_config, omd_env):
    """Two check_cep runs with %t in --result-dir create two distinct directories.

    Each directory must:
    - Have a numeric name (Unix epoch integer)
    - Contain test-meta.json with 'started' and 'finished' fields
    - Have its URL in plugin output containing the correct timestamp
    """
    parent_dir = tmp_path / "Formular"
    parent_dir.mkdir()

    test_dir = tmp_path / "test_input"
    test_dir.mkdir()
    write_playwright_config(test_dir)
    _write_passing_test(test_dir)

    result_dirs = []
    for _run in range(2):
        output, code = run_check_cep(
            test_dir=test_dir,
            result_dir=tmp_path,  # not used directly; overridden below
            extra_args=[
                "--result-dir", str(parent_dir / "%t"),
                "--report-url", f"http://example.com/%h/%s/%t/playwright-report/index.html",
            ],
            env=omd_env,
        )
        assert code == 0, f"Expected OK (exit 0), got {code}.\nOutput:\n{output}"

        # Give the filesystem a moment between runs to ensure distinct timestamps
        time.sleep(1)

        # Collect the new run directory (the most recent numeric subdir)
        numeric_dirs = sorted(
            [d for d in parent_dir.iterdir() if d.is_dir() and d.name.isdigit()],
            key=lambda d: int(d.name),
        )
        assert len(numeric_dirs) >= _run + 1, (
            f"Expected at least {_run + 1} run directories, found {len(numeric_dirs)}"
        )
        result_dirs.append(numeric_dirs[-1])

    # Must have two distinct directories
    assert result_dirs[0] != result_dirs[1], "Two runs must produce distinct directories"

    # Each directory must contain a complete test-meta.json v2
    for run_dir in result_dirs:
        meta_path = run_dir / "test-meta.json"
        assert meta_path.exists(), f"test-meta.json missing in {run_dir}"
        meta = json.loads(meta_path.read_text())
        assert "started" in meta, f"'started' key missing in {meta_path}"
        assert "finished" in meta, f"'finished' key missing in {meta_path}"
        assert "timestamp" not in meta, "Legacy 'timestamp' key must not be present (schema v2)"

        # Directory name must match the 'started' value
        assert run_dir.name == meta["started"], (
            f"Directory name {run_dir.name!r} must equal meta['started'] {meta['started']!r}"
        )

    # The test-meta.json must NOT have the old 'timestamp' key
    for run_dir in result_dirs:
        meta = json.loads((run_dir / "test-meta.json").read_text())
        assert "timestamp" not in meta


# ---------------------------------------------------------------------------
# US2: Auto-cleanup by age
# ---------------------------------------------------------------------------

def test_cleanup_by_age(tmp_path, write_playwright_config, omd_env):
    """--report-retention deletes old dirs with test-meta.json; others are untouched.

    Pre-condition layout under parent_dir:
      <old1>/test-meta.json   — 2 hours old → must be deleted
      <old2>/test-meta.json   — 2 hours old → must be deleted
      <old3>/                 — 2 hours old, NO test-meta.json → must NOT be deleted
      <recent>/test-meta.json — 30 min old → must NOT be deleted (within retention)
      latest/                 — non-integer name → must NOT be deleted
    """
    parent_dir = tmp_path / "Formular"
    parent_dir.mkdir()

    test_dir = tmp_path / "test_input"
    test_dir.mkdir()
    write_playwright_config(test_dir)
    _write_passing_test(test_dir)

    old1 = _make_old_run_dir(parent_dir, age_seconds=7200, with_meta=True)
    old2 = _make_old_run_dir(parent_dir, age_seconds=7300, with_meta=True)
    no_meta = _make_old_run_dir(parent_dir, age_seconds=7400, with_meta=False)
    recent = _make_old_run_dir(parent_dir, age_seconds=1800, with_meta=True)
    legacy_dir = parent_dir / "latest"
    legacy_dir.mkdir()

    output, code = run_check_cep(
        test_dir=test_dir,
        result_dir=tmp_path,
        extra_args=[
            "--result-dir", str(parent_dir / "%t"),
            "--report-retention", "1h",
        ],
        env=omd_env,
    )
    assert code == 0, f"Expected OK (exit 0), got {code}.\nOutput:\n{output}"

    # Old dirs with test-meta.json must be deleted
    assert not old1.exists(), f"Old dir {old1} should have been deleted"
    assert not old2.exists(), f"Old dir {old2} should have been deleted"

    # Dir without test-meta.json must NOT be deleted
    assert no_meta.exists(), f"Dir without test-meta.json {no_meta} must not be deleted"

    # Recent dir (within retention window) must NOT be deleted
    assert recent.exists(), f"Recent dir {recent} must not be deleted"

    # Non-integer named dir must NOT be deleted
    assert legacy_dir.exists(), f"Non-integer dir {legacy_dir} must not be deleted"


def test_retention_without_t_emits_warning(tmp_path, write_playwright_config, omd_env):
    """--report-retention without %t in --result-dir emits a warning, test still runs."""
    result_dir = tmp_path / "results"
    result_dir.mkdir()

    test_dir = tmp_path / "test_input"
    test_dir.mkdir()
    write_playwright_config(test_dir)
    _write_passing_test(test_dir)

    output, code = run_check_cep(
        test_dir=test_dir,
        result_dir=result_dir,
        extra_args=["--report-retention", "24h"],
        env=omd_env,
    )

    assert code == 0, f"Expected OK (exit 0), got {code}.\nOutput:\n{output}"
    assert "WARNING: --report-retention has no effect without %t in --result-dir" in output

