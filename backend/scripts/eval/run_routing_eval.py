"""
scripts/eval/run_routing_eval.py

Supervisor 라우팅 판단 평가기.

"supervisor가 제대로 판단했는지" = 사용자 메시지(+대화 맥락)를 올바른 agent로
분류했는지 = 라우팅 정확도. 라벨된 테스트셋(routing_dataset.json)으로 측정한다.

측정:
  - intent_accuracy : supervisor의 의도 분류 정확도(핵심 = 판단력)
  - route_accuracy  : route_to_agent 적용 후 최종 라우팅 정확도
  - 오분류 목록 + 혼동 쌍(expected→predicted)

실제 supervisor_node를 그대로 호출하므로 프롬프트/폴백/맥락처리까지 통째로 검증.
앱 로직은 건드리지 않는다(테스트 픽스처만 사용).

실행:
  D:\\AX\\diet_agent\\backend\\venv\\Scripts\\python.exe scripts/eval/run_routing_eval.py
"""
import sys, os, json, asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pathlib import Path
from collections import Counter
from app.agents.supervisor.node import supervisor_node, route_to_agent

DATA_PATH   = Path(__file__).parent / "routing_dataset.json"
REPORT_PATH = Path(__file__).parent / "routing_report.json"


async def eval_one(case: dict) -> dict:
    # supervisor_node가 읽는 최소 state만 구성(DB 불필요)
    pending = [{"meal_type": "lunch", "food_name": "제안식단"}] if case.get("pending") else None
    state = {
        "message": case["message"],
        "messages": case.get("context", []),
        "pending_meals": pending,
        "awaiting_confirmation": bool(case.get("pending")),
    }
    out = await supervisor_node(state)
    intent = out["intent"]
    route = route_to_agent({**state, "intent": intent})

    expected = case["expected"]
    return {
        "message":  case["message"],
        "expected": expected,
        "intent":   intent,
        "route":    route,
        "intent_ok": intent == expected,
        # confirm 케이스는 route가 confirm으로 강제될 수 있어 intent 기준이 본질
        "route_ok": route == expected or intent == expected,
    }


async def main():
    cases = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    print(f"=== Supervisor 라우팅 평가: {len(cases)}케이스 ===\n")

    rows, confusion = [], Counter()
    for i, c in enumerate(cases, 1):
        r = await eval_one(c)
        rows.append(r)
        mark = "✅" if r["intent_ok"] else "❌"
        print(f"[{i:2}] {mark} expected={r['expected']:11} got={r['intent']:11} | {r['message'][:38]}")
        if not r["intent_ok"]:
            confusion[f"{r['expected']}→{r['intent']}"] += 1

    n = len(rows)
    intent_acc = round(sum(x["intent_ok"] for x in rows) / n, 3)
    route_acc  = round(sum(x["route_ok"] for x in rows) / n, 3)

    print("\n=== 요약 ===")
    print(f"  intent_accuracy : {intent_acc}  ({sum(x['intent_ok'] for x in rows)}/{n})")
    print(f"  route_accuracy  : {route_acc}")
    if confusion:
        print("  오분류(혼동):")
        for k, v in confusion.most_common():
            print(f"    {k} : {v}")

    summary = {"n": n, "intent_accuracy": intent_acc, "route_accuracy": route_acc,
               "confusion": dict(confusion)}
    REPORT_PATH.write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n리포트 저장: {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
