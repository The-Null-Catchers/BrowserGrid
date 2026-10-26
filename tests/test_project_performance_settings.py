import pytest
from pydantic import ValidationError

from browsergrid.schemas import ProjectPerformanceSettings


def test_project_accepts_valid_budgets():
    settings = ProjectPerformanceSettings(
        performance_budgets={"first_contentful_paint_ms": 1800},
        enforce_performance_budgets=True,
    )
    assert settings.performance_budgets == {"first_contentful_paint_ms": 1800}
    assert settings.enforce_performance_budgets is True


@pytest.mark.parametrize(
    "budgets",
    [{}, {"unknown": 1}, {"first_paint_ms": -5}, {"first_paint_ms": float("inf")}],
)
def test_project_rejects_invalid_budgets(budgets):
    with pytest.raises(ValidationError):
        ProjectPerformanceSettings(performance_budgets=budgets)
