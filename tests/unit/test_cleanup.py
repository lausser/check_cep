"""Unit tests for LocalCleanup and parse_retention (T021 — 009-report-management)."""
import importlib.machinery
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Load the check_cep module directly (no package install required)
# ---------------------------------------------------------------------------

_PLUGIN = Path(__file__).parent.parent.parent / "src" / "check_cep"
_loader = importlib.machinery.SourceFileLoader("check_cep_mod", str(_PLUGIN))
_spec = importlib.util.spec_from_file_location("check_cep_mod", str(_PLUGIN), loader=_loader)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
# Register so unittest.mock.patch can resolve "check_cep_mod.time.time"
sys.modules.setdefault("check_cep_mod", _mod)

LocalCleanup = _mod.LocalCleanup
CleanupResult = _mod.CleanupResult
parse_retention = _mod.parse_retention
run_cleanup = _mod.run_cleanup

from tests.unit.test_run_context import make_ctx, make_config  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run_dir(parent: Path, started: int, with_meta: bool = True) -> Path:
    """Create a fake run directory under parent with optional test-meta.json."""
    d = parent / str(started)
    d.mkdir()
    if with_meta:
        meta = {"started": str(started), "finished": str(started + 10),
                "exitcode": 0, "status": "OK"}
        (d / "test-meta.json").write_text(json.dumps(meta))
    return d


# ---------------------------------------------------------------------------
# LocalCleanup.list_candidates tests
# ---------------------------------------------------------------------------

def test_old_dir_with_meta_is_returned(tmp_path):
    """Old directory with test-meta.json is returned as a candidate."""
    now = int(time.time())
    old_started = now - 7200  # 2 hours old
    _make_run_dir(tmp_path, old_started, with_meta=True)
    current_run_dir = str(tmp_path / str(now))

    plugin = LocalCleanup()
    candidates = plugin.list_candidates(str(tmp_path), current_run_dir, retention_seconds=3600)

    assert len(candidates) == 1
    assert candidates[0]["started"] == old_started


def test_dir_without_meta_is_skipped(tmp_path):
    """Directory without test-meta.json is never returned, even if old."""
    now = int(time.time())
    old_started = now - 7200
    _make_run_dir(tmp_path, old_started, with_meta=False)
    current_run_dir = str(tmp_path / str(now))

    plugin = LocalCleanup()
    candidates = plugin.list_candidates(str(tmp_path), current_run_dir, retention_seconds=3600)

    assert candidates == []


def test_non_integer_dir_name_is_skipped(tmp_path):
    """Directories with non-integer names (e.g. 'latest') are never candidates."""
    (tmp_path / "latest").mkdir()
    current_run_dir = str(tmp_path / "current")

    plugin = LocalCleanup()
    candidates = plugin.list_candidates(str(tmp_path), current_run_dir, retention_seconds=0)

    assert candidates == []


def test_current_run_dir_excluded(tmp_path):
    """The current run's directory is never included in candidates."""
    now = int(time.time())
    old_started = now - 7200
    _make_run_dir(tmp_path, old_started, with_meta=True)
    current_run_dir = str(tmp_path / str(old_started))  # same as old_started

    plugin = LocalCleanup()
    candidates = plugin.list_candidates(str(tmp_path), current_run_dir, retention_seconds=3600)

    assert candidates == []


def test_results_sorted_oldest_first(tmp_path):
    """Multiple candidates are sorted by started ascending (oldest first)."""
    now = int(time.time())
    times = [now - 10000, now - 5000, now - 20000]
    for t in times:
        _make_run_dir(tmp_path, t, with_meta=True)
    current_run_dir = str(tmp_path / str(now))

    plugin = LocalCleanup()
    candidates = plugin.list_candidates(str(tmp_path), current_run_dir, retention_seconds=3600)

    started_vals = [c["started"] for c in candidates]
    assert started_vals == sorted(started_vals)


def test_recent_dir_not_returned(tmp_path):
    """Directory younger than retention_seconds is not a candidate."""
    now = int(time.time())
    recent_started = now - 1800  # 30 min old
    _make_run_dir(tmp_path, recent_started, with_meta=True)
    current_run_dir = str(tmp_path / str(now))

    plugin = LocalCleanup()
    candidates = plugin.list_candidates(str(tmp_path), current_run_dir, retention_seconds=3600)

    assert candidates == []


# ---------------------------------------------------------------------------
# parse_retention tests
# ---------------------------------------------------------------------------

def test_parse_retention_valid():
    assert parse_retention("24h") == 86400
    assert parse_retention("1h") == 3600
    assert parse_retention("168h") == 168 * 3600


def test_parse_retention_missing_h():
    with pytest.raises(Exception, match="must end with 'h'"):
        parse_retention("24")


def test_parse_retention_zero():
    with pytest.raises(Exception, match="retention must be >= 1h"):
        parse_retention("0h")


def test_parse_retention_negative():
    with pytest.raises(Exception, match="retention must be >= 1h"):
        parse_retention("-1h")


def test_parse_retention_non_integer():
    with pytest.raises(Exception, match="positive integer"):
        parse_retention("abch")


# ---------------------------------------------------------------------------
# run_cleanup timeout guard tests
# ---------------------------------------------------------------------------

def test_run_cleanup_skips_when_insufficient_time(tmp_path):
    """When less than 10 s remain, cleanup is skipped entirely."""
    now_val = 1710763200.0
    # deadline is now_val + 5, so remaining = 5 < 10 → skip
    ctx = make_ctx(
        result_dir=str(tmp_path / "current"),
        timeout_deadline=now_val + 5,
        config=make_config(report_retention=3600),
    )
    with patch("check_cep_mod.time.time", return_value=now_val):
        result = run_cleanup(LocalCleanup(), ctx)
    assert result.deleted == []
    assert result.skipped == []
    assert result.failed == []


def test_run_cleanup_stops_mid_loop(tmp_path):
    """Cleanup stops after processing some dirs when deadline is crossed mid-loop."""
    base_time = 1710763200.0
    retention = 3600

    # Create 3 old dirs
    for i in range(3):
        started = int(base_time) - 7200 - i * 100
        _make_run_dir(tmp_path, started, with_meta=True)

    current_run_dir = str(tmp_path / str(int(base_time)))

    # time.time() starts OK, then crosses deadline after first deletion
    call_count = [0]
    def fake_time():
        call_count[0] += 1
        # First call: within budget (for initial check)
        # Second call: within budget (first iteration check)
        # Third call: over budget (second iteration → skip remaining)
        if call_count[0] <= 2:
            return base_time
        return base_time + 10000  # way past deadline

    ctx = make_ctx(
        result_dir=current_run_dir,
        timeout_deadline=base_time + 15,
        config=make_config(report_retention=retention),
    )
    with patch("check_cep_mod.time.time", side_effect=fake_time):
        result = run_cleanup(LocalCleanup(), ctx)

    # At least some were skipped when deadline crossed
    assert len(result.skipped) > 0
