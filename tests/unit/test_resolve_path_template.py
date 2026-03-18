"""Unit tests for resolve_path_template (T012 — 009-report-management / 010-run-context)."""
import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the check_cep module directly (no package install required)
# ---------------------------------------------------------------------------

_PLUGIN = Path(__file__).parent.parent.parent / "src" / "check_cep"
_loader = importlib.machinery.SourceFileLoader("check_cep_mod", str(_PLUGIN))
_spec = importlib.util.spec_from_file_location("check_cep_mod", str(_PLUGIN), loader=_loader)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

resolve_path_template = _mod.resolve_path_template

from tests.unit.test_run_context import make_ctx  # noqa: E402


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_t_placeholder_backward_compat():
    """%t absent: output is identical to old behaviour."""
    ctx = make_ctx(hostname="myhost", servicedescription="MyService")
    result = resolve_path_template("/omd/var/tmp/%h/%s", ctx)
    assert result == "/omd/var/tmp/myhost/MyService"


def test_t_placeholder_replaced():
    """%t present and started provided: %t is replaced with the started value."""
    ctx = make_ctx(hostname="myhost", servicedescription="MyService", started_str="1710763200")
    result = resolve_path_template("/omd/var/tmp/%h/%s/%t", ctx)
    assert result == "/omd/var/tmp/myhost/MyService/1710763200"


def test_h_s_t_combined():
    """All three placeholders resolved in one call."""
    ctx = make_ctx(hostname="srv01", servicedescription="Checkout", started_str="1710000000")
    result = resolve_path_template("/data/%h/%s/%t/results", ctx)
    assert result == "/data/srv01/Checkout/1710000000/results"


def test_t_present_started_empty():
    """%t in template with started_str='' leaves %t unresolved (guard case)."""
    ctx = make_ctx(hostname="host", servicedescription="svc", started_str="")
    result = resolve_path_template("/omd/var/tmp/%h/%s/%t", ctx)
    assert "%t" in result
    assert result == "/omd/var/tmp/host/svc/%t"


def test_no_placeholders_at_all():
    """Template with no placeholders passes through unchanged."""
    ctx = make_ctx(hostname="h", servicedescription="s")
    result = resolve_path_template("/fixed/path", ctx)
    assert result == "/fixed/path"


def test_t_only_placeholder():
    """Only %t in template."""
    ctx = make_ctx(hostname="h", servicedescription="s", started_str="999")
    result = resolve_path_template("%t", ctx)
    assert result == "999"
