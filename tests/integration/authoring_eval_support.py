"""Support for the gated behavioural authoring eval (spec 021, US2/US4/US5).

Drives the REAL `cep_authoring` orchestrator inside the AI image against the
self-contained sample app, then asserts **behavioural properties** of the run —
never the generated test's source text (FR-008 / SC-008).

Nothing here runs unless the caller has already passed the `GEMINI_API_KEY`
gate; the module has no import-time side effects and needs no key to import.

Property extraction (contracts/eval-properties.md) works only from observable
artifacts: the orchestrator exit code, the produced `.tar.gz`, the run log, the
packaged test's `steps.json` perfdata, and the packaged files themselves.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Paths & configuration
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_APP = _REPO_ROOT / "tests" / "authoring-eval" / "sample-app"
GOLDEN = _REPO_ROOT / "tests" / "authoring-eval" / "golden"

CEP_AI_IMAGE = os.environ.get("CEP_AI_IMAGE", "localhost/check_cep:ai-latest")
# Container user of the AI image — must match check_cep's CONTAINER_UID/GID so
# the rw authoring workspace is writable by the in-container process.
CONTAINER_UID = 1001
CONTAINER_GID = 1001
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")  # FR-014 pin
CEP_MAX_ITERATIONS = os.environ.get("CEP_MAX_ITERATIONS", "5")
CEP_EVAL_RETRIES = int(os.environ.get("CEP_EVAL_RETRIES", "1"))
HEADED = bool(os.environ.get("HEADED", ""))
CEP_SLOW_MO = os.environ.get("CEP_SLOW_MO", "")

# Credential-shaped strings the sample app uses; must never appear OUTSIDE .env.
_SECRET_MARKERS = ("Passw0rd!",)

# Model quota / availability signatures (R5): classified distinctly from a
# genuine authoring failure so an accidental trigger reports clearly.
_QUOTA_PATTERNS = re.compile(
    r"RESOURCE_EXHAUSTED|quota|rate.?limit|\b429\b|\b503\b|UNAVAILABLE|"
    r"overloaded|deadline exceeded|ECONNRESET|service unavailable",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Eval case model
# ---------------------------------------------------------------------------


@dataclass
class EvalCase:
    """One parametrized eval case (data-model §6)."""

    name: str                       # case id (capability, or adversarial variant)
    kind: str = "positive"          # "positive" | "adversarial"
    golden_dir: str = ""            # golden capability dir (defaults to `name`)
    intent_relpath: str = "intent.ai"   # intent within GOLDEN/<golden_dir>/
    expects_value: bool = False     # intent declares a "Values to Capture"
    # Per-capability behavioural check over (packaged_stdout, steps_json).
    capability_assert: Optional[Callable[[str, dict], bool]] = None
    # Adversarial variant defect kind ("incoherent"|"unsatisfiable"|"nondeterministic").
    adversarial_kind: str = ""

    @property
    def testname(self) -> str:
        """The .ai basename → cep_authoring TESTNAME (and package/testdir name)."""
        return self.name


@dataclass
class RunResult:
    exit_code: int
    workspace: Path
    combined_output: str
    attempts: int
    classification: str = "ran"     # "ran" | "quota_error"
    metrics: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Workspace preparation
# ---------------------------------------------------------------------------


def prepare_workspace(case: EvalCase, tmp_path: Path) -> Path:
    """Build a fresh per-case site workspace: sample app + the golden intent.

    Layout mirrors the 020 authoring mount root (`/home/pwuser/tests`):
      <ws>/journey/…            (copied sample app — intent Target URLs resolve)
      <ws>/probes/…
      <ws>/<Capability>.ai      (the golden intent, renamed to the testname)
      <ws>/assets/…             (any @-referenced templates, if the golden has them)
    """
    ws = tmp_path / f"ws-{case.name}"
    ws.mkdir(parents=True)

    # Copy the sample app pages so relative Target URLs resolve inside the mount.
    for sub in ("journey", "probes"):
        shutil.copytree(SAMPLE_APP / sub, ws / sub)

    src = GOLDEN / (case.golden_dir or case.name)
    # The intent, renamed to the capability so TESTNAME/package are predictable.
    shutil.copyfile(src / case.intent_relpath, ws / f"{case.testname}.ai")

    # @-referenced templates (vision cases) live under the golden assets/.
    golden_assets = src / "assets"
    if golden_assets.is_dir():
        shutil.copytree(golden_assets, ws / "assets")

    return ws


# ---------------------------------------------------------------------------
# Driving cep_authoring inside the AI image
# ---------------------------------------------------------------------------


def _container_name(testname: str) -> str:
    """Deterministic per-run container name so a timed-out run can be cleaned up."""
    return f"cep-eval-{testname.lower()}-{os.getpid()}"


def _podman_authoring_cmd(ws: Path, testname: str) -> list[str]:
    env_flags = [
        "--env", f"GEMINI_API_KEY={os.environ.get('GEMINI_API_KEY', '')}",
        "--env", f"GEMINI_MODEL={GEMINI_MODEL}",
    ]
    if HEADED:
        env_flags += ["--env", "HEADED=1"]
    if CEP_SLOW_MO:
        env_flags += ["--env", f"CEP_SLOW_MO={CEP_SLOW_MO}"]
    return [
        "podman", "run", "--rm",
        "--name", _container_name(testname),
        # Map the container user to the host operator, exactly as check_cep does
        # for --authoring (src/check_cep, CONTAINER_UID/GID). Without this the
        # rw workspace is root-owned inside the container while the process runs
        # as pwuser(1001), so `mkdir -p "$TESTDIR"` fails on permissions and the
        # AI has nowhere to write. Do NOT add `--user`: the image's default user
        # is already pwuser and keep-id maps the host UID onto it.
        f"--userns=keep-id:uid={CONTAINER_UID},gid={CONTAINER_GID}",
        "--security-opt", "label=disable",
        "--volume", f"{ws}:/home/pwuser/tests:rw,z",
        *env_flags,
        CEP_AI_IMAGE,
        "cep_authoring", "-n", str(CEP_MAX_ITERATIONS),
        f"/home/pwuser/tests/{testname}.ai",
    ]


def run_authoring(ws: Path, testname: str, proc_timeout: int = 900) -> RunResult:
    """Invoke cep_authoring in the AI image, with bounded whole-run retries (R5).

    A run whose output is dominated by quota/availability errors is classified
    `quota_error` (retried, then reported distinctly) rather than a real failure.
    """
    cmd = _podman_authoring_cmd(ws, testname)
    attempts = 0
    combined = ""
    code = 1
    timed_out = False
    for attempt in range(1, CEP_EVAL_RETRIES + 2):  # 1 try + CEP_EVAL_RETRIES
        attempts = attempt
        timed_out = False
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=proc_timeout)
            combined = (proc.stdout or "") + (proc.stderr or "")
            code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            # A hung/over-long run must report as a clean failure, not a harness
            # error. Surface whatever the orchestrator managed to emit.
            timed_out = True
            code = 124
            partial = (exc.stdout or b"") + (exc.stderr or b"")
            if isinstance(partial, bytes):
                partial = partial.decode(errors="replace")
            combined = f"{partial}\n[harness] cep_authoring exceeded {proc_timeout}s — killed."
            # Killing the podman CLI leaves the container running; remove it.
            subprocess.run(["podman", "rm", "-f", _container_name(testname)],
                           capture_output=True, timeout=60)
        if code == 0:
            break
        if timed_out or not _QUOTA_PATTERNS.search(combined):
            break  # genuine failure/timeout — do not waste more quota
        time.sleep(2)  # transient backoff before retry

    classification = "ran"
    if timed_out:
        # A run that stalls *because* the model backed off on quota is a budget
        # problem, not an authoring regression — classify it as such so it skips
        # rather than reporting a false failure.
        classification = "quota_error" if _QUOTA_PATTERNS.search(combined) else "timeout"
    elif code != 0 and _QUOTA_PATTERNS.search(combined):
        classification = "quota_error"

    return RunResult(
        exit_code=code,
        workspace=ws,
        combined_output=combined,
        attempts=attempts,
        classification=classification,
        metrics=read_run_metrics(ws, testname),
    )


# ---------------------------------------------------------------------------
# Run-metrics record (data-model §7, FR-015)
# ---------------------------------------------------------------------------


def read_run_metrics(ws: Path, testname: str) -> dict:
    """Read the compact metrics record cep_authoring writes at STOP/PACKAGE.

    Returns {} if absent (older image / preflight failure). Never gates pass/fail.
    """
    path = ws / f"{testname}-metrics.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return {}


# ---------------------------------------------------------------------------
# Package inspection
# ---------------------------------------------------------------------------


def _find_package(ws: Path, testname: str) -> Optional[Path]:
    matches = sorted(ws.glob(f"{testname}-*.tar.gz"))
    return matches[-1] if matches else None


def _extract_package(pkg: Path, dest: Path) -> Path:
    with tarfile.open(pkg, "r:gz") as tar:
        tar.extractall(dest)
    # Package top-level dir is <TestName>/.
    return dest / pkg.name.split("-")[0] if (dest / pkg.name.split("-")[0]).exists() \
        else next(p for p in dest.iterdir() if p.is_dir())


def run_packaged_test(pkg_dir: Path) -> tuple[int, str, dict]:
    """Run the packaged test in the AI image; return (exit, stdout, steps_json).

    No AI involved — this is a plain `npx playwright test` producing steps.json,
    from which perfdata is read. Used for values_emitted + capability asserts,
    all behavioural (never source text).
    """
    cmd = [
        "podman", "run", "--rm",
        f"--userns=keep-id:uid={CONTAINER_UID},gid={CONTAINER_GID}",
        "--security-opt", "label=disable",
        "--volume", f"{pkg_dir}:/home/pwuser/tests/_pkg:rw,z",
        CEP_AI_IMAGE,
        "bash", "-lc",
        "cd /home/pwuser/tests/_pkg && "
        "PLAYWRIGHT_JSON_OUTPUT_NAME=/home/pwuser/tests/_pkg/steps.json "
        "NODE_PATH=/home/pwuser/node_modules "
        "npx playwright test --reporter=json,line",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    combined = (proc.stdout or "") + (proc.stderr or "")
    steps: dict = {}
    steps_path = pkg_dir / "steps.json"
    if steps_path.is_file():
        try:
            steps = json.loads(steps_path.read_text())
        except (ValueError, OSError):
            steps = {}
    return proc.returncode, combined, steps


# ---------------------------------------------------------------------------
# Behavioural property assertions (contracts/eval-properties.md, T029)
# ---------------------------------------------------------------------------


def package_produced(result: RunResult) -> bool:
    return result.exit_code == 0 and _find_package(result.workspace, _tn(result)) is not None


def deterministic_passes(result: RunResult, clean_runs: int = 2) -> bool:
    """The orchestrator only packages after CLEAN_RUNS consecutive clean runs;
    confirm from its RUN-phase log that the required streak was reached."""
    return f"{clean_runs}/{clean_runs} clean runs" in result.combined_output


def critic_pass(result: RunResult) -> bool:
    return "GATE: pass" in result.combined_output


def no_secret_leak(pkg_dir: Path) -> bool:
    """No credential-shaped string appears in any packaged file except `.env`."""
    for path in pkg_dir.rglob("*"):
        if not path.is_file() or path.name == ".env":
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if any(marker in text for marker in _SECRET_MARKERS):
            return False
    return True


def report_complete(pkg_dir: Path) -> bool:
    """VERIFICATION.md present and substantive (verified/assumed/unverified shape)."""
    vf = pkg_dir / "VERIFICATION.md"
    if not vf.is_file():
        return False
    text = vf.read_text(errors="ignore").lower()
    return len(text) > 120 and ("verif" in text and ("assum" in text or "cannot" in text or "unverif" in text))


def perfdata_labels(packaged_stdout: str, steps: dict) -> list[str]:
    """Collect custom (non-duration) perfdata labels emitted by the packaged run.

    Reads the documented `NagiosPerfData: 'Label'=value` stdout convention and
    any `perfdata_*` step annotations — behaviour, not source text.
    """
    labels = re.findall(r"NagiosPerfData:\s*'([^']+)'=", packaged_stdout)

    def _walk(node):
        if isinstance(node, dict):
            for ann in node.get("annotations", []) or []:
                t = ann.get("type", "")
                if isinstance(t, str) and t.startswith("perfdata_"):
                    labels.append(t[len("perfdata_"):])
            for k in ("suites", "specs", "tests", "results", "steps"):
                for child in node.get(k, []) or []:
                    _walk(child)
    _walk(steps)
    return labels


def values_emitted(case: EvalCase, packaged_stdout: str, steps: dict) -> bool:
    """If the intent declares values to capture, ≥1 custom perfdata metric is emitted."""
    if not case.expects_value:
        return True
    return len(perfdata_labels(packaged_stdout, steps)) > 0


# ---------------------------------------------------------------------------
# Adversarial assertions (contracts/eval-properties.md, T034)
# ---------------------------------------------------------------------------

_REFUSAL_PATTERNS = re.compile(
    r"refuse|cannot|conflict|does not cohere|incoherent|unsatisfiable|"
    r"ambiguous|revise the intent|no package|not deterministic|"
    r"cap of .* iterations reached|NO PACKAGE",
    re.IGNORECASE,
)


def adversarial_holds(case: EvalCase, result: RunResult) -> bool:
    """A negative case must NOT yield a fabricated passing package; it must
    refuse/ask or flag the conflict (never silently weaken an assertion)."""
    produced = result.exit_code == 0 and _find_package(result.workspace, _tn(result)) is not None
    if produced:
        return False  # fabricated a green test → fail the adversarial case
    # No package: expect an explanation / flagged conflict in the run output or
    # the progress report.
    if _REFUSAL_PATTERNS.search(result.combined_output):
        return True
    progress = result.workspace / f"{case.testname}-progress.md"
    return progress.is_file()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tn(result: RunResult) -> str:
    """Recover the testname from the workspace (ws-<name>)."""
    return result.workspace.name[len("ws-"):]


def extract_and_run(result: RunResult, tmp_path: Path) -> tuple[Path, int, str, dict]:
    """Extract the produced package and run it once; return (pkg_dir, exit, stdout, steps)."""
    pkg = _find_package(result.workspace, _tn(result))
    assert pkg is not None, "no package to extract"
    dest = tmp_path / f"pkg-{_tn(result)}"
    dest.mkdir()
    pkg_dir = _extract_package(pkg, dest)
    exit_code, stdout, steps = run_packaged_test(pkg_dir)
    return pkg_dir, exit_code, stdout, steps
