"""Layered test artifacts end to end (spec 023 US2/US3/US4/US5/US6).

Each layer is staged as a copy under tmp_path, so the repository fixtures are
never mounted directly and the "sources unchanged" check sees exact copies.
"""
import hashlib
import json
import os
import re
import shutil
import tarfile
from pathlib import Path

import pytest

from conftest import _FIXTURES_DIR, run_check_cep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(r"\d+(\.\d+)?\s?(ms|s)\b")
_EPOCH_RE = re.compile(r"\b1\d{9}\b")
# Lines check_cep writes to stderr; run_check_cep() appends stderr to the output.
_STDERR_NOISE = ("WARNING: --test-dir is deprecated",)


def normalize_check_output(output, result_dir=None):
    """Return (status text, long output) with run-specific values neutralized.

    Durations become <t>, the result dir <rundir>, epoch timestamps <epoch>.
    Nothing else is removed (besides check_cep's own stderr warnings, which
    are not part of the Nagios output).
    """
    lines = [l for l in output.splitlines() if not l.startswith(_STDERR_NOISE)]
    first = lines[0].split(" | ", 1)[0] if lines else ""
    long_output = "\n".join(lines[1:])

    def clean(text):
        if result_dir:
            text = text.replace(str(result_dir), "<rundir>")
        text = _EPOCH_RE.sub("<epoch>", text)
        return _DURATION_RE.sub("<t>", text)
    return clean(first), clean(long_output)


def perfdata_labels(output):
    first = output.splitlines()[0] if output else ""
    if " | " not in first:
        return []
    return re.findall(r"'([^']*)'=", first.split(" | ", 1)[1])


def stage(tmp_path, *fixtures, name=None):
    """Copy one or more fixtures (merged in order) into a fresh dir."""
    dest = tmp_path / (name or "_".join(fixtures))
    for fixture in fixtures:
        shutil.copytree(_FIXTURES_DIR / fixture, dest, dirs_exist_ok=True)
    return dest


def make_tgz(src, path):
    with tarfile.open(path, "w:gz") as tar:
        tar.add(str(src), arcname=".")
    return path


def tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*")):
        digest.update(str(path.relative_to(root)).encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def run_layers(result_dir, *layers, extra=(), env=None):
    args = []
    for layer in layers:
        args += ["--test-artifact", str(layer)]
    return run_check_cep(None, result_dir, extra_args=args + list(extra), env=env)


def test_normalize_check_output_helper():
    a = "OK - test x succeeded | 'a'=12ms 'duration'=3s\n__Stdout x__\ntook 2.5s"
    b = "OK - test x succeeded | 'a'=99ms 'duration'=5s\n__Stdout x__\ntook 0.1s"
    c = "OK - test x succeeded | 'a'=99ms\n__Stdout x__\ntook 0.1s really"
    assert normalize_check_output(a) == normalize_check_output(b)
    assert normalize_check_output(b) != normalize_check_output(c)


# ---------------------------------------------------------------------------
# US2: compose a check from ordered layers
# ---------------------------------------------------------------------------

@pytest.fixture
def shared_and_service(tmp_path):
    return stage(tmp_path, "layers_shared"), stage(tmp_path, "layers_service")


def test_dir_plus_dir(test_env, shared_and_service):
    output, code = run_layers(test_env["result_dir"], *shared_and_service)
    assert code == 0, output
    assert output.startswith("OK -")


@pytest.mark.parametrize("archive_first", [False, True])
def test_dir_and_tgz(tmp_path, test_env, shared_and_service, archive_first):
    shared, service = shared_and_service
    if archive_first:
        layers = (make_tgz(shared, tmp_path / "shared.tgz"), service)
    else:
        layers = (shared, make_tgz(service, tmp_path / "service.tgz"))
    output, code = run_layers(test_env["result_dir"], *layers)
    assert code == 0, output


def test_override_is_logged(test_env, shared_and_service):
    output, code = run_layers(test_env["result_dir"], *shared_and_service, extra=["--debug"])
    assert code == 0, output
    assert "override: playwright.config.ts layer 2 wins over layer 1" in output


def test_sources_unchanged_and_tree_writable(test_env, shared_and_service):
    before = [tree_digest(layer) for layer in shared_and_service]
    output, code = run_layers(test_env["result_dir"], *shared_and_service)
    assert code == 0, output  # the test wrote written-by-test.txt into its cwd
    assert [tree_digest(layer) for layer in shared_and_service] == before
    assert not any((layer / "written-by-test.txt").exists() for layer in shared_and_service)


def test_three_layers_tests_only_in_middle(tmp_path, test_env):
    extra = tmp_path / "final"
    (extra / "notes").mkdir(parents=True)
    (extra / "notes" / "readme.md").write_text("override layer without tests")
    output, code = run_layers(test_env["result_dir"], stage(tmp_path, "layers_shared"),
                              stage(tmp_path, "layers_service"), extra)
    assert code == 0, output


def test_no_tests_after_merge(tmp_path, test_env):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "readme.md").write_text("no tests here")
    output, code = run_layers(test_env["result_dir"], stage(tmp_path, "layers_nested_shared"), docs)
    assert code == 3, output
    assert "no *.test.ts/*.test.js found after merging 2 layer(s)" in output


def test_type_conflict(tmp_path, test_env):
    first = tmp_path / "first"
    first.mkdir()
    (first / "functions").write_text("a file")
    output, code = run_layers(test_env["result_dir"], first, stage(tmp_path, "layers_shared"))
    assert code == 3, output
    assert output.startswith("UNKNOWN -")
    assert "type conflict" in output


def test_zip_rejected_before_container(tmp_path, test_env):
    z = tmp_path / "tests.zip"
    z.write_bytes(b"PK\x03\x04")
    output, code = run_layers(test_env["result_dir"], z)
    assert code == 3, output
    assert "must be a directory or a .tgz/.tar.gz file" in output


def test_test_meta_lists_layers(tmp_path, test_env, shared_and_service):
    shared, service = shared_and_service
    tgz = make_tgz(service, tmp_path / "service.tgz")
    output, code = run_layers(test_env["result_dir"], shared, tgz)
    assert code == 0, output
    meta = json.loads((test_env["result_dir"] / "test-meta.json").read_text())
    assert meta["layers"] == [
        {"position": 1, "path": str(shared), "type": "directory"},
        {"position": 2, "path": str(tgz), "type": "archive"},
    ]


def test_s3_with_two_artifacts(test_env):
    output, code = run_check_cep(None, test_env["result_dir"], extra_args=[
        "--test-source", "s3", "--test-artifact", "/b/a.tgz", "--test-artifact", "/b/c.tgz",
        "--s3-endpoint", "http://s3.invalid", "--aws-access-key-id", "k",
        "--aws-secret-access-key", "s"])
    assert code == 3, output
    assert "exactly one" in output


@pytest.mark.parametrize("second_as_tgz", [False, True])
def test_nested_layout_parity(tmp_path, test_env, second_as_tgz):
    """SC-004: today's nested layout gives the same result layered and merged."""
    shared = stage(tmp_path, "layers_nested_shared")
    case = stage(tmp_path, "layers_nested_case")
    if second_as_tgz:
        case = make_tgz(case, tmp_path / "case.tgz")
    merged = stage(tmp_path, "layers_nested_shared", "layers_nested_case", name="merged")

    results = {}
    for way, args in (("layered", ["--test-artifact", str(shared), "--test-artifact", str(case)]),
                      ("artifact", ["--test-artifact", str(merged)]),
                      ("testdir", ["--test-dir", str(merged)])):
        result_dir = tmp_path / f"res_{way}"
        result_dir.mkdir(mode=0o777)
        output, code = run_check_cep(None, result_dir, extra_args=args + ["--debug"])
        assert "run mode: discovery (config EXT/Shop/prod/playwright.config.ts, " \
               "workdir EXT/Shop/prod)" in output, output
        plain, plain_code = run_check_cep(None, result_dir, extra_args=args)
        results[way] = (plain_code, normalize_check_output(plain, result_dir), perfdata_labels(plain))
    assert results["layered"][0] == 0, results
    assert results["layered"] == results["artifact"] == results["testdir"]


def test_discovery_warns_about_ignored_dirs(tmp_path, test_env):
    tree = tmp_path / "two"
    for sub in ("a", "b"):
        shutil.copytree(_FIXTURES_DIR / "tc_pass", tree / sub)
        (tree / sub / "playwright.config.ts").write_text(
            (_FIXTURES_DIR / "layers_shared" / "playwright.config.ts").read_text())
    output, code = run_layers(test_env["result_dir"], tree, extra=["--debug"])
    assert code == 0, output
    assert "WARNING: test files also found in b; ignored" in output


# ---------------------------------------------------------------------------
# US5: existing setups keep working (FR-060)
# ---------------------------------------------------------------------------

_BASELINE_DIR = (Path(__file__).parent.parent.parent / "specs" / "023-layered-artifacts-secrets"
                 / "baseline")


@pytest.mark.parametrize("fixture", ["tc_pass", "tc_fail"])
def test_single_layer_parity(tmp_path, write_playwright_config, fixture):
    """--test-dir, --test-artifact <dir> and --test-artifact <tgz> agree, and
    match the pre-spec-023 baseline (T003) when it is present."""
    src = stage(tmp_path, fixture)
    write_playwright_config(src)
    tgz = make_tgz(src, tmp_path / f"{fixture}.tgz")
    results = {}
    for way, args in (("testdir", ["--test-dir", str(src)]),
                      ("artdir", ["--test-artifact", str(src)]),
                      ("arttgz", ["--test-artifact", str(tgz)])):
        result_dir = tmp_path / f"res_{way}"
        result_dir.mkdir(mode=0o777)
        output, code = run_check_cep(None, result_dir, extra_args=args)
        results[way] = (code, normalize_check_output(output, result_dir), perfdata_labels(output))
    assert results["testdir"] == results["artdir"] == results["arttgz"], results

    if not _BASELINE_DIR.is_dir():
        pytest.skip("no T003 baseline in specs/023-layered-artifacts-secrets/baseline")
    for way, (code, (first, _), labels) in results.items():
        baseline = dict(line.split(": ", 1) for line in
                        (_BASELINE_DIR / f"{fixture}_{way}.txt").read_text().splitlines()[:3]
                        if ": " in line)
        assert code == int(baseline["exit"]), way
        assert first == normalize_check_output(baseline["first"])[0], way
        assert labels == baseline.get("labels", "").split(), way


# ---------------------------------------------------------------------------
# US3: standard Playwright project layout (FR-040…FR-046, FR-050/051)
# ---------------------------------------------------------------------------

def _stats(result_dir):
    return json.loads((Path(result_dir) / "steps.json").read_text())["stats"]


def test_project_root_two_layers(tmp_path, test_env):
    config, tests = stage(tmp_path, "proj_config"), stage(tmp_path, "proj_tests")
    output, code = run_layers(test_env["result_dir"], config, tests, extra=["--debug"])
    assert code == 0, output
    assert "run mode: project-root (config playwright.config.ts, workdir .)" in output
    assert _stats(test_env["result_dir"])["expected"] == 3  # setup + two specs
    labels = perfdata_labels(output)
    assert len(labels) == len(set(labels)), labels

    # SC-004: the same tree as one directory gives the same result
    merged = stage(tmp_path, "proj_config", "proj_tests", name="merged")
    results = {}
    for way, layers in (("layered", (config, tests)), ("single", (merged,))):
        result_dir = tmp_path / f"res_{way}"
        result_dir.mkdir(mode=0o777)
        out, rc = run_layers(result_dir, *layers)
        results[way] = (rc, normalize_check_output(out, result_dir), perfdata_labels(out))
    assert results["layered"] == results["single"], results


def test_project_root_matched_no_tests(tmp_path, test_env):
    output, code = run_layers(test_env["result_dir"], stage(tmp_path, "proj_empty"))
    assert code == 3, output
    assert "matched no tests" in output


def test_project_root_failure_is_critical(tmp_path, test_env):
    tests = stage(tmp_path, "proj_tests")
    spec = tests / "tests" / "login.spec.ts"
    spec.write_text(spec.read_text().replace("toBe(expectedBaseURL)", "toBe('http://other/')"))
    output, code = run_layers(test_env["result_dir"], stage(tmp_path, "proj_config"), tests)
    assert code == 2, output
    assert output.startswith("CRITICAL -")


def test_project_root_syntax_error_is_critical(tmp_path, test_env):
    tests = stage(tmp_path, "proj_tests")
    (tests / "tests" / "login.spec.ts").write_text("import { test } from '@playwright/test';\ntest('x', () => {\n")
    output, code = run_layers(test_env["result_dir"], stage(tmp_path, "proj_config"), tests)
    assert code == 2, output
    assert output.startswith("CRITICAL -")
    assert "matched no tests" not in output


# slowMo must take effect (FR-045; user decision 2026-10-26: no skip path).
# "Headed" without a host display uses --vnc: the container starts its own
# X server, which needs no DISPLAY on the host.
@pytest.mark.parametrize("fixture,tests_per_run", [("tc_slowmo", 1), ("proj_slowmo", 2)])
@pytest.mark.parametrize("display", ["headless", "vnc"])
def test_slowmo_takes_effect(tmp_path, monkeypatch, fixture, tests_per_run, display):
    tree = stage(tmp_path, fixture)
    for name in ("DISPLAY", "WAYLAND_DISPLAY", "CEP_SLOW_MO", "CEP_SPECTATE"):
        monkeypatch.delenv(name, raising=False)
    extra = ["--vnc", "--timeout", "120"] if display == "vnc" else []
    # The control run without CEP_SLOW_MO proves the probe tells them apart.
    for slow_mo in ("200", None):
        result_dir = tmp_path / f"res_{slow_mo}"
        result_dir.mkdir(mode=0o777)
        output, code = run_check_cep(
            None, result_dir, env={"CEP_SLOW_MO": slow_mo} if slow_mo else None,
            extra_args=["--test-artifact", str(tree),
                        "--environ", f"CEP_SLOW_MO_EXPECT=slowmo-{slow_mo or 0}", *extra])
        assert code == 0, output
        assert _stats(result_dir)["expected"] == tests_per_run


# ---------------------------------------------------------------------------
# US6: the debug shell sees exactly what the check runs (FR-032)
# ---------------------------------------------------------------------------

def _shell_argv(tmp_path, layers, script):
    """check_cep's real --shell argv, with a non-interactive -c script."""
    from conftest import CEP_IMAGE, _mod as cep
    from test_modes import _CONFIG_DEFAULTS
    result_dir = tmp_path / "res_shell"
    result_dir.mkdir(mode=0o777, exist_ok=True)
    config = cep.RunConfig(**{**_CONFIG_DEFAULTS, "image": CEP_IMAGE, "shell": True,
                              "result_dir": str(result_dir), "test_artifacts": tuple(map(str, layers)),
                              "environ": [("CEP_SHELL_PROBE", "shellprobe-on")]})
    resolved = tuple(cep.resolve_layers(config, str(tmp_path), "testhost", "shell", "0"))
    ctx = cep.RunContext(hostname="testhost", servicedescription="shell", testname="testhost/shell",
                         testident="testhost__shell", container_name="testhost_shell_probe",
                         start_time=0.0, started_str="0", timeout_deadline=0.0,
                         result_dir=str(result_dir), omd_root=str(tmp_path), pid_file="/tmp/x.pid",
                         layers=resolved, config=config)
    env_vars = cep.build_env_vars(ctx)
    argv = cep.build_podman_command(ctx, "podman", env_vars)
    assert argv[-2] == "-c"
    argv = [tok for tok in argv if tok != "--tty"]
    return argv[:-1] + [script], {**os.environ, **env_vars}


def test_shell_shows_merged_tree(tmp_path):
    import subprocess
    shared, service = stage(tmp_path, "layers_shared"), stage(tmp_path, "layers_service")
    tgz = make_tgz(service, tmp_path / "service.tgz")
    argv, env = _shell_argv(tmp_path, (shared, tgz), "python3 /home/pwuser/run.py --prepare-only "
                            "&& ls -A /home/pwuser/tests && printenv CEP_SHELL_PROBE")
    proc = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=120,
                          stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for name in ("functions", ".npmrc", "login.test.ts", "shellprobe-on"):
        assert name in proc.stdout.split(), proc.stdout

    conflict = tmp_path / "conflict"
    conflict.mkdir()
    (conflict / "functions").write_text("a file")
    argv, env = _shell_argv(tmp_path, (conflict, shared), "python3 /home/pwuser/run.py --prepare-only "
                            "&& ls -A /home/pwuser/tests")
    proc = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=120,
                          stdin=subprocess.DEVNULL)
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert "type conflict" in proc.stdout
    assert ".npmrc" not in proc.stdout


# ---------------------------------------------------------------------------
# US4: one Naemon command for all services (FR-031)
# ---------------------------------------------------------------------------

def test_templated_layer(tmp_path, test_env, write_playwright_config):
    service_dir = tmp_path / "root" / "testhost" / "pytest_test"
    shutil.copytree(_FIXTURES_DIR / "tc_pass", service_dir)
    write_playwright_config(service_dir)
    template = f"{tmp_path}/root/%h/%s"
    output, code = run_layers(test_env["result_dir"], template)
    assert code == 0, output

    output, code = run_check_cep(None, test_env["result_dir"], extra_args=[
        "--test-artifact", template, "--service-description", "Nope"])
    assert code == 3, output
    assert f"{tmp_path}/root/testhost/Nope" in output
