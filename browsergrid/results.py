import json
from browsergrid.config import settings
from browsergrid.models import TestResult


def _array(value, label):
    if not isinstance(value, list):
        raise ValueError(f"Invalid report {label}")
    return value


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"Invalid report {label}")
    return value


def parse_report(data):
    length = len(data.encode()) if isinstance(data, str) else len(data)
    if length > settings().max_report_bytes:
        raise ValueError("Playwright report exceeds size limit")

    def reject_constant(value):
        raise ValueError("Non-finite report value")

    report = _object(json.loads(data, parse_constant=reject_constant), "root")
    suites = _array(report.get("suites"), "suites")
    errors = _array(report.get("errors", []), "errors")
    tests = []
    nodes = 0

    def visit(suite, parents=(), depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 20 or nodes > 20000:
            raise ValueError("Report hierarchy exceeds limit")
        suite = _object(suite, "suite")
        trail = parents + (str(suite.get("title", ""))[:500],)
        for spec in _array(suite.get("specs", []), "specs"):
            spec = _object(spec, "spec")
            nodes += 1
            if nodes > 20000:
                raise ValueError("Report hierarchy exceeds limit")
            for test in _array(spec.get("tests", []), "tests"):
                test = _object(test, "test")
                results = _array(test.get("results", []), "attempts")
                outcome = test.get("status")
                if outcome not in {"expected", "unexpected", "flaky", "skipped"}:
                    raise ValueError("Unknown Playwright test outcome")
                if not results and outcome != "skipped":
                    raise ValueError("Test outcome without execution attempts")
                if len(results) > 100:
                    raise ValueError("Too many test attempts")
                duration = 0
                messages = []
                for attempt in results:
                    attempt = _object(attempt, "attempt")
                    if attempt.get("status") not in {
                        "passed",
                        "failed",
                        "timedOut",
                        "skipped",
                        "interrupted",
                    }:
                        raise ValueError("Unknown Playwright attempt status")
                    value = attempt.get("duration", 0)
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or value < 0
                        or value > 3_600_000
                    ):
                        raise ValueError("Invalid attempt duration")
                    duration += value
                    error = _object(attempt.get("error") or {}, "error")
                    if error.get("message"):
                        messages.append(str(error["message"]))
                status = {
                    "expected": "passed",
                    "unexpected": "failed",
                    "flaky": "flaky",
                    "skipped": "skipped",
                }[outcome]
                if results and results[-1]["status"] == "timedOut":
                    status = "timed_out"
                # An expected failure is valid when Playwright explicitly records it.
                if (
                    outcome == "expected"
                    and results
                    and results[-1]["status"] != test.get("expectedStatus", "passed")
                ):
                    raise ValueError("Expected outcome conflicts with final attempt")
                if outcome == "flaky" and (
                    len(results) < 2
                    or results[-1]["status"] != test.get("expectedStatus", "passed")
                    or not any(
                        r["status"] != test.get("expectedStatus", "passed")
                        and r["status"] != "skipped"
                        for r in results[:-1]
                    )
                ):
                    raise ValueError("Flaky outcome without a failed retry history")
                tests.append(
                    {
                        "file": str(spec.get("file", suite.get("file", "")))[:500],
                        "title": str(spec.get("title", ""))[:1000],
                        "suite": " / ".join(trail)[:1000],
                        "status": status,
                        "duration_ms": min(3_600_000, int(duration)),
                        "retry": max(0, len(results) - 1),
                        "error": "\n".join(messages)[:20000] or None,
                    }
                )
                if len(tests) > 10000:
                    raise ValueError("Too many test results")
        for child in _array(suite.get("suites", []), "child suites"):
            visit(child, trail, depth + 1)

    for suite in suites:
        visit(suite)
    return tests, errors


def persist_results(db, job_id, data, redactor):
    tests, errors = parse_report(data)
    for test in tests:
        db.add(TestResult(job_id=job_id, **redactor.data(test)))
    return tests, errors
