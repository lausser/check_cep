"""Release version source and `check_cep --version` (spec 024 FR-010, FR-011)."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import _cep_mod as cep

_ROOT = Path(__file__).parent.parent.parent
_PLUGIN = _ROOT / "src" / "check_cep"
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-rc\.\d+)?$")


def _version():
    return (_ROOT / "VERSION").read_text().strip()


def test_version_file_format():
    assert _VERSION_RE.match(_version())


def test_cep_version_matches_version_file():
    assert cep.CEP_VERSION == _version()


def test_exactly_one_cep_version_line():
    lines = [line for line in _PLUGIN.read_text().splitlines()
             if line.startswith('CEP_VERSION = "')]
    assert len(lines) == 1, lines


@pytest.mark.parametrize("args", [["--version"], ["--version", "--bogus"], ["--bogus", "--version"]])
def test_version_option(args):
    proc = subprocess.run([sys.executable, str(_PLUGIN), *args],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == f"check_cep {_version()}\n"
