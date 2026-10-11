"""Public Render beta smoke test using a disposable Supabase user.

The test validates the deployed API contract without printing credentials or
retaining synthetic user data.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib import error, request
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
ARTIFACT = BACKEND / "artifacts" / "render-beta-smoke-v1.json"


def load_env(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def json_request(url: str, *, token: str | None = None, method: str = "GET",
                 payload: dict | None = None, timeout: int = 180):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=body, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {detail}") from exc


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
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"Supabase HTTP {exc.code} {method} {path}: {detail}") from exc


def stream(url: str, token: str, payload: dict) -> tuple[list[dict], float]:
    req = request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    events: list[dict] = []
    started = time.perf_counter()
    first_event_ms = None
    try:
        with request.urlopen(req, timeout=240) as response:
            for raw in response:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                if first_event_ms is None:
                    first_event_ms = (time.perf_counter() - started) * 1000
                events.append(json.loads(line[6:]))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"SSE HTTP {exc.code}: {detail}") from exc
    return events, round(first_event_ms or 0, 1)


def run(base_url: str) -> dict:
    load_env(BACKEND / ".env")
    base_url = base_url.rstrip("/")
    marker = uuid4().hex
    email = f"render-smoke-{marker}@example.invalid"
    password = f"T!{marker}a9"
    auth_id = None
    user_id = None
    token = None
    cleanup = "not_started"
    try:
        created = service_api("/auth/v1/admin/users", "POST", {
            "email": email,
            "password": password,
            "email_confirm": True,
        })
        auth_id = str(created["id"])
        signed_in = service_api("/auth/v1/token?grant_type=password", "POST", {
            "email": email,
            "password": password,
        })
        token = signed_in["access_token"]

        health_started = time.perf_counter()
        health = json_request(f"{base_url}/health", timeout=60)
        health_ms = round((time.perf_counter() - health_started) * 1000, 1)
        if health != {"status": "ok"}:
            raise AssertionError(f"unexpected health response: {health}")

        onboarding = json_request(f"{base_url}/users/onboarding", token=token, method="POST", payload={
            "goal": "diet",
            "region": "KR",
            "height_cm": 175,
            "weight_kg": 82,
            "age": 35,
            "sex": "male",
            "activity": "low_active",
            "general_adult_confirmed": True,
            "target_weight_kg": 75,
            "target_date": "2027-04-30",
            "goal_priority": "balance",
        })
        strategy_proposal = onboarding["pending_proposal"]
        strategy_confirmed = json_request(f"{base_url}/proposals/decision", token=token,
                                          method="POST", payload={
            "proposal_id": strategy_proposal["id"],
            "version": strategy_proposal["version"],
            "action": "confirm",
        })
        users = service_api(f"/rest/v1/users?auth_id=eq.{auth_id}&select=id")
        user_id = str(users[0]["id"])

        run_id = str(uuid4())
        thread_id = f"render-smoke-{marker}"
        payload = {
            "message": "오늘 간식으로 사과 100g 먹었어. 기록만 해줘.",
            "thread_id": thread_id,
            "requested_action": "record_only",
            "stream_run_id": run_id,
            "after_seq": 0,
        }
        events, first_event_ms = stream(f"{base_url}/chat", token, payload)
        event_types = [event.get("type") for event in events]
        if "error" in event_types:
            raise AssertionError(f"stream returned error event: {events[-1]}")
        completed = next((event for event in events if event.get("type") == "completed"), None)
        if not completed or not completed.get("pending_proposal"):
            raise AssertionError(f"stream did not complete with a proposal: {event_types}")
        meal_proposal = completed["pending_proposal"]

        replay, _ = stream(f"{base_url}/chat", token, {**payload, "after_seq": 0})
        replay_completed = next((event for event in replay if event.get("type") == "completed"), None)
        if not replay_completed or replay_completed.get("pending_proposal", {}).get("id") != meal_proposal["id"]:
            raise AssertionError("same run_id did not replay the same completed proposal")

        restored_pending = json_request(f"{base_url}/session/restore/{thread_id}", token=token)
        if restored_pending.get("pending_proposal", {}).get("id") != meal_proposal["id"]:
            raise AssertionError("session restore did not return the pending proposal")

        meals_before = len(service_api(f"/rest/v1/meal_logs?user_id=eq.{user_id}&select=id"))
        confirmed = json_request(f"{base_url}/proposals/decision", token=token, method="POST", payload={
            "proposal_id": meal_proposal["id"],
            "version": meal_proposal["version"],
            "action": "confirm",
        })
        duplicate = json_request(f"{base_url}/proposals/decision", token=token, method="POST", payload={
            "proposal_id": meal_proposal["id"],
            "version": meal_proposal["version"],
            "action": "confirm",
        })
        meals_after = len(service_api(f"/rest/v1/meal_logs?user_id=eq.{user_id}&select=id"))
        restored_after = json_request(f"{base_url}/session/restore/{thread_id}", token=token)

        if (meals_before, meals_after) != (0, 1):
            raise AssertionError(f"proposal idempotency failed: before={meals_before}, after={meals_after}")
        if confirmed["status"] != "confirmed" or duplicate["status"] != "confirmed":
            raise AssertionError("proposal confirmation did not remain idempotently confirmed")
        if restored_after.get("pending_proposal") is not None:
            raise AssertionError("resolved proposal remained pending after session restore")

        result = {
            "status": "passed",
            "base_url": base_url,
            "health_ms": health_ms,
            "first_sse_event_ms": first_event_ms,
            "sse_event_count": len(events),
            "sse_event_types": event_types,
            "same_run_replay": True,
            "pending_restore": True,
            "resolved_restore": True,
            "strategy_confirm_status": strategy_confirmed["status"],
            "meal_confirm_status": confirmed["status"],
            "duplicate_confirm_status": duplicate["status"],
            "meal_rows_after_duplicate_confirm": meals_after,
        }
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        if auth_id:
            try:
                # Use the admin endpoint as the reliable cleanup path for this disposable user.
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
            ARTIFACT.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://metadiet-api.onrender.com")
    args = parser.parse_args()
    result = run(args.base_url)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
