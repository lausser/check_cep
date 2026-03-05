"""Integration tests for check_cep.

Each test runs the full stack: check_cep (host) -> Podman container ->
Playwright -> result parsing -> Nagios output.

Requirements:
  - Podman installed and working (rootless)
  - Container image available (default: localhost/check_cep:latest)
  - Internet access (most tests navigate to https://www.consol.de)

Run with:
  pytest tests/integration/ -v

Override the image:
  CEP_IMAGE=localhost/check_cep:v1.58.2 pytest tests/integration/ -v
"""
import json

import pytest

from conftest import run_check_cep


# ---------------------------------------------------------------------------
# 1. Passing test
# ---------------------------------------------------------------------------

def test_passing(test_env):
    """A Playwright test that finds the expected text returns OK (exit 0)."""
    (test_env["tests_dir"] / "passing.test.ts").write_text("""\
import { test, expect } from '@playwright/test';

test('consol.de homepage has expected text', async ({ page }) => {
  await page.goto('https://www.consol.de');
  await expect(page.locator('body')).toContainText('Consulting & Solutions');
});
""")

    output, code = run_check_cep(test_env["test_dir"], test_env["result_dir"])

    assert code == 0, f"Expected exit 0 (OK), got {code}.\nOutput:\n{output}"
    assert output.startswith("OK -"), f"Expected 'OK -' prefix.\nOutput:\n{output}"
    assert "succeeded" in output


# ---------------------------------------------------------------------------
# 2. Failing test (text not found on page)
# ---------------------------------------------------------------------------

def test_failing(test_env):
    """A Playwright assertion that never matches returns CRITICAL (exit 2)."""
    (test_env["tests_dir"] / "failing.test.ts").write_text("""\
import { test, expect } from '@playwright/test';

test('homepage contains non-existent text', async ({ page }) => {
  await page.goto('https://www.consol.de');
  await expect(page.locator('body')).toContainText('blublablubla');
});
""")

    output, code = run_check_cep(test_env["test_dir"], test_env["result_dir"])

    assert code == 2, f"Expected exit 2 (CRITICAL), got {code}.\nOutput:\n{output}"
    assert output.startswith("CRITICAL -"), f"Expected 'CRITICAL -' prefix.\nOutput:\n{output}"
    assert "failed" in output


# ---------------------------------------------------------------------------
# 3. Test that times out
# ---------------------------------------------------------------------------

def test_timeout(test_env):
    """A test that hangs is killed by the container timeout -> CRITICAL 'timed out'."""
    (test_env["tests_dir"] / "timeout.test.ts").write_text("""\
import { test } from '@playwright/test';

test('test that never finishes', async ({ page }) => {
  // waitForTimeout is capped by playwright per-test timeout,
  // so we use a navigation to a non-routable address to hang indefinitely.
  await page.goto('http://192.0.2.1/', { timeout: 999000 });
});
""")

    # --timeout 15 means Playwright gets 15 s before the container is killed.
    output, code = run_check_cep(
        test_env["test_dir"],
        test_env["result_dir"],
        extra_args=["--timeout", "15"],
        proc_timeout=60,
    )

    assert code == 2, f"Expected exit 2 (CRITICAL), got {code}.\nOutput:\n{output}"
    assert "timed out" in output, f"Expected 'timed out' in output.\nOutput:\n{output}"


# ---------------------------------------------------------------------------
# 4. Syntax error in the test file
# ---------------------------------------------------------------------------

def test_syntax_error(test_env):
    """A .test.ts with invalid syntax causes Playwright to fail -> CRITICAL."""
    (test_env["tests_dir"] / "broken.test.ts").write_text("""\
import { test, expect } from '@playwright/test';

// Deliberately unclosed arrow function — TypeScript parse error
test('broken syntax', async ({ page }) => {
  const obj = {
    key: 'value'
  // missing closing brace
;
""")

    output, code = run_check_cep(test_env["test_dir"], test_env["result_dir"])

    # Playwright exits non-zero; check_cep maps this to CRITICAL or UNKNOWN
    assert code in (2, 3), f"Expected exit 2 or 3, got {code}.\nOutput:\n{output}"
    assert output.startswith(("CRITICAL -", "UNKNOWN -")), (
        f"Expected CRITICAL or UNKNOWN prefix.\nOutput:\n{output}"
    )


# ---------------------------------------------------------------------------
# 5. Test injects custom performance data
# ---------------------------------------------------------------------------

def test_custom_perfdata(test_env):
    """console.log('NagiosPerfData: ...') in the test appears in check_cep output."""
    (test_env["tests_dir"] / "perfdata.test.ts").write_text("""\
import { test, expect } from '@playwright/test';

test('test with custom perfdata', async ({ page }) => {
  await page.goto('https://www.consol.de');
  await expect(page.locator('body')).toContainText('Consulting & Solutions');
  // Inject custom Nagios perfdata — check_cep picks this up from steps.json stdout
  console.log("NagiosPerfData: 'MyResponseTime'=123ms");
  console.log("NagiosPerfData: 'MyPageWeight'=456");
});
""")

    output, code = run_check_cep(test_env["test_dir"], test_env["result_dir"])

    assert code == 0, f"Expected exit 0 (OK), got {code}.\nOutput:\n{output}"
    assert "'MyResponseTime'=123ms" in output, (
        f"Custom perfdata 'MyResponseTime'=123ms not found in output.\nOutput:\n{output}"
    )
    assert "'MyPageWeight'=456" in output, (
        f"Custom perfdata 'MyPageWeight'=456 not found in output.\nOutput:\n{output}"
    )


# ---------------------------------------------------------------------------
# 6. HTML report and result files are written
# ---------------------------------------------------------------------------

def test_report_written(test_env):
    """After a run, the result directory contains all expected artefacts."""
    (test_env["tests_dir"] / "report_check.test.ts").write_text("""\
import { test, expect } from '@playwright/test';

test('consol.de homepage loads', async ({ page }) => {
  await page.goto('https://www.consol.de');
  await expect(page.locator('body')).toContainText('Consulting & Solutions');
});
""")

    output, code = run_check_cep(test_env["test_dir"], test_env["result_dir"])

    result_dir = test_env["result_dir"]

    # Exit code
    assert code == 0, f"Expected exit 0 (OK), got {code}.\nOutput:\n{output}"

    # steps.json must exist and be valid JSON
    steps_json = result_dir / "steps.json"
    assert steps_json.exists(), "steps.json was not written"
    data = json.loads(steps_json.read_text())
    assert "suites" in data or "stats" in data, "steps.json has unexpected structure"

    # test-meta.json must exist and contain expected fields
    meta_json = result_dir / "test-meta.json"
    assert meta_json.exists(), "test-meta.json was not written"
    meta = json.loads(meta_json.read_text())
    assert meta["hostname"] == "testhost"
    assert meta["servicedescription"] == "pytest_test"
    assert meta["status"] == "OK"
    assert "duration" in meta
    assert "timestamp" in meta

    # HTML report must exist and be non-empty
    report = result_dir / "playwright-report" / "index.html"
    assert report.exists(), "playwright-report/index.html was not written"
    assert report.stat().st_size > 1000, "playwright-report/index.html looks empty"
