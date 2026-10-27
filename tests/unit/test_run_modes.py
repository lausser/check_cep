"""Unit tests for the container dispatcher run.py (spec 023).

Covers the exit-code protocol (normalize_exit, CEPUNKNOWN, crash safety;
contracts/container-io.md §6), the FR-053 stderr helpers, and run-mode
selection.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from conftest import _cep_mod as cep

_RUN_PY = Path(__file__).parent.parent.parent / "src" / "container" / "image" / "run.py"
_spec = importlib.util.spec_from_file_location("run_mod", str(_RUN_PY))
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)

from test_exit_status import STDIO_CASES, VISIBLE_CASES  # noqa: E402


def _markers(text):
    return text.count("CEPUNKNOWN [[[")


# ---------------------------------------------------------------------------
# normalize_exit — one test per table row (contracts/container-io.md §6)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (0, (0, None)),
    (150, (1, None)),
    (124, (2, None)),
    (137, (2, None)),
    (1, (2, None)),
    (2, (2, None)),
    (3, (2, None)),
    (255, (2, None)),
])
def test_normalize_exit_table(raw, expected):
    assert run.normalize_exit(raw) == expected


@pytest.mark.parametrize("raw", [125, 126, 127])
def test_normalize_exit_not_started(raw):
    assert run.normalize_exit(raw) == (3, f"playwright could not be started (exit {raw})")


def test_raw_3_never_passes_through():
    assert run.normalize_exit(3) == (2, None)


def test_emit_unknown(capsys):
    assert run.emit_unknown("a\nb") == 3
    assert capsys.readouterr().out == "CEPUNKNOWN [[[a b]]]\n"


# ---------------------------------------------------------------------------
# FR-053 helpers: identical to the host implementation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entry,expected", STDIO_CASES)
def test_stdio_text_matches_host(entry, expected):
    assert run.stdio_text(entry) == expected == cep.stdio_text(entry)


@pytest.mark.parametrize("report,expected", VISIBLE_CASES)
def test_report_has_visible_stderr_matches_host(report, expected):
    assert run.report_has_visible_stderr(report) is expected
    assert cep.report_has_visible_stderr(report) is expected


# ---------------------------------------------------------------------------
# main(): normalization applied after Playwright
# ---------------------------------------------------------------------------

class _Plugin:
    def __init__(self):
        self.published = []

    def acquire_tests(self, test_name, dest_path, deadline=None):
        Path(dest_path).mkdir(parents=True, exist_ok=True)
        (Path(dest_path) / "a.test.ts").write_text("// t")

    def publish_results(self, test_name, results_path, nagios_state):
        self.published.append(nagios_state)


@pytest.fixture
def fake_container(tmp_path, monkeypatch):
    """Run run.main() against tmp_path as $HOME with fake plugins."""
    (tmp_path / "results").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TEST_ARTIFACT_LAYERS", json.dumps([]))
    plugin = _Plugin()
    monkeypatch.setattr(run, "load_plugin", lambda registry, value, axis: None if axis == "LOGGING" else plugin)

    def go(raw_rc, steps=None):
        def fake_playwright(workdir, results_path, *a, **k):
            if steps is not None:
                (Path(results_path) / "steps.json").write_text(json.dumps(steps))
            return raw_rc
        monkeypatch.setattr(run, "run_playwright", fake_playwright)
        rc = run.main()
        meta = json.loads((tmp_path / "results" / "test-meta.json").read_text())
        return rc, meta, plugin
    return go


@pytest.mark.parametrize("raw", [125, 126, 127])
def test_main_marks_playwright_not_started(fake_container, capsys, raw):
    rc, meta, plugin = fake_container(raw)
    assert rc == 3
    out = capsys.readouterr().out
    assert _markers(out) == 1
    assert f"playwright could not be started (exit {raw})" in out
    assert meta["status"] == "UNKNOWN"
    assert plugin.published == [3]


def test_main_visible_stderr_raises_to_warning(fake_container):
    steps = {"suites": [{"specs": [{"tests": [{"results": [{"stderr": [{"text": "slow"}]}]}]}]}]}
    rc, meta, _ = fake_container(0, steps)
    assert rc == 1
    assert meta["status"] == "WARNING"


def test_main_empty_stderr_stays_ok(fake_container):
    steps = {"suites": [{"specs": [{"tests": [{"results": [{"stderr": [{"buffer": ""}]}]}]}]}]}
    rc, meta, _ = fake_container(0, steps)
    assert rc == 0


def test_main_failure_not_raised(fake_container):
    steps = {"suites": [{"specs": [{"tests": [{"results": [{"stderr": [{"text": "x"}]}]}]}]}]}
    rc, _, _ = fake_container(1, steps)
    assert rc == 2


# ---------------------------------------------------------------------------
# run_guarded: crash safety (constitution 2.2.0, Principle IV)
# ---------------------------------------------------------------------------

def test_guarded_exception(monkeypatch, capsys):
    monkeypatch.setattr(run, "main", lambda **k: (_ for _ in ()).throw(ValueError("bad")))
    assert run.run_guarded([]) == 3
    out = capsys.readouterr().out
    assert _markers(out) == 1
    assert "run.py failed: ValueError('bad')" in out


def test_guarded_stray_sys_exit_1(monkeypatch, capsys):
    monkeypatch.setattr(run, "main", lambda **k: sys.exit(1))
    assert run.run_guarded([]) == 3
    assert _markers(capsys.readouterr().out) == 1


def test_guarded_unknown_option(capsys):
    assert run.run_guarded(["--no-such-option"]) == 3
    assert _markers(capsys.readouterr().out) == 1


@pytest.mark.parametrize("code", [0, 1, 2])
def test_guarded_return_value_passes(monkeypatch, capsys, code):
    monkeypatch.setattr(run, "main", lambda **k: code)
    assert run.run_guarded([]) == code
    assert _markers(capsys.readouterr().out) == 0


def test_guarded_bare_sys_exit(monkeypatch, capsys):
    monkeypatch.setattr(run, "main", lambda **k: sys.exit())
    assert run.run_guarded([]) == 0
    assert _markers(capsys.readouterr().out) == 0


def test_guarded_sys_exit_3_passes(monkeypatch, capsys):
    def marked_exit(**k):
        run.emit_unknown("plugin missing")
        sys.exit(3)
    monkeypatch.setattr(run, "main", marked_exit)
    assert run.run_guarded([]) == 3
    assert _markers(capsys.readouterr().out) == 1


def test_guarded_keyboard_interrupt_propagates(monkeypatch):
    def interrupt(**k):
        raise KeyboardInterrupt
    monkeypatch.setattr(run, "main", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run.run_guarded([])


def test_load_plugin_invalid_value_prints_marker(capsys):
    with pytest.raises(SystemExit) as exc:
        run.load_plugin({"local": "source_local"}, "nope", "TEST_SOURCE")
    assert exc.value.code == 3
    assert _markers(capsys.readouterr().out) == 1


def test_parse_run_args_prepare_only():
    assert run.parse_run_args(["--prepare-only"]).prepare_only is True
    assert run.parse_run_args([]).prepare_only is False


# ---------------------------------------------------------------------------
# Discovery (FR-042) and test-meta layers (FR-033)
# ---------------------------------------------------------------------------

def _touch(root, rel, text="// t"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_discovery_root_first(tmp_path):
    for rel in ("b/y.test.ts", "a/x/z.test.ts", "root.test.ts"):
        _touch(tmp_path, rel)
    mode = run.select_discovery_dir(str(tmp_path))
    assert mode.kind == "discovery"
    assert mode.workdir == str(tmp_path)
    assert mode.ignored_dirs == ("a/x", "b")


def test_discovery_byte_order_independent_of_creation(tmp_path):
    _touch(tmp_path, "b/y.test.ts")      # created first
    _touch(tmp_path, "a/x/z.test.js")
    _touch(tmp_path, "a/x/playwright.config.ts", "export default {}")
    mode = run.select_discovery_dir(str(tmp_path))
    assert mode.workdir == str(tmp_path / "a" / "x")
    assert mode.config == str(tmp_path / "a" / "x" / "playwright.config.ts")
    assert mode.ignored_dirs == ("b",)


def test_discovery_skips_shared_dirs(tmp_path):
    for skip in ("functions", "variables", "node_modules"):
        _touch(tmp_path, f"{skip}/helper.test.ts")
    _touch(tmp_path, "real/login.test.ts")
    mode = run.select_discovery_dir(str(tmp_path))
    assert mode.workdir == str(tmp_path / "real")
    assert mode.ignored_dirs == ()


def test_discovery_no_tests(tmp_path):
    _touch(tmp_path, "readme.md", "docs")
    with pytest.raises(run.NoTestsError):
        run.select_discovery_dir(str(tmp_path))


def test_describe_run_mode(tmp_path):
    mode = run.RunMode("discovery", str(tmp_path / "EXT/Shop/prod/playwright.config.ts"),
                       str(tmp_path / "EXT/Shop/prod"))
    assert run.describe_run_mode(mode, str(tmp_path)) == \
        "run mode: discovery (config EXT/Shop/prod/playwright.config.ts, workdir EXT/Shop/prod)"
    assert run.describe_run_mode(run.RunMode("discovery", None, str(tmp_path)), str(tmp_path)) == \
        "run mode: discovery (config none, workdir .)"


def test_write_test_meta_layers(tmp_path):
    layers = [{"position": 1, "path": "/abs/a", "type": "directory"},
              {"position": 2, "path": "/abs/b.tgz", "type": "archive"}]
    run.write_test_meta(str(tmp_path), "h", "s", 0, 1.0, "loc", "1", layers=layers)
    meta = json.loads((tmp_path / "test-meta.json").read_text())
    assert meta["layers"] == layers
    assert "container_path" not in json.dumps(meta)


def test_layer_records_local_and_s3(monkeypatch):
    monkeypatch.setenv("TEST_ARTIFACT_LAYERS", json.dumps([
        {"position": 1, "host_path": "/h/a", "type": "directory", "container_path": "/home/pwuser/layers/01"}]))
    assert run.layer_records("local") == [{"position": 1, "path": "/h/a", "type": "directory"}]
    monkeypatch.setenv("TEST_ARTIFACT", "/bucket/key.tgz")
    assert run.layer_records("s3") == [{"position": 1, "path": "s3:/bucket/key.tgz", "type": "archive"}]


def test_prepare_no_tests_message(tmp_path):
    class Empty:
        def acquire_tests(self, name, dest, deadline):
            Path(dest).mkdir(parents=True, exist_ok=True)
    with pytest.raises(run.PrepareError, match=r"no \*\.test\.ts/\*\.test\.js found after merging 2 layer\(s\)"):
        run.prepare(Empty(), "t", str(tmp_path / "tests"), 60, 2)


def test_prepare_bare_timeout_gets_generic_message(tmp_path):
    from _layers import LayerTimeout

    class Slow:
        def acquire_tests(self, name, dest, deadline):
            raise LayerTimeout()
    with pytest.raises(run.PrepareError, match="acquiring/merging layers exceeded the timeout of 60s"):
        run.prepare(Slow(), "t", str(tmp_path), 60, 1)


def test_prepare_keeps_specific_timeout_message(tmp_path):
    from _layers import LayerTimeout

    class S3:
        def acquire_tests(self, name, dest, deadline):
            raise LayerTimeout("layer #1 (s3:/b/k): download timed out after 5s")
    with pytest.raises(run.PrepareError, match="download timed out after 5s"):
        run.prepare(S3(), "t", str(tmp_path), 60, 1)


def test_prepare_only_stops_before_playwright(fake_container, monkeypatch, capsys):
    monkeypatch.setattr(run, "run_playwright", lambda *a, **k: pytest.fail("must not run"))
    assert run.main(prepare_only=True) == 0
    assert "check root ready" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# US3: project-root mode, "no tests", spectate wrapper (FR-040…FR-046)
# ---------------------------------------------------------------------------

def test_project_root_mode_wins_over_nested_tests(tmp_path):
    _touch(tmp_path, "playwright.config.ts", "export default {}")
    _touch(tmp_path, "nested/x.test.ts")
    _touch(tmp_path, "nested/playwright.config.ts", "export default {}")
    mode = run.detect_run_mode(str(tmp_path))
    assert mode == run.RunMode("project-root", str(tmp_path / "playwright.config.ts"), str(tmp_path))
    assert run.describe_run_mode(mode, str(tmp_path)) == \
        "run mode: project-root (config playwright.config.ts, workdir .)"


def test_config_lookup_order(tmp_path):
    _touch(tmp_path, "playwright.config.mjs", "export default {}")
    _touch(tmp_path, "playwright.config.js", "module.exports = {}")
    assert run.detect_run_mode(str(tmp_path)).config == str(tmp_path / "playwright.config.js")


def test_no_root_config_falls_back_to_discovery(tmp_path):
    _touch(tmp_path, "sub/x.test.ts")
    _touch(tmp_path, "sub/playwright.config.ts", "export default {}")
    mode = run.detect_run_mode(str(tmp_path))
    assert mode.kind == "discovery"
    assert mode.config == str(tmp_path / "sub" / "playwright.config.ts")
    assert mode.workdir == str(tmp_path / "sub")


_ZERO_STATS = {"expected": 0, "unexpected": 0, "flaky": 0, "skipped": 0}


@pytest.mark.parametrize("data,expected", [
    ({"suites": [], "stats": _ZERO_STATS, "errors": [{"message": "Error: No tests found"}]}, True),
    ({"suites": [], "stats": {**_ZERO_STATS, "expected": 1},
      "errors": [{"message": "Error: No tests found"}]}, False),
    ({"suites": [], "stats": _ZERO_STATS,
      "errors": [{"message": "SyntaxError: /home/pwuser/tests/tests/login.spec.ts: Unexpected token (5:0)"}]},
     False),
    ({"suites": [], "stats": _ZERO_STATS, "errors": []}, False),
    ({"suites": [], "stats": _ZERO_STATS}, False),
    (None, False),
])
def test_steps_has_no_tests(data, expected):
    assert run.steps_has_no_tests(data) is expected


def test_spectate_wrapper_with_config():
    src = run.build_spectate_wrapper("/home/pwuser/tests/playwright.config.ts", 400)
    assert "import base from './playwright.config.ts';" in src
    assert "testDir" not in src
    assert "slowMo = 400" in src
    assert "actionTimeout: 30000" in src
    assert "use: spectate(base.use)" in src
    assert "base.projects.map((p: any) => ({ ...p, use: spectate(p.use) }))" in src


def test_spectate_wrapper_without_config():
    src = run.build_spectate_wrapper(None, 200)
    assert "import" not in src
    assert "testDir" not in src
    assert "slowMo: 200" in src


def test_playwright_argv_handles_spaces(tmp_path, monkeypatch):
    workdir = tmp_path / "with space"
    workdir.mkdir()
    (workdir / "playwright.config.ts").write_text("export default {}")
    calls = []

    class Proc:
        returncode, stdout, stderr = 0, b"", b""

    monkeypatch.setattr(run.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)) or Proc())
    monkeypatch.delenv("CEP_SLOW_MO", raising=False)
    run.run_playwright(str(workdir), str(tmp_path), 30, config_path=str(workdir / "playwright.config.ts"),
                       project_root=True)
    cmd, kw = calls[0]
    assert isinstance(cmd, list) and "shell" not in kw
    assert cmd[:3] == ["timeout", "40", "npx"]
    assert cmd[-2:] == ["--config", str(workdir / "playwright.config.ts")]
    assert kw["cwd"] == str(workdir)


def test_playwright_spectate_wrapper_next_to_config(tmp_path, monkeypatch):
    (tmp_path / "playwright.config.ts").write_text("export default {}")
    calls = []

    class Proc:
        returncode, stdout, stderr = 0, b"", b""

    monkeypatch.setattr(run.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Proc())
    monkeypatch.setenv("CEP_SLOW_MO", "250")
    run.run_playwright(str(tmp_path), str(tmp_path), 30, headed=True,
                       config_path=str(tmp_path / "playwright.config.ts"))
    wrapper = tmp_path / ".cep-spectate.config.ts"
    assert wrapper.exists()
    assert calls[0][-2:] == ["--config", str(wrapper)]
    assert "--headed" in calls[0]


def test_main_project_root_no_tests_is_unknown(fake_container, monkeypatch, capsys):
    def acquire_config_only(self, name, dest, deadline=None):
        Path(dest).mkdir(parents=True, exist_ok=True)
        (Path(dest) / "playwright.config.ts").write_text("export default { testDir: './nothing' }")
    monkeypatch.setattr(_Plugin, "acquire_tests", acquire_config_only)
    no_tests = {"suites": [], "stats": _ZERO_STATS, "errors": [{"message": "Error: No tests found"}]}
    rc, meta, plugin = fake_container(1, no_tests)
    assert rc == 3
    assert "Playwright configuration playwright.config.ts matched no tests" in capsys.readouterr().out
    assert meta["status"] == "UNKNOWN"
    assert plugin.published == [3]
