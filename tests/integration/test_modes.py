"""Parametrized integration tests: fixtures × {local, s3, lightpanda} modes.

Local mode tests run without any external services (SKIP_INTEGRATION is not
required). S3 mode tests require the compose stack and are skipped when
SKIP_INTEGRATION=1. Lightpanda mode re-runs the DOM-only fixtures with
--browser lightpanda (vision fixtures are skipped — no rendering engine).
"""

import json
import os
import subprocess

import pytest

from conftest import run_check_cep, local_test_dir, run_check_cep_s3
from conftest import _mod as cep, CEP_PLUGIN


# ---------------------------------------------------------------------------
# Fixture parameter table
# (fixture_name, expected_exit, expected_prefix, extra_args, keyword)
# expected_exit=None means 2-or-3 (lenient; no table uses it since spec 023)
# keyword is checked in output when not None
# ---------------------------------------------------------------------------

FIXTURES = [
    ("tc_pass", 0, "OK -", [], None),
    ("tc_register_pass", 0, "OK -", [], None),
    ("tc_fail", 2, "CRITICAL -", [], None),
    ("tc_timeout", 2, "CRITICAL -", ["--timeout", "15"], "timed out"),
    ("tc_syntax", 2, "CRITICAL -", [], None),
    ("tc_vision_basic", 0, "OK -", [], None),
    ("tc_vision_ambiguous", 0, "OK -", [], None),
    ("tc_vision_color", 0, "OK -", [], None),
    ("tc_vision_debug", 0, "OK -", [], None),
    ("tc_vision_workflow", 0, "OK -", [], None),
    ("tc_vision_example_form", 0, "OK -", [], None),
    ("tc_vision_example_console", 0, "OK -", [], None),
    ("tc_vision_example_login", 0, "OK -", [], None),
    ("tc_shop_catalog_grid", 0, "OK -", [], None),
    ("tc_news_homepage_busy", 0, "OK -", [], None),
    ("tc_marketplace_preview_tile", 0, "OK -", [], None),
    ("tc_marketplace_anchor_then_target", 0, "OK -", [], None),
    ("tc_marketplace_real_photo_pair", 0, "OK -", [], None),
]


# ---------------------------------------------------------------------------
# Local mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_name,expected_exit,expected_prefix,extra_args,keyword",
    FIXTURES,
    ids=[f[0] for f in FIXTURES],
)
def test_local(
    tmp_path,
    omd_env,
    write_playwright_config,
    fixture_name,
    expected_exit,
    expected_prefix,
    extra_args,
    keyword,
):
    result_dir = tmp_path / "results"
    test_dir = local_test_dir(tmp_path, fixture_name, write_playwright_config)

    output, code = run_check_cep(
        test_dir,
        result_dir,
        extra_args=[
            "--host-name",
            "testhost",
            "--service-description",
            fixture_name,
        ]
        + extra_args,
        env=omd_env,
        proc_timeout=120,
    )

    # Exit code
    if expected_exit is None:
        assert code in (2, 3), f"[{fixture_name}] Expected exit 2 or 3, got {code}.\nOutput:\n{output}"
    else:
        assert code == expected_exit, f"[{fixture_name}] Expected exit {expected_exit}, got {code}.\nOutput:\n{output}"

    # Output prefix
    if expected_prefix is None:
        assert output.startswith(("CRITICAL -", "UNKNOWN -")), (
            f"[{fixture_name}] Expected CRITICAL or UNKNOWN prefix.\nOutput:\n{output}"
        )
    else:
        assert output.startswith(expected_prefix), (
            f"[{fixture_name}] Expected '{expected_prefix}' prefix.\nOutput:\n{output}"
        )

    # Keyword check (e.g. "timed out" for tc_timeout)
    if keyword:
        assert keyword in output, f"[{fixture_name}] Expected '{keyword}' in output.\nOutput:\n{output}"

    # Result artefacts — only for tests that complete (not tc_timeout which is killed)
    if fixture_name != "tc_timeout":
        steps_json = result_dir / "steps.json"
        assert steps_json.exists(), f"[{fixture_name}] steps.json not written"
        data = json.loads(steps_json.read_text())
        assert isinstance(data, dict), f"[{fixture_name}] steps.json is not a JSON object"

        meta_json = result_dir / "test-meta.json"
        assert meta_json.exists(), f"[{fixture_name}] test-meta.json not written"
        meta = json.loads(meta_json.read_text())
        assert meta["hostname"] == "testhost"
        assert meta["servicedescription"] == fixture_name
        assert "status" in meta


# ---------------------------------------------------------------------------
# Local mode — Lightpanda browser
# ---------------------------------------------------------------------------
# Lightpanda 1.0.2 CDP support is verified empirically in this lane. Read-only
# navigation/DOM queries and the syntax, failure, and timeout verdict paths are
# deterministic. Vision remains Chromium-only because Lightpanda has no visual
# rendering engine.
#
# `tc_pass` remains a strict-xfail canary for normal Playwright interaction. On
# 1.0.2, number/date fills and the display-button click complete, but the page
# does not reflect the number input in `#output-number`; the Chromium-equivalent
# assertion therefore fails. An XPASS means the full fixture interaction and
# value propagation work, signalling that its promotion should be re-reviewed.
FIXTURES_LIGHTPANDA = [
    ("tc_lp_pass", 0, "OK -", [], None),
    ("tc_syntax", 2, "CRITICAL -", [], None),
    ("tc_fail", 2, "CRITICAL -", [], None),
    ("tc_timeout", 2, "CRITICAL -", ["--timeout", "15"], "timed out"),
    pytest.param(
        "tc_pass",
        0,
        "OK -",
        [],
        None,
        id="tc_pass_canary",
        marks=pytest.mark.xfail(
            strict=True,
            reason="Lightpanda canary: tc_pass hits an unsupported interaction "
            "(number-input fill() -> InvalidStateError; heavy-page click also "
            "hangs). XPASS after a pin bump = engine broadly supports "
            "interaction; re-review FIXTURES_LIGHTPANDA promotion (spec 018 R6).",
        ),
    ),
]


@pytest.mark.parametrize(
    "fixture_name,expected_exit,expected_prefix,extra_args,keyword",
    FIXTURES_LIGHTPANDA,
    ids=[getattr(f, "id", None) or f[0] for f in FIXTURES_LIGHTPANDA],
)
def test_local_lightpanda(
    tmp_path,
    omd_env,
    write_playwright_config,
    fixture_name,
    expected_exit,
    expected_prefix,
    extra_args,
    keyword,
):
    result_dir = tmp_path / "results"
    test_dir = local_test_dir(tmp_path, fixture_name, write_playwright_config)

    output, code = run_check_cep(
        test_dir,
        result_dir,
        extra_args=[
            "--host-name",
            "testhost",
            "--service-description",
            fixture_name,
            "--browser",
            "lightpanda",
        ]
        + extra_args,
        env=omd_env,
        proc_timeout=120,
        spectate=False,
    )

    # Exit code
    if expected_exit is None:
        assert code in (2, 3), f"[{fixture_name}/lightpanda] Expected exit 2 or 3, got {code}.\nOutput:\n{output}"
    else:
        assert code == expected_exit, (
            f"[{fixture_name}/lightpanda] Expected exit {expected_exit}, got {code}.\nOutput:\n{output}"
        )

    # Output prefix
    if expected_prefix is None:
        assert output.startswith(("CRITICAL -", "UNKNOWN -")), (
            f"[{fixture_name}/lightpanda] Expected CRITICAL or UNKNOWN prefix.\nOutput:\n{output}"
        )
    else:
        assert output.startswith(expected_prefix), (
            f"[{fixture_name}/lightpanda] Expected '{expected_prefix}' prefix.\nOutput:\n{output}"
        )

    # Keyword check
    if keyword:
        assert keyword in output, f"[{fixture_name}/lightpanda] Expected '{keyword}' in output.\nOutput:\n{output}"

    # Result artefacts — only for tests that complete (not tc_timeout which is killed)
    if fixture_name != "tc_timeout":
        steps_json = result_dir / "steps.json"
        assert steps_json.exists(), f"[{fixture_name}/lightpanda] steps.json not written"
        data = json.loads(steps_json.read_text())
        assert isinstance(data, dict), f"[{fixture_name}/lightpanda] steps.json is not a JSON object"

        meta_json = result_dir / "test-meta.json"
        assert meta_json.exists(), f"[{fixture_name}/lightpanda] test-meta.json not written"
        meta = json.loads(meta_json.read_text())
        assert meta["hostname"] == "testhost"
        assert meta["servicedescription"] == fixture_name
        assert "status" in meta


# ---------------------------------------------------------------------------
# S3 mode — placeholder until Phase 4 (T014)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_name,expected_exit,expected_prefix,extra_args,keyword",
    FIXTURES,
    ids=[f[0] for f in FIXTURES],
)
@pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION"),
    reason="compose stack not available (SKIP_INTEGRATION set)",
)
def test_s3(
    tmp_path,
    omd_env,
    write_playwright_config,
    compose_stack,
    cep_image,
    container_cleanup,
    fixture_name,
    expected_exit,
    expected_prefix,
    extra_args,
    keyword,
):
    output, code, result_dir, report_prefix = run_check_cep_s3(
        fixture_name,
        omd_env,
        tmp_path,
        cep_image,
        compose_stack,
        write_playwright_config,
        extra_args=extra_args,
        cleanup_paths=container_cleanup,
    )

    # Exit code
    if expected_exit is None:
        assert code in (2, 3), f"[{fixture_name}/s3] Expected exit 2 or 3, got {code}.\nOutput:\n{output}"
    else:
        assert code == expected_exit, (
            f"[{fixture_name}/s3] Expected exit {expected_exit}, got {code}.\nOutput:\n{output}"
        )

    # Output prefix
    if expected_prefix is None:
        assert output.startswith(("CRITICAL -", "UNKNOWN -")), (
            f"[{fixture_name}/s3] Expected CRITICAL or UNKNOWN prefix.\nOutput:\n{output}"
        )
    else:
        assert output.startswith(expected_prefix), (
            f"[{fixture_name}/s3] Expected '{expected_prefix}' prefix.\nOutput:\n{output}"
        )

    if keyword:
        assert keyword in output, f"[{fixture_name}/s3] Expected '{keyword}' in output.\nOutput:\n{output}"

    # Local result artefacts (always present after FR-000 fix)
    if fixture_name != "tc_timeout":
        steps_json = result_dir / "steps.json"
        assert steps_json.exists(), f"[{fixture_name}/s3] steps.json not written locally"
        data = json.loads(steps_json.read_text())
        assert isinstance(data, dict)

        meta_json = result_dir / "test-meta.json"
        assert meta_json.exists(), f"[{fixture_name}/s3] test-meta.json not written locally"
        meta = json.loads(meta_json.read_text())
        assert "hostname" in meta
        assert "servicedescription" in meta
        assert "status" in meta

    # S3 bucket artefacts — tc_timeout is killed before Playwright produces
    # an HTML report, so only test-meta.json may be present.
    if fixture_name != "tc_timeout":
        s3 = compose_stack
        objects = s3.list_objects_v2(Bucket="cep-reports", Prefix=report_prefix + "/")
        keys = [obj["Key"] for obj in objects.get("Contents", [])]
        assert any("index.html" in k for k in keys), (
            f"[{fixture_name}/s3] playwright-report/index.html not found in cep-reports.\nKeys: {keys}"
        )
        assert any("test-meta.json" in k for k in keys), (
            f"[{fixture_name}/s3] test-meta.json not found in cep-reports.\nKeys: {keys}"
        )


# ---------------------------------------------------------------------------
# Authoring mode (spec 020/022) — --authoring / --environ / --opencode-config
# ---------------------------------------------------------------------------
#
# The env-injection and mount behaviour is verified at the unit level by
# building the podman command directly (no container launch). The exit-3
# refusals and the no-key warning are verified via subprocess against a fake
# `podman` on PATH so the tests are hermetic and never spawn a real container.

_CONFIG_DEFAULTS = dict(
    host_name="testhost",
    service_description="Portfolio",
    image="check_cep:ai",
    probe_location="local",
    test_source="local",
    result_dest="local",
    logging="none",
    test_dir=None,
    test_artifacts=(),
    result_dir="/tmp/cep-results",
    testscripts_cache="/tmp/cep-cache",
    report_retention=None,
    timeout=60,
    memory_limit="2g",
    debug=False,
    shell=False,
    authoring=False,
    environ=[],
    opencode_config=None,
    headed=False,
    vnc=False,
    browser="chromium",
    report_url=None,
    href_target="_blank",
    registry_username=None,
    registry_password=None,
    s3_endpoint=None,
    aws_access_key_id=None,
    aws_secret_access_key=None,
    s3_report_bucket=None,
    s3_report_path=None,
    s3_report_url=None,
    loki_endpoint=None,
    loki_user=None,
    loki_password=None,
    loki_proxy=None,
    current_status=None,
)


def _make_config(**overrides):
    base = dict(_CONFIG_DEFAULTS)
    base.update(overrides)
    return cep.RunConfig(**base)


def _make_ctx(config, omd_root, layers=()):
    return cep.RunContext(
        hostname=config.host_name,
        servicedescription=config.service_description,
        testname=f"{config.host_name}/{config.service_description}",
        testident="testident",
        container_name="testhost_Portfolio",
        start_time=0.0,
        started_str="0",
        timeout_deadline=0.0,
        result_dir=config.result_dir,
        omd_root=omd_root,
        pid_file="/tmp/cep.pid",
        layers=layers,
        config=config,
    )


def _tests_mount(cmd):
    """Return the podman --volume spec that mounts /home/pwuser/tests."""
    for i, tok in enumerate(cmd):
        if tok == "--volume" and ":/home/pwuser/tests:" in cmd[i + 1]:
            return cmd[i + 1]
    return None


def _opencode_config_mount(cmd):
    """Return the podman --volume spec that mounts the opencode overlay, or None."""
    marker = ":" + cep.OPENCODE_CONFIG_CONTAINER_PATH + ":"
    for i, tok in enumerate(cmd):
        if tok == "--volume" and marker in cmd[i + 1]:
            return cmd[i + 1]
    return None


def test_authoring_environ_passthrough_and_mount(tmp_path, monkeypatch):
    """--environ NAME=VALUE (explicit) and bare NAME (host-forwarded) reach the
    container in every mode (spec 023 FR-001). Like every container variable
    they are passed to podman as a bare `--env NAME`; the value lives only in
    build_env_vars(ctx), which becomes the podman process environment, so it
    never appears on the podman command line (FR-004, D1). --authoring
    switches the tests mount to the site-level dir, read-write."""
    omd_root = str(tmp_path)
    site = tmp_path / "etc" / "check_cep" / "tests" / "testhost"
    site.mkdir(parents=True)

    monkeypatch.setenv("GEMINI_API_KEY", "host-env-key-456")

    def bare_env_names(cmd):
        return [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "--env"]

    # (1) authoring + explicit --environ NAME=VALUE: value in the builder,
    # bare name on the command line
    cfg = _make_config(authoring=True, shell=True,
                        environ=[("OPENCODE_MODEL", "opencode/big-pickle")])
    ctx = _make_ctx(cfg, omd_root)
    env = cep.build_env_vars(ctx)
    cmd = cep.build_podman_command(ctx, "podman", env)
    assert env.get("OPENCODE_MODEL") == "opencode/big-pickle"
    assert "OPENCODE_MODEL" in bare_env_names(cmd)
    assert not any("opencode/big-pickle" in tok for tok in cmd)
    mount = _tests_mount(cmd)
    assert mount is not None and mount.endswith(":/home/pwuser/tests:rw,z")
    assert str(site) in mount, f"expected site-level mount, got {mount}"

    # (2) authoring + bare --environ NAME: the host value is resolved into the
    # builder; the command line carries only the name
    cfg = _make_config(authoring=True, shell=True,
                        environ=[("GEMINI_API_KEY", None)])
    ctx = _make_ctx(cfg, omd_root)
    env = cep.build_env_vars(ctx)
    cmd = cep.build_podman_command(ctx, "podman", env)
    assert env.get("GEMINI_API_KEY") == "host-env-key-456"
    assert "GEMINI_API_KEY" in bare_env_names(cmd)
    assert not any("host-env-key-456" in tok for tok in cmd), \
        "the value must not appear on the command line"

    # (3) authoring + no --environ at all: nothing extra injected (keyless
    # default is the normal path, not a degraded one)
    cfg = _make_config(authoring=True, shell=True)
    env = cep.build_env_vars(_make_ctx(cfg, omd_root))
    assert "GEMINI_API_KEY" not in env and "OPENCODE_API_KEY" not in env

    # (4) plain --shell and (5) scheduled run: --environ is active too
    # (spec 023 FR-001, SC-003 a) — present as bare names, values off argv
    for extra in ({"shell": True}, {}):
        cfg = _make_config(test_dir=str(tmp_path / "svc"),
                            environ=[("OPENCODE_API_KEY", "should-not-leak"),
                                     ("GEMINI_API_KEY", "should-not-leak-either")],
                            **extra)
        ctx = _make_ctx(cfg, omd_root)
        env = cep.build_env_vars(ctx)
        cmd = cep.build_podman_command(ctx, "podman", env)
        assert env["OPENCODE_API_KEY"] == "should-not-leak"
        assert {"OPENCODE_API_KEY", "GEMINI_API_KEY"} <= set(bare_env_names(cmd))
        assert not any("should-not-leak" in tok for tok in cmd)

    # (4)/(5) mounts: the layers are mounted read-only under
    # /home/pwuser/layers/; /home/pwuser/tests is built inside the container
    # (spec 023, SC-003 b)
    svc = tmp_path / "svc"
    svc.mkdir()
    for extra in ({"shell": True}, {}):
        cfg = _make_config(test_dir=str(svc), **extra)
        layers = tuple(cep.resolve_layers(cfg, omd_root, "testhost", "Portfolio", "0"))
        ctx = _make_ctx(cfg, omd_root, layers)
        cmd = cep.build_podman_command(ctx, "podman", cep.build_env_vars(ctx))
        assert _tests_mount(cmd) is None
        assert f"{svc}:/home/pwuser/layers/01:ro,z" in cmd


def test_opencode_config_overlay_mount_and_env(tmp_path):
    """--authoring --opencode-config FILE bind-mounts the host file next to
    the baked opencode.json (never over it) and sets OPENCODE_CONFIG to the
    container overlay path so opencode merges providers/models on top."""
    omd_root = str(tmp_path)
    site = tmp_path / "etc" / "check_cep" / "tests" / "testhost"
    site.mkdir(parents=True)
    overlay = tmp_path / "cep-providers.json"
    overlay.write_text('{"provider": {}}\n')

    cfg = _make_config(authoring=True, shell=True,
                       opencode_config=str(overlay))
    ctx = _make_ctx(cfg, omd_root)
    env = cep.build_env_vars(ctx)
    cmd = cep.build_podman_command(ctx, "podman", env)

    assert env.get("OPENCODE_CONFIG") == cep.OPENCODE_CONFIG_CONTAINER_PATH
    # Bare name on the command line; the value travels in the podman process
    # environment (spec 023 D1)
    assert any(cmd[i] == "--env" and cmd[i + 1] == "OPENCODE_CONFIG" for i in range(len(cmd) - 1))

    mount = _opencode_config_mount(cmd)
    assert mount is not None, f"expected overlay mount, cmd={cmd}"
    assert mount.startswith(str(overlay) + ":")
    assert mount.endswith(":" + cep.OPENCODE_CONFIG_CONTAINER_PATH + ":ro,z")
    assert not any(
        cmd[i] == "--volume"
        and ":/home/pwuser/.config/opencode/opencode.json:" in cmd[i + 1]
        for i in range(len(cmd) - 1)
    ), "must not replace the baked opencode.json"


def test_opencode_config_absent_injects_nothing(tmp_path):
    """Without --opencode-config, authoring injects neither OPENCODE_CONFIG
    nor an overlay mount."""
    omd_root = str(tmp_path)
    (tmp_path / "etc" / "check_cep" / "tests" / "testhost").mkdir(parents=True)
    cfg = _make_config(authoring=True, shell=True)
    ctx = _make_ctx(cfg, omd_root)
    env = cep.build_env_vars(ctx)
    cmd = cep.build_podman_command(ctx, "podman", env)
    assert "OPENCODE_CONFIG" not in env
    assert _opencode_config_mount(cmd) is None


def test_opencode_config_wins_over_environ(tmp_path):
    """--opencode-config sets OPENCODE_CONFIG after --environ, so a stray
    --environ OPENCODE_CONFIG=… cannot point opencode at an unmounted path."""
    omd_root = str(tmp_path)
    (tmp_path / "etc" / "check_cep" / "tests" / "testhost").mkdir(parents=True)
    overlay = tmp_path / "cep-providers.json"
    overlay.write_text("{}\n")
    cfg = _make_config(
        authoring=True, shell=True,
        opencode_config=str(overlay),
        environ=[("OPENCODE_CONFIG", "/tmp/not-the-overlay.json")],
    )
    env = cep.build_env_vars(_make_ctx(cfg, omd_root))
    assert env["OPENCODE_CONFIG"] == cep.OPENCODE_CONFIG_CONTAINER_PATH


def test_opencode_config_inert_outside_authoring(tmp_path):
    """Even if RunConfig carries opencode_config, non-authoring runs mount
    and inject nothing (same structural guard as --environ)."""
    overlay = tmp_path / "cep-providers.json"
    overlay.write_text("{}\n")
    cfg = _make_config(opencode_config=str(overlay),
                       test_dir=str(tmp_path / "svc"))
    ctx = _make_ctx(cfg, str(tmp_path))
    env = cep.build_env_vars(ctx)
    cmd = cep.build_podman_command(ctx, "podman", env)
    assert "OPENCODE_CONFIG" not in env
    assert _opencode_config_mount(cmd) is None


# --- Subprocess helpers for the refusal / warning paths --------------------

def _fake_podman(tmp_path):
    """Create a fake `podman` on a bin dir; returns the PATH-prefixed dir.

    Responds to `podman info` with minimal cgroup-v1 YAML and exits 0 for any
    other subcommand (run/rm/...), so main() completes without a real
    container.
    """
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(exist_ok=True)
    podman = bin_dir / "podman"
    podman.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  info) printf "host:\\n  cgroupVersion: v1\\n" ;;\n'
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    podman.chmod(0o755)
    return str(bin_dir)


def _run_authoring(tmp_path, extra_args, extra_env=None, authoring=True):
    omd_root = tmp_path / "omd"
    omd_root.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items()}
    env.pop("GEMINI_API_KEY", None)
    env.pop("OPENCODE_API_KEY", None)
    env["OMD_ROOT"] = str(omd_root)
    env["PATH"] = _fake_podman(tmp_path) + os.pathsep + env["PATH"]
    if extra_env:
        env.update(extra_env)
    cmd = [
        "python3", str(CEP_PLUGIN),
        "--host-name", "testhost",
        "--service-description", "Portfolio",
        "--image", "check_cep:ai",
        "--probe-location", "local",
    ]
    if authoring:
        cmd.append("--authoring")
    cmd += extra_args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    return proc.stdout + proc.stderr, proc.returncode


def test_authoring_refuses_s3(tmp_path):
    """--authoring --test-source s3 exits 3 with an actionable message."""
    out, code = _run_authoring(tmp_path, ["--test-source", "s3"])
    assert code == 3, out
    assert "authoring works on a local site workspace" in out
    assert "test-source s3" in out


def test_authoring_refuses_missing_workspace(tmp_path):
    """--authoring against a non-existent workspace exits 3, naming the dir."""
    out, code = _run_authoring(tmp_path, [])  # no site dir created under OMD_ROOT
    assert code == 3, out
    assert "workspace does not exist" in out
    assert "etc/check_cep/tests/testhost" in out


def test_authoring_keyless_starts_without_warning(tmp_path):
    """--authoring with no --environ at all (the default, keyless free-tier
    path) still starts cleanly (exit 0 via fake podman) with no credential
    warning — keyless is the normal path, not a degraded one (spec 022)."""
    site = tmp_path / "omd" / "etc" / "check_cep" / "tests" / "testhost"
    site.mkdir(parents=True)
    result_dir = tmp_path / "results"
    out, code = _run_authoring(
        tmp_path,
        ["--result-dir", str(result_dir)],
    )
    assert code == 0, out
    assert "WARNING" not in out


def test_authoring_environ_bare_missing_host_var_exits_3(tmp_path):
    """Bare `--environ NAME` with an unset host var is a usage error, exit 3,
    before any container starts (contracts §5)."""
    site = tmp_path / "omd" / "etc" / "check_cep" / "tests" / "testhost"
    site.mkdir(parents=True)
    out, code = _run_authoring(tmp_path, ["--environ", "TOTALLY_UNSET_VAR_XYZ"])
    assert code == 3, out
    assert "TOTALLY_UNSET_VAR_XYZ" in out


def test_authoring_environ_invalid_name_exits_3(tmp_path):
    """A malformed --environ variable name is a usage error, exit 3."""
    out, code = _run_authoring(tmp_path, ["--environ", "not a valid name=x"])
    assert code == 3, out


def test_environ_outside_authoring_is_active(tmp_path):
    """--environ without --authoring is active since spec 023 (FR-001, SC-003 a):
    no warning, the run starts normally (the injection itself is verified in
    test_environ_injection.py)."""
    (tmp_path / "omd" / "etc" / "check_cep" / "tests" / "testhost" / "Portfolio").mkdir(parents=True)
    out, code = _run_authoring(
        tmp_path,
        ["--environ", "OPENCODE_MODEL=opencode/big-pickle",
         "--result-dir", str(tmp_path / "results")],
        authoring=False,
    )
    assert code == 0, out
    assert "only takes effect with --authoring" not in out


def test_opencode_config_outside_authoring_warns_and_ignored(tmp_path):
    """--opencode-config without --authoring prints a warning and does not
    fail the run (safe default for templated commands)."""
    overlay = tmp_path / "cep-providers.json"
    overlay.write_text("{}\n")
    # The service's test directory must exist: since spec 023 a missing one
    # is UNKNOWN before the container starts.
    (tmp_path / "omd" / "etc" / "check_cep" / "tests" / "testhost" / "Portfolio").mkdir(parents=True)
    out, code = _run_authoring(
        tmp_path,
        ["--opencode-config", str(overlay), "--result-dir", str(tmp_path / "results")],
        authoring=False,
    )
    assert code == 0, out
    assert "only takes effect with --authoring" in out


def test_opencode_config_missing_file_exits_3(tmp_path):
    """--authoring --opencode-config pointing at a missing file is a usage
    error (exit 3) before any container starts."""
    site = tmp_path / "omd" / "etc" / "check_cep" / "tests" / "testhost"
    site.mkdir(parents=True)
    missing = tmp_path / "no-such-providers.json"
    out, code = _run_authoring(
        tmp_path,
        ["--opencode-config", str(missing)],
    )
    assert code == 3, out
    assert "not a file" in out
    assert str(missing) in out or "no-such-providers.json" in out
