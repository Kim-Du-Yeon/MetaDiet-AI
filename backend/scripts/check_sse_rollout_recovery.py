"""Destructive-to-synthetic-only SSE/Pod recovery check for the local kind cluster."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib import request
from uuid import uuid4



ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
ARTIFACT = BACKEND / "artifacts" / "sse-pod-recovery-v1.json"


def load_env(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def api(url: str, token: str, method: str = "GET", payload: dict | None = None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
    })
    with request.urlopen(req, timeout=90) as response:
        return json.loads(response.read())


def service_api(path: str, method: str = "GET", payload: dict | None = None):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_KEY"]
    body = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(f"{base}{path}", data=body, method=method, headers={
        "apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "Prefer": "return=representation",
    })
    with request.urlopen(req, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def stream(url: str, token: str, payload: dict, on_event=None) -> list[dict]:
    req = request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
    })
    events = []
    with request.urlopen(req, timeout=180) as response:
        for raw in response:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            events.append(event)
            if on_event:
                on_event(event)
    return events


def kubectl(*args: str, capture=True):
    return subprocess.run(["kubectl", *args], check=True, text=True,
                          capture_output=capture)


def run(base_url: str) -> dict:
    load_env(BACKEND / ".env")
    marker = uuid4().hex
    email = f"sse-recovery-{marker}@example.invalid"
    password = f"T!{marker}a9"
    created = service_api("/auth/v1/admin/users", "POST", {
        "email": email, "password": password, "email_confirm": True,
    })
    auth_id = str(created["id"])
    signed_in = service_api("/auth/v1/token?grant_type=password", "POST", {"email": email, "password": password})
    token = signed_in["access_token"]
    user_id = None
    port_forward = None
    first_error = None
    try:
        onboarding = api(f"{base_url}/users/onboarding", token, "POST", {
            "goal": "diet", "region": "KR", "height_cm": 175, "weight_kg": 82,
            "age": 35, "sex": "male", "activity": "low_active",
            "general_adult_confirmed": True, "target_weight_kg": 75,
            "target_date": "2027-04-30", "goal_priority": "balance",
        })
        proposal = onboarding["pending_proposal"]
        api(f"{base_url}/proposals/decision", token, "POST", {
            "proposal_id": proposal["id"], "version": proposal["version"], "action": "confirm",
        })
        users = service_api(f"/rest/v1/users?auth_id=eq.{auth_id}&select=id")
        user_id = str(users[0]["id"])

        pod = kubectl("get", "pods", "-l", "app=metadiet-api", "-o",
                      "jsonpath={.items[0].metadata.name}").stdout
        port_forward = subprocess.Popen(
            ["kubectl", "port-forward", f"pod/{pod}", "18081:8080"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(50):
            if port_forward.poll() is not None:
                raise RuntimeError("kubectl port-forward exited before the test request")
            try:
                request.urlopen("http://127.0.0.1:18081/health", timeout=1).read()
                break
            except Exception:
                time.sleep(.1)
        else:
            raise RuntimeError("kubectl port-forward did not become ready")

        run_id = str(uuid4())
        thread_id = f"sse-recovery-{marker}"
        payload = {
            "message": "오늘 간식으로 사과 100g 먹었어. 기록만 해줘.",
            "thread_id": thread_id, "requested_action": "record_only",
            "stream_run_id": run_id, "after_seq": 0,
        }
        first_events = []
        first_progress = threading.Event()

        def first_request():
            nonlocal first_error
            try:
                first_events.extend(stream("http://127.0.0.1:18081/chat", token, payload,
                    lambda event: first_progress.set() if event.get("type") == "progress" else None))
            except Exception as exc:
                first_error = type(exc).__name__

        thread = threading.Thread(target=first_request, daemon=True)
        thread.start()
        if not first_progress.wait(60):
            raise RuntimeError("the targeted Pod produced no progress event")
        kubectl("delete", "pod", pod, "--grace-period=0", "--force", capture=True)
        thread.join(30)
        kubectl("rollout", "status", "deployment/metadiet-api", "--timeout=180s", capture=True)

        last_seq = max((int(event.get("seq", 0)) for event in first_events), default=0)
        recovered = stream(f"{base_url}/chat", token, {**payload, "after_seq": last_seq})
        completed = next((event for event in recovered if event.get("type") == "completed"), None)
        if not completed or not completed.get("pending_proposal"):
            raise AssertionError("reconnected stream did not complete with one pending proposal")
        final_proposal = completed["pending_proposal"]

        pending_before = len(service_api(
            f"/rest/v1/agent_proposals?user_id=eq.{user_id}&thread_id=eq.{thread_id}&status=eq.pending&select=id"))
        meals_before = len(service_api(f"/rest/v1/meal_logs?user_id=eq.{user_id}&select=id"))
        confirmed = api(f"{base_url}/proposals/decision", token, "POST", {
            "proposal_id": final_proposal["id"], "version": final_proposal["version"], "action": "confirm",
        })
        duplicate = api(f"{base_url}/proposals/decision", token, "POST", {
            "proposal_id": final_proposal["id"], "version": final_proposal["version"], "action": "confirm",
        })
        meals_after = len(service_api(f"/rest/v1/meal_logs?user_id=eq.{user_id}&select=id"))
        result = {
            "status": "passed", "targeted_pod": pod, "first_connection_error": first_error,
            "last_seq_before_disconnect": last_seq, "recovered_event_count": len(recovered),
            "completed": True, "pending_proposals_before_confirm": pending_before,
            "meal_rows_before_confirm": meals_before, "meal_rows_after_duplicate_confirm": meals_after,
            "confirm_status": confirmed["status"], "duplicate_confirm_status": duplicate["status"],
        }
        expected = (pending_before, meals_before, meals_after, confirmed["status"], duplicate["status"])
        if expected != (1, 0, 1, "confirmed", "confirmed"):
            raise AssertionError(f"SSE recovery/idempotency contract failed: {expected}")
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        if port_forward and port_forward.poll() is None:
            port_forward.terminate()
            try:
                port_forward.wait(5)
            except subprocess.TimeoutExpired:
                port_forward.kill()
        try:
            api(f"{base_url}/users/me", token, "DELETE", {"confirmation": "DELETE"})
        except Exception:
            if user_id:
                service_api(f"/rest/v1/users?id=eq.{user_id}", "DELETE")
            try:
                service_api(f"/auth/v1/admin/users/{auth_id}", "DELETE")
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    args = parser.parse_args()
    print(json.dumps(run(args.base_url), ensure_ascii=False))


if __name__ == "__main__":
    main()
