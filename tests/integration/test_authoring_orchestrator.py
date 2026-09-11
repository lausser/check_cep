"""Unit-style tests for the cep_authoring orchestrator (spec 020, US4).

These exercise the parts that need no real AI or browser:
  - PREFLIGHT failures (missing required section, missing @-referenced file,
    a `google/…` model without GEMINI_API_KEY) each exit 2 with a message
    naming the problem.
  - Cap-termination: when the loop never passes the gate, it produces no
    package, writes a progress report, and exits 1.
  - Critic verdict extraction (contract §3): clean JSON, JSON embedded in
    prose, and unparseable output each drive the correct GATE outcome.

`opencode` and `npx` are stubbed on PATH so the loop runs without the real
tools. Unless a case configures otherwise, RUN is stubbed to always fail, so
the gate is never reached and the cap path is exercised deterministically.
The default free model (`opencode/big-pickle`) is keyless, so no credential
env var is needed to pass PREFLIGHT.
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


def _fakebin(tmp_path, npx_exit=1, critic_output=None):
    """Create fake `opencode` and `npx` on a bin dir; return the dir path to
    prepend to PATH.

    `opencode` no-ops (exit 0) for AUTHOR calls. When invoked with
    `--agent critic` it prints `critic_output` verbatim to stdout, if given.

    `npx` exits `npx_exit`; on a simulated clean run (npx_exit=0) it also
    touches VERIFICATION.md in its cwd (== $TESTDIR during phase_run),
    mirroring a real verification pass so GATE evaluation can be exercised.
    """
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(exist_ok=True)
    critic_block = ""
    if critic_output is not None:
        critic_block = f"""
is_critic=0
for a in "$@"; do
  [ "$a" = "--agent" ] && is_critic=1
done
if [ "$is_critic" = "1" ]; then
  cat <<'CRITIC_OUTPUT_EOF'
{critic_output}
CRITIC_OUTPUT_EOF
  exit 0
fi
"""
    (bin_dir / "opencode").write_text(f"#!/bin/sh\n{critic_block}exit 0\n")
    npx_block = "touch VERIFICATION.md\n" if npx_exit == 0 else ""
    (bin_dir / "npx").write_text(
        f"#!/bin/sh\n# stubbed `npx playwright test`\n{npx_block}exit {npx_exit}\n"
    )
    for name in ("opencode", "npx"):
        (bin_dir / name).chmod(0o755)
    return str(bin_dir)


def _run(intent_path, args=None, env_extra=None, tmp_path=None, npx_exit=1, critic_output=None):
    env = dict(os.environ)
    # Never leak host AI credentials into the deterministic offline tests.
    for key in ("GEMINI_API_KEY", "OPENCODE_API_KEY", "OPENCODE_MODEL"):
        env.pop(key, None)
    if tmp_path is not None:
        env["PATH"] = (
            _fakebin(tmp_path, npx_exit=npx_exit, critic_output=critic_output)
            + os.pathsep
            + env["PATH"]
        )
    if critic_output is not None:
        # phase_critic bails out before invoking opencode if the (real,
        # container-only) critic prompt file is absent — provide a stub so
        # CRITIC is actually reached in these host-side tests.
        skill_dir = tmp_path / "fake-skill"
        (skill_dir / "references").mkdir(parents=True, exist_ok=True)
        (skill_dir / "references" / "critic-prompt.md").write_text("Review the test.\n")
        env["CEP_SKILL_DIR"] = str(skill_dir)
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
    out, code = _run(intent, args=["--dry-run"])
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
    out, code = _run(intent, args=["--dry-run"])
    assert code == 2, out
    assert "@login-button.png" in out
    assert "referenced file not found" in out


def test_preflight_google_model_without_key_fails(tmp_path):
    """A `google/…` OPENCODE_MODEL without GEMINI_API_KEY fails PREFLIGHT
    with exit 2 (contract §1) — the only credential check left."""
    intent = tmp_path / "Portfolio.ai"
    intent.write_text(_INTENT_TEMPLATE.format(name="Portfolio"))
    out, code = _run(
        intent,
        args=["--dry-run"],
        env_extra={"OPENCODE_MODEL": "google/gemini-3.1-flash-lite"},
    )
    assert code == 2, out
    assert "GEMINI_API_KEY" in out


def test_dry_run_passes_on_valid_intent(tmp_path):
    intent = tmp_path / "Portfolio.ai"
    intent.write_text(_INTENT_TEMPLATE.format(name="Portfolio"))
    out, code = _run(intent, args=["--dry-run"])
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
        tmp_path=tmp_path,
    )
    assert code == 1, out
    # progress report written, no package tarball
    assert (tmp_path / "Portfolio-progress.md").exists(), out
    assert not list(tmp_path.glob("*.tar.gz")), "no package should be produced at the cap"
    assert "cap of 2 iterations reached" in out


def test_verdict_extraction_clean_json(tmp_path):
    """A critic stdout that is exactly a JSON object parses via the
    whole-stdout JSON.parse path and gates as pass."""
    intent = tmp_path / "Portfolio.ai"
    intent.write_text(_INTENT_TEMPLATE.format(name="Portfolio"))
    out, code = _run(
        intent,
        args=["-n", "1", "-r", "1"],
        tmp_path=tmp_path,
        npx_exit=0,
        critic_output='{"verdict": "pass", "findings": []}',
    )
    assert "GATE: pass" in out, out


def test_verdict_extraction_json_in_prose(tmp_path):
    """A critic stdout with the JSON object embedded in surrounding prose
    falls back to the last-{…}-block regex and still gates as pass."""
    intent = tmp_path / "Portfolio.ai"
    intent.write_text(_INTENT_TEMPLATE.format(name="Portfolio"))
    critic_output = (
        "Here is my review of the authored test.\n"
        '{"verdict": "pass", "findings": '
        '[{"severity": "low", "criterion": "style", "problem": "minor", "evidence": "n/a"}]}\n'
        "Let me know if you have questions."
    )
    out, code = _run(
        intent,
        args=["-n", "1", "-r", "1"],
        tmp_path=tmp_path,
        npx_exit=0,
        critic_output=critic_output,
    )
    assert "GATE: pass" in out, out


def test_verdict_extraction_garbage(tmp_path):
    """Unparseable critic stdout extracts an empty verdict, which gates as
    fail (conservative default — never a silent pass)."""
    intent = tmp_path / "Portfolio.ai"
    intent.write_text(_INTENT_TEMPLATE.format(name="Portfolio"))
    out, code = _run(
        intent,
        args=["-n", "1", "-r", "1"],
        tmp_path=tmp_path,
        npx_exit=0,
        critic_output="not json at all, just garbage output",
    )
    assert "GATE: pass" not in out, out
    assert "not passing" in out, out
