"""Unit tests for RunConfig, RunContext, build_env_vars, and build_podman_command."""
import pytest

from conftest import (
    RunConfig,
    RunContext,
    derive_testname,
    derive_testident,
    sanitize_container_name,
    resolve_path_template,
    build_env_vars,
    build_podman_command,
    resolve_report_url,
    make_config,
    make_ctx,
)


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


# ---------------------------------------------------------------------------
# build_env_vars: TEST_ARTIFACT / S3_BUCKET (017-s3-tgz-source, T009)
# ---------------------------------------------------------------------------

def test_build_env_vars_test_artifact_present():
    ctx = make_ctx(config=make_config(test_artifact="/mybucket/checks/login.tgz"))
    env = build_env_vars(ctx)
    assert env["TEST_ARTIFACT"] == "/mybucket/checks/login.tgz"


def test_build_env_vars_test_artifact_absent_when_not_set():
    ctx = make_ctx(config=make_config(test_artifact=None))
    env = build_env_vars(ctx)
    assert "TEST_ARTIFACT" not in env


def test_build_env_vars_s3_bucket_never_present():
    ctx = make_ctx(config=make_config(test_artifact="/b/k.tgz", s3_endpoint="https://s3"))
    env = build_env_vars(ctx)
    assert "S3_BUCKET" not in env


# ---------------------------------------------------------------------------
# build_podman_command: volume mounts (017-s3-tgz-source, T009 / T014)
# ---------------------------------------------------------------------------

def _cmd_volumes(ctx):
    """Return only the --volume values from build_podman_command output."""
    cmd = build_podman_command(ctx, "podman", {})
    volumes = []
    for i, token in enumerate(cmd):
        if token == "--volume" and i + 1 < len(cmd):
            volumes.append(cmd[i + 1])
    return volumes


def test_podman_s3_mounts_testscripts_cache():
    ctx = make_ctx(config=make_config(
        test_source="s3",
        test_artifact="/mybucket/checks/login.tgz",
        testscripts_cache="/omd/var/tmp/tscache",
    ))
    volumes = _cmd_volumes(ctx)
    assert any(":/home/pwuser/testscripts-cache:rw,z" in v for v in volumes)


def test_podman_s3_no_tests_mount():
    ctx = make_ctx(config=make_config(
        test_source="s3",
        test_artifact="/mybucket/checks/login.tgz",
        testscripts_cache="/omd/var/tmp/tscache",
    ))
    volumes = _cmd_volumes(ctx)
    # :/home/pwuser/tests: with colon suffix ensures we don't match testscripts-cache
    assert not any(":/home/pwuser/tests:" in v for v in volumes)


def test_podman_local_tgz_mounts_input_artifact():
    ctx = make_ctx(config=make_config(
        test_source="local",
        test_artifact="/omd/etc/mytests.tgz",
    ))
    volumes = _cmd_volumes(ctx)
    assert any(":/home/pwuser/input-artifact.tgz:ro,z" in v for v in volumes)
    assert not any(":/home/pwuser/tests:" in v for v in volumes)


def test_podman_local_dir_mounts_tests():
    ctx = make_ctx(config=make_config(
        test_source="local",
        test_artifact="/omd/etc/mytests/",
    ))
    volumes = _cmd_volumes(ctx)
    assert any(":/home/pwuser/tests:ro,z" in v for v in volumes)
    assert not any("input-artifact" in v for v in volumes)


def test_podman_local_deprecated_test_dir_mounts_tests():
    ctx = make_ctx(config=make_config(
        test_source="local",
        test_dir="/omd/etc/mylegacytests",
    ))
    volumes = _cmd_volumes(ctx)
    assert any(":/home/pwuser/tests:ro,z" in v for v in volumes)
