"""Explicit proposal approval; model output is never authority to commit."""
from app.db.proposals import ProposalRepository


async def approval_node(state, config=None):
    proposal = state.get("pending_proposal")
    if not proposal:
        return {"response": "확정할 제안이 없습니다.", "awaiting_confirmation": False, "pending_meals": None}
    decision = state.get("proposal_decision")
    if decision:
        if str(decision["proposal_id"]) != proposal["id"] or decision["version"] != proposal["version"]:
            return {"response": "화면의 제안이 변경되었습니다. 최신 제안을 확인해주세요.", "proposal_decision": None}
        action = decision["action"]
    else:
        text = state.get("message", "").strip().lower().rstrip(".!。")
        if text in {"네", "예", "응", "확정", "확정해줘", "저장해줘", "confirm", "yes"}:
            action = "confirm"
        elif text in {"아니요", "아니", "취소", "취소해줘", "cancel", "no"}:
            action = "cancel"
        else:
            # A revision is a model task, never interpreted as permission to save.
            from app.agents.team import team_node
            return await team_node(state, config)
    resolved = await ProposalRepository().resolve(state["user_id"], proposal["id"], proposal["version"], action)
    label = {"plan": "식단 계획", "intake": "실제 섭취 기록", "measurement": "인바디 측정", "strategy": "새 전략",
             "meal_delete": "섭취 기록 삭제", "meal_replace": "섭취 기록 수정"}[proposal["kind"]]
    message = f"{label}을 {'확정했습니다' if action == 'confirm' else '취소했습니다'}."
    if proposal["kind"] == "plan" and action == "confirm":
        message += " 실제 섭취량에는 반영되지 않습니다. 드신 뒤 기록해주세요."
    return {"response": message, "agent_used": "confirm", "pending_proposal": None,
            "pending_meals": None, "awaiting_confirmation": False, "proposal_decision": None,
            "proposal_result": resolved, "execution_status": resolved["status"]}
