"""Verify deployed beta-feedback idempotency and account-deletion cascade.

Only disposable synthetic users are touched. The artifact contains aggregate
statuses/timings and never credentials, tokens, identifiers, or free text.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
ARTIFACT = BACKEND / "artifacts" / "beta-feedback-lifecycle-v1.json"


def load_env(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def api_request(url: str, *, token: str, method: str = "GET", payload: dict | None = None,
                timeout=180) -> tuple[int, dict | None]:
    body = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"public API HTTP {exc.code} at {urlparse(url).path}: {detail}") from exc


def service_api(path: str, method: str = "GET", payload: dict | None = None):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_KEY"]
    body = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(f"{base}{path}", data=body, method=method, headers={
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    })
    try:
        with request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Supabase HTTP {exc.code} {method} {path}: {detail}") from exc


def redacted_summary(*, create_status: int, replay_status: int, rows_after_replay: int,
                     rows_after_delete: int, create_ms: float, replay_ms: float) -> dict:
    return {
        "status": "passed",
        "create_http_status": create_status,
        "replay_http_status": replay_status,
        "rows_after_replay": rows_after_replay,
        "rows_after_delete": rows_after_delete,
        "create_ms": create_ms,
        "replay_ms": replay_ms,
    }


def run(base_url: str) -> dict:
    load_env(BACKEND / ".env")
    base_url = base_url.rstrip("/")
    marker = uuid4().hex
    email = f"feedback-check-{marker}@example.invalid"
    password = f"T!{marker}a9"
    auth_id = None
    user_id = None
    cleanup = "not_started"
    try:
        created_auth = service_api("/auth/v1/admin/users", "POST", {
            "email": email,
            "password": password,
            "email_confirm": True,
        })
        auth_id = str(created_auth["id"])
        signed_in = service_api("/auth/v1/token?grant_type=password", "POST", {
            "email": email,
            "password": password,
        })
        token = signed_in["access_token"]
        users = service_api("/rest/v1/users", "POST", {
            "auth_id": auth_id,
            "name": "synthetic-feedback-check",
            "goal": "maintain",
        })
        user_id = str(users[0]["id"])
        submission_id = str(uuid4())
        payload = {
            "rating": 4,
            "category": "general",
            "client_submission_id": submission_id,
        }

        started = time.perf_counter()
        create_status, first = api_request(
            f"{base_url}/feedback", token=token, method="POST", payload=payload
        )
        create_ms = round((time.perf_counter() - started) * 1000, 1)
        started = time.perf_counter()
        replay_status, second = api_request(
            f"{base_url}/feedback", token=token, method="POST", payload=payload
        )
        replay_ms = round((time.perf_counter() - started) * 1000, 1)
        if first["id"] != second["id"] or not first["created"] or second["created"]:
            raise AssertionError("idempotent replay contract failed")

        rows_after_replay = len(service_api(
            f"/rest/v1/beta_feedback?user_id=eq.{user_id}&select=id"
        ))
        if rows_after_replay != 1:
            raise AssertionError("feedback replay created duplicate rows")

        delete_status, _ = api_request(
            f"{base_url}/users/me",
            token=token,
            method="DELETE",
            payload={"confirmation": "DELETE"},
        )
        if delete_status != 200:
            raise AssertionError("account deletion did not return HTTP 200")
        rows_after_delete = len(service_api(
            f"/rest/v1/beta_feedback?user_id=eq.{user_id}&select=id"
        ))
        if rows_after_delete != 0:
            raise AssertionError("account deletion did not cascade to beta feedback")

        result = redacted_summary(
            create_status=create_status,
            replay_status=replay_status,
            rows_after_replay=rows_after_replay,
            rows_after_delete=rows_after_delete,
            create_ms=create_ms,
            replay_ms=replay_ms,
        )
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(json.dumps(result, indent=2), encoding="utf-8")
        cleanup = "deleted_by_public_api"
        return result
    finally:
        if auth_id and cleanup != "deleted_by_public_api":
            try:
                service_api(f"/auth/v1/admin/users/{auth_id}", "DELETE")
                cleanup = "auth_user_deleted"
            except Exception:
                if user_id:
                    try:
                        service_api(f"/rest/v1/users?id=eq.{user_id}", "DELETE")
                        cleanup = "domain_user_deleted"
                    except Exception:
                        cleanup = "failed"
                else:
                    cleanup = "failed"
        if ARTIFACT.exists():
            stored = json.loads(ARTIFACT.read_text(encoding="utf-8"))
            stored["synthetic_cleanup"] = cleanup
            ARTIFACT.write_text(json.dumps(stored, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://metadiet-api.onrender.com")
    args = parser.parse_args()
    print(json.dumps(run(args.base_url)))


if __name__ == "__main__":
    main()
