"""scripts/release.py in throw-away git repos (spec 024 FR-020…025, contracts R-1/R-2/R-2b)."""
import datetime
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "release.py"
_spec = importlib.util.spec_from_file_location("release_mod", str(_SCRIPT))
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)

TODAY = datetime.date.today().isoformat()
REMOTE_COMMANDS = {"push", "fetch", "pull", "ls-remote", "clone", "remote"}

CHANGES = """# Changes

## Spec 024 — Professional Versioning

Body of 024.

---

## 0.23.0 — 2026-10-27 — Spec 023 — Layered Artifacts

Body of 023.

---

## Spec 022 — Older

Body of 022.
"""


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "src" / "container").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "config", "tag.gpgsign", "false")
    (repo / "VERSION").write_text("0.23.0\n")
    (repo / "CHANGES.md").write_text(CHANGES)
    (repo / "src" / "check_cep").write_text('import os\n\nCEP_VERSION = "0.23.0"\n\nprint(CEP_VERSION)\n')
    (repo / "src" / "container" / "versions.env").write_text("PLAYWRIGHT_VERSION=1.60.0\nPLAYWRIGHT_BASE_DIGEST=sha256:x\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "tag", "-a", "0.23.0", "-m", "check_cep 0.23.0")
    monkeypatch.chdir(repo)
    return repo


@pytest.fixture
def calls(monkeypatch):
    """Record every git invocation of release.py."""
    recorded = []
    real_run = subprocess.run

    def spy(argv, *a, **k):
        recorded.append(list(argv))
        return real_run(argv, *a, **k)
    monkeypatch.setattr(release.subprocess, "run", spy)
    return recorded


def state(repo):
    files = {p: (repo / p).read_text() for p in ("VERSION", "CHANGES.md", "src/check_cep")}
    return git(repo, "rev-parse", "HEAD"), git(repo, "tag", "--list"), files, git(repo, "status", "--porcelain")


def run(*argv):
    return release.main(list(argv))


def add_commit(repo, path, text, msg="change"):
    (repo / path).write_text(text)
    git(repo, "add", path)
    git(repo, "commit", "-q", "-m", msg)


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------

def test_prepare_spec_release(repo, calls, capsys):
    assert run("prepare", "0.24.0") == 0
    assert f"## 0.24.0 — {TODAY} — Spec 024 — Professional Versioning\n" in (repo / "CHANGES.md").read_text()
    assert (repo / "VERSION").read_text() == "0.24.0\n"
    assert 'CEP_VERSION = "0.24.0"' in (repo / "src" / "check_cep").read_text()
    assert git(repo, "log", "-1", "--format=%s") == "chore(release): 0.24.0"
    assert git(repo, "rev-list", "--count", "HEAD") == "2"
    assert git(repo, "cat-file", "-t", "0.24.0") == "tag"
    assert git(repo, "rev-parse", "0.24.0^{commit}") == git(repo, "rev-parse", "HEAD")
    assert git(repo, "status", "--porcelain") == ""
    assert "git push origin main 0.24.0" in capsys.readouterr().out
    for argv in calls:
        assert not REMOTE_COMMANDS & set(argv), argv
    body = git(repo, "log", "-1", "--format=%B") + git(repo, "tag", "-n99", "--list", "0.24.0")
    assert "Claude" not in body and "Co-Authored-By" not in body


def test_prepare_patch_release(repo):
    run("prepare", "0.24.0")
    add_commit(repo, "CHANGES.md", (repo / "CHANGES.md").read_text().replace(
        "# Changes\n", "# Changes\n\n## 0.24.1 — Unreleased — Playwright v1.64.0\n\nBump.\n\n---\n"))
    assert run("prepare", "0.24.1") == 0
    assert f"## 0.24.1 — {TODAY} — Playwright v1.64.0\n" in (repo / "CHANGES.md").read_text()
    assert "Unreleased" not in (repo / "CHANGES.md").read_text()


def test_prepare_rc_then_final(repo):
    assert run("prepare", "0.24.0-rc.1") == 0
    assert f"## 0.24.0-rc.1 — {TODAY} — Spec 024 — Professional Versioning\n" in (repo / "CHANGES.md").read_text()
    assert run("prepare", "0.24.0") == 0
    text = (repo / "CHANGES.md").read_text()
    assert f"## 0.24.0 — {TODAY} — Spec 024 — Professional Versioning\n" in text
    assert "0.24.0-rc.1 —" not in text


def test_prepare_default_proposal_needs_yes(repo, capsys):
    before = state(repo)
    assert run("prepare") == 1
    assert "proposed version: 0.24.0" in capsys.readouterr().out
    assert state(repo) == before
    assert run("prepare", "--yes") == 0
    assert git(repo, "describe", "--exact-match", "HEAD") == "0.24.0"


def test_prepare_dry_run_changes_nothing(repo, capsys):
    before = state(repo)
    assert run("prepare", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "proposed version: 0.24.0" in out and "dry run" in out
    assert run("prepare", "0.24.0", "--dry-run") == 0
    assert state(repo) == before


def test_version_file_whitespace_is_stripped(repo):
    add_commit(repo, "VERSION", "  0.23.0  \n\n")
    assert run("prepare", "0.24.0") == 0


def _dirty(repo):
    (repo / "src" / "check_cep").write_text('CEP_VERSION = "0.23.0"\n# dirty\n')


def _untracked(repo):
    (repo / "new.txt").write_text("x")


def _branch(repo):
    git(repo, "checkout", "-q", "-b", "feature")


def _tag_exists(repo):
    git(repo, "tag", "-a", "0.24.0", "-m", "x")


def _no_chapter(repo):
    add_commit(repo, "CHANGES.md", CHANGES.replace("## Spec 024 — Professional Versioning", "## Something"))


def _no_stamp(repo):
    add_commit(repo, "src/check_cep", "import os\n")


def _two_stamps(repo):
    add_commit(repo, "src/check_cep", 'CEP_VERSION = "0.23.0"\nCEP_VERSION = "0.23.0"\n')


def _no_version_file(repo):
    git(repo, "rm", "-q", "VERSION")
    git(repo, "commit", "-q", "-m", "rm")


def _empty_version_file(repo):
    add_commit(repo, "VERSION", "\n")


@pytest.mark.parametrize("setup,version,message", [
    (_dirty, "0.24.0", "not clean"),
    (_untracked, "0.24.0", "not clean"),
    (_branch, "0.24.0", "main"),
    (_tag_exists, "0.24.0", "already exists"),
    (None, "0.23.0", "not greater"),
    (None, "0.22.5", "not greater"),
    (None, "0.23.0-rc.1", "not greater"),
    (None, "v0.24.0", "invalid version"),
    (None, "0.24", "invalid version"),
    (None, "0.024.0", "invalid version"),
    (None, "0.24.00", "invalid version"),
    (None, "0.24.0-rc.01", "invalid version"),
    (_no_chapter, "0.24.0", "no chapter"),
    (None, "0.24.1", "no chapter"),
    (_no_stamp, "0.24.0", "exactly one"),
    (_two_stamps, "0.24.0", "exactly one"),
    (_no_version_file, "0.24.0", "VERSION"),
    (_empty_version_file, "0.24.0", "VERSION"),
])
def test_prepare_aborts_without_changes(repo, capsys, setup, version, message):
    if setup:
        setup(repo)
    head, tags = git(repo, "rev-parse", "HEAD"), git(repo, "tag", "--list")
    files = {p: (repo / p).read_text() for p in ("CHANGES.md", "src/check_cep") if (repo / p).exists()}
    status = git(repo, "status", "--porcelain")
    assert run("prepare", version) == 1
    assert message in capsys.readouterr().err
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "tag", "--list") == tags
    assert {p: (repo / p).read_text() for p in files} == files
    assert git(repo, "status", "--porcelain") == status


def test_tag_failure_rolls_back_commit(repo, monkeypatch, capsys):
    """A failed `git tag` must not leave the release commit behind (review C03)."""
    before = state(repo)
    real_git = release.git

    def failing_git(*args, **kwargs):
        if args and args[0] == "tag":
            raise release.ReleaseError("git tag failed: simulated")
        return real_git(*args, **kwargs)
    monkeypatch.setattr(release, "git", failing_git)
    assert run("prepare", "0.24.0") == 1
    assert "simulated" in capsys.readouterr().err
    assert state(repo) == before


def test_not_a_git_repo(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert run("prepare", "0.24.0") == 1
    assert "not inside a git repository" in capsys.readouterr().err


def test_cli_entry_point(repo):
    proc = subprocess.run([sys.executable, str(_SCRIPT), "prepare", "--dry-run"],
                          cwd=repo, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "0.24.0" in proc.stdout


# ---------------------------------------------------------------------------
# notes
# ---------------------------------------------------------------------------

def test_notes(repo, capsys):
    assert run("notes", "0.23.0") == 0
    assert capsys.readouterr().out == "Body of 023.\n"


def test_notes_after_release(repo, capsys):
    run("prepare", "0.24.0")
    capsys.readouterr()
    assert run("notes", "0.24.0") == 0
    assert capsys.readouterr().out == "Body of 024.\n"


def test_notes_absent(repo, capsys):
    assert run("notes", "0.99.0") == 1
    assert run("notes", "0.23") == 1


# ---------------------------------------------------------------------------
# aliases
# ---------------------------------------------------------------------------

def _tags(repo, *names):
    for name in names:
        git(repo, "tag", "-a", name, "-m", name)


def _aliases(capsys, version):
    rc = run("aliases", version)
    return rc, capsys.readouterr().out.split()


def test_aliases_newest_release(repo, calls, capsys):
    _tags(repo, "0.24.0", "0.12", "0.6", "nightly")
    assert _aliases(capsys, "0.24.0") == (0, ["0.24.0", "0.24.0-pw1.60.0", "0.24", "latest"])
    for argv in calls:
        assert not REMOTE_COMMANDS & set(argv), argv


def test_aliases_older_line_patch(repo, capsys):
    _tags(repo, "0.24.0", "0.23.2")
    assert _aliases(capsys, "0.23.2") == (0, ["0.23.2", "0.23.2-pw1.60.0", "0.23"])


def test_aliases_rc(repo, capsys):
    _tags(repo, "0.24.0", "0.25.0-rc.1")
    assert _aliases(capsys, "0.25.0-rc.1") == (0, ["0.25.0-rc.1", "0.25.0-rc.1-pw1.60.0"])


def test_aliases_rerun_after_newer_patch(repo, capsys):
    _tags(repo, "0.24.0", "0.24.1")
    assert _aliases(capsys, "0.24.0") == (0, ["0.24.0", "0.24.0-pw1.60.0"])


def test_aliases_final_beats_its_rc(repo, capsys):
    _tags(repo, "0.25.0-rc.1", "0.25.0")
    assert _aliases(capsys, "0.25.0") == (0, ["0.25.0", "0.25.0-pw1.60.0", "0.25", "latest"])


@pytest.mark.parametrize("version", ["v0.24.0", "0.24", "latest", "0.24.0-beta.1", "0.01.0"])
def test_aliases_invalid(repo, capsys, version):
    _tags(repo, version)
    assert run("aliases", version) == 1


def test_aliases_requires_local_tag(repo, capsys):
    assert run("aliases", "0.24.0") == 1
    assert "not a local git tag" in capsys.readouterr().err
