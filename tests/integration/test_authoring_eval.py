"""Gated behavioural evaluation of the AI test-authoring workflow (spec 021).

Runs the REAL `cep_authoring` orchestrator against the self-contained sample app
and asserts capability OUTCOMES — never the generated test's source text
(FR-008 / SC-008).

Gating (contracts §6, spec 022): the sole gate is the explicit `CEP_AI_EVAL=1`
opt-in — the default free model (opencode/big-pickle) is keyless, so
credential presence can no longer gate the eval. With the flag unset every
case `skip`s and the fast/offline suite stays green (SC-006). A second skip
guards on the AI image being present.

A run whose output is dominated by quota/availability errors FAILS the case
immediately (never retried or skipped, user decision 2026-07-20) — the fix is
more budget (another free model or a Zen key via OPENCODE_MODEL), not a retry.

Run only these cases:
    CEP_AI_EVAL=1 pytest -m authoring_eval tests/integration/test_authoring_eval.py -v
"""

import json

import pytest

from conftest import requires_ai_image, requires_ai_eval
from authoring_eval_support import (
    EvalCase,
    adversarial_holds,
    critic_pass,
    deterministic_passes,
    extract_and_run,
    no_secret_leak,
    package_produced,
    perfdata_labels,
    prepare_workspace,
    report_complete,
    run_authoring,
    values_emitted,
)

# ---------------------------------------------------------------------------
# Positive-path cases (one per golden capability)
# ---------------------------------------------------------------------------

POSITIVE_CASES = [
    EvalCase("MultiPageJourney", expects_value=True),
    EvalCase("ConsentFirstVisit"),
    EvalCase("AmbiguousElements"),
    EvalCase("StableVsDynamic", expects_value=True),
    EvalCase("AsyncLoading", expects_value=True),
    EvalCase("ResponsiveBreakpoint"),
    EvalCase("NoStableLocator"),
    EvalCase("MovingElement"),
    EvalCase("Iframe"),
]

# Extra per-capability behavioural checks over (pkg_exit, stdout, steps). The
# base signal — "the packaged test passes" — is asserted for every case; these
# add a capability-specific behavioural signal without reading source.
CAPABILITY_ASSERTS = {
    # Reaching the dashboard and capturing the stable balance both show up as the
    # AvailableBalance perfdata metric (a run artifact, not source text).
    "MultiPageJourney": lambda e, o, s: "AvailableBalance" in perfdata_labels(o, s),
}


def _record_metrics(record_property, case, result):
    """Attach the per-run metrics to the pytest record (SC-007). Never gated on."""
    record_property("case", case.name)
    record_property("attempts", result.attempts)
    for key, value in (result.metrics or {}).items():
        record_property(f"metric_{key}", value)


@pytest.mark.authoring_eval
@requires_ai_eval
@requires_ai_image
@pytest.mark.parametrize("case", POSITIVE_CASES, ids=lambda c: c.name)
def test_authoring_positive(case, tmp_path, record_property):
    ws = prepare_workspace(case, tmp_path)
    result = run_authoring(ws, case.testname)
    _record_metrics(record_property, case, result)

    assert result.classification != "quota_error", (
        f"quota/availability error for {case.name} — needs more budget "
        f"(another free model or a Zen key via OPENCODE_MODEL), not a "
        f"migration bug:\n{result.combined_output[-2000:]}"
    )

    # --- behavioural properties (contracts/eval-properties.md) ---
    assert package_produced(result), f"no package produced:\n{result.combined_output[-2000:]}"
    assert deterministic_passes(result), "orchestrator never reached the clean-run streak"
    assert critic_pass(result), "critic did not return pass"

    pkg_dir, pkg_exit, stdout, steps = extract_and_run(result, tmp_path)
    assert no_secret_leak(pkg_dir), "a credential-shaped string leaked outside .env"
    assert report_complete(pkg_dir), "VERIFICATION.md missing or not substantive"
    assert values_emitted(case, stdout, steps), "requested value(s) not emitted as perfdata"

    # capability-specific behavioural signal
    assert pkg_exit == 0, f"packaged test did not pass:\n{stdout[-2000:]}"
    extra = CAPABILITY_ASSERTS.get(case.name)
    if extra is not None:
        assert extra(pkg_exit, stdout, steps), f"capability assertion failed:\n{stdout[-1000:]}"


# ---------------------------------------------------------------------------
# Adversarial cases (US4): the workflow must refuse/flag, never fabricate a
# passing test (SC-003).
# ---------------------------------------------------------------------------

ADVERSARIAL_CASES = [
    EvalCase("incoherent", kind="adversarial", golden_dir="MultiPageJourney",
             intent_relpath="adversarial/incoherent.ai", adversarial_kind="incoherent"),
    EvalCase("unsatisfiable", kind="adversarial", golden_dir="StableVsDynamic",
             intent_relpath="adversarial/unsatisfiable.ai", adversarial_kind="unsatisfiable"),
    EvalCase("nondeterministic", kind="adversarial", golden_dir="StableVsDynamic",
             intent_relpath="adversarial/nondeterministic.ai", adversarial_kind="nondeterministic"),
]


@pytest.mark.authoring_eval
@requires_ai_eval
@requires_ai_image
@pytest.mark.parametrize("case", ADVERSARIAL_CASES, ids=lambda c: c.name)
def test_authoring_adversarial(case, tmp_path, record_property):
    ws = prepare_workspace(case, tmp_path)
    result = run_authoring(ws, case.testname)
    _record_metrics(record_property, case, result)

    assert result.classification != "quota_error", (
        f"quota/availability error for {case.name} — needs more budget "
        f"(another free model or a Zen key via OPENCODE_MODEL), not a "
        f"migration bug:\n{result.combined_output[-2000:]}"
    )

    # The one hard requirement: no fabricated passing test — refuse or flag the
    # conflict (never silently weaken an assertion). See contracts/eval-properties.
    assert adversarial_holds(case, result), (
        f"adversarial case {case.name!r} did not refuse/flag:\n{result.combined_output[-2000:]}"
    )
