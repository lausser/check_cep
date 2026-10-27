#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run.py - Container-side dispatcher for CEP.

Reads environment variables, dynamically loads plugin modules, orchestrates:
acquire tests -> run Playwright -> write test-meta.json -> publish results -> ship logs.
Contains NO plugin-specific logic.

Exit-code protocol (constitution 2.2.0 Principle IV, contracts/container-io.md §6):
0 passed, 1 passed with author-signalled warning, 2 Playwright failure or
timeout, 3 the tests could not run properly — always preceded by a
`CEPUNKNOWN [[[reason]]]` line on stdout. No other code leaves run.py.
"""

import argparse
import base64
import binascii
import importlib
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from typing import Any, List, NamedTuple, Optional, Protocol, Tuple, runtime_checkable

logger = logging.getLogger("run.py")

# Make container-side plugins importable at module level (run.py is the entry
# point in the container; plugins/ is a sibling directory).
_PLUGINS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
if _PLUGINS_DIR not in sys.path:
    sys.path.insert(0, _PLUGINS_DIR)

from _shared import SKIP_DIRS as _SKIP_DIRS, TEST_FILE_SUFFIXES
from _layers import LayerTimeout


# ---------------------------------------------------------------------------
# Exit-code protocol (spec 023 FR-052)
# ---------------------------------------------------------------------------

def emit_unknown(message: str) -> int:
    """Print the CEPUNKNOWN marker the host turns into Nagios UNKNOWN; return 3."""
    one_line = " ".join(str(message).split())
    print(f"CEPUNKNOWN [[[{one_line}]]]", flush=True)
    return 3


def normalize_exit(rc: int) -> Tuple[int, Optional[str]]:
    """Map the raw `timeout … npx playwright test` code to the protocol.

    Returns (protocol exit, CEPUNKNOWN message or None). Nothing passes
    through unchanged: a raw 3 is a Playwright failure, never protocol 3.
    """
    if rc == 0:
        return 0, None
    if rc == 150:
        return 1, None  # author-signalled warning (check_dopla parity, FR-053)
    if rc in (124, 137):
        return 2, None  # coreutils timeout (SIGTERM/SIGKILL)
    if rc in (125, 126, 127):
        # coreutils timeout could not run npx — the tests never ran
        return 3, f"playwright could not be started (exit {rc})"
    return 2, None


def stdio_text(entry: Any) -> str:
    """Text of one Playwright stdout/stderr entry: `text`, or base64 `buffer`.

    Must stay identical to check_cep's copy (spec 023 FR-053); invalid entries
    and undecodable buffers count as empty.
    """
    if not isinstance(entry, dict):
        return ""
    if isinstance(entry.get("text"), str):
        return entry["text"]
    if isinstance(entry.get("buffer"), str):
        try:
            return base64.b64decode(entry["buffer"], validate=True).decode("utf-8", "replace")
        except (binascii.Error, ValueError):
            return ""
    return ""


def report_has_visible_stderr(obj: Any) -> bool:
    """True if any `stderr` list anywhere in the report has visible content.

    Searches the whole report, retries included (spec 023 FR-053). Must stay
    identical to check_cep's copy.
    """
    if isinstance(obj, dict):
        stderr = obj.get("stderr")
        if isinstance(stderr, list) and any(stdio_text(e).strip() for e in stderr):
            return True
        return any(report_has_visible_stderr(v) for v in obj.values())
    if isinstance(obj, list):
        return any(report_has_visible_stderr(v) for v in obj)
    return False


def load_steps(results_path: str) -> Optional[dict]:
    """Return the parsed steps.json report, or None if missing or unreadable."""
    try:
        with open(os.path.join(results_path, "steps.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Plugin Protocols
# ---------------------------------------------------------------------------

@runtime_checkable
class TestSourcePlugin(Protocol):
    # deadline: absolute epoch seconds (spec 023 FR-030, contracts/container-io.md §4)
    def acquire_tests(self, test_name: str, dest_path: str, deadline: float) -> None: ...


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
        emit_unknown(f"{axis_name}='{env_value}' not valid. "
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
        emit_unknown(f"Plugin '{module_name}' not found: {e}")
        sys.exit(3)
    except Exception as e:
        emit_unknown(f"Failed to load plugin '{module_name}': {e}")
        sys.exit(3)


# ---------------------------------------------------------------------------
# test-meta.json writing (T013)
# ---------------------------------------------------------------------------

def write_test_meta(results_path: str, hostname: str, servicedescription: str,
                    exitcode: int, duration: float, probe_location: str,
                    cep_started: str = "", layers: Optional[List[dict]] = None) -> dict:
    """Write test-meta.json with execution metadata (v2 schema).

    `layers` (spec 023 FR-033) records position, host path and type of every
    layer; never contents or container paths.
    """
    meta = {
        "started": cep_started if cep_started else str(int(time.time())),
        "finished": str(int(time.time())),
        "hostname": hostname,
        "servicedescription": servicedescription,
        "exitcode": exitcode,
        "duration": f"{duration:.3f}",
        "probe_location": probe_location,
        "status": {0: "OK", 1: "WARNING", 2: "CRITICAL"}.get(exitcode, "UNKNOWN"),
    }
    if layers is not None:
        meta["layers"] = layers
    meta_path = os.path.join(results_path, "test-meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=4)
    return meta


# ---------------------------------------------------------------------------
# Test tree preparation and run mode (spec 023, contracts/container-io.md §5)
# ---------------------------------------------------------------------------

# Playwright's own config lookup order.
PLAYWRIGHT_CONFIG_NAMES = ("playwright.config.ts", "playwright.config.js",
                           "playwright.config.mts", "playwright.config.mjs",
                           "playwright.config.cts", "playwright.config.cjs")


class NoTestsError(Exception):
    """Discovery found no *.test.ts / *.test.js file."""


class PrepareError(Exception):
    """The test tree could not be prepared; the message becomes the CEPUNKNOWN reason."""


class RunMode(NamedTuple):
    kind: str                  # "project-root" or "discovery"
    config: Optional[str]      # absolute path of the active config, if any
    workdir: str               # absolute cwd for Playwright
    ignored_dirs: Tuple[str, ...] = ()   # discovery: other test dirs (relative)


def find_config(directory: str) -> Optional[str]:
    """Return the first Playwright config in `directory`, in Playwright's order."""
    for name in PLAYWRIGHT_CONFIG_NAMES:
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    return None


def select_discovery_dir(test_dir: str) -> RunMode:
    """Pick the byte-wise first directory that holds test files (FR-042).

    Shared-utility folders (SKIP_DIRS) are never candidates. Raises
    NoTestsError when the tree holds no test file at all.
    """
    candidates = []
    for root, dirs, files in os.walk(test_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        if any(f.endswith(TEST_FILE_SUFFIXES) for f in files):
            rel = os.path.relpath(root, test_dir)
            candidates.append("" if rel == "." else rel)
    if not candidates:
        raise NoTestsError()
    candidates.sort(key=lambda p: p.encode())
    workdir = os.path.normpath(os.path.join(test_dir, candidates[0]))
    return RunMode("discovery", find_config(workdir), workdir, tuple(candidates[1:]))


def detect_run_mode(test_dir: str) -> RunMode:
    """Choose how Playwright runs on the merged tree (FR-040, FR-041).

    A Playwright config at the root means project-root mode: Playwright runs
    from the root with that config and picks the tests itself. Otherwise
    discovery mode, as before spec 023.
    """
    config = find_config(test_dir)
    if config:
        return RunMode("project-root", config, test_dir)
    return select_discovery_dir(test_dir)


def steps_has_no_tests(data: Optional[dict]) -> bool:
    """True only for Playwright's "No tests found" report (research R-09).

    A syntax or import error also yields no suites and zero stats, but its
    `errors` entry names the failure: that stays a Playwright failure.
    """
    if not data or data.get("suites"):
        return False
    stats = data.get("stats", {})
    if sum(stats.get(k, 0) for k in ("expected", "unexpected", "flaky", "skipped")):
        return False
    errors = data.get("errors") or []
    return bool(errors) and all("No tests found" in e.get("message", "") for e in errors)


def describe_run_mode(mode: RunMode, test_dir: str) -> str:
    """The one debug line for both modes (contracts/container-io.md §7)."""
    config = os.path.relpath(mode.config, test_dir) if mode.config else "none"
    return f"run mode: {mode.kind} (config {config}, workdir {os.path.relpath(mode.workdir, test_dir)})"


def layer_records(test_source: str) -> List[dict]:
    """The `layers` entry of test-meta.json (FR-033), from the host's handoff."""
    if test_source == "s3":
        return [{"position": 1, "path": "s3:" + os.environ.get("TEST_ARTIFACT", ""),
                 "type": "archive"}]
    try:
        layers = json.loads(os.environ.get("TEST_ARTIFACT_LAYERS", "[]"))
    except ValueError:
        return []
    return [{"position": l["position"], "path": l["host_path"], "type": l["type"]}
            for l in layers]


def prepare(source_module, test_name: str, test_dir: str, timeout_sec: int,
            n_layers: int) -> RunMode:
    """Acquire and merge the layers into test_dir, then choose the run mode.

    Shared by scheduled runs and `--prepare-only` (FR-032). Raises
    PrepareError with the CEPUNKNOWN reason.
    """
    try:
        source_module.acquire_tests(test_name, test_dir, time.time() + timeout_sec)
    except LayerTimeout as e:
        raise PrepareError(str(e) or f"acquiring/merging layers exceeded the timeout of {timeout_sec}s")
    except Exception as e:
        raise PrepareError(str(e))

    try:
        mode = detect_run_mode(test_dir)
    except NoTestsError:
        raise PrepareError(f"no *.test.ts/*.test.js found after merging {n_layers} layer(s)")
    if mode.ignored_dirs:
        print(f"WARNING: test files also found in {', '.join(mode.ignored_dirs)}; ignored",
              file=sys.stderr, flush=True)
    logger.debug(describe_run_mode(mode, test_dir))
    return mode


def start_virtual_display() -> None:
    """Headed mode without a forwarded display: serve one over VNC on :1.

    Xtigervnc is a combined X server + VNC server in one process; it avoids
    the XSHM problems that make x11vnc show a black screen with Xvfb. The
    host publishes port 5900 (Wayland hosts, --vnc).
    """
    subprocess.Popen(
        ["Xtigervnc", ":1",
         "-geometry", "1280x720", "-depth", "24",
         "-SecurityTypes", "None",
         "-rfbport", "5900",
         "-ac"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    os.environ["DISPLAY"] = ":1"
    # Give the VNC viewer on the host time to connect and render the desktop
    # before Playwright starts — otherwise tests finish before the spectator
    # sees anything.
    time.sleep(3)


# ---------------------------------------------------------------------------
# Playwright invocation (T012)
# ---------------------------------------------------------------------------

def build_spectate_wrapper(config_path: Optional[str], slow_mo: int) -> str:
    """TypeScript config that adds slowMo and relaxed timeouts (FR-045, R-11).

    It imports the active config relatively and never touches testDir, so it
    must live next to that config. Project `use` blocks take precedence over
    the top-level `use`, so the values are merged into every project too.
    """
    if not config_path:
        return (f"export default {{ expect: {{ timeout: 30000 }}, "
                f"use: {{ actionTimeout: 30000, launchOptions: {{ slowMo: {slow_mo} }} }} }};\n")
    return (
        f"import base from './{os.path.basename(config_path)}';\n"
        f"const slowMo = {slow_mo};\n"
        "const spectate = (use: any = {}) => ({ ...use, actionTimeout: 30000,\n"
        "  launchOptions: { ...(use.launchOptions || {}), slowMo } });\n"
        "export default {\n"
        "  ...base,\n"
        "  expect: { ...(base.expect || {}), timeout: 30000 },\n"
        "  use: spectate(base.use),\n"
        "  ...(base.projects ? { projects: base.projects.map((p: any) => ({ ...p, use: spectate(p.use) })) } : {}),\n"
        "};\n"
    )


def run_playwright(workdir: str, results_path: str, timeout_sec: int,
                   headed: bool = False, browser: str = "chromium",
                   config_path: Optional[str] = None, project_root: bool = False) -> int:
    """Run Playwright tests with coreutils timeout wrapping.

    Runs from `workdir`. In project-root mode the config is passed explicitly
    (`--config`); in discovery mode Playwright finds the config in workdir.
    Returns the raw Playwright exit code.
    """
    env = os.environ.copy()
    env["CI"] = "1"
    env["PLAYWRIGHT_JSON_OUTPUT_NAME"] = os.path.join(results_path, "steps.json")
    env["PLAYWRIGHT_HTML_OUTPUT_DIR"] = os.path.join(results_path, "playwright-report")
    # Screenshots and traces go to the results dir, not into the test tree.
    env["PLAYWRIGHT_OUTPUT_DIR"] = os.path.join(results_path, "test-results")

    # Wrap with coreutils timeout (PWTIMEOUT + 10s buffer). An argv list,
    # never a shell: workdirs and config paths come from layer content.
    # npx walks up from the test tree to ~/node_modules.
    cmd = ["timeout", str(timeout_sec + 10), "npx", "playwright", "test",
           "--output", os.path.join(results_path, "test-results"),
           "--reporter=line,html,json"]
    if headed:
        cmd.append("--headed")

    active_config = config_path if project_root else None
    # Spectate mode: a wrapper next to the active config adds slowMo and
    # bumped timeouts. Wayland/display flags are handled by the in-place
    # Chromium binary wrapper (see Dockerfile).
    slow_mo = os.environ.get("CEP_SLOW_MO", "")
    if slow_mo:
        wrapper_dir = os.path.dirname(config_path) if config_path else workdir
        active_config = os.path.join(wrapper_dir, ".cep-spectate.config.ts")
        with open(active_config, "w") as f:
            f.write(build_spectate_wrapper(config_path, int(slow_mo)))
        logger.debug(f"Config wrapper {active_config}: slowMo={slow_mo}")
    if active_config:
        cmd += ["--config", active_config]

    # Always expose the browser selection to the Playwright process so test
    # code can guard screenshot/vision calls via process.env.BROWSER.
    env["BROWSER"] = browser

    # Inject Lightpanda monkey-patch via NODE_OPTIONS
    if browser == "lightpanda":
        node_opts = env.get("NODE_OPTIONS", "")
        env["NODE_OPTIONS"] = (node_opts + " --require /home/pwuser/patch-lightpanda.js").strip()

    logger.debug(f"Running: {cmd} in {workdir}")
    proc = subprocess.run(cmd, capture_output=True, cwd=workdir, env=env)

    for stream, writer in ((proc.stdout, sys.stdout.buffer),
                           (proc.stderr, sys.stderr.buffer)):
        if stream:
            writer.write(stream)
            writer.flush()

    # coreutils timeout exits 124 (SIGTERM) or 137 (SIGKILL).
    # Playwright never gets to print its own timeout message, so emit a
    # marker that check_cep's check_timeout() can detect.
    if proc.returncode in (124, 137):
        print("PWTIMEOUT_EXCEEDED", flush=True)

    return proc.returncode


# ---------------------------------------------------------------------------
# Lightpanda CDP lifecycle
# ---------------------------------------------------------------------------

def start_lightpanda_cdp() -> subprocess.Popen:
    """Start Lightpanda CDP server and wait until it accepts connections.

    Returns the Popen handle (caller must terminate).
    Raises RuntimeError on startup failure.
    """
    logger.debug("Starting Lightpanda CDP server on 127.0.0.1:9222")
    proc = subprocess.Popen(
        ["/usr/local/bin/lightpanda", "serve", "--host", "127.0.0.1", "--port", "9222"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    for _ in range(30):
        try:
            req = urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1)
            req.close()
            logger.debug("Lightpanda CDP server ready")
            return proc
        except Exception:
            time.sleep(0.2)
    proc.kill()
    proc.wait()
    raise RuntimeError("Lightpanda CDP server failed to start")


def stop_lightpanda_cdp(proc: subprocess.Popen) -> None:
    """Terminate the Lightpanda CDP server process."""
    logger.debug("Terminating Lightpanda process")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


# ---------------------------------------------------------------------------
# Main orchestration (T014)
# ---------------------------------------------------------------------------

def main(prepare_only: bool = False) -> int:
    """Container-side main: acquire_tests -> Playwright -> test-meta -> publish -> logs.

    With prepare_only (`--prepare-only`, used by `check_cep --shell`), stop
    once the test tree is built: exit 0, or 3 with a CEPUNKNOWN reason.
    """
    # Read environment variables
    test_source = os.environ.get("TEST_SOURCE", "local")
    result_dest = os.environ.get("RESULT_DEST", "local")
    logging_mode = os.environ.get("LOGGING", "none")
    hostname = os.environ.get("NAGIOS_HOSTNAME", "")
    servicedescription = os.environ.get("NAGIOS_SERVICEDESC", "")
    testident = os.environ.get("TESTIDENT", "")
    timeout_sec = int(os.environ.get("PWTIMEOUT", "60"))
    cep_started = os.environ.get("CEP_STARTED", "")
    probe_location = os.environ.get("PROBE_LOCATION", "unknown")
    debug = os.environ.get("DEBUG", "")
    headed = bool(os.environ.get("HEADED", ""))
    browser = os.environ.get("BROWSER", "chromium")

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

    # Step 1: Build the check root (merged layers) and choose the run mode. Acquisition
    # time counts toward PWTIMEOUT (FR-030).
    layers = layer_records(test_source)
    acquire_start = time.time()
    try:
        mode = prepare(source_module, test_name, test_dir, timeout_sec, max(1, len(layers)))
    except PrepareError as e:
        return emit_unknown(str(e))
    acquire_secs = time.time() - acquire_start

    if prepare_only:
        print(f"check root ready: {test_dir} ({mode.kind})", file=sys.stderr, flush=True)
        return 0

    # Step 2: Headed mode without a forwarded display gets a virtual one,
    # started only after the tree is ready (a merge error needs no display).
    if headed and not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
        start_virtual_display()

    # Step 2b: Start Lightpanda CDP server if requested
    lightpanda_proc = None
    if browser == "lightpanda":
        try:
            lightpanda_proc = start_lightpanda_cdp()
        except (RuntimeError, OSError) as e:
            return emit_unknown(str(e))

    # Step 3: Run Playwright in the run mode's working directory
    start_time = time.time()
    try:
        exitcode = run_playwright(mode.workdir, results_dir,
                                  max(1, timeout_sec - int(acquire_secs)),
                                  headed=headed, browser=browser, config_path=mode.config,
                                  project_root=mode.kind == "project-root")
    finally:
        if lightpanda_proc is not None:
            stop_lightpanda_cdp(lightpanda_proc)
    duration = time.time() - start_time

    # Normalize to the protocol (contracts/container-io.md §6)
    exitcode, unknown_reason = normalize_exit(exitcode)
    steps = load_steps(results_dir)
    if unknown_reason:
        exitcode = emit_unknown(unknown_reason)
    elif mode.kind == "project-root" and steps_has_no_tests(steps):
        # The config selected nothing: a setup problem, not a test failure.
        # Continue so test-meta, publish and logs still run (FR-043).
        exitcode = emit_unknown(f"Playwright configuration {os.path.basename(mode.config)} "
                                "matched no tests")
    elif exitcode == 0 and report_has_visible_stderr(steps):
        logger.debug("visible stderr in steps.json: passed run raised to WARNING")
        exitcode = 1

    # Step 4: Write test-meta.json
    meta = write_test_meta(results_dir, hostname, servicedescription, exitcode, duration,
                           probe_location, cep_started, layers=layers)

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
                "started": meta["started"],
                "finished": meta["finished"],
            }
            logging_module.ship_logs(test_name, summary)
        except Exception as e:
            print(f"LOKIERROR [[[logging failed: {e}]]]")
            logger.error(f"ship_logs failed: {e}")

    # Print duration for host-side parsing
    print(f"PLAYWRIGHTCHECKDURATIONFORPLUGIN={int(duration)}")

    return exitcode


class _RunArgumentParser(argparse.ArgumentParser):
    """Usage errors follow the protocol: CEPUNKNOWN marker, then exit 3."""

    def error(self, message: str) -> None:
        emit_unknown(f"run.py: {message}")
        sys.exit(3)


def parse_run_args(argv: Optional[List[str]]) -> argparse.Namespace:
    parser = _RunArgumentParser(prog="run.py")
    parser.add_argument("--prepare-only", action="store_true",
                        help="build the test tree and exit (used by check_cep --shell)")
    return parser.parse_args(argv)


def run_guarded(argv: Optional[List[str]] = None) -> int:
    """Top-level crash boundary (constitution 2.2.0, Principle IV).

    Protocol codes 0-2 leave run.py only as main()'s return value. A SystemExit
    passes only with 0/None or 3 (every code-3 exit prints its marker first);
    any other exit or exception becomes CEPUNKNOWN + 3. BaseException (e.g.
    KeyboardInterrupt) is deliberately not caught.
    """
    try:
        args = parse_run_args(argv)
        return main(prepare_only=args.prepare_only)
    except SystemExit as exc:
        if exc.code is None or exc.code in (0, 3):
            return exc.code or 0
        return emit_unknown(f"run.py failed: {exc!r}")
    except Exception as exc:
        return emit_unknown(f"run.py failed: {exc!r}")


if __name__ == "__main__":
    sys.exit(run_guarded())
