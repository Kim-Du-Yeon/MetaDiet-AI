"""
ocr/image_classifier.py

업로드된 이미지가 '인바디 결과지'인지 '음식 사진'인지 LLM(Vision)이 판단.
→ 사용자는 카메라 버튼 하나만 쓰고, Agent가 종류를 알아서 분기(하드코딩 없는 판단).

분류만 담당(저비용: detail=low, 출력 1단어). 실제 추출은 검증된 기존 함수
(inbody_ocr.extract_inbody_from_image / food_vision.identify_foods_from_image)에 위임.
"""
from app.ocr.vision import read_image


CLASSIFY_PROMPT = """이 이미지가 무엇인지 한 단어로만 분류하세요.
- inbody : InBody 등 체성분 분석 결과지(수치/그래프가 있는 측정 용지)
- food   : 사람이 먹는 음식 또는 음료 사진
- unknown: 위 둘 다 아님
inbody / food / unknown 중 하나만 출력. 다른 텍스트 금지."""


async def classify_image_type(image_bytes: bytes) -> str:
    """이미지 종류 판단 → 'inbody' | 'food' | 'unknown'."""
    resp = await read_image(image_bytes, CLASSIFY_PROMPT, max_tokens=128)
    out = resp.strip().lower()
    if "inbody" in out:
        return "inbody"
    if "food" in out:
        return "food"
    return "unknown"

