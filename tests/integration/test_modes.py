"""Parametrized integration tests: fixtures × {local, s3, lightpanda} modes.

Local mode tests run without any external services (SKIP_INTEGRATION is not
required). S3 mode tests require the compose stack and are skipped when
SKIP_INTEGRATION=1. Lightpanda mode re-runs the DOM-only fixtures with
--browser lightpanda (vision fixtures are skipped — no rendering engine).
"""
import json
import os

import pytest

from conftest import run_check_cep, local_test_dir, run_check_cep_s3


# ---------------------------------------------------------------------------
# Fixture parameter table
# (fixture_name, expected_exit, expected_prefix, extra_args, keyword)
# expected_exit=None means 2-or-3 (tc_syntax)
# keyword is checked in output when not None
# ---------------------------------------------------------------------------

FIXTURES = [
    ("tc_pass",          0,    "OK -",       [],                    None),
    ("tc_register_pass", 0,    "OK -",       [],                    None),
    ("tc_fail",          2,    "CRITICAL -", [],                    None),
    ("tc_timeout",       2,    "CRITICAL -", ["--timeout", "15"],   "timed out"),
    ("tc_syntax",        None, None,         [],                    None),
    ("tc_vision_basic",     0,    "OK -",       [],                    None),
    ("tc_vision_ambiguous", 0,    "OK -",       [],                    None),
    ("tc_vision_color",     0,    "OK -",       [],                    None),
    ("tc_vision_debug",     0,    "OK -",       [],                    None),
    ("tc_vision_workflow",  0,    "OK -",       [],                    None),
    ("tc_vision_example_form", 0,  "OK -",       [],                    None),
    ("tc_vision_example_console", 0, "OK -",    [],                    None),
    ("tc_vision_example_login", 0,   "OK -",    [],                    None),
]


# ---------------------------------------------------------------------------
# Local mode
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fixture_name,expected_exit,expected_prefix,extra_args,keyword",
    FIXTURES,
    ids=[f[0] for f in FIXTURES],
)
def test_local(
    tmp_path,
    omd_env,
    write_playwright_config,
    fixture_name,
    expected_exit,
    expected_prefix,
    extra_args,
    keyword,
):
    result_dir = tmp_path / "results"
    test_dir = local_test_dir(tmp_path, fixture_name, write_playwright_config)

    output, code = run_check_cep(
        test_dir,
        result_dir,
        extra_args=[
            "--host-name", "testhost",
            "--service-description", fixture_name,
        ] + extra_args,
        env=omd_env,
        proc_timeout=120,
    )

    # Exit code
    if expected_exit is None:
        assert code in (2, 3), (
            f"[{fixture_name}] Expected exit 2 or 3, got {code}.\nOutput:\n{output}"
        )
    else:
        assert code == expected_exit, (
            f"[{fixture_name}] Expected exit {expected_exit}, got {code}.\nOutput:\n{output}"
        )

    # Output prefix
    if expected_prefix is None:
        assert output.startswith(("CRITICAL -", "UNKNOWN -")), (
            f"[{fixture_name}] Expected CRITICAL or UNKNOWN prefix.\nOutput:\n{output}"
        )
    else:
        assert output.startswith(expected_prefix), (
            f"[{fixture_name}] Expected '{expected_prefix}' prefix.\nOutput:\n{output}"
        )

    # Keyword check (e.g. "timed out" for tc_timeout)
    if keyword:
        assert keyword in output, (
            f"[{fixture_name}] Expected '{keyword}' in output.\nOutput:\n{output}"
        )

    # Result artefacts — only for tests that complete (not tc_timeout which is killed)
    if fixture_name != "tc_timeout":
        steps_json = result_dir / "steps.json"
        assert steps_json.exists(), f"[{fixture_name}] steps.json not written"
        data = json.loads(steps_json.read_text())
        assert isinstance(data, dict), f"[{fixture_name}] steps.json is not a JSON object"

        meta_json = result_dir / "test-meta.json"
        assert meta_json.exists(), f"[{fixture_name}] test-meta.json not written"
        meta = json.loads(meta_json.read_text())
        assert meta["hostname"] == "testhost"
        assert meta["servicedescription"] == fixture_name
        assert "status" in meta


# ---------------------------------------------------------------------------
# Local mode — Lightpanda browser
# ---------------------------------------------------------------------------
# Lightpanda's CDP support is WIP: single navigation + DOM reads work,
# but fill(), click()-navigation, and second goto() crash the server.
# We use a dedicated fixture (tc_lp_pass) that stays within these limits.

FIXTURES_LIGHTPANDA = [
    ("tc_lp_pass", 0,    "OK -",       [],  None),
    ("tc_syntax",  None, None,         [],  None),
]


@pytest.mark.parametrize(
    "fixture_name,expected_exit,expected_prefix,extra_args,keyword",
    FIXTURES_LIGHTPANDA,
    ids=[f[0] for f in FIXTURES_LIGHTPANDA],
)
def test_local_lightpanda(
    tmp_path,
    omd_env,
    write_playwright_config,
    fixture_name,
    expected_exit,
    expected_prefix,
    extra_args,
    keyword,
):
    result_dir = tmp_path / "results"
    test_dir = local_test_dir(tmp_path, fixture_name, write_playwright_config)

    output, code = run_check_cep(
        test_dir,
        result_dir,
        extra_args=[
            "--host-name", "testhost",
            "--service-description", fixture_name,
            "--browser", "lightpanda",
        ] + extra_args,
        env=omd_env,
        proc_timeout=120,
    )

    # Exit code
    if expected_exit is None:
        assert code in (2, 3), (
            f"[{fixture_name}/lightpanda] Expected exit 2 or 3, got {code}.\nOutput:\n{output}"
        )
    else:
        assert code == expected_exit, (
            f"[{fixture_name}/lightpanda] Expected exit {expected_exit}, got {code}.\nOutput:\n{output}"
        )

    # Output prefix
    if expected_prefix is None:
        assert output.startswith(("CRITICAL -", "UNKNOWN -")), (
            f"[{fixture_name}/lightpanda] Expected CRITICAL or UNKNOWN prefix.\nOutput:\n{output}"
        )
    else:
        assert output.startswith(expected_prefix), (
            f"[{fixture_name}/lightpanda] Expected '{expected_prefix}' prefix.\nOutput:\n{output}"
        )

    # Keyword check
    if keyword:
        assert keyword in output, (
            f"[{fixture_name}/lightpanda] Expected '{keyword}' in output.\nOutput:\n{output}"
        )

    # Result artefacts
    steps_json = result_dir / "steps.json"
    assert steps_json.exists(), f"[{fixture_name}/lightpanda] steps.json not written"
    data = json.loads(steps_json.read_text())
    assert isinstance(data, dict), f"[{fixture_name}/lightpanda] steps.json is not a JSON object"

    meta_json = result_dir / "test-meta.json"
    assert meta_json.exists(), f"[{fixture_name}/lightpanda] test-meta.json not written"
    meta = json.loads(meta_json.read_text())
    assert meta["hostname"] == "testhost"
    assert meta["servicedescription"] == fixture_name
    assert "status" in meta


# ---------------------------------------------------------------------------
# S3 mode — placeholder until Phase 4 (T014)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fixture_name,expected_exit,expected_prefix,extra_args,keyword",
    FIXTURES,
    ids=[f[0] for f in FIXTURES],
)
@pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION"),
    reason="compose stack not available (SKIP_INTEGRATION set)",
)
def test_s3(
    tmp_path,
    omd_env,
    write_playwright_config,
    compose_stack,
    cep_image,
    container_cleanup,
    fixture_name,
    expected_exit,
    expected_prefix,
    extra_args,
    keyword,
):
    output, code, result_dir, report_prefix = run_check_cep_s3(
        fixture_name,
        omd_env,
        tmp_path,
        cep_image,
        compose_stack,
        write_playwright_config,
        extra_args=extra_args,
        cleanup_paths=container_cleanup,
    )

    # Exit code
    if expected_exit is None:
        assert code in (2, 3), (
            f"[{fixture_name}/s3] Expected exit 2 or 3, got {code}.\nOutput:\n{output}"
        )
    else:
        assert code == expected_exit, (
            f"[{fixture_name}/s3] Expected exit {expected_exit}, got {code}.\nOutput:\n{output}"
        )

    # Output prefix
    if expected_prefix is None:
        assert output.startswith(("CRITICAL -", "UNKNOWN -")), (
            f"[{fixture_name}/s3] Expected CRITICAL or UNKNOWN prefix.\nOutput:\n{output}"
        )
    else:
        assert output.startswith(expected_prefix), (
            f"[{fixture_name}/s3] Expected '{expected_prefix}' prefix.\nOutput:\n{output}"
        )

    if keyword:
        assert keyword in output, (
            f"[{fixture_name}/s3] Expected '{keyword}' in output.\nOutput:\n{output}"
        )

    # Local result artefacts (always present after FR-000 fix)
    if fixture_name != "tc_timeout":
        steps_json = result_dir / "steps.json"
        assert steps_json.exists(), f"[{fixture_name}/s3] steps.json not written locally"
        data = json.loads(steps_json.read_text())
        assert isinstance(data, dict)

        meta_json = result_dir / "test-meta.json"
        assert meta_json.exists(), f"[{fixture_name}/s3] test-meta.json not written locally"
        meta = json.loads(meta_json.read_text())
        assert "hostname" in meta
        assert "servicedescription" in meta
        assert "status" in meta

    # S3 bucket artefacts — tc_timeout is killed before Playwright produces
    # an HTML report, so only test-meta.json may be present.
    if fixture_name != "tc_timeout":
        s3 = compose_stack
        objects = s3.list_objects_v2(Bucket="cep-reports", Prefix=report_prefix + "/")
        keys = [obj["Key"] for obj in objects.get("Contents", [])]
        assert any("index.html" in k for k in keys), (
            f"[{fixture_name}/s3] playwright-report/index.html not found in cep-reports.\nKeys: {keys}"
        )
        assert any("test-meta.json" in k for k in keys), (
            f"[{fixture_name}/s3] test-meta.json not found in cep-reports.\nKeys: {keys}"
        )
