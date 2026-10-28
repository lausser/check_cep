"""scripts/check-versions.py: one Playwright source, VERSION == CEP_VERSION (spec 024 FR-014, R-3)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "check-versions.py"

ENV = "src/container/versions.env"
PKG = "src/container/package.json"
LOCK = "src/container/package-lock.json"


def _lock(version):
    return {"name": "x", "lockfileVersion": 3, "packages": {
        "": {"dependencies": {"@playwright/test": version}},
        "node_modules/@playwright/test": {"version": version},
    }}


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "src" / "container").mkdir(parents=True)
    files = {
        ENV: "# comment\nPLAYWRIGHT_VERSION=1.60.0\nPLAYWRIGHT_BASE_DIGEST=sha256:abc\n",
        PKG: json.dumps({"dependencies": {"@playwright/test": "1.60.0"}}),
        LOCK: json.dumps(_lock("1.60.0")),
        "VERSION": "0.23.0\n",
        "src/check_cep": 'import os\nCEP_VERSION = "0.23.0"\n',
    }
    for rel, text in files.items():
        (tmp_path / rel).write_text(text)
    return tmp_path


def _run(root):
    proc = subprocess.run([sys.executable, str(_SCRIPT), "--root", str(root)],
                          capture_output=True, text=True, timeout=30)
    assert "Traceback" not in proc.stderr, proc.stderr
    return proc.returncode, proc.stdout + proc.stderr


def test_consistent(tree):
    assert _run(tree)[0] == 0


def test_real_repository_is_consistent():
    assert _run(_SCRIPT.parent.parent)[0] == 0


def test_range_not_exact(tree):
    (tree / PKG).write_text(json.dumps({"dependencies": {"@playwright/test": "~1.60.0"}}))
    rc, out = _run(tree)
    assert rc == 1
    assert f"{PKG}: ~1.60.0" in out


def test_package_json_differs(tree):
    (tree / PKG).write_text(json.dumps({"dependencies": {"@playwright/test": "1.59.0"}}))
    rc, out = _run(tree)
    assert rc == 1
    line = next(line for line in out.splitlines() if line.startswith(PKG))
    assert "1.59.0" in line and ENV in line and "1.60.0" in line


def test_lockfile_differs(tree):
    (tree / LOCK).write_text(json.dumps(_lock("1.59.0")))
    rc, out = _run(tree)
    assert rc == 1
    assert f"{LOCK}: 1.59.0" in out


def test_version_differs_from_cep_version(tree):
    (tree / "VERSION").write_text("0.24.0\n")
    rc, out = _run(tree)
    assert rc == 1
    assert "src/check_cep" in out and "0.23.0" in out and "0.24.0" in out


def test_all_conflicts_listed(tree):
    (tree / PKG).write_text(json.dumps({"dependencies": {"@playwright/test": "1.59.0"}}))
    (tree / LOCK).write_text(json.dumps(_lock("1.58.0")))
    (tree / "VERSION").write_text("0.24.0\n")
    rc, out = _run(tree)
    assert rc == 1
    for rel in (PKG, LOCK, "src/check_cep"):
        assert rel in out


@pytest.mark.parametrize("rel,content", [
    (ENV, "PLAYWRIGHT_BASE_DIGEST=sha256:abc\n"),
    (ENV, None),
    (PKG, None),
    (PKG, "{not json"),
    (PKG, json.dumps({"dependencies": {}})),
    (LOCK, None),
    (LOCK, "{not json"),
    (LOCK, json.dumps({"packages": {}})),
    ("VERSION", None),
    ("VERSION", "\n"),
    ("src/check_cep", None),
    ("src/check_cep", "import os\n"),
    ("src/check_cep", 'CEP_VERSION = "0.23.0"\nCEP_VERSION = "0.23.0"\n'),
])
def test_broken_sources_named(tree, rel, content):
    path = tree / rel
    if content is None:
        path.unlink()
    else:
        path.write_text(content)
    rc, out = _run(tree)
    assert rc == 1
    assert rel in out
