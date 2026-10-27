"""--environ secret injection end to end (spec 023 US1, quickstart Scenario 1).

The value reaches the test, never appears in the podman argv, the --debug
output or the Nagios output, and the container environment consists of
exactly the image defaults, check_cep's infrastructure variables and the
--environ names (FR-011).
"""
import json
import os
import subprocess

from conftest import (CEP_IMAGE, _mod as cep, local_test_dir, run_check_cep)

ODD_VALUE = 'a b "c" \'d\' e=f\ng'


def _run(tmp_path, test_env, write_playwright_config, extra=(), env=None):
    test_dir = local_test_dir(tmp_path, "tc_environ", write_playwright_config)
    return run_check_cep(test_dir, test_env["result_dir"], extra_args=list(extra), env=env)


def test_bare_environ(tmp_path, test_env, write_playwright_config):
    output, code = _run(tmp_path, test_env, write_playwright_config,
                        ["--environ", "APP_PASSWORD"], env={"APP_PASSWORD": "s3cret"})
    assert code == 0, output
    assert output.startswith("OK -")
    assert "only takes effect with --authoring" not in output


def test_explicit_environ_debug_hides_value(tmp_path, test_env, write_playwright_config):
    output, code = _run(tmp_path, test_env, write_playwright_config,
                        ["--environ", "APP_PASSWORD=s3cret", "--debug"])
    assert code == 0, output
    assert "s3cret" not in output
    # (6) the logged podman command names the variable but carries no value
    cmd_lines = [l for l in output.splitlines() if "running command:" in l]
    assert cmd_lines and "--env APP_PASSWORD" in cmd_lines[0]


def test_leaked_secret_is_masked(tmp_path, test_env, write_playwright_config):
    output, code = _run(tmp_path, test_env, write_playwright_config,
                        ["--environ", "APP_PASSWORD=s3cret",
                         "--environ", "CEP_LEAK_CHECK=leakcheck-on"])
    assert code == 2, output
    assert output.startswith("CRITICAL -")
    assert "***" in output
    assert "s3cret" not in output


def test_reserved_name_rejected_before_container(tmp_path, test_env, write_playwright_config):
    output, code = _run(tmp_path, test_env, write_playwright_config,
                        ["--environ", "TEST_SOURCE=s3"])
    assert code == 3, output
    assert "reserved" in output
    ps = subprocess.run(["podman", "ps", "-a", "--filter", "name=testhost_pytest_test",
                         "--format", "{{.Names}}"], capture_output=True, text=True)
    assert ps.stdout.strip() == ""


def test_bare_unset_is_unknown(tmp_path, test_env, write_playwright_config):
    env = {k: v for k, v in os.environ.items() if k != "CEP_UNSET_VAR"}
    output, code = _run(tmp_path, test_env, write_playwright_config,
                        ["--environ", "CEP_UNSET_VAR"], env=env)
    assert code == 3, output


def test_no_implicit_forwarding(tmp_path, test_env, write_playwright_config):
    output, code = _run(tmp_path, test_env, write_playwright_config,
                        ["--environ", "APP_PASSWORD"],
                        env={"APP_PASSWORD": "s3cret", "GEMINI_API_KEY": "leak"})
    assert code == 0, output
    assert "leak" not in output


def test_odd_value_explicit(tmp_path, test_env, write_playwright_config):
    output, code = _run(tmp_path, test_env, write_playwright_config,
                        ["--environ", "APP_PASSWORD=s3cret", "--environ", f"CEP_ODD_VALUE={ODD_VALUE}"])
    assert code == 0, output


def test_odd_value_bare(tmp_path, test_env, write_playwright_config):
    output, code = _run(tmp_path, test_env, write_playwright_config,
                        ["--environ", "APP_PASSWORD=s3cret", "--environ", "CEP_ODD_VALUE"],
                        env={"CEP_ODD_VALUE": ODD_VALUE})
    assert code == 0, output


# ---------------------------------------------------------------------------
# FR-011: the container environment has exactly three sources
# ---------------------------------------------------------------------------

def _container_env_names(tmp_path, environ):
    """Run the image's `env` through the real check_cep argv; return printed names."""
    config = cep.RunConfig(**{**_config_defaults(tmp_path), "environ": environ})
    ctx = _ctx(config, tmp_path)
    env_vars = cep.build_env_vars(ctx)
    argv = cep.build_podman_command(ctx, "podman", env_vars)
    image_at = argv.index(config.image)
    argv = argv[:image_at] + ["--entrypoint", "env"] + argv[image_at:]
    host = {**os.environ, "CEP_HOST_ONLY": "x", "http_proxy": "http://p:3128",
            "HTTPS_PROXY": "http://p:3128", "NO_PROXY": "localhost"}
    proc = subprocess.run(argv, env={**host, **env_vars}, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL,
                          timeout=120)
    assert proc.returncode == 0, proc.stderr
    names = {line.split("=", 1)[0] for line in proc.stdout.splitlines() if "=" in line}
    return names, env_vars


def _image_env_names():
    out = subprocess.run(["podman", "image", "inspect", "--format", "{{json .Config.Env}}",
                          CEP_IMAGE], capture_output=True, text=True, check=True).stdout
    return {entry.split("=", 1)[0] for entry in json.loads(out)}


def _config_defaults(tmp_path):
    from test_modes import _CONFIG_DEFAULTS
    results = tmp_path / "res"
    results.mkdir(exist_ok=True)
    tests = tmp_path / "tests_in"
    tests.mkdir(exist_ok=True)
    return {**_CONFIG_DEFAULTS, "image": CEP_IMAGE, "result_dir": str(results),
            "test_dir": str(tests)}


def _ctx(config, tmp_path):
    from test_modes import _make_ctx
    return _make_ctx(config, str(tmp_path))


def _expected(env_vars, image_names):
    expected = image_names | {"container", "HOSTNAME", "HOME"} | set(env_vars)
    if "PATH" not in image_names:
        expected.add("PATH")
    return expected


def test_container_env_is_exactly_three_sources(tmp_path):
    names, env_vars = _container_env_names(tmp_path, [("APP_PASSWORD", "s3cret")])
    expected = _expected(env_vars, _image_env_names())
    assert names == expected, (f"extra: {sorted(names - expected)}, "
                               f"missing: {sorted(expected - names)}")
    assert not {"CEP_HOST_ONLY", "http_proxy", "HTTPS_PROXY", "NO_PROXY"} & names


def test_proxy_opt_in(tmp_path):
    names, env_vars = _container_env_names(tmp_path, [("HTTPS_PROXY", None)])
    assert "HTTPS_PROXY" in names
    assert "http_proxy" not in names
