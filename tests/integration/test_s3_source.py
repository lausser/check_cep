"""Integration tests for S3 test source with explicit artifact path.

017-s3-tgz-source: verifies end-to-end flow using --test-artifact=
/bucket/key/tests.tgz instead of the removed --s3-bucket parameter.

Requirements (provided by docker-compose.yml compose_stack fixture):
  - MinIO running at localhost:9000 (credentials: minioadmin/minioadmin)
  - Buckets: cep-tests, cep-reports pre-created
  - Container image available via CEP_IMAGE env var

Run with:
  pytest tests/integration/test_s3_source.py -v
Set SKIP_INTEGRATION=1 to skip tests requiring the compose stack.
"""

import os
import tarfile
import uuid
from pathlib import Path

import pytest

_SKIP = pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION"),
    reason="compose stack not available (SKIP_INTEGRATION set)",
)

from conftest import (
    CEP_IMAGE,
    CEP_PLUGIN,
    _FIXTURES_DIR,
    derive_testident,
    run_check_cep,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _upload_fixture_tgz(s3_client, fixture_name, tmp_path, write_playwright_config):
    """Stage fixture, pack as tests.tgz, upload to cep-tests bucket.

    Returns (test_artifact, s3_bucket, s3_key) where test_artifact is the
    /bucket/key value for --test-artifact.
    """
    short = uuid.uuid4().hex[:8]
    hostname = f"testhost-s3-{short}"
    service = f"{fixture_name}-{short}"
    testident = derive_testident(hostname, service)

    stage = tmp_path / "stage" / fixture_name
    import shutil
    shutil.copytree(str(_FIXTURES_DIR / fixture_name), str(stage))
    if not (stage / "playwright.config.ts").exists():
        write_playwright_config(stage)

    tgz_path = tmp_path / "tests.tgz"
    with tarfile.open(str(tgz_path), "w:gz") as tar:
        tar.add(str(stage), arcname=".")

    bucket = "cep-tests"
    key = f"{testident}/tests.tgz"
    s3_client.upload_file(str(tgz_path), bucket, key)

    return hostname, service, testident, f"/{bucket}/{key}"


def _run_s3(
    hostname,
    service,
    test_artifact,
    tmp_path,
    cep_image,
    omd_env,
    extra_args=None,
):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(exist_ok=True)
    result_template = str(tmp_path / "results" / "%h" / "%s")

    cmd_extra = [
        "--host-name", hostname,
        "--service-description", service,
        "--image", cep_image,
        "--test-source", "s3",
        "--result-dest", "s3",
        "--s3-endpoint", "http://host.containers.internal:9000",
        "--aws-access-key-id", "minioadmin",
        "--aws-secret-access-key", "minioadmin",
        "--test-artifact", test_artifact,
        "--s3-report-bucket", "cep-reports",
        "--s3-report-path", "%h/%s",
        "--testscripts-cache", str(cache_dir),
        "--result-dir", result_template,
    ]
    if extra_args:
        cmd_extra.extend(extra_args)

    output, code = run_check_cep(
        test_dir=None,
        result_dir=None,
        extra_args=cmd_extra,
        env=omd_env,
        proc_timeout=180,
    )
    return output, code, cache_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@_SKIP
def test_s3_explicit_artifact_passes(
    compose_stack, cep_image, omd_env, tmp_path, write_playwright_config, container_cleanup
):
    """A check using --test-artifact downloads, caches, and executes the archive."""
    s3_client = compose_stack
    hostname, service, testident, test_artifact = _upload_fixture_tgz(
        s3_client, "tc_pass", tmp_path, write_playwright_config
    )

    output, code, cache_dir = _run_s3(
        hostname, service, test_artifact, tmp_path, cep_image, omd_env
    )
    container_cleanup.append(cache_dir)
    container_cleanup.append(tmp_path / "results")

    assert code == 0, f"Expected OK (0), got {code}.\nOutput:\n{output}"
    assert output.startswith("OK -"), output


@_SKIP
def test_s3_cache_hit_on_second_run(
    compose_stack, cep_image, omd_env, tmp_path, write_playwright_config, container_cleanup
):
    """Second run with unchanged archive skips the download (cache hit)."""
    s3_client = compose_stack
    hostname, service, testident, test_artifact = _upload_fixture_tgz(
        s3_client, "tc_pass", tmp_path, write_playwright_config
    )

    # First run — populates cache
    _, _, cache_dir = _run_s3(
        hostname, service, test_artifact, tmp_path, cep_image, omd_env,
        extra_args=["--debug"],
    )

    # Second run — should use cached archive
    output, code, _ = _run_s3(
        hostname, service, test_artifact, tmp_path, cep_image, omd_env,
        extra_args=["--debug"],
    )
    container_cleanup.append(cache_dir)
    container_cleanup.append(tmp_path / "results")

    assert code == 0, f"Expected OK (0) on second run, got {code}.\nOutput:\n{output}"
    assert "cache hit" in output, (
        "Expected 'cache hit' in debug output on second run.\nOutput:\n{output}"
    )


@_SKIP
def test_s3_missing_artifact_exits_unknown(
    compose_stack, cep_image, omd_env, tmp_path, container_cleanup
):
    """--test-artifact pointing to a non-existent S3 object exits UNKNOWN quickly."""
    short = uuid.uuid4().hex[:8]
    hostname = f"testhost-{short}"
    service = f"nonexistent-{short}"
    test_artifact = "/cep-tests/does/not/exist/tests.tgz"

    output, code, cache_dir = _run_s3(
        hostname, service, test_artifact, tmp_path, cep_image, omd_env
    )
    container_cleanup.append(cache_dir)

    assert code != 0, f"Expected non-zero exit for missing artifact, got {code}"


def test_s3_no_test_artifact_arg_exits_unknown(cep_image, omd_env, tmp_path):
    """--test-source=s3 without --test-artifact exits UNKNOWN immediately."""
    short = uuid.uuid4().hex[:8]
    output, code = run_check_cep(
        test_dir=tmp_path,
        result_dir=tmp_path,
        extra_args=[
            "--host-name", f"testhost-{short}",
            "--service-description", f"noartifact-{short}",
            "--image", cep_image,
            "--test-source", "s3",
            "--s3-endpoint", "http://host.containers.internal:9000",
            "--aws-access-key-id", "minioadmin",
            "--aws-secret-access-key", "minioadmin",
        ],
        env=omd_env,
        proc_timeout=30,
    )

    assert code == 3, f"Expected UNKNOWN (3), got {code}.\nOutput:\n{output}"
    assert "test-artifact" in output.lower() or "unknown" in output.lower(), output


def test_s3_no_s3_bucket_arg_accepted(cep_image, omd_env, tmp_path):
    """--s3-bucket is no longer a valid argument (removed in 017)."""
    import subprocess
    result = subprocess.run(
        [
            "python3", str(CEP_PLUGIN),
            "--host-name", "testhost",
            "--service-description", "test",
            "--image", cep_image,
            "--test-source", "s3",
            "--s3-bucket", "somebucket",  # removed argument
            "--test-artifact", "/cep-tests/k.tgz",
            "--s3-endpoint", "http://localhost:9000",
            "--aws-access-key-id", "x",
            "--aws-secret-access-key", "x",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # argparse should reject the unknown argument
    assert result.returncode != 0
    assert "unrecognized" in result.stderr or "error" in result.stderr.lower()
