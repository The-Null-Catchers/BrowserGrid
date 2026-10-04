import json
import pytest
from browsergrid.execution.output import RuntimeOutput
from browsergrid.security import Redactor


def test_log_budget_counts_serialized_utf8_and_redacted_output():
    output = RuntimeOutput(Redactor(["secret"]), max_bytes=50)
    assert output.prepare("secret") == ("log", {"message": "[REDACTED]"})
    assert output.prepare("ع" * 20)[0] == "output_truncated"
    assert output.prepare("x" * 100) is None
    assert output.prepare("small") is None
    assert output.bytes <= 50


def test_event_count_limit_warns_once():
    output = RuntimeOutput(Redactor([]), max_events=1)
    assert output.prepare("first")[0] == "log"
    assert output.prepare("second")[0] == "output_truncated"
    assert output.prepare("third") is None


@pytest.mark.parametrize("value", [None, False, True, "0", -1, 256, [], {}])
def test_invalid_completed_value_cannot_set_success(value):
    output = RuntimeOutput(Redactor([]))
    assert (
        output.prepare("@bg:" + json.dumps({"kind": "completed", "exit_code": value}))[0] == "log"
    )
    assert output.exit_code is None


def test_control_messages_do_not_disable_budget(db, monkeypatch):
    from tests.test_worker import prepare
    from browsergrid.models import Job, Event
    from sqlalchemy import select

    rid, jid, _ = prepare(db, monkeypatch)
    job = db.get(Job, jid)
    output = RuntimeOutput(Redactor([]), max_events=1, max_bytes=100)

    def ingest(payload):
        message = output.prepare("@bg:" + json.dumps(payload))
        if message:
            output.apply(db, job, message)
            db.commit()

    ingest({"kind": "state", "state": "installing_dependencies"})
    for _ in range(100):
        ingest({"kind": "state", "state": "installing_dependencies"})
    ingest({"kind": "state", "state": "starting_browser"})
    ingest({"kind": "state", "state": "running"})
    ingest(
        {
            "kind": "runtime",
            "data": {
                "browser_version": "real-value",
                "playwright": "1.58.2",
                "image": "forged-image",
            },
        }
    )
    for _ in range(100):
        ingest(
            {"kind": "runtime", "data": {"browser_version": "forged-value", "playwright": "1.58.2"}}
        )
    ingest({"kind": "completed", "exit_code": 143})
    assert output.exit_code == 143
    assert job.status == "running"
    assert job.runtime["browser_version"] == "real-value"
    assert "image" not in job.runtime
    events = list(db.scalars(select(Event).where(Event.run_id == rid)))
    assert sum(e.kind == "output_truncated" for e in events) == 1
    assert sum(e.kind == "runtime" for e in events) == 1
    assert len(events) < 10


@pytest.mark.parametrize(
    "line",
    [
        "@bg:[]",
        '@bg:{"kind":[]}',
        '@bg:{"kind":"test_end","duration":NaN}',
        '@bg:{"kind":"test_end","duration":1e999}',
    ],
)
def test_malformed_or_nonfinite_messages_become_bounded_text(line):
    output = RuntimeOutput(Redactor([]))
    message = output.prepare(line)
    assert message[0] == "log"
    assert message[1]["message"] == line


def test_error_payload_with_unhashable_code_does_not_crash(db, monkeypatch):
    from tests.test_worker import prepare
    from browsergrid.models import Job

    _, jid, _ = prepare(db, monkeypatch)
    output = RuntimeOutput(Redactor([]))
    message = output.prepare('@bg:{"kind":"error","code":[]}')
    output.apply(db, db.get(Job, jid), message)
    db.commit()
    assert output.setup_error is None


def test_redaction_does_not_change_structural_protocol_labels(db, monkeypatch):
    from tests.test_worker import prepare
    from browsergrid.models import Job

    _, jid, _ = prepare(db, monkeypatch)
    job = db.get(Job, jid)
    output = RuntimeOutput(Redactor(["running", "state", "completed", "1.58.2", "private-message"]))
    for state in ["installing_dependencies", "starting_browser", "running"]:
        message = output.prepare("@bg:" + json.dumps({"kind": "state", "state": state}))
        output.apply(db, job, message)
    message = output.prepare(
        '@bg:{"kind":"error","code":"TEST_PROCESS_INTERRUPTED","message":"private-message"}'
    )
    assert message[1]["message"] == "[REDACTED]"
    output.apply(db, job, message)
    output.apply(db, job, output.prepare('@bg:{"kind":"completed","exit_code":143}'))
    db.commit()
    assert job.status == "running"
    assert output.exit_code == 143


def test_deeply_nested_stdout_cannot_crash_redaction():
    nested = 0
    for _ in range(600):
        nested = [nested]
    line = "@bg:" + json.dumps({"kind": "test_end", "data": nested})
    output = RuntimeOutput(Redactor([]), max_bytes=100)
    assert output.prepare(line)[0] == "output_truncated"
