"""Unit tests for --environ handling and the container environment (spec 023 US1).

FR-001/FR-003/FR-004/FR-006/FR-007/FR-008/FR-011/FR-012/FR-048 and design
decision D1: build_env_vars() is the single builder of the container
environment; every name reaches podman bare (`--env NAME`), values only via
the podman process environment.
"""
import pytest

from conftest import _cep_mod as cep, make_config, make_ctx

build_env_vars = cep.build_env_vars
build_podman_command = cep.build_podman_command
parse_environ_arg = cep.parse_environ_arg

DISPLAY_NAMES = {"DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"}


def _argv(ctx):
    return build_podman_command(ctx, "podman", build_env_vars(ctx))


def _env_names(argv):
    return [argv[i + 1] for i, tok in enumerate(argv) if tok == "--env"]


@pytest.fixture
def x11(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")


# ---------------------------------------------------------------------------
# (a)-(c) reserved names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["TEST_SOURCE=s3", "NAGIOS_FOO=1", "AWS_REGION=x",
                                 "TEST_ARTIFACT_LAYERS=x", "LOKI_X", "S3_X=1"])
def test_reserved_names_rejected(raw, monkeypatch):
    monkeypatch.delenv("LOKI_X", raising=False)
    with pytest.raises(ValueError, match="reserved"):
        parse_environ_arg(raw)


@pytest.mark.parametrize("raw", ["OPENCODE_CONFIG=x", "APP_PASSWORD="])
def test_allowed_names(raw):
    name, value = parse_environ_arg(raw)
    assert name == raw.split("=")[0]


def test_reserved_tables_are_exact():
    assert cep.RESERVED_ENV_NAMES == frozenset(
        "TEST_SOURCE RESULT_DEST LOGGING PWTIMEOUT PROBE_LOCATION TESTIDENT TERM "
        "FORCE_COLOR CEP_STARTED DEBUG HEADED BROWSER REPORT_PATH CEP_SLOW_MO "
        "CEP_VISION_HIGHLIGHT_MS CEP_PLUGIN_VERSION".split())
    assert len(cep.RESERVED_ENV_NAMES) == 16
    assert cep.RESERVED_ENV_PREFIXES == ("NAGIOS_", "TEST_ARTIFACT", "S3_", "AWS_", "LOKI_")


def _is_reserved(name):
    return name in cep.RESERVED_ENV_NAMES or name.startswith(cep.RESERVED_ENV_PREFIXES)


def test_drift_guard_every_builder_key_is_reserved(monkeypatch, x11, tmp_path):
    """G1: a new infrastructure variable must be added to the reserved tables."""
    monkeypatch.setenv("CEP_SLOW_MO", "400")
    monkeypatch.setenv("CEP_VISION_HIGHLIGHT_MS", "2000")
    layer_dir = tmp_path / "layer"
    layer_dir.mkdir()
    config = make_config(
        debug=True, headed=True, test_source="s3", result_dest="s3",
        test_artifacts=("/b/k.tgz",), s3_endpoint="http://s3", aws_access_key_id="AKIAX",
        aws_secret_access_key="sekrit", s3_report_bucket="rb", s3_report_path="%h",
        logging="loki", loki_endpoint="http://loki", loki_user="u", loki_password="lokipw",
        loki_proxy="http://p", current_status="OK", environ=[])
    ctx = make_ctx(config=config)
    if "layers" in cep.RunContext.__dataclass_fields__:
        ctx = make_ctx(config=config, layers=(cep.Layer(1, str(layer_dir), "directory",
                                                        "/home/pwuser/layers/01"),))
    unreserved = {k for k in build_env_vars(ctx) if not _is_reserved(k)}
    assert unreserved <= DISPLAY_NAMES | {"OPENCODE_CONFIG"}, unreserved


# ---------------------------------------------------------------------------
# (d)-(g) the single builder and bare argv
# ---------------------------------------------------------------------------

def _assert_bare(argv, ctx, *secrets):
    names = _env_names(argv)
    assert all("=" not in n for n in names), names
    assert len(names) == len(set(names)), names
    assert set(names) == set(build_env_vars(ctx).keys())
    for secret in secrets:
        assert not any(secret in tok for tok in argv), secret


def test_scheduled_environ_values_in_builder_not_argv(monkeypatch):
    monkeypatch.setenv("TOKEN", "tok")
    ctx = make_ctx(config=make_config(environ=[("APP_PASSWORD", "s3cret"), ("TOKEN", None)]))
    env = build_env_vars(ctx)
    assert all(isinstance(v, str) for v in env.values())
    assert env["APP_PASSWORD"] == "s3cret"
    assert env["TOKEN"] == "tok"
    _assert_bare(_argv(ctx), ctx, "s3cret", "tok")


@pytest.mark.parametrize("mode", ["shell", "headed", "vnc", "authoring"])
def test_all_modes_bare(monkeypatch, x11, tmp_path, mode):
    monkeypatch.setenv("TOKEN", "tok")
    ctx = make_ctx(omd_root=str(tmp_path), config=make_config(
        environ=[("APP_PASSWORD", "s3cret"), ("TOKEN", None)], **{mode: True}))
    env = build_env_vars(ctx)
    assert env["APP_PASSWORD"] == "s3cret" and env["TOKEN"] == "tok"
    _assert_bare(_argv(ctx), ctx, "s3cret", "tok")


def test_repeated_name_last_wins():
    ctx = make_ctx(config=make_config(environ=[("A", "1"), ("A", "2")]))
    assert build_env_vars(ctx)["A"] == "2"
    assert _env_names(_argv(ctx)).count("A") == 1


def test_opencode_overlay_wins(tmp_path):
    ctx = make_ctx(omd_root=str(tmp_path), config=make_config(
        authoring=True, shell=True, opencode_config="/x/providers.json",
        environ=[("OPENCODE_CONFIG", "other")]))
    assert build_env_vars(ctx)["OPENCODE_CONFIG"] == cep.OPENCODE_CONFIG_CONTAINER_PATH
    assert _env_names(_argv(ctx)).count("OPENCODE_CONFIG") == 1


# ---------------------------------------------------------------------------
# (h) no implicit forwarding, (i) FR-011 flags and spectate
# ---------------------------------------------------------------------------

def test_no_implicit_forwarding(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "leak")
    ctx = make_ctx(config=make_config(environ=[("APP_PASSWORD", "s3cret")]))
    assert "GEMINI_API_KEY" not in _env_names(_argv(ctx))


@pytest.mark.parametrize("mode", [None, "shell", "headed", "vnc", "authoring"])
def test_proxy_and_env_host_disabled(x11, tmp_path, mode):
    overrides = {mode: True} if mode else {}
    ctx = make_ctx(omd_root=str(tmp_path), config=make_config(**overrides))
    argv = _argv(ctx)
    image_at = argv.index(ctx.config.image)
    for flag in ("--http-proxy=false", "--env-host=false"):
        assert argv.count(flag) == 1
        assert argv.index(flag) < image_at


def test_spectate_x11_plugin_display_wins(monkeypatch, x11):
    monkeypatch.setenv("CEP_SLOW_MO", "400")
    monkeypatch.setenv("CEP_VISION_HIGHLIGHT_MS", "2000")
    ctx = make_ctx(config=make_config(headed=True, environ=[("DISPLAY", ":9")]))
    env = build_env_vars(ctx)
    assert env["DISPLAY"] == ":0"
    assert env["CEP_SLOW_MO"] == "400"
    assert env["CEP_VISION_HIGHLIGHT_MS"] == "2000"
    argv = _argv(ctx)
    assert "/tmp/.X11-unix:/tmp/.X11-unix:ro" in argv
    assert _env_names(argv).count("DISPLAY") == 1
    assert any(tok.startswith("--userns=keep-id:") for tok in argv)
    assert "--http-proxy=false" in argv and "--env-host=false" in argv


def test_spectate_wayland(monkeypatch, tmp_path):
    monkeypatch.setattr(cep, "detect_display_server", lambda: "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    ctx = make_ctx(config=make_config(headed=True))
    env = build_env_vars(ctx)
    assert env["WAYLAND_DISPLAY"] == "wayland-0"
    assert env["XDG_RUNTIME_DIR"] == str(tmp_path)
    argv = _argv(ctx)
    sock = str(tmp_path / "wayland-0")
    assert f"{sock}:{sock}:ro" in argv


def test_spectate_vnc():
    ctx = make_ctx(config=make_config(vnc=True))
    argv = _argv(ctx)
    assert "127.0.0.1:5900:5900" in argv
    assert build_env_vars(ctx)["HEADED"] == "1"


# ---------------------------------------------------------------------------
# (j) FR-012 credential cloaking
# ---------------------------------------------------------------------------

def test_credentials_never_in_argv():
    ctx = make_ctx(config=make_config(
        test_source="s3", test_artifacts=("/b/k.tgz",), s3_endpoint="http://s3",
        aws_access_key_id="AKIAX", aws_secret_access_key="sekrit",
        logging="loki", loki_endpoint="http://loki", loki_password="lokipw"))
    env = build_env_vars(ctx)
    assert env["AWS_ACCESS_KEY_ID"] == "AKIAX"
    assert env["AWS_SECRET_ACCESS_KEY"] == "sekrit"
    assert env["LOKI_PASSWORD"] == "lokipw"
    _assert_bare(_argv(ctx), ctx, "AKIAX", "sekrit", "lokipw")


def test_registry_login_password_via_stdin(monkeypatch):
    calls = []

    class _Proc:
        returncode, stdout, stderr = 0, b"", b""

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return _Proc()

    monkeypatch.setattr(cep.subprocess, "run", fake_run)
    cep.retry_with_auth("podman", ["podman", "run", "reg.io/x:1"], "reg.io/x:1", "USER", "regpw",
                        env={"A": "1"})
    login_cmd, login_kw = calls[0]
    assert login_cmd == ["podman", "login", "-u", "USER", "--password-stdin", "reg.io"]
    assert login_kw["input"] == b"regpw"
    assert not any("regpw" in tok for cmd, _ in calls for tok in cmd)
    assert calls[1][1]["env"] == {"A": "1"}


def test_vnc_drops_user_display_variables():
    """--vnc brings its own X server; a user DISPLAY must not suppress it (FR-048)."""
    ctx = make_ctx(config=make_config(vnc=True, environ=[("DISPLAY", ":9"), ("WAYLAND_DISPLAY", "w")]))
    env = build_env_vars(ctx)
    assert "DISPLAY" not in env and "WAYLAND_DISPLAY" not in env
    assert "DISPLAY" not in _env_names(_argv(ctx))


# ---------------------------------------------------------------------------
# spec 024: plugin version passed into every container (C-2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", [None, "shell", "headed", "vnc", "authoring"])
def test_plugin_version_in_every_mode(x11, tmp_path, mode):
    overrides = {mode: True} if mode else {}
    ctx = make_ctx(omd_root=str(tmp_path), config=make_config(**overrides))
    assert build_env_vars(ctx)["CEP_PLUGIN_VERSION"] == cep.CEP_VERSION
    assert "CEP_PLUGIN_VERSION" in _env_names(_argv(ctx))


def test_plugin_version_is_reserved():
    with pytest.raises(ValueError, match="reserved"):
        parse_environ_arg("CEP_PLUGIN_VERSION=x")
