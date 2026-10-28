""".github/workflows/image.yml structure (spec 024 FR-030…037, contracts W-1)."""
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_WORKFLOW = Path(__file__).parent.parent.parent / ".github" / "workflows" / "image.yml"
RELEASE_REGEX = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-rc\.(0|[1-9][0-9]*))?$"


@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(_WORKFLOW.read_text())


@pytest.fixture(scope="module")
def jobs(wf):
    return wf["jobs"]


def _triggers(wf):
    # PyYAML (YAML 1.1) reads the bare key `on` as boolean True.
    return wf.get("on", wf.get(True))


def _runs(job):
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_triggers(wf):
    on = _triggers(wf)
    assert "pull_request" in on
    assert on["push"]["branches"] == ["main"]
    assert on["push"]["tags"]


def test_default_permissions_read_only(wf):
    assert wf["permissions"] == {"contents": "read"}


def test_gate(jobs):
    gate = jobs["gate"]
    assert "refs/tags/" in gate["if"]
    assert set(gate["outputs"]) == {"release_tag", "prerelease"}
    assert RELEASE_REGEX in _runs(gate)


def test_publish(jobs):
    publish = jobs["publish"]
    assert {"test", "gate"} <= set(publish["needs"])
    assert "needs.gate.outputs.release_tag == 'true'" in publish["if"]
    assert publish["permissions"]["contents"] == "write"
    assert publish["permissions"]["packages"] == "write"
    assert publish["concurrency"]["group"] == "ghcr-publish"
    assert publish["concurrency"]["cancel-in-progress"] is False
    checkout = next(s for s in publish["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0
    runs = _runs(publish)
    repair = next(s for s in publish["steps"] if s.get("name", "").startswith("Repair"))
    assert "PW_PRESENT" in repair["run"], "an existing immutable -pw tag must not be rewritten"
    assert "^{commit}" in runs and "GITHUB_SHA" in runs
    assert "scripts/release.py aliases" in runs
    assert "gh release create" in runs and "--verify-tag" in runs
    assert publish["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_no_other_job_writes_or_publishes(jobs):
    for name, job in jobs.items():
        if name == "publish":
            continue
        assert "permissions" not in job or all(v == "read" for v in job["permissions"].values()), name
        assert job.get("concurrency", {}).get("group") != "ghcr-publish", name
        for step in job["steps"]:
            assert step.get("with", {}).get("push") in (None, False), name


def test_actions_pinned_by_sha(jobs):
    for name, job in jobs.items():
        for step in job["steps"]:
            uses = step.get("uses")
            if uses and not uses.startswith("./"):
                assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", uses), (name, uses)


def test_no_git_push(jobs):
    for job in jobs.values():
        assert "git push" not in _runs(job)


@pytest.mark.parametrize("tag,ok", [("0.24.0", True), ("0.25.0-rc.1", True), ("10.0.12", True),
                                    ("0.01.0", False), ("0.24.00", False), ("0.24.0-rc.01", False),
                                    ("v0.24.0", False), ("0.24", False), ("nightly", False)])
def test_gate_regex(tag, ok):
    """The gate accepts exactly what scripts/release.py accepts (review R01)."""
    assert bool(re.fullmatch(RELEASE_REGEX, tag)) is ok
