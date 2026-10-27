"""End-to-end exit-status classification (spec 023 US8, FR-052/FR-053).

Infrastructure failures surface as UNKNOWN; only Playwright failures are
CRITICAL; a passing test with visible stderr is WARNING.
"""
import json

from conftest import run_check_cep, local_test_dir


def test_missing_image_is_unknown(test_env):
    (test_env["test_dir"] / "a.test.ts").write_text("// never runs")
    output, code = run_check_cep(test_env["test_dir"], test_env["result_dir"],
                                 extra_args=["--image", "localhost/check_cep:does-not-exist"])
    assert code == 3, output
    assert output.startswith("UNKNOWN - test pytest_test could not be started on host"), output
    assert "podman exit code 125" in output


def test_container_exit_3_is_unknown(test_env):
    # No test files at all: run.py cannot run anything and exits 3.
    output, code = run_check_cep(test_env["test_dir"], test_env["result_dir"])
    assert code == 3, output
    assert output.startswith("UNKNOWN - test pytest_test"), output
    assert "CRITICAL" not in output


def test_failure_stays_critical(tmp_path, test_env, write_playwright_config):
    test_dir = local_test_dir(tmp_path, "tc_fail", write_playwright_config)
    output, code = run_check_cep(test_dir, test_env["result_dir"])
    assert code == 2, output
    assert output.startswith("CRITICAL -"), output


def test_visible_stderr_is_warning(tmp_path, test_env, write_playwright_config):
    test_dir = local_test_dir(tmp_path, "tc_warn", write_playwright_config)
    output, code = run_check_cep(test_dir, test_env["result_dir"])
    assert code == 1, output
    assert output.startswith("WARNING - test pytest_test succeeded"), output
    assert "slow backend" in output
    meta = json.loads((test_env["result_dir"] / "test-meta.json").read_text())
    assert meta["status"] == "WARNING"


def test_pass_has_no_stderr_section(tmp_path, test_env, write_playwright_config):
    # Guards against Playwright's empty {"buffer": ""} causing a false WARNING.
    test_dir = local_test_dir(tmp_path, "tc_pass", write_playwright_config)
    output, code = run_check_cep(test_dir, test_env["result_dir"])
    assert code == 0, output
    assert output.startswith("OK -"), output
    assert "__Stderr" not in output
