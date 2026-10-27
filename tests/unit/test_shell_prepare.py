"""--shell builds the check root before the prompt (spec 023 US6, FR-032)."""
import importlib.util
from pathlib import Path

from conftest import _cep_mod as cep, make_config, make_ctx

_RUN_PY = Path(__file__).parent.parent.parent / "src" / "container" / "image" / "run.py"


def _argv(ctx):
    return cep.build_podman_command(ctx, "podman", cep.build_env_vars(ctx))


def test_shell_prepares_tree_then_execs_bash():
    layer = cep.Layer(1, "/abs/a", "directory", "/home/pwuser/layers/01")
    ctx = make_ctx(config=make_config(shell=True), layers=(layer,))
    argv = _argv(ctx)
    assert argv[-5:] == ["--entrypoint", "bash", ctx.config.image, "-c",
                         "python3 /home/pwuser/run.py --prepare-only && exec bash -i"]
    assert "--tty" in argv and "--interactive" in argv
    assert "/abs/a:/home/pwuser/layers/01:ro,z" in argv


def test_authoring_shell_unchanged(tmp_path):
    ctx = make_ctx(omd_root=str(tmp_path), config=make_config(shell=True, authoring=True))
    argv = _argv(ctx)
    assert argv[-3:] == ["--entrypoint", "bash", ctx.config.image]
    assert "-c" not in argv
    assert any(tok.endswith(":/home/pwuser/tests:rw,z") for tok in argv)


def test_scheduled_run_has_no_entrypoint():
    argv = _argv(make_ctx())
    assert argv[-1] == make_ctx().config.image
    assert "--entrypoint" not in argv


def test_run_py_parses_prepare_only():
    spec = importlib.util.spec_from_file_location("run_mod_shell", str(_RUN_PY))
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    assert run.parse_run_args(["--prepare-only"]).prepare_only is True
