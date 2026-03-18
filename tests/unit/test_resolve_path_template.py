"""Unit tests for resolve_path_template (T012 — 009-report-management)."""
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_t_placeholder_backward_compat():
    """%t absent: output is identical to old behaviour."""
    result = resolve_path_template(
        "/omd/var/tmp/%h/%s",
        hostname="myhost",
        servicedescription="MyService",
    )
    assert result == "/omd/var/tmp/myhost/MyService"


def test_t_placeholder_replaced():
    """%t present and started provided: %t is replaced with the started value."""
    result = resolve_path_template(
        "/omd/var/tmp/%h/%s/%t",
        hostname="myhost",
        servicedescription="MyService",
        started="1710763200",
    )
    assert result == "/omd/var/tmp/myhost/MyService/1710763200"


def test_h_s_t_combined():
    """All three placeholders resolved in one call."""
    result = resolve_path_template(
        "/data/%h/%s/%t/results",
        hostname="srv01",
        servicedescription="Checkout",
        started="1710000000",
    )
    assert result == "/data/srv01/Checkout/1710000000/results"


def test_t_present_started_empty():
    """%t in template with started='' leaves %t unresolved (guard case)."""
    result = resolve_path_template(
        "/omd/var/tmp/%h/%s/%t",
        hostname="host",
        servicedescription="svc",
        started="",
    )
    # %t must NOT be replaced when started is empty
    assert "%t" in result
    assert result == "/omd/var/tmp/host/svc/%t"


def test_no_placeholders_at_all():
    """Template with no placeholders passes through unchanged."""
    result = resolve_path_template("/fixed/path", hostname="h", servicedescription="s")
    assert result == "/fixed/path"


def test_t_only_placeholder():
    """Only %t in template."""
    result = resolve_path_template("%t", hostname="h", servicedescription="s", started="999")
    assert result == "999"
