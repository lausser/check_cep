"""Unit-style tests for the cep_authoring orchestrator (spec 020, US4).

These exercise the parts that need no real AI or browser:
  - PREFLIGHT failures (missing required section, missing @-referenced file)
    each exit 2 with a message naming the problem.
  - Cap-termination: when the loop never passes the gate, it produces no
    package, writes a progress report, and exits 1.

`gemini` and `npx` are stubbed on PATH so the loop runs without the real
tools. RUN is stubbed to always fail, so the gate is never reached and the
cap path is exercised deterministically.
"""

import os
import subprocess
from pathlib import Path

CEP_AUTHORING = (
    Path(__file__).parent.parent.parent / "src" / "container" / "image" / "cep_authoring"
)

_INTENT_TEMPLATE = """# Test Intent: {name}

Site: demo

## Target URL

https://example.com

## Desired Flow

I opened the page and saw the heading.

## Success Criteria

The heading is visible.

## Lessons Learned
"""


def _fakebin(tmp_path, npx_exit=1):
    """Create fake `gemini` (no-op success) and `npx` (playwright fails) on a
    bin dir; return the dir path to prepend to PATH."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "gemini").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "npx").write_text(f"#!/bin/sh\n# stubbed `npx playwright test`\nexit {npx_exit}\n")
    for name in ("gemini", "npx"):
        (bin_dir / name).chmod(0o755)
    return str(bin_dir)


def _run(intent_path, args=None, env_extra=None, tmp_path=None):
    env = dict(os.environ)
    if tmp_path is not None:
        env["PATH"] = _fakebin(tmp_path) + os.pathsep + env["PATH"]
    if env_extra:
        env.update(env_extra)
    cmd = ["bash", str(CEP_AUTHORING)] + (args or []) + [str(intent_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    return proc.stdout + proc.stderr, proc.returncode


def test_preflight_missing_section(tmp_path):
    intent = tmp_path / "Portfolio.ai"
    text = _INTENT_TEMPLATE.format(name="Portfolio").replace(
        "## Success Criteria\n\nThe heading is visible.\n\n", ""
    )
    intent.write_text(text)
    out, code = _run(intent, args=["--dry-run"], env_extra={"GEMINI_API_KEY": "x"})
    assert code == 2, out
    assert "## Success Criteria" in out
    assert "missing required section" in out


def test_preflight_missing_referenced_file(tmp_path):
    intent = tmp_path / "Portfolio.ai"
    text = _INTENT_TEMPLATE.format(name="Portfolio").replace(
        "## Element Hints", ""
    )
    # add a reference to a file that does not exist
    text = text.replace(
        "I opened the page and saw the heading.",
        "I clicked the button that looks like @login-button.png.",
    )
    intent.write_text(text)
    out, code = _run(intent, args=["--dry-run"], env_extra={"GEMINI_API_KEY": "x"})
    assert code == 2, out
    assert "@login-button.png" in out
    assert "referenced file not found" in out


def test_dry_run_passes_on_valid_intent(tmp_path):
    intent = tmp_path / "Portfolio.ai"
    intent.write_text(_INTENT_TEMPLATE.format(name="Portfolio"))
    out, code = _run(intent, args=["--dry-run"], env_extra={"GEMINI_API_KEY": "x"})
    assert code == 0, out
    assert "DRY-RUN" in out


def test_cap_termination_no_package(tmp_path):
    """RUN always fails → gate never passes → cap reached → exit 1, a progress
    report is written, and no package is produced."""
    intent = tmp_path / "Portfolio.ai"
    intent.write_text(_INTENT_TEMPLATE.format(name="Portfolio"))
    out, code = _run(
        intent,
        args=["-n", "2", "-r", "2"],
        env_extra={"GEMINI_API_KEY": "x"},
        tmp_path=tmp_path,
    )
    assert code == 1, out
    # progress report written, no package tarball
    assert (tmp_path / "Portfolio-progress.md").exists(), out
    assert not list(tmp_path.glob("*.tar.gz")), "no package should be produced at the cap"
    assert "cap of 2 iterations reached" in out
