"""source_local.py - Test source plugin: local mount.

Two modes depending on TEST_ARTIFACT:

* Directory (already mounted at /home/pwuser/tests by the host):
  Validates that ~/tests exists and contains test files.

* TGZ archive (mounted at /home/pwuser/input-artifact.tgz by the host):
  Extracts the archive to ~/tests and then validates test files are present.
"""

import os
import tarfile

from _shared import has_test_files as _has_test_files

# Fixed container-side mount point for local tgz artifacts
_INPUT_ARTIFACT_PATH = "/home/pwuser/input-artifact.tgz"


def acquire_tests(_test_name: str, dest_path: str) -> None:
    """Ensure test files are present at dest_path.

    Args:
        _test_name: Unused — artifact type is determined from TEST_ARTIFACT env var
        dest_path: Container-side path where tests must be (/home/pwuser/tests)

    Environment variables used:
        TEST_ARTIFACT: Optional.  If set and ends .tgz/.tar.gz, the archive
                       mounted at /home/pwuser/input-artifact.tgz is extracted
                       to dest_path.  Otherwise dest_path is expected to be
                       pre-mounted by the host.

    Raises:
        RuntimeError: If extraction fails or no test files are found
    """
    test_artifact = os.environ.get("TEST_ARTIFACT", "")

    if test_artifact.endswith(".tgz") or test_artifact.endswith(".tar.gz"):
        # Archive mode: extract from fixed mount point
        if not os.path.isfile(_INPUT_ARTIFACT_PATH):
            raise RuntimeError(
                f"Expected archive at {_INPUT_ARTIFACT_PATH!r} but file not found; "
                "check that --test-artifact path is correct and the file is readable"
            )
        try:
            os.makedirs(dest_path, exist_ok=True)
            with tarfile.open(_INPUT_ARTIFACT_PATH, mode="r:gz") as tar:
                tar.extractall(path=dest_path)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to extract {_INPUT_ARTIFACT_PATH}: {exc}"
            ) from exc
    else:
        # Directory mode: host has already mounted dest_path
        if not os.path.isdir(dest_path):
            raise RuntimeError(f"Test directory {dest_path!r} does not exist")

    if not _has_test_files(dest_path):
        raise RuntimeError(
            f"No test files (*.test.ts, *.test.js) found in {dest_path!r}"
        )
