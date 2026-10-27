"""Unit tests for output masking (spec 023 FR-009, FR-012, R-13, design D4).

One choke point per channel: nagios_exit() for stdout, MaskingFilter for the
check_cep logger, and a masked copy of container output for --debug
forwarding. Perfdata and protocol parsing are never masked.
"""
import io
import logging

import pytest

from conftest import _cep_mod as cep, make_config, make_ctx
from test_exit_status import main_env  # noqa: F401  (pytest fixture)


@pytest.fixture(autouse=True)
def reset_masks():
    cep.set_mask_values([])
    yield
    cep.set_mask_values([])


def test_longest_first_and_empty_ignored():
    cep.set_mask_values(["s3", "s3cret", ""])
    assert cep.mask_secrets("a s3cret b s3") == "a *** b ***"


def test_set_replaces_previous_values():
    cep.set_mask_values(["old"])
    cep.set_mask_values(["new"])
    assert cep.mask_secrets("old new") == "old ***"


def test_nagios_exit_masks_text_not_perfdata(capsys):
    cep.set_mask_values(["s3cret"])
    rc = cep.nagios_exit("CRITICAL", "x s3cret", "'lbl_s3cret'=1ms", "long s3cret")
    assert rc == 2
    assert capsys.readouterr().out == "CRITICAL - x *** | 'lbl_s3cret'=1ms\nlong ***\n"


@pytest.mark.parametrize("value", ["with space", 'q"uo\'te', "a=b", "line1\nline2"])
def test_odd_values_masked(value):
    cep.set_mask_values([value])
    assert cep.mask_secrets(f"<{value}>") == "<***>"


def test_masking_filter_masks_record_and_clears_args():
    cep.set_mask_values(["s3cret"])
    ctx = make_ctx(config=make_config(environ=[("APP_PASSWORD", "s3cret")]))
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    seen = []

    class Capture(logging.Handler):
        def emit(self, record):
            seen.append(record)

    log = logging.getLogger("check_cep_masking_test")
    log.setLevel(logging.DEBUG)
    log.addFilter(cep.MaskingFilter())
    log.addHandler(handler)
    log.addHandler(capture := Capture())
    try:
        log.debug("RunContext: %s", ctx)
    finally:
        log.removeHandler(handler)
        log.removeHandler(capture)
    assert "s3cret" not in stream.getvalue()
    assert "***" in stream.getvalue()
    assert "APP_PASSWORD" in stream.getvalue()
    assert seen[0].args == ()


def test_config_repr_hides_credentials():
    config = make_config(registry_password="regpw", aws_access_key_id="AKIAX",
                         aws_secret_access_key="sekrit", loki_password="lokipw")
    text = repr(config)
    for secret in ("regpw", "AKIAX", "sekrit", "lokipw"):
        assert secret not in text


def test_mask_values_include_credentials_and_bare_environ(monkeypatch):
    monkeypatch.setenv("TOKEN", "tok")
    config = make_config(environ=[("APP_PASSWORD", "s3cret"), ("TOKEN", None), ("EMPTY", "")],
                         aws_access_key_id="AKIAX", aws_secret_access_key="sekrit",
                         loki_password="lokipw", registry_password="regpw")
    assert set(cep.mask_values(config)) == {"s3cret", "tok", "AKIAX", "sekrit", "lokipw", "regpw"}


def test_plugin_credentials_masked_in_output(capsys):
    config = make_config(aws_secret_access_key="sekrit", loki_password="lokipw")
    cep.set_mask_values(cep.mask_values(config))
    cep.nagios_exit("UNKNOWN", "x sekrit", "", "lokipw")
    assert capsys.readouterr().out == "UNKNOWN - x ***\n***\n"


def test_protocol_parsing_sees_unmasked_output(main_env, capsys):  # noqa: F811
    """A secret that collides with protocol text must not break classification."""
    rc = main_env((b"Test timeout of 30000ms exceeded\n", b"took 30000ms\n", 2),
                  extra=("--environ", "X=30000", "--debug"))
    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out.startswith("CRITICAL - test svc timed out")
    assert "took ***ms" in captured.err
    assert "30000" not in captured.err


def test_html_escaped_form_is_masked():
    config = make_config(environ=[("APP_PASSWORD", 'pa"ss<1>')])
    cep.set_mask_values(cep.mask_values(config))
    shown = cep.sanitize_output('error: expected pa"ss<1>'.encode())
    assert cep.mask_secrets(shown) == "error: expected ***"
