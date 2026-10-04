import json
from browsergrid.results import parse_report


def test_flaky_retry_results_preserved():
    report = {
        "suites": [
            {
                "title": "auth",
                "specs": [
                    {
                        "title": "login",
                        "file": "auth.spec.ts",
                        "tests": [
                            {
                                "status": "flaky",
                                "results": [
                                    {
                                        "status": "failed",
                                        "duration": 50,
                                        "error": {"message": "initial error"},
                                    },
                                    {"status": "passed", "duration": 30},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    tests, errors = parse_report(json.dumps(report))
    assert not errors
    assert tests[0]["status"] == "flaky"
    assert tests[0]["retry"] == 1
    assert tests[0]["duration_ms"] == 80
    assert tests[0]["error"] == "initial error"


def report_test(test):
    return json.dumps(
        {"suites": [{"title": "suite", "specs": [{"title": "test", "tests": [test]}]}]}
    )


def test_outcome_without_attempts_cannot_pass():
    import pytest

    with pytest.raises(ValueError, match="without execution"):
        parse_report(report_test({"status": "expected", "results": []}))


def test_expected_outcome_must_match_attempt():
    import pytest

    with pytest.raises(ValueError, match="conflicts"):
        parse_report(
            report_test({"status": "expected", "results": [{"status": "failed", "duration": 1}]})
        )


def test_expected_failure_is_supported():
    rows, _ = parse_report(
        report_test(
            {
                "status": "expected",
                "expectedStatus": "failed",
                "results": [{"status": "failed", "duration": 1}],
            }
        )
    )
    assert rows[0]["status"] == "passed"


def test_expected_failure_can_be_flaky():
    rows, _ = parse_report(
        report_test(
            {
                "status": "flaky",
                "expectedStatus": "failed",
                "results": [
                    {"status": "passed", "duration": 1},
                    {"status": "failed", "duration": 1},
                ],
            }
        )
    )
    assert rows[0]["status"] == "flaky"


def test_skipped_test_without_attempts():
    rows, _ = parse_report(report_test({"status": "skipped", "results": []}))
    assert rows[0]["status"] == "skipped"


def test_report_size_is_bounded(monkeypatch):
    import pytest
    from browsergrid.config import settings

    monkeypatch.setattr(settings(), "max_report_bytes", 10)
    with pytest.raises(ValueError, match="size limit"):
        parse_report('{"suites":[]}')


def test_report_rejects_nonfinite_numbers():
    import pytest

    with pytest.raises(ValueError, match="Non-finite"):
        parse_report('{"suites":[],"extra":NaN}')


def test_flaky_requires_failed_retry_history():
    import pytest

    with pytest.raises(ValueError, match="Flaky"):
        parse_report(
            report_test({"status": "flaky", "results": [{"status": "passed", "duration": 1}]})
        )
