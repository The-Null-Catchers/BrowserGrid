from unittest.mock import MagicMock
import pytest
from browsergrid.watchdog import expired, sweep


@pytest.mark.parametrize(
    "labels",
    [
        {},
        {"browsergrid.deadline": "bad"},
        {"browsergrid.deadline": "nan"},
        {"browsergrid.deadline": "inf"},
        {"browsergrid.deadline": "99"},
    ],
)
def test_invalid_or_expired_deadlines_are_removed(labels):
    assert expired(labels, 100)


def test_live_deadline_is_preserved():
    assert not expired({"browsergrid.deadline": "101"}, 100)


def test_watchdog_enforces_deadline_without_database_or_worker():
    backend = MagicMock()
    old = MagicMock(labels={"browsergrid.deadline": "90"})
    live = MagicMock(labels={"browsergrid.deadline": "110"})
    backend.client.containers.list.return_value = [old, live]
    assert sweep(backend, 100) == 1
    backend.stop.assert_called_once_with(old)
