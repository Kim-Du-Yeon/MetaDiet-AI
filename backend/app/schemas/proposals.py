"""Server-validated, immutable payloads reviewed before domain writes."""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from app.core.service_clock import service_today


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MealItem(StrictModel):
    food_name: str = Field(min_length=1, max_length=200)
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    quantity_g: float = Field(gt=0, le=10000)
    calories: float = Field(ge=0, le=30000)
    protein_g: float = Field(ge=0, le=10000)
    carbs_g: float = Field(ge=0, le=10000)
    fat_g: float = Field(ge=0, le=10000)
    sodium_mg: float = Field(default=0, ge=0, le=1000000)
    source: Literal["csv", "llm_estimated"] = "csv"


class MealProposal(StrictModel):
    kind: Literal["intake", "plan"]
    log_date: date
    meals: list[MealItem] = Field(min_length=1, max_length=30)


class MeasurementProposal(StrictModel):
    kind: Literal["measurement"] = "measurement"
    measured_date: date
    weight_kg: float = Field(gt=0, le=500)
    skeletal_muscle_kg: float = Field(gt=0, le=250)
    body_fat_kg: float = Field(ge=0, le=400)
    body_fat_pct: float = Field(ge=0, le=100)
    bmi: float | None = Field(default=None, gt=0, le=200)
    bmr_kcal: float | None = Field(default=None, gt=0, le=10000)
    protein_kg: float | None = Field(default=None, ge=0, le=200)
    mineral_kg: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def physical_consistency(self):
        if self.skeletal_muscle_kg > self.weight_kg or self.body_fat_kg > self.weight_kg:
            raise ValueError("체성분 값은 체중을 초과할 수 없습니다. 원본을 확인해주세요.")
        if self.measured_date > service_today():
            raise ValueError("측정일은 미래일 수 없습니다.")
        return self


class WeightProposal(StrictModel):
    kind: Literal["weight"] = "weight"
    measured_date: date
    weight_kg: float = Field(gt=0, le=500)
    source: Literal["manual"] = "manual"

    @model_validator(mode="after")
    def date_not_in_future(self):
        if self.measured_date > service_today():
            raise ValueError("측정일은 미래일 수 없습니다.")
        return self


class Evidence(StrictModel):
    source: str = Field(min_length=1)
    page: str
    excerpt: str = Field(min_length=1)
    source_url: str | None = None
    edition: str | None = None
    population: str | None = None
    document_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class StrategyProposal(StrictModel):
    kind: Literal["strategy"] = "strategy"
    daily_calories: float = Field(gt=0, le=10000)
    protein_g: float = Field(ge=0, le=1000)
    carbs_g: float = Field(ge=0, le=2000)
    fat_g: float = Field(ge=0, le=1000)
    strategy_note: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    effective_date: date
    based_on_strategy_id: UUID | None = None
    evidence_policy: dict | None = None  # Generated/rechecked by server; never authorizes itself.

    @model_validator(mode="after")
    def macro_consistency(self):
        calculated = 4 * (self.protein_g + self.carbs_g) + 9 * self.fat_g
        if abs(calculated - self.daily_calories) > max(10, self.daily_calories * 0.05):
            raise ValueError("열량과 영양소 환산값이 일치하지 않습니다.")
        return self


class MealChangeProposal(StrictModel):
    kind: Literal["meal_delete", "meal_replace"]
    meal_id: UUID
    expected: dict
    meal: MealItem | None = None

    @model_validator(mode="after")
    def replacement_required(self):
        if self.kind == "meal_replace" and self.meal is None:
            raise ValueError("Replacement requires a meal")
        return self


ProposalPayload = Annotated[MealProposal | MeasurementProposal | WeightProposal | StrategyProposal | MealChangeProposal, Field(discriminator="kind")]
payload_adapter = TypeAdapter(ProposalPayload)


class ProposalDecision(StrictModel):
    proposal_id: UUID
    version: int = Field(ge=1)
    action: Literal["confirm", "cancel"]


class MeasurementRevision(StrictModel):
    version: int = Field(ge=1)
    payload: MeasurementProposal


class WeightRevision(StrictModel):
    version: int = Field(ge=1)
    payload: WeightProposal
