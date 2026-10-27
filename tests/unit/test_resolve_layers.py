"""Unit tests for host-side layer resolution and mounts (spec 023 US2/US4:
FR-020, FR-025, FR-028, FR-029, FR-031; data-model §2; contracts/cli.md §1)."""
import json
import tarfile

import pytest

from conftest import _cep_mod as cep, make_config, make_ctx

Layer = cep.Layer
resolve_layers = cep.resolve_layers


def _resolve(tmp_path, *artifacts, **overrides):
    config = make_config(test_artifacts=tuple(str(a) for a in artifacts), **overrides)
    return resolve_layers(config, str(tmp_path), "web01", "Login", "1700000000")


def _tgz(path):
    with tarfile.open(path, "w:gz"):
        pass
    return path


def test_dirs_and_archive(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    c = _tgz(tmp_path / "c.tgz")
    layers = _resolve(tmp_path, a, b, c)
    assert layers == [
        Layer(1, str(a), "directory", "/home/pwuser/layers/01"),
        Layer(2, str(b), "directory", "/home/pwuser/layers/02"),
        Layer(3, str(c), "archive", "/home/pwuser/layers/03.tgz"),
    ]


def test_tar_gz_is_archive(tmp_path):
    t = _tgz(tmp_path / "x.tar.gz")
    assert _resolve(tmp_path, t)[0].type == "archive"


def test_relative_path_made_absolute(tmp_path, monkeypatch):
    (tmp_path / "rel").mkdir()
    monkeypatch.chdir(tmp_path)
    assert _resolve(tmp_path, "rel")[0].host_path == str(tmp_path / "rel")


def test_missing_path(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    with pytest.raises(ValueError, match=rf"^--test-artifact #2 \({tmp_path}/nope\): does not exist$"):
        _resolve(tmp_path, a, tmp_path / "nope")


def test_unsupported_type(tmp_path):
    z = tmp_path / "x.zip"
    z.write_bytes(b"PK")
    with pytest.raises(ValueError, match="must be a directory or a .tgz/.tar.gz file"):
        _resolve(tmp_path, z)


def test_implicit_default(tmp_path):
    default = tmp_path / "etc" / "check_cep" / "tests" / "web01" / "Login"
    default.mkdir(parents=True)
    assert _resolve(tmp_path) == [Layer(1, str(default), "directory", "/home/pwuser/layers/01")]


def test_implicit_default_missing(tmp_path):
    expected = tmp_path / "etc" / "check_cep" / "tests" / "web01" / "Login"
    with pytest.raises(ValueError, match=rf"^test directory \({expected}\) does not exist$"):
        _resolve(tmp_path)


def test_test_dir_is_one_layer(tmp_path):
    d = tmp_path / "legacy"
    d.mkdir()
    assert _resolve(tmp_path, test_dir=str(d))[0].host_path == str(d)


# ---------------------------------------------------------------------------
# US4: %h/%s templates (FR-031)
# ---------------------------------------------------------------------------

def test_template_dir(tmp_path):
    d = tmp_path / "web01" / "Login"
    d.mkdir(parents=True)
    assert _resolve(tmp_path, tmp_path / "%h" / "%s")[0].host_path == str(d)


def test_template_archive(tmp_path):
    (tmp_path / "web01").mkdir()
    t = _tgz(tmp_path / "web01" / "Login.tgz")
    layer = _resolve(tmp_path, f"{tmp_path}/%h/%s.tgz")[0]
    assert (layer.host_path, layer.type) == (str(t), "archive")


def test_template_missing_shows_resolved_path(tmp_path):
    with pytest.raises(ValueError) as exc:
        _resolve(tmp_path, tmp_path / "%h" / "%s")
    assert f"{tmp_path}/web01/Login" in str(exc.value)
    assert "%h" not in str(exc.value)


def test_template_service_with_spaces(tmp_path):
    config = make_config(test_artifacts=(f"{tmp_path}/%h/%s",))
    expected = cep.resolve_path_template(f"{tmp_path}/%h/%s", "web01", "Login Page")
    (tmp_path / "web01" / "Login Page").mkdir(parents=True)
    layers = resolve_layers(config, str(tmp_path), "web01", "Login Page", "1")
    assert layers[0].host_path == expected


# ---------------------------------------------------------------------------
# env handoff and mounts
# ---------------------------------------------------------------------------

def test_env_carries_layer_json(tmp_path):
    layer = Layer(1, "/abs/a", "directory", "/home/pwuser/layers/01")
    env = cep.build_env_vars(make_ctx(layers=(layer,)))
    assert json.loads(env["TEST_ARTIFACT_LAYERS"]) == [
        {"position": 1, "host_path": "/abs/a", "type": "directory",
         "container_path": "/home/pwuser/layers/01"}]
    assert "TEST_ARTIFACT" not in env


def test_mounts_layers_readonly(tmp_path):
    layers = (Layer(1, "/abs/a", "directory", "/home/pwuser/layers/01"),
              Layer(2, "/abs/b.tgz", "archive", "/home/pwuser/layers/02.tgz"))
    ctx = make_ctx(layers=layers)
    cmd = cep.build_podman_command(ctx, "podman", cep.build_env_vars(ctx))
    volumes = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "--volume"]
    assert "/abs/a:/home/pwuser/layers/01:ro,z" in volumes
    assert "/abs/b.tgz:/home/pwuser/layers/02.tgz:ro,z" in volumes
    assert not any(":/home/pwuser/tests:" in v for v in volumes)
    assert not any("input-artifact" in v for v in volumes)


# ---------------------------------------------------------------------------
# select_layers: S3 and authoring rules (FR-028, FR-029)
# ---------------------------------------------------------------------------

def test_s3_more_than_one_artifact(tmp_path):
    config = make_config(test_source="s3", test_artifacts=("/b/a.tgz", "/b/c.tgz"))
    with pytest.raises(ValueError, match=r"--test-source s3 supports exactly one --test-artifact \(got 2\)"):
        cep.select_layers(config, str(tmp_path), "h", "s", "1")


def test_s3_single_artifact_no_layers(tmp_path):
    config = make_config(test_source="s3", test_artifacts=("/b/a.tgz",))
    assert cep.select_layers(config, str(tmp_path), "h", "s", "1") == ()


def test_authoring_ignores_artifacts_with_warning(tmp_path, capsys):
    config = make_config(authoring=True, shell=True, test_artifacts=("/x", "/y"))
    assert cep.select_layers(config, str(tmp_path), "h", "s", "1") == ()
    assert "WARNING: --authoring ignores --test-artifact (2 given)" in capsys.readouterr().err
