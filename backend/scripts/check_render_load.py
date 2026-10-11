"""Bounded public-beta load check for Render using one disposable user."""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from uuid import uuid4

from check_render_beta import BACKEND, json_request, load_env, service_api, stream


ARTIFACT = BACKEND / "artifacts" / "render-beta-load-v1.json"


def run_batch(count: int, concurrency: int, operation) -> dict:
    durations: list[float] = []
    failures: list[str] = []

    def measured(index: int):
        started = time.perf_counter()
        operation(index)
        return (time.perf_counter() - started) * 1000

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(measured, index) for index in range(count)]
        for future in as_completed(futures):
            try:
                durations.append(future.result())
            except Exception as exc:  # Report only type; responses can contain sensitive data.
                failures.append(type(exc).__name__)

    ordered = sorted(durations)
    percentile = lambda q: round(ordered[min(len(ordered) - 1, int(len(ordered) * q))], 1) if ordered else None
    return {
        "requests": count,
        "concurrency": concurrency,
        "successes": len(durations),
        "failures": len(failures),
        "failure_types": sorted(set(failures)),
        "latency_ms": {
            "min": round(min(durations), 1) if durations else None,
            "mean": round(statistics.fmean(durations), 1) if durations else None,
            "p50": percentile(.50),
            "p95": percentile(.95),
            "max": round(max(durations), 1) if durations else None,
        },
    }


def run(base_url: str, *, health_requests: int, read_requests: int,
        agent_requests: int) -> dict:
    load_env(BACKEND / ".env")
    base_url = base_url.rstrip("/")
    marker = uuid4().hex
    email = f"render-load-{marker}@example.invalid"
    password = f"T!{marker}a9"
    auth_id = None
    cleanup = "not_started"
    try:
        health = run_batch(health_requests, min(10, health_requests),
                           lambda _: json_request(f"{base_url}/health", timeout=60))
        if health["failures"]:
            raise RuntimeError(f"health load failures: {health}")

        created = service_api("/auth/v1/admin/users", "POST", {
            "email": email, "password": password, "email_confirm": True,
        })
        auth_id = str(created["id"])
        signed_in = service_api("/auth/v1/token?grant_type=password", "POST", {
            "email": email, "password": password,
        })
        token = signed_in["access_token"]
        onboarding = json_request(f"{base_url}/users/onboarding", token=token, method="POST", payload={
            "goal": "diet", "region": "KR", "height_cm": 175, "weight_kg": 82,
            "age": 35, "sex": "male", "activity": "low_active",
            "general_adult_confirmed": True, "target_weight_kg": 75,
            "target_date": "2027-04-30", "goal_priority": "balance",
        })
        proposal = onboarding["pending_proposal"]
        json_request(f"{base_url}/proposals/decision", token=token, method="POST", payload={
            "proposal_id": proposal["id"], "version": proposal["version"], "action": "confirm",
        })

        read_paths = ["/users/onboarding", "/strategy/current", "/inbody/history"]
        reads = run_batch(read_requests, min(5, read_requests),
                          lambda index: json_request(f"{base_url}{read_paths[index % len(read_paths)]}",
                                                     token=token, timeout=90))
        if reads["failures"]:
            raise RuntimeError(f"authenticated read failures: {reads}")

        def agent_call(index: int):
            run_id = str(uuid4())
            events, first_ms = stream(f"{base_url}/chat", token, {
                "message": f"오늘 간식으로 사과 {100 + index * 10}g 먹었어. 기록만 해줘.",
                "thread_id": f"render-load-{marker}-{index}",
                "requested_action": "record_only",
                "stream_run_id": run_id,
                "after_seq": 0,
            })
            completed = next((event for event in events if event.get("type") == "completed"), None)
            if not completed or not completed.get("pending_proposal"):
                raise RuntimeError("agent stream did not complete with a proposal")
            return {"first_event_ms": first_ms, "event_count": len(events)}

        agent_started = time.perf_counter()
        agent_results: list[dict] = []
        agent_failures: list[str] = []
        with ThreadPoolExecutor(max_workers=max(1, agent_requests)) as executor:
            futures = [executor.submit(agent_call, index) for index in range(agent_requests)]
            for future in as_completed(futures):
                try:
                    agent_results.append(future.result())
                except Exception as exc:
                    agent_failures.append(type(exc).__name__)
        agents = {
            "requests": agent_requests,
            "concurrency": agent_requests,
            "successes": len(agent_results),
            "failures": len(agent_failures),
            "failure_types": sorted(set(agent_failures)),
            "wall_seconds": round(time.perf_counter() - agent_started, 2),
            "first_event_ms": sorted(result["first_event_ms"] for result in agent_results),
            "event_counts": sorted(result["event_count"] for result in agent_results),
        }
        if agent_failures:
            raise RuntimeError(f"agent load failures: {agents}")

        result = {"status": "passed", "base_url": base_url,
                  "health": health, "authenticated_reads": reads, "agents": agents}
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        if auth_id:
            try:
                service_api(f"/auth/v1/admin/users/{auth_id}", "DELETE")
                cleanup = "auth_user_deleted"
            except Exception:
                cleanup = "failed"
        if ARTIFACT.exists():
            stored = json.loads(ARTIFACT.read_text(encoding="utf-8"))
            stored["synthetic_cleanup"] = cleanup
            ARTIFACT.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://metadiet-api.onrender.com")
    parser.add_argument("--health-requests", type=int, default=50)
    parser.add_argument("--read-requests", type=int, default=30)
    parser.add_argument("--agent-requests", type=int, default=2)
    args = parser.parse_args()
    if min(args.health_requests, args.read_requests, args.agent_requests) < 1:
        raise SystemExit("request counts must be positive")
    print(json.dumps(run(args.base_url, health_requests=args.health_requests,
                         read_requests=args.read_requests,
                         agent_requests=args.agent_requests), ensure_ascii=False))


if __name__ == "__main__":
    main()
