"""Loki log forwarding tests.

Requires the compose stack (SKIP_INTEGRATION must NOT be set).
"""
import os

import pytest

from conftest import run_check_cep, local_test_dir, query_loki


pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION"),
    reason="compose stack not available (SKIP_INTEGRATION set)",
)


def test_loki_log_received(tmp_path, write_playwright_config, compose_stack):
    """check_cep forwards a log entry to Loki; entry contains expected labels."""
    test_dir = local_test_dir(tmp_path, "tc_pass", write_playwright_config)
    result_dir = tmp_path / "results"

    output, code = run_check_cep(
        test_dir,
        result_dir,
        extra_args=[
            "--host-name", "loki-testhost",
            "--service-description", "loki-testsvc",
            "--logging", "loki",
            "--loki-endpoint", "http://host.containers.internal:3100",
        ],
        proc_timeout=120,
    )

    assert code == 0, f"Expected exit 0.\nOutput:\n{output}"

    entry = query_loki("loki-testhost", "loki-testsvc", timeout=15)
    assert entry["labels"]["host_name"] == "loki-testhost"
    assert entry["labels"]["service_description"] == "loki-testsvc"
    assert "status" in entry["labels"] or any(
        "status" in v[1] for v in entry["values"]
    ), f"'status' not found in Loki entry: {entry}"


def test_loki_unreachable_nonfatal(tmp_path, write_playwright_config, compose_stack):
    """A dead Loki endpoint must not affect the Nagios exit code."""
    test_dir = local_test_dir(tmp_path, "tc_pass", write_playwright_config)
    result_dir = tmp_path / "results"

    output, code = run_check_cep(
        test_dir,
        result_dir,
        extra_args=[
            "--host-name", "loki-nonfatal-host",
            "--service-description", "loki-nonfatal-svc",
            "--logging", "loki",
            "--loki-endpoint", "http://192.0.2.2:3100",
        ],
        proc_timeout=120,
    )

    assert code == 0, f"Expected exit 0 even with unreachable Loki.\nOutput:\n{output}"
    assert output.startswith("OK -"), f"Expected 'OK -' prefix.\nOutput:\n{output}"
