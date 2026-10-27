"""Unit tests for the host-side exit-status classification (spec 023, US8).

FR-052 / contracts/nagios-output.md §0: CRITICAL only when Playwright reports a
failure; everything that prevented the tests from running properly is UNKNOWN.
FR-053: author-signalled WARNING (visible stderr, exit 1). FR-054: report
`errors` on a passed run are CRITICAL.
"""
import itertools
import sys

import pytest

from conftest import _cep_mod as cep

ContainerOutcome = cep.ContainerOutcome
classify_result = cep.classify_result

SVC = "svc"
HOST = "H"


def outcome(rc, **kw):
    fields = dict(rc=rc, oom_killed=False, timed_out=False, duplicate=False,
                  auth_failed=False, cep_unknown=None, has_stderr_in_steps=False,
                  has_report_errors=False, podman_error="")
    fields.update(kw)
    return ContainerOutcome(**fields)


# ---------------------------------------------------------------------------
# Marker / podman error extraction
# ---------------------------------------------------------------------------

class TestExtractCepUnknown:
    def test_message_extracted(self):
        assert cep.extract_cep_unknown("x\nCEPUNKNOWN [[[layer #2 (/x): boom]]]\n") == "layer #2 (/x): boom"

    def test_absent(self):
        assert cep.extract_cep_unknown("all fine\n") is None

    def test_first_of_several(self):
        assert cep.extract_cep_unknown("CEPUNKNOWN [[[a]]]\nCEPUNKNOWN [[[b]]]") == "a"


class TestExtractPodmanError:
    def test_error_line_preferred(self):
        stderr = "Trying to pull x...\nError: docker.io/x/y: image not known\nmore\n"
        assert cep.extract_podman_error(stderr) == "Error: docker.io/x/y: image not known"

    def test_fallback_last_non_empty_line(self):
        assert cep.extract_podman_error("first\nsecond\n\n  \n") == "second"

    def test_capped(self):
        assert len(cep.extract_podman_error("Error: " + "x" * 1000)) == cep.PODMAN_ERROR_MAX_LEN == 300

    def test_empty(self):
        assert cep.extract_podman_error("") == ""


# ---------------------------------------------------------------------------
# classify_result: one test per row of contracts/nagios-output.md §0
# ---------------------------------------------------------------------------

class TestClassifyResult:
    def test_1_oom(self):
        assert classify_result(outcome(137, oom_killed=True), SVC, HOST) == ("UNKNOWN", "test svc OOM killed")

    def test_1_oom_wins_over_rc2(self):
        assert classify_result(outcome(2, oom_killed=True), SVC, HOST)[0] == "UNKNOWN"

    def test_1_oom_wins_over_rc1(self):
        assert classify_result(outcome(1, oom_killed=True), SVC, HOST)[0] == "UNKNOWN"

    def test_2a_duplicate(self):
        status, summary = classify_result(outcome(125, duplicate=True), SVC, HOST)
        assert status == "UNKNOWN"
        assert summary == "test svc duplicate, running on host H"

    def test_2b_auth_failure(self):
        o = outcome(125, auth_failed=True, podman_error="Error: unauthorized")
        assert classify_result(o, SVC, HOST) == (
            "UNKNOWN",
            "podman failed for test svc on host H (podman exit code 125): Error: unauthorized")

    @pytest.mark.parametrize("rc", [125, 126, 127])
    def test_2c_podman_failure(self, rc):
        o = outcome(rc, podman_error="Error: image not known")
        assert classify_result(o, SVC, HOST) == (
            "UNKNOWN",
            f"test svc could not be started on host H (podman exit code {rc}): Error: image not known")

    def test_3_rc3_with_marker(self):
        assert classify_result(outcome(3, cep_unknown="boom"), SVC, HOST) == ("UNKNOWN", "test svc: boom")

    def test_3_rc3_without_marker(self):
        assert classify_result(outcome(3), SVC, HOST) == ("UNKNOWN", "test svc failed")

    def test_3_rc3_report_errors_still_unknown(self):
        assert classify_result(outcome(3, has_report_errors=True), SVC, HOST)[0] == "UNKNOWN"

    def test_4_ok(self):
        assert classify_result(outcome(0), SVC, HOST) == ("OK", "test svc succeeded")

    def test_4_stderr_warning(self):
        assert classify_result(outcome(0, has_stderr_in_steps=True), SVC, HOST) == ("WARNING", "test svc succeeded")

    def test_4b_rc1_warning(self):
        assert classify_result(outcome(1), SVC, HOST) == ("WARNING", "test svc succeeded")

    @pytest.mark.parametrize("rc", [0, 1])
    @pytest.mark.parametrize("stderr", [False, True])
    def test_4a_report_errors_critical(self, rc, stderr):
        o = outcome(rc, has_report_errors=True, has_stderr_in_steps=stderr)
        assert classify_result(o, SVC, HOST) == ("CRITICAL", "test svc failed")

    def test_5_timeout(self):
        assert classify_result(outcome(2, timed_out=True), SVC, HOST) == ("CRITICAL", "test svc timed out")

    def test_5_failed(self):
        assert classify_result(outcome(2), SVC, HOST) == ("CRITICAL", "test svc failed")

    @pytest.mark.parametrize("rc", [130, 137, 150, 255])
    def test_6_unexpected(self, rc):
        assert classify_result(outcome(rc), SVC, HOST) == (
            "UNKNOWN", f"test svc ended with unexpected exit code {rc} on host H")


def test_property_critical_and_warning_only_where_allowed():
    """SC-010: CRITICAL only for rc 2 or rc 0/1 with report errors; WARNING only for rc 0/1."""
    bools = (False, True)
    for rc in range(256):
        for oom, to, dup, auth, unk, stderr, errs in itertools.product(
                bools, bools, bools, bools, (None, "m"), bools, bools):
            o = outcome(rc, oom_killed=oom, timed_out=to, duplicate=dup, auth_failed=auth,
                        cep_unknown=unk, has_stderr_in_steps=stderr, has_report_errors=errs)
            status, _ = classify_result(o, SVC, HOST)
            if status == "CRITICAL":
                assert not oom and (rc == 2 or (rc in (0, 1) and errs)), o
            if status == "WARNING":
                assert rc in (0, 1) and not oom, o


# ---------------------------------------------------------------------------
# FR-053 visible-stderr rule and FR-054 report errors
# ---------------------------------------------------------------------------

# Shared fixtures so the host and run.py implementations can be compared.
STDIO_CASES = [
    ({"text": "x"}, "x"),
    ({"buffer": "eA=="}, "x"),
    ({"buffer": "!!!not-base64"}, ""),
    ("not a dict", ""),
    (None, ""),
]


def _report(stderr_entries, where="results0"):
    result0 = {"stderr": [], "errors": []}
    result1 = {"stderr": [], "errors": []}
    if where == "results0":
        result0["stderr"] = stderr_entries
    elif where == "results1":
        result1["stderr"] = stderr_entries
    spec = {"title": "t", "tests": [{"projectName": "p", "results": [result0, result1]}]}
    if where == "nested":
        spec["tests"][0]["results"][0]["stderr"] = []
        nested = {"title": "inner", "specs": [{"title": "n", "tests": [
            {"projectName": "p", "results": [{"stderr": stderr_entries}]}]}]}
        return {"suites": [{"title": "a.test.ts", "specs": [spec], "suites": [nested]}]}
    return {"suites": [{"title": "a.test.ts", "specs": [spec]}]}


VISIBLE_CASES = [
    (_report([{"buffer": ""}]), False),
    (_report([{"text": "  \n"}]), False),
    (_report([{"text": "slow backend\n"}], where="results1"), True),
    (_report([{"buffer": "eA=="}], where="nested"), True),
    ({"suites": []}, False),
]


@pytest.mark.parametrize("entry,expected", STDIO_CASES)
def test_stdio_text(entry, expected):
    assert cep.stdio_text(entry) == expected


@pytest.mark.parametrize("report,expected", VISIBLE_CASES)
def test_report_has_visible_stderr(report, expected):
    assert cep.report_has_visible_stderr(report) is expected


def test_extract_output_ignores_empty_stderr_and_renders_buffer():
    out, has_stderr = cep.extract_output_from_steps(_report([{"buffer": ""}]))
    assert not has_stderr
    assert "__Stderr" not in out
    out, has_stderr = cep.extract_output_from_steps(_report([{"buffer": "aGVsbG8="}]))
    assert has_stderr
    assert "hello" in out


class TestReportHasErrors:
    def test_root_errors(self):
        assert cep.report_has_errors({"suites": [], "errors": [{"message": "x"}]})

    def test_first_result_errors(self):
        report = _report([])
        report["suites"][0]["specs"][0]["tests"][0]["results"][0]["errors"] = [{"message": "x"}]
        assert cep.report_has_errors(report)

    def test_later_result_errors_ignored(self):
        report = _report([])
        report["suites"][0]["specs"][0]["tests"][0]["results"][1]["errors"] = [{"message": "x"}]
        assert not cep.report_has_errors(report)

    def test_clean(self):
        assert not cep.report_has_errors(_report([]))


# ---------------------------------------------------------------------------
# F1: registry login never yields a synthetic CRITICAL
# ---------------------------------------------------------------------------

class _Proc:
    def __init__(self, rc, stdout=b"", stderr=b""):
        self.returncode, self.stdout, self.stderr = rc, stdout, stderr


def test_retry_with_auth_image_without_registry(monkeypatch):
    monkeypatch.setattr(cep.subprocess, "run", lambda *a, **k: pytest.fail("no subprocess expected"))
    out, err, rc = cep.retry_with_auth("podman", ["podman", "run", "img"], "img", "u", "p")
    assert rc == 125
    assert b"names no registry" in err


def test_retry_with_auth_failed_login(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return _Proc(125, b"", b"Error: logging into reg.io: invalid username/password\n")

    monkeypatch.setattr(cep.subprocess, "run", fake_run)
    out, err, rc = cep.retry_with_auth("podman", ["podman", "run", "reg.io/x:1"], "reg.io/x:1", "u", "pw")
    assert rc == 125
    assert b"invalid username/password" in err
    assert len(calls) == 1  # the container is not re-run after a failed login


# ---------------------------------------------------------------------------
# main() wiring
# ---------------------------------------------------------------------------

class _FakeEnv:
    def __init__(self):
        self.ok = True
        self.container_bin = "podman"
        self.has_cgroups2 = False
        self.failure = None


@pytest.fixture
def main_env(tmp_path, monkeypatch):
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "a.test.ts").write_text("// t")
    monkeypatch.setenv("OMD_ROOT", str(tmp_path))
    monkeypatch.setattr(cep, "ContainerEnv", _FakeEnv)
    monkeypatch.setattr(cep, "container_cleanup", lambda *a: None)

    def run(execute_result, extra=()):
        monkeypatch.setattr(cep, "execute_container", lambda *a, **k: execute_result)
        monkeypatch.setattr(sys, "argv", [
            "check_cep", "--host-name", "h", "--service-description", "svc",
            "--image", "localhost/x:1", "--probe-location", "l",
            "--test-dir", str(test_dir), "--result-dir", str(tmp_path / "res"), *extra])
        return cep.main()
    return run


def test_main_cepunknown(main_env, capsys):
    rc = main_env((b"CEPUNKNOWN [[[boom]]]\n", b"", 3))
    assert rc == 3
    assert capsys.readouterr().out.startswith("UNKNOWN - test svc: boom")


def test_main_podman_125(main_env, capsys):
    rc = main_env((b"", b"Error: docker.io/x/y: image not known\n", 125))
    assert rc == 3
    first = capsys.readouterr().out.splitlines()[0]
    assert first.startswith("UNKNOWN - test svc could not be started on host ")
    assert "(podman exit code 125): Error: docker.io/x/y: image not known" in first


def test_main_auth_required_without_credentials(main_env, capsys):
    rc = main_env((b"", b"Error: initializing source: Authentication is required\n", 125))
    assert rc == 3
    first = capsys.readouterr().out.splitlines()[0]
    assert first.startswith("UNKNOWN - podman failed for test svc on host ")
    assert "Authentication is required" in first


def test_main_auth_login_failure(main_env, monkeypatch, capsys):
    monkeypatch.setattr(cep.subprocess, "run",
                        lambda *a, **k: _Proc(125, b"", b"Error: login failed\n"))
    rc = main_env((b"", b"Error: x: Authentication is required\n", 125),
                  extra=("--registry-username", "u", "--registry-password", "pw"))
    assert rc == 3
    first = capsys.readouterr().out.splitlines()[0]
    assert first == f"UNKNOWN - podman failed for test svc on host {cep.os.uname()[1]} " \
                    "(podman exit code 125): Error: login failed | 'duration'=0s"


def test_buffer_stdout_is_rendered_and_parsed():
    """Playwright stores bytes written to stdout as base64 `buffer` (non-ASCII output)."""
    import base64
    result = {"stdout": [{"buffer": base64.b64encode("Grüße\n".encode()).decode()},
                         {"buffer": base64.b64encode(b"NagiosPerfData: 'x'=5ms").decode()},
                         "garbage", {"buffer": "!!"}],
              "stderr": [], "errors": []}
    report = {"suites": [{"title": "a.test.ts", "specs": [{"title": "t", "tests": [
        {"projectName": "p", "results": [result]}]}]}]}
    output, _ = cep.extract_output_from_steps(report)
    assert "Grüße" in output
    assert cep.extract_nagios_perfdata_from_stdout(report) == [{"label": "x", "value": "5", "unit": "ms"}]


def test_stdio_text_bad_utf8_uses_replacement_char():
    import base64
    assert cep.stdio_text({"buffer": base64.b64encode(b"a\xffb").decode()}) == "a�b"


# ---------------------------------------------------------------------------
# A report left over from an earlier run is not this run's result
# ---------------------------------------------------------------------------

def test_steps_json_from_earlier_run_is_ignored(tmp_path):
    """An UNKNOWN before Playwright (merge error, podman 125) leaves the previous
    steps.json in the result dir; its perfdata must not be reported again."""
    import os
    import time
    report = tmp_path / "steps.json"
    report.write_text('{"suites": []}')
    start = time.time()
    os.utime(report, (start - 60, start - 60))
    assert cep.parse_steps_json(str(report), not_before=start) is None
    os.utime(report, (start + 1, start + 1))
    assert cep.parse_steps_json(str(report), not_before=start) == {"suites": []}
    assert cep.parse_steps_json(str(report)) == {"suites": []}
    # Whole-second mtimes: a fresh report may carry a timestamp just before start.
    os.utime(report, (int(start), int(start)))
    assert cep.parse_steps_json(str(report), not_before=start) == {"suites": []}
    assert cep.parse_steps_json(str(tmp_path / "missing.json"), not_before=start) is None


def test_marker_line_is_not_repeated_in_long_output():
    """The CEPUNKNOWN reason is in the status line; the raw marker is protocol."""
    text = "prep log\nCEPUNKNOWN [[[type conflict at x]]]\nlast line\n"
    assert cep.strip_cep_unknown(text) == "prep log\nlast line\n"
    assert cep.strip_cep_unknown("CEPUNKNOWN [[[only]]]") == ""
