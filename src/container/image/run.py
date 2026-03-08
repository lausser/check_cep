#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run.py - Container-side dispatcher for CEP.

Reads environment variables, dynamically loads plugin modules, orchestrates:
acquire tests -> run Playwright -> write test-meta.json -> publish results -> ship logs.
Contains NO plugin-specific logic.
"""

import importlib
import json
import logging
import os
import subprocess
import sys
import time
from typing import Protocol, runtime_checkable

logger = logging.getLogger("run.py")


# ---------------------------------------------------------------------------
# Plugin Protocols
# ---------------------------------------------------------------------------

@runtime_checkable
class TestSourcePlugin(Protocol):
    def acquire_tests(self, test_name: str, dest_path: str) -> None: ...


@runtime_checkable
class ResultDestPlugin(Protocol):
    def publish_results(self, test_name: str, results_path: str, nagios_state: int) -> None: ...


@runtime_checkable
class LoggingPlugin(Protocol):
    def ship_logs(self, test_name: str, summary: dict) -> None: ...


# ---------------------------------------------------------------------------
# Plugin registries: env var value -> module name
# ---------------------------------------------------------------------------

_SOURCE_MODULES = {"local": "source_local", "s3": "source_s3"}
_DEST_MODULES = {"local": "dest_local", "s3": "dest_s3"}
_LOGGING_MODULES = {"none": None, "loki": "logging_loki"}


def load_plugin(registry: dict, env_value: str, axis_name: str):
    """Load a plugin module by looking up the env var value in the registry.

    Returns the imported module, or None for 'none' logging.
    Exits with UNKNOWN on any loading failure.
    """
    if env_value not in registry:
        print(f"UNKNOWN: {axis_name}='{env_value}' not valid. "
              f"Allowed: {', '.join(registry.keys())}")
        sys.exit(3)

    module_name = registry[env_value]
    if module_name is None:
        return None

    try:
        # Plugins are in the plugins/ subdirectory relative to run.py
        plugin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
        if plugin_dir not in sys.path:
            sys.path.insert(0, plugin_dir)
        module = importlib.import_module(module_name)
        return module
    except ModuleNotFoundError as e:
        print(f"UNKNOWN: Plugin '{module_name}' not found: {e}")
        sys.exit(3)
    except Exception as e:
        print(f"UNKNOWN: Failed to load plugin '{module_name}': {e}")
        sys.exit(3)


# ---------------------------------------------------------------------------
# test-meta.json writing (T013)
# ---------------------------------------------------------------------------

def write_test_meta(results_path: str, hostname: str, servicedescription: str,
                    exitcode: int, duration: float, probe_location: str) -> dict:
    """Write test-meta.json with execution metadata."""
    meta = {
        "timestamp": str(int(time.time())),
        "hostname": hostname,
        "servicedescription": servicedescription,
        "exitcode": exitcode,
        "duration": f"{duration:.3f}",
        "probe_location": probe_location,
        "status": {0: "OK", 1: "WARNING", 2: "CRITICAL"}.get(exitcode, "UNKNOWN"),
    }
    meta_path = os.path.join(results_path, "test-meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=4)
    return meta


# ---------------------------------------------------------------------------
# Test discovery
# ---------------------------------------------------------------------------

def find_test_subdir(test_dir: str) -> str:
    """Walk test_dir and return the directory containing the first *.test.ts file.

    Skips 'functions', 'variables', and 'node_modules' directories — these are
    shared-utility folders that never hold test entry points.

    Raises RuntimeError if no *.test.ts file is found.
    """
    skip = {"functions", "variables", "node_modules"}
    for root, dirs, files in os.walk(test_dir):
        dirs[:] = [d for d in dirs if d not in skip]
        for fname in files:
            if fname.endswith(".test.ts") or fname.endswith(".test.js"):
                logger.debug(f"Found test file: {os.path.join(root, fname)}")
                return root
    raise RuntimeError(f"No *.test.ts / *.test.js found under '{test_dir}'")


# ---------------------------------------------------------------------------
# Playwright invocation (T012)
# ---------------------------------------------------------------------------

def run_playwright(test_dir: str, results_path: str, timeout_sec: int,
                   headed: bool = False) -> int:
    """Run Playwright tests with coreutils timeout wrapping.

    Returns Playwright exit code.
    """
    env = os.environ.copy()
    env["CI"] = "1"
    env["PLAYWRIGHT_JSON_OUTPUT_NAME"] = os.path.join(results_path, "steps.json")
    env["PLAYWRIGHT_HTML_OUTPUT_DIR"] = os.path.join(results_path, "playwright-report")
    # Redirect test-results (screenshots, traces) to results dir so test_dir
    # can stay read-only.
    env["PLAYWRIGHT_OUTPUT_DIR"] = os.path.join(results_path, "test-results")

    # Wrap with coreutils timeout (PWTIMEOUT + 10s buffer)
    # test_dir is ~/tests — npx walks up to ~/node_modules.
    timeout_val = timeout_sec + 10
    cmd = (f"timeout {timeout_val} npx playwright test"
           f" --output {os.path.join(results_path, 'test-results')}"
           f" --reporter=line,html,json")

    if headed:
        cmd += " --headed"

    logger.debug(f"Running: {cmd} in {test_dir}")
    proc = subprocess.run(cmd, shell=True, capture_output=True, cwd=test_dir, env=env)

    # Print stdout/stderr for check_cep to capture
    if proc.stdout:
        sys.stdout.buffer.write(proc.stdout)
        sys.stdout.buffer.flush()
    if proc.stderr:
        sys.stderr.buffer.write(proc.stderr)
        sys.stderr.buffer.flush()

    # coreutils timeout exits 124 (SIGTERM) or 137 (SIGKILL).
    # Playwright never gets to print its own timeout message, so emit a
    # marker that check_cep's check_timeout() can detect.
    if proc.returncode in (124, 137):
        print("PWTIMEOUT_EXCEEDED", flush=True)

    return proc.returncode


# ---------------------------------------------------------------------------
# Main orchestration (T014)
# ---------------------------------------------------------------------------

def main() -> int:
    """Container-side main: acquire_tests -> Playwright -> test-meta -> publish -> logs."""
    # Read environment variables
    test_source = os.environ.get("TEST_SOURCE", "local")
    result_dest = os.environ.get("RESULT_DEST", "local")
    logging_mode = os.environ.get("LOGGING", "none")
    hostname = os.environ.get("NAGIOS_HOSTNAME", "")
    servicedescription = os.environ.get("NAGIOS_SERVICEDESC", "")
    testident = os.environ.get("TESTIDENT", "")
    timeout_sec = int(os.environ.get("PWTIMEOUT", "60"))
    probe_location = os.environ.get("PROBE_LOCATION", "unknown")
    debug = os.environ.get("DEBUG", "")
    headed = bool(os.environ.get("HEADED", ""))

    # Configure logging
    if debug:
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger("boto3").setLevel(logging.INFO)
        logging.getLogger("botocore").setLevel(logging.INFO)
        logging.getLogger("s3transfer").setLevel(logging.INFO)
        logging.getLogger("urllib3").setLevel(logging.INFO)
    else:
        logging.basicConfig(level=logging.INFO)

    test_name = f"{hostname}__{servicedescription}"
    home = os.path.expanduser("~")
    test_dir = os.path.join(home, "tests")
    results_dir = os.path.join(home, "results")

    # Load plugins
    source_module = load_plugin(_SOURCE_MODULES, test_source, "TEST_SOURCE")
    dest_module = load_plugin(_DEST_MODULES, result_dest, "RESULT_DEST")
    logging_module = load_plugin(_LOGGING_MODULES, logging_mode, "LOGGING")

    # Step 1: Acquire tests
    try:
        source_module.acquire_tests(test_name, test_dir)
    except Exception as e:
        print(f"UNKNOWN: Test acquisition failed: {e}")
        return 3

    # Step 2: Locate the test subfolder (playwright.config.ts lives next to *.test.ts)
    try:
        active_test_dir = find_test_subdir(test_dir)
    except RuntimeError as e:
        print(f"UNKNOWN: {e}")
        return 3

    # Step 3: Run Playwright from the subfolder that contains playwright.config.ts
    start_time = time.time()
    exitcode = run_playwright(active_test_dir, results_dir, timeout_sec, headed=headed)
    duration = time.time() - start_time

    # Normalize exit codes
    if exitcode == 124 or exitcode == 137:
        # timeout or SIGKILL
        exitcode = 2
    elif exitcode != 0 and exitcode != 3:
        exitcode = 2

    # Step 4: Write test-meta.json
    meta = write_test_meta(results_dir, hostname, servicedescription, exitcode, duration, probe_location)

    # Step 5: Publish results (non-fatal)
    try:
        dest_module.publish_results(test_name, results_dir, exitcode)
    except Exception as e:
        print(f"S3UPLOADHASFAILED [[[publish_results error: {e}]]]")
        logger.error(f"publish_results failed: {e}")

    # Step 6: Ship logs (optional, non-fatal)
    if logging_module is not None:
        try:
            summary = {
                "hostname": hostname,
                "servicedescription": servicedescription,
                "status": meta["status"],
                "duration": meta["duration"],
                "probe_location": probe_location,
                "timestamp": meta["timestamp"],
            }
            logging_module.ship_logs(test_name, summary)
        except Exception as e:
            print(f"LOKIERROR [[[logging failed: {e}]]]")
            logger.error(f"ship_logs failed: {e}")

    # Print duration for host-side parsing
    print(f"PLAYWRIGHTCHECKDURATIONFORPLUGIN={int(duration)}")

    return exitcode


if __name__ == "__main__":
    sys.exit(main())
