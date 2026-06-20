"""
off_topic/node.py

역할: 식단/영양/운동/체중/인바디/목표와 무관한 질문에 고정 응답.
      supervisor가 이미 off_topic으로 분류했으므로 LLM 재호출 없이 안내 메시지만 반환(토큰 비용 0).
"""
from app.schemas.models import AgentState

OFF_TOPIC_RESPONSE = (
    "저는 식단 코칭 AI입니다 😊\n"
    "영양, 식단 기록, 체중 목표, 식단 계획 등\n"
    "식단 관련 질문을 도와드릴 수 있어요.\n"
    "궁금한 식단 정보가 있으신가요?"
)


async def off_topic_node(state: AgentState) -> dict:
    return {"response": OFF_TOPIC_RESPONSE, "agent_used": "off_topic"}
