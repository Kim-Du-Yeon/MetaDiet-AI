"""Live Gemini team smoke test with synthetic input and no database writes."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agents.team import DietTeam


class SyntheticProposals:
    async def create(self, user, thread, payload, key):
        return {"id": "synthetic", "version": 1, "kind": payload["kind"], "payload": payload, "status": "pending"}


async def main():
    result = await DietTeam({"user_id": "synthetic", "thread_id": "smoke", "run_id": "smoke",
        "message": "오늘 점심에 조리된 쌀밥 200g을 먹었어. 기록만 해줘. 음식 검색 후 계산해서 확인할 제안을 만들어줘.",
        "requested_action": "record_only", "tool_policy": ["search_foods", "nutrition_lookup", "propose_meal"]},
        repository=SyntheticProposals(), db=object()).execute()
    assert result["pending_proposal"] and result["pending_proposal"]["kind"] == "intake", result["execution_status"]
    assert result["awaiting_confirmation"]
    names = [event["tool"] for event in result["agent_events"] if event["type"] == "tool_succeeded"]
    assert "delegate_meal" in names and "nutrition_lookup" in names and "propose_meal" in names
    print("PASS: Gemini supervisor delegates; specialist selects tools; proposal awaits approval")
    print(json.dumps({"tools": names, "usage": result["execution_usage"]}))


if __name__ == "__main__":
    asyncio.run(main())
