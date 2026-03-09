"""Session-scoped fixtures shared across all test subdirectories.

Provides:
  - PLAYWRIGHT_CONFIG constant (written at runtime alongside each .test.ts)
  - write_playwright_config fixture (callable)
  - cep_image session fixture (build or reuse via CEP_IMAGE env var)
  - compose_stack session fixture (MinIO + Loki via podman-compose)
  - pytest_sessionstart hook: cleans sub-UID garbage from prior runs
"""
import glob
import os
import subprocess
import time
from pathlib import Path

import pytest

try:
    import boto3
    import urllib.request
    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False

# ---------------------------------------------------------------------------
# Clean up sub-UID garbage from prior runs
# ---------------------------------------------------------------------------
# Rootless Podman maps pwuser to a host sub-UID.  pytest cannot rm_rf those
# files when it garbage-collects old tmp dirs.  We use `podman run --user root`
# to remove them before pytest tries (and warns about) the same dirs.

_CEP_IMAGE_DEFAULT = os.environ.get("CEP_IMAGE", "check_cep:test")


def _clean_garbage_dirs():
    """Remove sub-UID files in pytest garbage dirs via the container image."""
    basetemp = Path(f"/tmp/pytest-of-{os.environ.get('USER', 'root')}")
    for gdir in basetemp.glob("garbage-*"):
        subprocess.run(
            ["podman", "run", "--rm", "--user", "root",
             "--volume", f"{gdir}:/cleanup:rw,z",
             _CEP_IMAGE_DEFAULT, "bash", "-c",
             "find /cleanup -not -writable -exec chmod 777 {} +; rm -rf /cleanup/*"],
            capture_output=True,
            timeout=60,
        )
        try:
            import shutil
            shutil.rmtree(str(gdir))
        except OSError:
            pass


def pytest_configure(config):
    """Clean sub-UID garbage before pytest's own tmp cleanup.

    Must run in pytest_configure (not pytest_sessionstart) because pytest's
    make_numbered_dir_with_cleanup moves old dirs to garbage and tries to
    rm_rf them before sessionstart fires.
    """
    _clean_garbage_dirs()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# playwright.config.ts written alongside every .test.ts at runtime.
# testDir: '.' because playwright.config.ts is a sibling of the test file.
PLAYWRIGHT_CONFIG = """\
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  timeout: 30000,
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
"""

_REPO_ROOT = Path(__file__).parent.parent
_CONTAINER_DIR = _REPO_ROOT / "src" / "container"
_COMPOSE_FILE = _REPO_ROOT / "tests" / "compose" / "docker-compose.yml"
_MINIO_HEALTH = "http://localhost:9000/minio/health/live"
_LOKI_HEALTH = "http://localhost:3100/ready"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def write_playwright_config():
    """Return a callable that writes PLAYWRIGHT_CONFIG into a given directory."""
    def _write(dest_dir: Path) -> None:
        (dest_dir / "playwright.config.ts").write_text(PLAYWRIGHT_CONFIG)
    return _write


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def cep_image():
    """Return the container image tag to use for all tests.

    If CEP_IMAGE is set, use it directly (no build).
    Otherwise build src/container/ and yield 'check_cep:test'.
    """
    image = os.environ.get("CEP_IMAGE")
    if image:
        yield image
        return

    image = "check_cep:test"
    subprocess.run(
        ["podman", "build", "-t", image, str(_CONTAINER_DIR)],
        check=True,
    )
    yield image
    # No teardown — keep the image for subsequent runs


def _wait_for_url(url: str, timeout: int = 30) -> None:
    """Poll url with 1 s backoff until HTTP 200 or timeout."""
    deadline = time.time() + timeout
    last_exc = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_exc = exc
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {url}: {last_exc}")


@pytest.fixture(scope="session")
def compose_stack():
    """Start MinIO + Loki via podman-compose; yield boto3 s3 client; teardown.

    Skipped entirely when SKIP_INTEGRATION=1.
    """
    if os.environ.get("SKIP_INTEGRATION"):
        pytest.skip("compose stack not available (SKIP_INTEGRATION set)")

    subprocess.run(
        ["podman-compose", "-f", str(_COMPOSE_FILE), "up", "-d"],
        check=True,
    )

    try:
        _wait_for_url(_MINIO_HEALTH, timeout=30)
        _wait_for_url(_LOKI_HEALTH, timeout=30)

        if not _BOTO3_AVAILABLE:
            raise RuntimeError("boto3 is required for S3 mode tests; install with pip install boto3")

        s3 = boto3.client(
            "s3",
            endpoint_url="http://localhost:9000",
            aws_access_key_id="minioadmin",
            aws_secret_access_key="minioadmin",
            region_name="us-east-1",
        )
        for bucket in ("cep-tests", "cep-reports"):
            try:
                s3.create_bucket(Bucket=bucket)
            except s3.exceptions.BucketAlreadyOwnedByYou:
                pass

        yield s3

    finally:
        subprocess.run(
            ["podman-compose", "-f", str(_COMPOSE_FILE), "down"],
            check=False,
        )
