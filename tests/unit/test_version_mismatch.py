"""Best-effort plugin/image version mismatch diagnostic (spec 024 FR-016, C-5)."""
import json
import logging

import pytest

from conftest import _cep_mod as cep

log_version_mismatch = cep.log_version_mismatch


def _write_meta(tmp_path, meta):
    (tmp_path / "test-meta.json").write_text(json.dumps(meta))


def _mismatch_lines(caplog):
    return [r.getMessage() for r in caplog.records if "version mismatch" in r.getMessage()]


def test_mismatch_logged_at_debug(tmp_path, caplog):
    _write_meta(tmp_path, {"versions": {"plugin": "0.24.0", "image": "0.23.0", "playwright": "1.60.0"}})
    with caplog.at_level(logging.DEBUG, logger="check_cep"):
        log_version_mismatch(str(tmp_path))
    assert _mismatch_lines(caplog) == ["version mismatch: plugin 0.24.0, image 0.23.0"]
    assert all(r.levelno == logging.DEBUG for r in caplog.records)


@pytest.mark.parametrize("versions", [
    {"plugin": "0.24.0", "image": "0.24.0", "playwright": "1.60.0"},
    {"plugin": "0.24.0", "image": "unknown", "playwright": "unknown"},
    {"plugin": "unknown", "image": "0.24.0", "playwright": "1.60.0"},
    {"plugin": "0.24.0"},
])
def test_no_log_when_equal_or_unknown(tmp_path, caplog, versions):
    _write_meta(tmp_path, {"versions": versions})
    with caplog.at_level(logging.DEBUG, logger="check_cep"):
        log_version_mismatch(str(tmp_path))
    assert _mismatch_lines(caplog) == []


@pytest.mark.parametrize("content", [None, "{not json", "[]", '{"versions": "x"}', '{"started": "1"}',
                                     '{"versions": {"plugin": 1, "image": ["x"]}}'])
def test_unreadable_meta_never_raises(tmp_path, caplog, content):
    if content is not None:
        (tmp_path / "test-meta.json").write_text(content)
    with caplog.at_level(logging.DEBUG, logger="check_cep"):
        log_version_mismatch(str(tmp_path))
    assert _mismatch_lines(caplog) == []


def test_missing_result_dir_never_raises(tmp_path):
    log_version_mismatch(str(tmp_path / "nope"))
