"""Shared fixtures for check_cep integration tests.

Each test gets isolated test and result directories (via tmp_path).
The container image is taken from the session-scoped cep_image fixture
(defined in tests/conftest.py) or falls back to CEP_IMAGE env var.
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tarfile
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CEP_IMAGE = os.environ.get("CEP_IMAGE", "check_cep:test")
CEP_PLUGIN = Path(__file__).parent.parent.parent / "src" / "check_cep"
_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Spectate mode: run browsers headed so a human can watch the tests.
# Set CEP_SPECTATE=1 to enable.  Injects --headed, slower highlight
# timings, and Playwright slowMo so the spectator's eyes can follow.
_SPECTATE = bool(os.environ.get("CEP_SPECTATE", ""))
_SPECTATE_HIGHLIGHT_MS = os.environ.get("CEP_VISION_HIGHLIGHT_MS", "2000")
_SPECTATE_SLOW_MO = os.environ.get("CEP_SLOW_MO", "400")

# ---------------------------------------------------------------------------
# Import derive_testident directly from src/check_cep (single source of truth)
# ---------------------------------------------------------------------------

_loader = importlib.machinery.SourceFileLoader("check_cep_mod", str(CEP_PLUGIN))
_spec = importlib.util.spec_from_file_location("check_cep_mod", str(CEP_PLUGIN), loader=_loader)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
derive_testident = _mod.derive_testident

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def omd_env(tmp_path):
    """Simulate an OMD site environment for check_cep subprocess calls."""
    return {"OMD_ROOT": str(tmp_path), "OMD_SITE": "testsite"}


@pytest.fixture
def test_env(tmp_path, write_playwright_config):
    """Provide isolated test-input and result directories.

    Returns a dict with:
      test_dir   — dir containing playwright.config.ts + *.test.ts (flat layout)
      result_dir — empty dir for check_cep results

    Uses the shared write_playwright_config fixture from tests/conftest.py
    (single source of truth for playwright.config.ts content).
    """
    test_dir = tmp_path / "test_input"
    result_dir = tmp_path / "results"

    test_dir.mkdir()
    result_dir.mkdir(mode=0o777)

    write_playwright_config(test_dir)

    return {
        "test_dir": test_dir,
        "result_dir": result_dir,
    }


# ---------------------------------------------------------------------------
# Container-owned file cleanup
# ---------------------------------------------------------------------------

def _container_rm(paths):
    """Remove files owned by the container's sub-UID via podman.

    Rootless Podman maps pwuser to a host sub-UID that the host user cannot
    delete.  We re-use the test image as root to rm -rf the offending paths.
    """
    for p in paths:
        p = str(p)
        if not os.path.exists(p):
            continue
        subprocess.run(
            ["podman", "run", "--rm", "--user", "root",
             "--volume", f"{p}:/cleanup:rw,z",
             CEP_IMAGE, "bash", "-c", "rm -rf /cleanup/*"],
            capture_output=True,
            timeout=30,
        )


@pytest.fixture
def container_cleanup():
    """Fixture that cleans up container-owned files after the test.

    Tests register paths via the returned list; teardown deletes them.
    """
    paths = []
    yield paths
    _container_rm(paths)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run_check_cep(test_dir, result_dir, extra_args=None, env=None, proc_timeout=180):
    """Run check_cep as a subprocess and return (combined_output, returncode).

    combined_output is stdout + stderr joined for easy assertion.
    proc_timeout is the Python subprocess timeout (should exceed check_cep's
    own --timeout to avoid a race).
    env, if given, is merged on top of the current os.environ.

    When CEP_SPECTATE is set, --headed and slow-motion env vars are injected
    automatically so the spectator can watch the browser on their desktop.
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

    merged_env = {**os.environ}
    if env:
        merged_env.update(env)

    if _SPECTATE:
        # Inject --headed unless already present
        if "--headed" not in cmd:
            cmd.append("--headed")
        # Bump the container-side Playwright timeout (slowMo + highlights add up)
        if "--timeout" not in cmd:
            cmd.extend(["--timeout", "300"])
        # Slow-motion defaults (overridable via explicit env vars)
        merged_env.setdefault("CEP_VISION_HIGHLIGHT_MS", _SPECTATE_HIGHLIGHT_MS)
        merged_env.setdefault("CEP_SLOW_MO", _SPECTATE_SLOW_MO)
        # More generous proc_timeout — headed + slowMo adds significant time
        proc_timeout = max(proc_timeout, 600)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=proc_timeout,
        env=merged_env,
    )
    combined = proc.stdout + proc.stderr
    return combined, proc.returncode


def local_test_dir(tmp_path, fixture_name, write_playwright_config):
    """Copy the entire fixture directory + write playwright.config.ts into a temp dir.

    Returns the Path of the directory containing the files — this is the
    value to pass as test_dir to run_check_cep().

    If the fixture already ships a committed playwright.config.ts, it is
    preserved (self-contained example fixtures).  Otherwise the shared
    config is written so flat fixtures from earlier specs keep working.
    """
    dest = tmp_path / "tests" / fixture_name
    src_dir = _FIXTURES_DIR / fixture_name
    shutil.copytree(src_dir, dest)
    if not (dest / "playwright.config.ts").exists():
        write_playwright_config(dest)
    return dest


def run_check_cep_s3(fixture_name, omd_env, tmp_path, cep_image, s3_client,
                     write_playwright_config, extra_args=None, proc_timeout=180,
                     cleanup_paths=None):
    """Run check_cep in S3 mode against the MinIO compose service.

    Uploads scripts.tgz to cep-tests/{testident}/scripts.tgz,
    then invokes check_cep with --test-source s3 --result-dest s3.

    The full fixture directory tree is staged (copytree) so that example
    fixtures with assets/, pages/, functions/, variables/ subdirectories
    are packaged correctly.  If the fixture ships its own
    playwright.config.ts it is preserved; otherwise the shared config is
    written into the staging root.

    If cleanup_paths (list) is passed, dirs with container-owned files are
    appended so the container_cleanup fixture can remove them at teardown.

    Returns (output, exit_code, resolved_result_dir, report_prefix).
    """
    short = uuid.uuid4().hex[:8]
    hostname = f"testhost-{short}"
    service = f"{fixture_name}-{short}"
    testident = derive_testident(hostname, service)

    # Stage: copy the entire fixture tree into a temp staging dir
    stage = tmp_path / "stage" / fixture_name
    src_dir = _FIXTURES_DIR / fixture_name
    shutil.copytree(src_dir, stage)
    if not (stage / "playwright.config.ts").exists():
        write_playwright_config(stage)

    # Pack as flat scripts.tgz (no leading directory)
    tgz_path = tmp_path / "scripts.tgz"
    with tarfile.open(str(tgz_path), "w:gz") as tar:
        tar.add(str(stage), arcname=".")

    # Upload to MinIO
    s3_key = f"{testident}/scripts.tgz"
    s3_client.upload_file(str(tgz_path), "cep-tests", s3_key)

    # Prepare host-side dirs
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
        "--s3-bucket", "cep-tests",
        "--s3-report-bucket", "cep-reports",
        "--s3-report-path", "%h/%s",
        "--testscripts-cache", str(cache_dir),
        "--result-dir", result_template,
    ]
    if extra_args:
        cmd_extra.extend(extra_args)

    # run_check_cep hardcodes some args; extra_args override them because
    # argparse uses the last occurrence for store actions.
    # test_dir is not used in S3 mode (no local test mount), so tmp_path is fine.
    output, code = run_check_cep(
        test_dir=tmp_path,
        result_dir=tmp_path,
        extra_args=cmd_extra,
        env=omd_env,
        proc_timeout=proc_timeout,
    )

    resolved_result_dir = tmp_path / "results" / hostname / service
    report_prefix = f"{hostname}/{service}"

    # Register dirs that contain container-owned (sub-UID) files for cleanup
    if cleanup_paths is not None:
        cleanup_paths.append(cache_dir)
        cleanup_paths.append(tmp_path / "results")

    return output, code, resolved_result_dir, report_prefix


def query_loki(host_name: str, service_description: str, timeout: int = 10) -> dict:
    """Poll Loki until a log entry for the given host/service appears.

    Returns the first matching stream value dict.
    Raises TimeoutError if nothing arrives within timeout seconds.
    """
    query = '{job="cep",host_name="' + host_name + '"}'
    encoded = urllib.parse.urlencode({"query": query, "limit": "10"})
    url = f"http://localhost:3100/loki/api/v1/query_range?{encoded}"

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                import json as _json
                data = _json.loads(resp.read())
                streams = data.get("data", {}).get("result", [])
                for stream in streams:
                    labels = stream.get("stream", {})
                    if labels.get("service_description") == service_description:
                        values = stream.get("values", [])
                        if values:
                            return {"labels": labels, "values": values}
        except Exception:
            pass
        time.sleep(1)

    raise TimeoutError(
        f"No Loki log entry for host_name={host_name!r} "
        f"service_description={service_description!r} within {timeout}s"
    )
