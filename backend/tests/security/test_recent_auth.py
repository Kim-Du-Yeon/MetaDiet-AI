import pytest
from fastapi import HTTPException
from types import SimpleNamespace


def test_recent_password_auth_uses_amr_timestamp_not_refreshed_token_iat():
    from app.core.auth import validate_recent_auth_payload

    payload = {
        "sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "session_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "iat": 10_000,
        "amr": [{"method": "password", "timestamp": 9_900}],
    }

    context = validate_recent_auth_payload(payload, now=10_050, max_age_seconds=300)

    assert context.auth_id == payload["sub"]
    assert context.session_id == payload["session_id"]


def test_refreshed_token_does_not_hide_old_password_authentication():
    from app.core.auth import validate_recent_auth_payload

    payload = {
        "sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "session_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "iat": 10_000,
        "amr": [{"method": "password", "timestamp": 9_000}],
    }

    with pytest.raises(HTTPException) as exc:
        validate_recent_auth_payload(payload, now=10_050, max_age_seconds=300)

    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "recent_authentication_required"


@pytest.mark.parametrize("payload", [
    {"sub": "u1", "amr": [{"method": "password", "timestamp": 10_000}]},
    {"sub": "u1", "session_id": "s1", "amr": []},
])
def test_recent_auth_requires_session_and_password_amr(payload):
    from app.core.auth import validate_recent_auth_payload

    with pytest.raises(HTTPException) as exc:
        validate_recent_auth_payload(payload, now=10_050, max_age_seconds=300)

    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "recent_authentication_required"


def test_active_auth_id_confirms_user_still_exists(monkeypatch):
    from app.core import auth

    monkeypatch.setattr(auth, "_decode_verified_token", lambda token: {"sub": "u1"})
    client = SimpleNamespace(auth=SimpleNamespace(
        get_user=lambda token: SimpleNamespace(user=SimpleNamespace(id="u1"))
    ))
    monkeypatch.setattr(auth, "get_supabase", lambda: client)

    assert auth.get_active_auth_id("signed-token") == "u1"


def test_deleted_auth_user_cannot_reenter_onboarding(monkeypatch):
    from app.core import auth

    monkeypatch.setattr(auth, "_decode_verified_token", lambda token: {"sub": "deleted-u1"})

    def missing_user(token):
        raise RuntimeError("user not found")

    client = SimpleNamespace(auth=SimpleNamespace(get_user=missing_user))
    monkeypatch.setattr(auth, "get_supabase", lambda: client)

    with pytest.raises(HTTPException) as exc:
        auth.get_active_auth_id("still-unexpired-token")

    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "auth_session_inactive"
