"""Perfdata label generation (spec 023 FR-051, SC-007, research R-12).

The first block pins the labels existing layouts produce today (FR-060):
they must stay byte-identical. The second block covers the new layouts.
"""
import pytest

from conftest import _cep_mod as cep


def _labels(steps):
    perfdata = cep.extract_perfdata_from_steps(steps)
    perfdata.extend(cep.extract_nagios_perfdata_from_stdout(steps))
    perfdata = cep.normalize_perfdata_labels(perfdata)
    if hasattr(cep, "ensure_unique_labels"):
        perfdata = cep.ensure_unique_labels(perfdata)
    return [p["label"] for p in perfdata]


def _result(steps=(), duration=100):
    return {"duration": duration, "steps": [{"title": t, "duration": 5, "steps": []} for t in steps]}


def _test(project="chromium", steps=(), annotations=()):
    return {"projectName": project, "results": [_result(steps)], "annotations": list(annotations)}


def _spec(title, tests):
    return {"title": title, "tests": tests}


def _suite(title, specs):
    return {"title": title, "specs": specs, "suites": []}


def _steps(*suites):
    return {"suites": list(suites)}


# ---------------------------------------------------------------------------
# Pinned legacy labels (T040) — must never change
# ---------------------------------------------------------------------------

LEGACY_CASES = {
    "one_test_ts_suite": (
        _steps(_suite("login.test.ts", [_spec("logs in", [_test(steps=["open page", "submit"])])])),
        ["OpenPage", "Submit", "TestDuration"],
    ),
    "two_test_ts_suites": (
        _steps(_suite("a.test.ts", [_spec("first", [_test(steps=["go"])])]),
               _suite("b.test.ts", [_spec("second", [_test(steps=["go"])])])),
        ["AFirstGo", "AFirst_test_duration", "BSecondGo", "BSecond_test_duration"],
    ),
    "two_test_js_suites_unstripped": (
        _steps(_suite("a.test.js", [_spec("first", [_test()])]),
               _suite("b.test.js", [_spec("second", [_test()])])),
        ["A.test.jsFirst_test_duration", "B.test.jsSecond_test_duration"],
    ),
    "two_projects_one_spec": (
        _steps(_suite("login.test.ts", [_spec("logs in", [_test("alpha", ["go"]), _test("beta", ["go"])])])),
        ["LogsInAlphaGo", "LogsInAlpha_test_duration", "LogsInBetaGo", "LogsInBeta_test_duration"],
    ),
    "annotation_single_project": (
        _steps(_suite("shop.test.ts", [_spec("buys", [
            _test(annotations=[{"type": "perfdata_items", "description": "3"}])])])),
        ["TestDuration", "Items"],
    ),
}


@pytest.mark.parametrize("name", list(LEGACY_CASES))
def test_legacy_labels_unchanged(name):
    steps, expected = LEGACY_CASES[name]
    assert _labels(steps) == expected


# ---------------------------------------------------------------------------
# New layouts (T045): .spec files, collisions, projects, uniqueness
# ---------------------------------------------------------------------------

NEW_CASES = {
    "spec_suites": (
        _steps(_suite("login.spec.ts", [_spec("logs in", [_test(steps=["go"])])]),
               _suite("checkout.spec.ts", [_spec("pays", [_test()])])),
        ["LoginLogsInGo", "LoginLogsIn_test_duration", "CheckoutPays_test_duration"],
    ),
    "basename_collision_uses_path": (
        _steps(_suite("login.spec.ts", [_spec("a", [_test()])]),
               _suite("sub/login.spec.ts", [_spec("a", [_test()])])),
        ["LoginA_test_duration", "SubLoginA_test_duration"],
    ),
    "other_suffixes_stripped": (
        _steps(_suite("a.spec.mts", [_spec("x", [_test()])]),
               _suite("b.test.cjs", [_spec("x", [_test()])]),
               _suite("c.spec.tsx", [_spec("x", [_test()])])),
        ["AX_test_duration", "BX_test_duration", "CX_test_duration"],
    ),
    # FR-051: a legacy config could already run a setup project; its label
    # (suffix kept) must not change.
    "setup_and_teardown_keep_their_suffix": (
        _steps(_suite("auth.setup.ts", [_spec("authenticate", [_test()])]),
               _suite("db.teardown.ts", [_spec("cleanup", [_test()])])),
        ["Auth.setup.tsAuthenticate_test_duration", "Db.teardown.tsCleanup_test_duration"],
    ),
    "annotation_per_project": (
        _steps(_suite("shop.spec.ts", [_spec("buys", [
            _test("a", annotations=[{"type": "perfdata_items", "description": "3"}]),
            _test("b", annotations=[{"type": "perfdata_items", "description": "4"}])])])),
        ["BuysA_test_duration", "BuysAItems", "BuysB_test_duration", "BuysBItems"],
    ),
}


@pytest.mark.parametrize("name", list(NEW_CASES))
def test_new_layout_labels(name):
    steps, expected = NEW_CASES[name]
    assert _labels(steps) == expected


def test_ensure_unique_labels():
    perfdata = [{"label": "x", "value": 1}, {"label": "x", "value": 2}, {"label": "x", "value": 3}]
    assert [p["label"] for p in cep.ensure_unique_labels(perfdata)] == ["x", "x_2", "x_3"]


@pytest.mark.parametrize("steps", [c[0] for c in list(LEGACY_CASES.values()) + list(NEW_CASES.values())])
def test_no_duplicate_labels(steps):
    labels = _labels(steps)
    assert len(labels) == len(set(labels)), labels


def test_output_headers_follow_the_same_rule():
    def with_stdout(title):
        test = _test()
        test["results"][0]["stdout"] = [{"text": "hello"}]
        return _suite(title, [_spec("a", [test])])
    output, _ = cep.extract_output_from_steps(
        _steps(with_stdout("login.spec.ts"), with_stdout("sub/login.spec.ts"), with_stdout("x.test.js")))
    assert "__Stdout login - a__" in output
    assert "__Stdout sub login - a__" in output
    assert "__Stdout x.test.js - a__" in output


def test_ensure_unique_labels_skips_suffixes_already_taken():
    perfdata = [{"label": "x", "value": 1}, {"label": "x", "value": 2}, {"label": "x_2", "value": 3}]
    labels = [p["label"] for p in cep.ensure_unique_labels(perfdata)]
    assert labels == ["x", "x_3", "x_2"]
