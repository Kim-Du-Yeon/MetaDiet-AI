"""
ocr/inbody_ocr.py

역할: 인바디 사진 → 핵심 체성분 수치 추출
기대효과:
  - 사용자가 숫자를 직접 타이핑하는 번거로움 제거
  - 입력 오류(오타) 원천 차단
  - 인바디 결과지를 찍어서 올리는 것만으로 전략 재설정 트리거

기존 칼로리 앱과의 차이:
  - 기존 앱: 체중만 수동 입력
  - 이 앱: 골격근량·체지방률·BMR까지 자동 추출 →
           "근손실 없이 체지방만 줄었는가"를 판단하는 근거로 활용

구현 방식:
  GPT-4o Vision을 사용 (별도 Vision 전용 기능이 아니라
  인바디 "데이터 파싱"에만 Vision 사용 - 식단 인식과 구분)
  → tesseract OCR 대비 한국어 인바디 용지 인식률 월등히 높음
"""
import base64
import re
import json
from openai import AsyncOpenAI
from app.core.config import get_settings

client = AsyncOpenAI(api_key=get_settings().openai_api_key)

INBODY_EXTRACT_PROMPT = """
이 이미지는 InBody 체성분 분석 결과지입니다.
아래 항목들을 정확히 추출해서 JSON으로만 응답하세요.
찾을 수 없는 값은 null로 표시하세요.

{
  "measured_date": "YYYY-MM-DD (날짜/시간 섹션에서)",
  "height_cm": 숫자,
  "weight_kg": 숫자,
  "skeletal_muscle_kg": 숫자 (골격근량),
  "body_fat_kg": 숫자 (체지방량),
  "body_fat_pct": 숫자 (체지방률 %),
  "bmi": 숫자,
  "bmr_kcal": 숫자 (기초대사량),
  "protein_kg": 숫자 (단백질 kg),
  "mineral_kg": 숫자 (무기질 kg),
  "total_body_water_kg": 숫자 (체수분)
}

JSON 외 다른 텍스트는 절대 출력하지 마세요.
"""

async def extract_inbody_from_image(image_bytes: bytes) -> dict:
    """
    인바디 이미지 bytes → 파싱된 체성분 dict 반환
    """
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": INBODY_EXTRACT_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "high"
                        }
                    }
                ]
            }
        ],
        max_tokens=500,
        temperature=0,   # 수치 추출은 창의성 불필요 → 0
    )

    raw = response.choices[0].message.content.strip()

    # JSON 펜스 제거 후 파싱
    raw = re.sub(r"```json|```", "", raw).strip()
    data = json.loads(raw)

    # 필수값 검증
    required = ["weight_kg", "skeletal_muscle_kg", "body_fat_pct"]
    for field in required:
        if data.get(field) is None:
            raise ValueError(f"인바디 OCR 실패: {field} 추출 불가. 이미지를 다시 업로드해주세요.")

    return data
