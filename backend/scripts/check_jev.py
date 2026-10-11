"""Live Jev capability probe with public synthetic requests, never user health records."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.jev import JevClient
from app.agents.runtime import ExecutionBudget


async def main():
    client = JevClient()
    budget = ExecutionBudget(max_model_calls=9, timeout_seconds=60)
    cases = [("밥 200g 먹었어. 기록만 해줘", "meal"),
             ("내 체중 관리 목표를 점검해줘", "goal"),
             ("WHO 당류 섭취 권고의 공식 근거를 찾아줘", "evidence")]
    rows = []
    for repeat in range(3):
      for request, expected in cases:
        candidates = {
            "meal": "Food intake recording or meal planning",
            "goal": "Review the person's weight-management goal",
            "evidence": "Retrieve official nutrition evidence"}
        names = list(candidates)
        names = names[repeat:] + names[:repeat]
        result = await client.choose(state={"request": request}, candidates={name: candidates[name] for name in names},
                                     budget=budget, min_confidence=0)
        rows.append({"expected": expected, "repeat": repeat, **result.event()})
    destination = ROOT / "artifacts/jev-capability"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(json.dumps({"scope": "three synthetic capability probes, not quality evaluation",
        "cases": rows, "model_calls": budget.model_calls,
        "choice_accuracy": sum(row["choice"] == row["expected"] for row in rows) / len(rows),
        "candidate_order_rotated": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"results": [{"expected": row["expected"], "choice": row["choice"],
        "model": row["model"], "fallback": row["fallback_reason"], "seconds": row["seconds"]} for row in rows]}))
    if any(row["fallback_reason"] for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
