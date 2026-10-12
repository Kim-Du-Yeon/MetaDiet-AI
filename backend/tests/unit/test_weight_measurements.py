from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.service_clock import service_today


class Cursor:
    def __init__(self, row): self.row = row
    async def fetchone(self): return self.row


class RecordingConnection:
    def __init__(self, rows): self.rows, self.calls = list(rows), []
    async def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return Cursor(self.rows.pop(0) if self.rows else None)


def test_weight_proposal_rejects_future_date():
    from app.schemas.proposals import WeightProposal

    with pytest.raises(ValidationError, match="미래"):
        WeightProposal(measured_date="2999-01-01", weight_kg=70)


async def test_weight_proposal_confirmation_writes_weight_log():
    from app.db.proposals import ProposalRepository

    conn = RecordingConnection([{"id": "weight-1"}])

    result = await ProposalRepository()._apply(conn, "user-1", {"id": "proposal-1"}, {
        "kind": "weight", "measured_date": service_today().isoformat(),
        "weight_kg": 71.2, "source": "manual",
    })

    assert result == {"weight_log_id": "weight-1"}
    sql = conn.calls[0][0]
    assert "weight_logs" in sql
    assert "on conflict" in sql.lower()


async def test_measurement_confirmation_writes_inbody_and_weight_in_one_transaction():
    from app.db.proposals import ProposalRepository

    conn = RecordingConnection([{"id": "inbody-1"}, {"id": "weight-1"}])

    result = await ProposalRepository()._apply(conn, "user-1", {"id": "proposal-1"}, {
        "kind": "measurement", "measured_date": service_today().isoformat(),
        "weight_kg": 70, "skeletal_muscle_kg": 30, "body_fat_kg": 14,
        "body_fat_pct": 20, "bmi": None, "bmr_kcal": None,
        "protein_kg": None, "mineral_kg": None,
    })

    assert result == {"measurement_id": "inbody-1", "weight_log_id": "weight-1"}
    assert "inbody_logs" in conn.calls[0][0]
    assert "weight_logs" in conn.calls[1][0]


async def test_onboarding_upserts_initial_weight_in_same_transaction(monkeypatch):
    from app.core import onboarding

    conn = AsyncMock()
    cursors = []
    values = [None] * 8
    for value in values:
        cursor = AsyncMock()
        cursor.fetchone.return_value = value
        cursors.append(cursor)
    conn.execute.side_effect = cursors

    @asynccontextmanager
    async def connect():
        yield conn

    monkeypatch.setattr(onboarding, "connection", connect)
    monkeypatch.setattr(onboarding, "baseline_payload", lambda profile, active_id: {
        "kind": "strategy", "daily_calories": 2000, "protein_g": 100,
        "carbs_g": 275, "fat_g": 55.56, "strategy_note": "test",
        "evidence": [{"source": "x", "page": "1", "excerpt": "x"}],
        "policy_version": "v1", "effective_date": service_today().isoformat(),
        "based_on_strategy_id": None,
        "evidence_policy": {"goal_assessment": {"status": "baseline"}},
    })
    create = AsyncMock(return_value={"id": "p", "kind": "strategy"})
    monkeypatch.setattr(onboarding.ProposalRepository, "create", create)

    req = onboarding.OnboardingRequest(goal="maintain", region="KR", age=30,
        weight_kg=70, height_cm=170, sex="male", activity="low_active",
        general_adult_confirmed=True)
    await onboarding.save_onboarding(req, "auth-1")

    assert any("insert into weight_logs" in call.args[0] and "on conflict" in call.args[0].lower()
               for call in conn.execute.call_args_list)


async def test_dashboard_prefers_inbody_weight_on_same_date(fake_sb, mock_current_user):
    from app.api.routes.main import get_dashboard_summary

    fake_sb.tables["users"] = [{"weight_kg": 72, "created_at": "2026-10-01T00:00:00Z"}]
    fake_sb.tables["weight_logs"] = [
        {"measured_date": "2026-10-12", "weight_kg": 71, "source": "manual"},
        {"measured_date": "2026-10-12", "weight_kg": 70.5, "source": "inbody"},
    ]
    fake_sb.tables["inbody_logs"] = [{"measured_date": "2026-10-12", "weight_kg": 70.5,
        "skeletal_muscle_kg": 30, "body_fat_kg": 14, "body_fat_pct": 20}]

    result = await get_dashboard_summary(current_user=mock_current_user)

    assert len(result["weight_history"]) == 1
    assert result["latest_weight"]["source"] == "inbody"


async def test_direct_body_composition_calculates_fat_mass(monkeypatch, mock_current_user):
    from app.api.routes import main

    repo = AsyncMock()
    repo.create.return_value = {"id": "p1", "kind": "measurement"}
    monkeypatch.setattr(main, "ProposalRepository", lambda: repo)
    request = main.MeasurementEntryRequest(measured_date=service_today(), weight_kg=70,
        skeletal_muscle_kg=30, body_fat_pct=20)

    await main.propose_body_composition(request, current_user=mock_current_user)

    assert repo.create.call_args.args[2]["body_fat_kg"] == 14.0
