"""
ocr/food_vision.py

음식 사진 → 음식명 리스트 추출 (GPT-4o Vision).

설계 원칙 (inbody_ocr와 동일 철학):
  - Vision을 '데이터 파싱'에만 사용. AI가 식단을 멋대로 자동 기록하는 게 아니라
    "무슨 음식인지"만 인식 → 사용자 확인("네") → 양(g)은 사용자가 직접 입력.
  - 양(g) 추정은 어떤 모델이든 부정확하므로 절대 추정하지 않음 → 신뢰도 확보.
  - 인식된 음식명은 기존 diet_logger 흐름(CSV 영양계산 + HITL 확정)으로 그대로 연결.

기존 칼로리 앱과의 차이:
  - 기존: 음식을 일일이 타이핑/검색
  - 이 앱: 사진 한 장 → 음식명 자동 인식 → 확인만 하면 기존 RAG·검증 파이프라인으로
"""
import base64
import re
import json
from openai import AsyncOpenAI
from app.core.config import get_settings

client = AsyncOpenAI(api_key=get_settings().openai_api_key)

FOOD_IDENTIFY_PROMPT = """이 사진에 보이는 '음식'의 이름만 한국어로 나열하세요.
규칙:
- 사람이 먹는 음식/음료만. 식기·배경·장식·로고는 제외.
- 양(g)·칼로리·영양성분은 절대 쓰지 마세요. 음식 '이름'만.
- 한 접시에 여러 음식이 있으면 각각 분리해서.
- 일반적으로 통용되는 명칭으로 (예: "연어구이", "쌀밥", "김치찌개").
JSON 배열로만 응답: ["음식1","음식2"]
음식이 안 보이면 []. JSON 외 텍스트 절대 금지."""


async def identify_foods_from_image(image_bytes: bytes) -> list[str]:
    """음식 사진 bytes → 음식명 리스트. 인식 실패 시 빈 리스트."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": FOOD_IDENTIFY_PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}",
                               "detail": "low"}},   # 음식 식별엔 low로 충분(토큰 절감)
            ],
        }],
        max_tokens=200,
        temperature=0,
    )
    raw = re.sub(r"```json|```", "", resp.choices[0].message.content.strip()).strip()
    try:
        foods = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [f.strip() for f in foods if isinstance(f, str) and f.strip()]
