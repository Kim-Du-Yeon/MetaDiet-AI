"""
rag/region_guidance.py

RAG 지역 우선순위 가드레일 문구의 단일 출처.
한국 KDRIs와 WHO 등 국제 기준이 동시에 검색됐을 때 어느 쪽을 우선 채택할지
LLM에 명시적으로 지시한다(qa.py 및 실채팅 RAG 호출 노드가 공유).
"""
REGION_GUIDANCE = {
    "KR": (
        "한국인 영양 기준(KDRIs 2020)이 검색된 경우 이를 최우선으로 적용하고, "
        "KDRIs에 없는 내용은 WHO 등 국제 기준으로 보완하되 출처를 명시할 것. "
        "두 기준이 충돌하면 반드시 KDRIs를 채택하고 차이를 사용자에게 안내할 것."
    ),
    "INTL": (
        "WHO 및 국제 영양 기준을 우선 적용하고, "
        "한국 특이 식품/식문화 관련 내용은 KDRIs를 참고할 것. "
        "출처를 항상 명시할 것."
    ),
}


def get_region_guidance(user_region: str | None) -> str:
    """user_region(KR/INTL)에 맞는 지역 우선순위 가드레일 문구. 없거나 미지원 값이면 KR 기본값."""
    return REGION_GUIDANCE.get(user_region, REGION_GUIDANCE["KR"])
