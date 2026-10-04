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
