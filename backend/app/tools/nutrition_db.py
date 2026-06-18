"""
nutrition_db.py

국가표준식품성분표 CSV 기반 영양성분 조회 Tool.

CSV 식품명 네이밍 패턴:
  국가표준식품성분표는 "주재료, 세부분류, 조리법" 형태로 저장됨.
  예: 현미밥 → "멥쌀, 현미, 밥"
      닭가슴살 → "닭고기, 가슴, 생것"
      삼겹살 → "돼지고기, 삼겹살, 생것"

검색 전략 (LLM 기반, 하드코딩 없음):
  1. LLM이 사용자 입력 → CSV 검색용 키워드 리스트로 분해
     예: "현미밥" → ["현미", "밥"]
  2. 키워드 AND 검색으로 후보 추출
  3. 후보가 여러 개면 LLM이 가장 적합한 항목 선택

설계 원칙:
  - 컬럼 매핑: LLM이 CSV 컬럼명 자동 파악 (strip 정규화 포함)
  - CSV 경로: config.get_csv_path()에서 관리
  - CSV 구조·컬럼명이 바뀌어도 코드 수정 불필요
"""
import pandas as pd
import json
import re
from functools import lru_cache
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from app.core.config import get_settings

# 전역 캐시 (서버 생애주기 중 최초 1회만 초기화)
_column_mapping: dict | None = None


@lru_cache(maxsize=1)
def _load_raw_df() -> pd.DataFrame:
    """
    CSV 원본 로드 (lru_cache로 한 번만 읽음).
    컬럼명 공백을 strip() 정규화해서 반환.
    """
    csv_path = get_settings().get_csv_path()
    try:
        try:
            df = pd.read_csv(csv_path, encoding="cp949")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="utf-8")

        # 컬럼명 공백 정규화 ("지방 " → "지방" 등)
        df.columns = [c.strip() for c in df.columns]

        print(f"=== 식품성분표 로드 완료: {len(df)}개 식품, {len(df.columns)}개 컬럼 ===")
        print(f"=== CSV 경로: {csv_path} ===")
        return df
    except Exception as e:
        print(f"=== 식품성분표 로드 실패: {e} ===")
        print(f"=== 시도한 경로: {csv_path} ===")
        print("=== .env에 NUTRITION_CSV_PATH=절대경로 를 추가하면 경로를 직접 지정할 수 있습니다 ===")
        return pd.DataFrame()


async def _get_column_mapping() -> dict:
    """
    LLM이 CSV 컬럼명을 보고 핵심 영양소 컬럼을 자동 파악.
    컬럼명이 strip() 정규화된 df 기준으로 매핑.
    서버 생애주기 중 최초 1회만 실행 후 전역 캐시에 저장.
    """
    global _column_mapping
    if _column_mapping is not None:
        return _column_mapping

    df = _load_raw_df()
    if df.empty:
        return {}

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        openai_api_key=get_settings().openai_api_key
    )

    # 앞 40개 컬럼 전달 (strip 정규화된 상태)
    columns = list(df.columns[:40])
    resp = await llm.ainvoke(
        f"""아래 CSV 컬럼 목록에서 식품 영양성분 관련 핵심 컬럼을 찾아 JSON으로만 응답하세요.

컬럼 목록: {columns}

아래 JSON 형식으로 정확한 컬럼명을 반환하세요 (없으면 null):
{{
  "food_name":  "식품명에 해당하는 컬럼명",
  "food_group": "식품군/분류에 해당하는 컬럼명",
  "calories":   "에너지/칼로리에 해당하는 컬럼명",
  "protein":    "단백질에 해당하는 컬럼명",
  "fat":        "지방에 해당하는 컬럼명",
  "carbs":      "탄수화물에 해당하는 컬럼명",
  "sodium":     "나트륨에 해당하는 컬럼명"
}}
JSON 외 텍스트 금지."""
    )

    raw = re.sub(r"```json|```", "", resp.content).strip()
    _column_mapping = json.loads(raw)
    print(f"=== 컬럼 매핑 완료: {_column_mapping} ===")
    return _column_mapping


async def _decompose_keywords_with_llm(food_name: str) -> list[str]:
    """
    LLM이 사용자 입력 음식명을 CSV 검색에 적합한 키워드 리스트로 분해.

    국가표준식품성분표는 "주재료, 세부분류, 조리법" 형태라
    "현미밥" 그대로 검색하면 못 찾음.
    LLM이 CSV 패턴에 맞게 핵심 키워드로 분해.

    예: "현미밥"   → ["현미", "밥"]
        "닭가슴살" → ["닭", "가슴"]
        "삼겹살"   → ["돼지", "삼겹"]  또는 ["삼겹"]
        "오트밀"   → ["오트밀"]
        "연어"     → ["연어"]
    """
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        openai_api_key=get_settings().openai_api_key
    )

    resp = await llm.ainvoke(
        f"""국가표준식품성분표의 식품명은 "주재료, 세부분류, 조리법" 형태로 저장됩니다.
예시:
  현미밥 → 멥쌀, 현미, 밥
  닭가슴살 → 닭고기, 가슴, 생것
  삼겹살 → 돼지고기, 삼겹살, 생것
  소고기 → 쇠고기, 등심, 생것
  오트밀 → 귀리, 오트밀
  연어 → 연어, 생것

사용자 입력 음식: "{food_name}"

위 음식을 CSV 식품명에서 AND 검색할 핵심 키워드 리스트로 분해하세요.
- 2개 이내의 짧은 키워드로
- 각 키워드는 CSV 식품명의 일부분에 반드시 포함될 수 있는 단어
- 조리법(생것/밥 등)은 음식 성격에 따라 포함하거나 생략

JSON 배열로만 응답: ["키워드1", "키워드2"]
예: 현미밥 → ["현미", "밥"]
JSON 외 텍스트 금지."""
    )

    raw = re.sub(r"```json|```", "", resp.content).strip()
    keywords = json.loads(raw)
    print(f"=== 키워드 분해: \"{food_name}\" → {keywords} ===")
    return keywords


async def _find_best_match_with_llm(
    food_name: str,
    df: pd.DataFrame,
    col_map: dict
) -> dict | None:
    """
    1단계: LLM이 분해한 키워드로 AND 검색 → 후보 추출
    2단계: 후보 여러 개면 LLM이 가장 적합한 항목 선택
    """
    food_col = col_map.get("food_name", "식품명")
    if food_col not in df.columns:
        return None

    # ── 1단계: LLM 키워드 분해 → AND 검색 ──────────────────────────
    keywords = await _decompose_keywords_with_llm(food_name)

    candidates = df.copy()
    for kw in keywords:
        candidates = candidates[candidates[food_col].str.contains(kw, na=False)]

    # AND 검색 실패 시 첫 번째 키워드만으로 재시도
    if candidates.empty and keywords:
        print(f"=== AND 검색 실패 → 첫 키워드 \"{keywords[0]}\" 단독 검색 ===")
        candidates = df[df[food_col].str.contains(keywords[0], na=False)]

    # 첫 키워드도 실패 시 원본 food_name 포함 검색
    if candidates.empty:
        print(f"=== 키워드 검색 실패 → 원본 \"{food_name}\" 포함 검색 ===")
        candidates = df[df[food_col].str.contains(food_name, na=False)]

    if candidates.empty:
        return None

    # 후보 1개면 바로 반환
    if len(candidates) == 1:
        return candidates.iloc[0].to_dict()

    # ── 2단계: 후보 여러 개면 LLM이 최적 선택 ──────────────────────
    candidate_names = candidates[food_col].head(20).tolist()

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        openai_api_key=get_settings().openai_api_key
    )

    resp = await llm.ainvoke(
        f"""사용자가 입력한 음식: "{food_name}"

식품성분표 후보 목록:
{candidate_names}

위 후보 중 사용자가 입력한 음식과 가장 잘 일치하는 항목을 하나만 선택하세요.
선택 기준 (LLM이 종합 판단):
1. 사용자 의도에 가장 부합하는 조리 형태
2. 일반적으로 그 음식을 먹을 때의 기본형
3. 특수 품종명(삼광, 오대 등)보다 기본형 우선

선택한 식품명만 출력하세요. 다른 텍스트 금지."""
    )

    selected_name = resp.content.strip()
    match = df[df[food_col] == selected_name]

    if not match.empty:
        return match.iloc[0].to_dict()

    # LLM 선택이 정확히 일치하지 않으면 첫 번째 후보 폴백
    return candidates.iloc[0].to_dict()


@tool
async def nutrition_db_tool(food_name: str, quantity_g: float) -> dict:
    """
    국가표준식품성분표에서 음식의 영양성분을 조회합니다.
    food_name: LLM이 교정한 한국어 음식명
    quantity_g: 섭취량 (g)
    반환: 칼로리, 단백질, 탄수화물, 지방, 나트륨 (quantity_g 기준으로 환산)
    """
    df = _load_raw_df()
    if df.empty:
        return {
            "food_name":   food_name,
            "quantity_g":  quantity_g,
            "found_in_db": False,
            "reason": "CSV 로드 실패 — .env의 NUTRITION_CSV_PATH 또는 파일 위치를 확인하세요",
        }

    # LLM이 컬럼 자동 파악 (strip 정규화된 컬럼명 기준)
    col_map = await _get_column_mapping()
    if not col_map:
        return {
            "food_name":   food_name,
            "quantity_g":  quantity_g,
            "found_in_db": False,
            "reason": "컬럼 매핑 실패",
        }

    # LLM 키워드 분해 + AND 검색 + LLM 최적 선택
    match = await _find_best_match_with_llm(food_name, df, col_map)

    if match:
        ratio = quantity_g / 100.0
        food_col = col_map.get("food_name", "식품명")

        def safe_float(val) -> float:
            try:
                return round(float(str(val).strip() or 0) * ratio, 1)
            except (ValueError, TypeError):
                return 0.0

        result = {
            "food_name":    food_name,
            "matched_name": match.get(food_col, food_name),
            "quantity_g":   quantity_g,
            "calories":     safe_float(match.get(col_map.get("calories"))),
            "protein_g":    safe_float(match.get(col_map.get("protein"))),
            "carbs_g":      safe_float(match.get(col_map.get("carbs"))),
            "fat_g":        safe_float(match.get(col_map.get("fat"))),
            "sodium_mg":    safe_float(match.get(col_map.get("sodium"))),
            "found_in_db":  True,
        }
        print(
            f"=== CSV 조회 성공: {food_name} → {result['matched_name']} "
            f"({quantity_g}g) | {result['calories']}kcal / "
            f"단백질 {result['protein_g']}g ==="
        )
        return result

    print(f"=== CSV 미발견: {food_name} → LLM 추정으로 폴백 ===")
    return {
        "food_name":    food_name,
        "matched_name": None,
        "quantity_g":   quantity_g,
        "found_in_db":  False,
    }


@tool
async def search_food_tool(keyword: str) -> list:
    """
    식품성분표에서 키워드로 식품 목록 검색.
    LLM이 컬럼을 자동 파악해서 반환.
    """
    df = _load_raw_df()
    if df.empty:
        return []

    col_map = await _get_column_mapping()
    food_col = col_map.get("food_name", "식품명")

    if food_col not in df.columns:
        return []

    results = df[df[food_col].str.contains(keyword, na=False)]

    return_cols = [c for c in [
        food_col,
        col_map.get("food_group"),
        col_map.get("calories"),
        col_map.get("protein"),
        col_map.get("fat"),
        col_map.get("carbs"),
        col_map.get("sodium"),
    ] if c and c in df.columns]

    return results[return_cols].head(10).to_dict("records")
