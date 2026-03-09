"""dest_local.py - Result destination plugin: local mount.

When result-dest=local, artefacts are already at ~/results via host mount.
This plugin ensures the file layout is correct for check_cep to read after exit.
"""

import logging
import os
import subprocess

logger = logging.getLogger("dest_local")


def publish_results(test_name: str, results_path: str, nagios_state: int) -> None:
    """Ensure artefacts in results_path are arranged for host reading.

    Args:
        test_name: TESTNAME — symbolic identifier
        results_path: Container-side path containing Playwright output ("~/results")
        nagios_state: Playwright exit code (0=pass, 1=fail, 2=error)

    In rootless Podman, files written by pwuser inside the container appear on
    the host owned by a sub-uid (e.g. 525287) that is not the calling user.
    Fix: "sudo chown -R root:root" maps to the host user's uid (root-in-container
    == host-user-on-host in rootless Podman), restoring readable ownership.

    Exception: with --userns=keep-id (headed mode), pwuser inside already maps
    to the host user, so chown to root would map to a subordinate uid instead.
    """
    # With --userns=keep-id (headed/debug mode), pwuser IS the host user —
    # chown to root would be wrong.  Detect via HEADED env var.
    if os.environ.get("HEADED"):
        logger.debug(f"Headed mode: skipping chown (keep-id maps pwuser to host user)")
        return

    # Fix ownership so the host user can read/delete result files.
    # root inside a rootless Podman container == the host user outside it.
    try:
        subprocess.run(
            ["sudo", "chown", "-R", "root:root", results_path],
            check=True, capture_output=True,
        )
        # Directories need x-bit, files need r-bit for the host user.
        subprocess.run(
            ["sudo", "chmod", "-R", "u+rwX,go+rX", results_path],
            check=True, capture_output=True,
        )
        logger.debug(f"Fixed ownership of {results_path}")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Could not fix ownership of {results_path}: {e.stderr}")
