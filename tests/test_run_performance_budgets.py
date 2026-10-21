import pytest
from pydantic import ValidationError
from browsergrid.schemas import RunConfig

SOURCE = {"type": "inline", "code": "console.log('ok')"}


def test_run_accepts_optional_timing_budgets():
    config = RunConfig(source=SOURCE, performance_budgets={"first_contentful_paint_ms": 1800}, enforce_performance_budgets=True)
    assert config.performance_budgets == {"first_contentful_paint_ms": 1800}
    assert config.enforce_performance_budgets is True


@pytest.mark.parametrize("budgets", [{}, {"unknown_ms": 100}, {"navigation_duration_ms": -1}, {"navigation_duration_ms": float("inf")}])
def test_run_rejects_invalid_timing_budgets(budgets):
    with pytest.raises(ValidationError):
        RunConfig(source=SOURCE, performance_budgets=budgets)
