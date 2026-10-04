import json
from browsergrid.models import TestResult


def parse_report(data):
    report = json.loads(data)
    if not isinstance(report, dict) or not isinstance(report.get("suites"), list):
        raise ValueError("Invalid Playwright report")
    tests = []

    def visit(suite, parents=(), depth=0):
        if depth > 20:
            raise ValueError("Report nesting exceeds limit")
        name = str(suite.get("title", ""))[:500]
        trail = parents + (name,)
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                results = test.get("results", [])
                outcome = test.get("status")
                status = {
                    "expected": "passed",
                    "unexpected": "failed",
                    "flaky": "flaky",
                    "skipped": "skipped",
                }.get(outcome, "failed")
                if results and results[-1].get("status") == "timedOut":
                    status = "timed_out"
                tests.append(
                    {
                        "file": str(spec.get("file", suite.get("file", "")))[:500],
                        "title": str(spec.get("title", ""))[:1000],
                        "suite": " / ".join(trail)[:1000],
                        "status": status,
                        "duration_ms": max(
                            0, min(3_600_000, sum(int(r.get("duration", 0)) for r in results))
                        ),
                        "retry": max(0, len(results) - 1),
                        "error": "\n".join(
                            str(r.get("error", {}).get("message", ""))
                            for r in results
                            if r.get("error", {}).get("message")
                        )[:20000]
                        or None,
                    }
                )
                if len(tests) > 10000:
                    raise ValueError("Too many test results")
        for child in suite.get("suites", []):
            visit(child, trail, depth + 1)

    for suite in report["suites"]:
        visit(suite)
    return tests, report.get("errors", [])


def persist_results(db, job_id, data, redactor):
    tests, errors = parse_report(data)
    for test in tests:
        db.add(TestResult(job_id=job_id, **redactor.data(test)))
    return tests, errors
