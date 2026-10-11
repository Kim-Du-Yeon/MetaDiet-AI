import pytest
from pydantic import ValidationError
from app.schemas.proposals import MealProposal, MeasurementProposal, StrategyProposal


def test_plan_and_intake_are_explicit_different_kinds():
    data = {"log_date": "2026-10-09", "meals": [{"food_name": "밥", "meal_type": "lunch",
            "quantity_g": 100, "calories": 150, "protein_g": 3, "carbs_g": 33, "fat_g": 1, "source": "csv"}]}
    assert MealProposal(kind="plan", **data).kind != MealProposal(kind="intake", **data).kind


def test_nonfinite_or_negative_nutrition_is_rejected():
    with pytest.raises(ValidationError):
        MealProposal(kind="intake", log_date="2026-10-09", meals=[{"food_name": "밥", "meal_type": "lunch",
            "quantity_g": 100, "calories": float("nan"), "protein_g": -1, "carbs_g": 33, "fat_g": 1}])


def test_measurement_keeps_observed_values_and_date():
    value = MeasurementProposal(measured_date="2026-10-08", weight_kg=56.1,
        skeletal_muscle_kg=23.1, body_fat_kg=12, body_fat_pct=21.4)
    assert value.weight_kg == 56.1
    assert value.measured_date.isoformat() == "2026-10-08"


def test_strategy_requires_explanation_and_evidence():
    with pytest.raises(ValidationError):
        StrategyProposal(daily_calories=1800, protein_g=120, carbs_g=200, fat_g=60)
