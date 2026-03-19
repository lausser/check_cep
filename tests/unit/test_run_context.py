"""Unit tests for RunConfig, RunContext, and make_ctx/make_config helpers
(T013-T019 — 010-run-context)."""
import importlib.machinery
import importlib.util
import sys
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
sys.modules.setdefault("check_cep_mod", _mod)

RunConfig = _mod.RunConfig
RunContext = _mod.RunContext
derive_testname = _mod.derive_testname
derive_testident = _mod.derive_testident
sanitize_container_name = _mod.sanitize_container_name
resolve_path_template = _mod.resolve_path_template
build_env_vars = _mod.build_env_vars
resolve_report_url = _mod.resolve_report_url


# ---------------------------------------------------------------------------
# Test helpers (T013, T014, T015)
# ---------------------------------------------------------------------------

def make_config(**overrides) -> RunConfig:
    """Build a RunConfig with sensible test defaults. Override any field by name."""
    defaults = dict(
        host_name="testhost",
        service_description="TestService",
        image="ghcr.io/example/playwright:latest",
        probe_location="local",
        test_source="local",
        result_dest="local",
        logging="none",
        test_dir="/omd/etc/check_cep/tests/%h/%s",
        result_dir="/omd/var/tmp/check_cep/%h/%s/%t",
        testscripts_cache="/omd/var/tmp/check_cep_cache",
        report_retention=None,
        timeout=60,
        memory_limit="2g",
        debug=False,
        shell=False,
        headed=False,
        browser="chromium",
        report_url=None,
        href_target="_blank",
        registry_username=None,
        registry_password=None,
        s3_endpoint=None,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        s3_bucket=None,
        s3_report_bucket=None,
        s3_report_path=None,
        s3_report_url=None,
        loki_endpoint=None,
        loki_user=None,
        loki_password=None,
        loki_proxy=None,
        current_status=None,
    )
    defaults.update(overrides)
    return RunConfig(**defaults)


def make_ctx(**overrides) -> RunContext:
    """Build a RunContext with sensible test defaults. Override any field by name."""
    defaults = dict(
        hostname="testhost",
        servicedescription="TestService",
        testname="testhost/TestService",
        testident="testhost__TestService",
        container_name="testhost_TestService",
        start_time=1700000000.0,
        started_str="1700000000",
        timeout_deadline=1700000060.0,
        result_dir="/tmp/test_results",
        omd_root="",
        pid_file="/tmp/var/tmp/check_cep.testhost__TestService.pid",
        config=make_config(),
    )
    defaults.update(overrides)
    return RunContext(**defaults)


# ---------------------------------------------------------------------------
# RunContext construction tests (T016)
# ---------------------------------------------------------------------------

def test_started_str_is_int_of_start_time():
    ctx = make_ctx(start_time=1700000042.9, started_str="1700000042")
    assert ctx.started_str == "1700000042"


def test_timeout_deadline_equals_start_plus_timeout():
    ctx = make_ctx(start_time=1700000000.0, timeout_deadline=1700000090.0,
                   config=make_config(timeout=90))
    assert ctx.timeout_deadline == ctx.start_time + ctx.config.timeout


def test_pid_file_contains_testident():
    ctx = make_ctx(testident="myhost__MyService",
                   pid_file="/tmp/var/tmp/check_cep.myhost__MyService.pid")
    assert ctx.testident in ctx.pid_file


def test_result_dir_template_expansion():
    expanded = resolve_path_template("/omd/var/tmp/check_cep/%h/%s/%t", "h1", "s1", "123")
    assert expanded == "/omd/var/tmp/check_cep/h1/s1/123"


def test_runcontext_is_immutable():
    ctx = make_ctx()
    with pytest.raises(Exception):
        ctx.hostname = "other"  # type: ignore[misc]


def test_runconfig_is_immutable():
    cfg = make_config()
    with pytest.raises(Exception):
        cfg.host_name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# build_env_vars tests (T017)
# ---------------------------------------------------------------------------

def test_build_env_vars_cep_started_matches_started_str():
    ctx = make_ctx(started_str="1700000042")
    env = build_env_vars(ctx)
    assert env["CEP_STARTED"] == "1700000042"


def test_build_env_vars_hostname_from_ctx():
    ctx = make_ctx(hostname="myhost")
    env = build_env_vars(ctx)
    assert env["NAGIOS_HOSTNAME"] == "myhost"


def test_build_env_vars_debug_flag():
    ctx = make_ctx(config=make_config(debug=True))
    env = build_env_vars(ctx)
    assert env.get("DEBUG") == "1"


def test_build_env_vars_no_debug_by_default():
    ctx = make_ctx()
    env = build_env_vars(ctx)
    assert "DEBUG" not in env


# ---------------------------------------------------------------------------
# resolve_report_url tests (T019)
# ---------------------------------------------------------------------------

def test_resolve_report_url_template_vars():
    ctx = make_ctx(
        hostname="web01",
        servicedescription="Login",
        testident="web01__Login",
        config=make_config(
            report_url="https://reports/%h/%s/%i/%t",
            probe_location="eu-west",
            s3_report_bucket="my-bucket",
        ),
    )
    url = resolve_report_url(ctx, "1700000042")
    assert url == "https://reports/web01/Login/web01__Login/1700000042"


def test_resolve_report_url_probe_and_bucket():
    ctx = make_ctx(
        config=make_config(
            report_url="https://r/%l/%b",
            probe_location="us-east",
            s3_report_bucket="bucket-1",
        ),
    )
    url = resolve_report_url(ctx, "0")
    assert url == "https://r/us-east/bucket-1"


def test_resolve_report_url_empty_bucket():
    ctx = make_ctx(
        config=make_config(
            report_url="https://r/%b/end",
            s3_report_bucket=None,
        ),
    )
    url = resolve_report_url(ctx, "0")
    assert url == "https://r//end"
