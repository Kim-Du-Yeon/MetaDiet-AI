from contextlib import asynccontextmanager

import pytest


class Cursor:
    def __init__(self, row=None):
        self.row = row

    async def fetchone(self):
        return self.row


class TombstonedConnection:
    def __init__(self):
        self.queries = []

    async def execute(self, sql, params=()):
        normalized = " ".join(sql.split()).lower()
        self.queries.append((normalized, params))
        if normalized.startswith("select 1 from account_deletion_tombstones"):
            return Cursor({"exists": 1})
        return Cursor()


@pytest.mark.asyncio
async def test_onboarding_cannot_recreate_profile_during_partial_auth_deletion(monkeypatch):
    from app.core import onboarding
    from app.core.energy_policy import EnergyInputs

    connection = TombstonedConnection()

    @asynccontextmanager
    async def connect():
        yield connection

    monkeypatch.setattr(onboarding, "connection", connect)
    request = onboarding.OnboardingRequest(
        **EnergyInputs(
            age=30,
            sex="male",
            weight_kg=70,
            height_cm=170,
            activity="low_active",
            general_adult_confirmed=True,
        ).model_dump(),
        goal="maintain",
    )

    with pytest.raises(onboarding.AccountDeletionInProgress):
        await onboarding.save_onboarding(
            request, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        )

    assert not any(sql.startswith("insert into users") for sql, _ in connection.queries)
    assert not any(sql.startswith("update users") for sql, _ in connection.queries)
