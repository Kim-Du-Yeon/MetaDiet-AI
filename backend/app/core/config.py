"""
config.py

환경변수 기반 설정 관리.
하드코딩 없이 .env 파일에서 모든 설정값을 읽어옵니다.

필수 환경변수 (.env에 추가 필요):
  GEMINI_API_KEY
  SUPABASE_URL
  SUPABASE_SERVICE_KEY
  SUPABASE_JWT_SECRET
  SUPABASE_DB_URL
  PINECONE_API_KEY

선택 환경변수 (기본값 있음):
  PINECONE_INDEX_NAME      기본값: diet-agent-rag
  NUTRITION_CSV_PATH       기본값: (backend 기준 ../docs/nutrition/식품성분표_10개정판.csv)
  LANGSMITH_TRACING        기본값: true
  LANGSMITH_ENDPOINT       기본값: https://api.smith.langchain.com
  LANGSMITH_API_KEY        기본값: ""
  LANGSMITH_PROJECT        기본값: diet-agent
  ENVIRONMENT              기본값: development
"""
import os
from typing import Literal
from pydantic_settings import BaseSettings
from functools import lru_cache


def _default_csv_path() -> str:
    """
    NUTRITION_CSV_PATH 미설정 시 기본 경로 계산.
    config.py 위치: backend/app/core/config.py
    CSV 위치:       diet_agent/docs/nutrition/식품성분표_10개정판.csv
    따라서 config.py 기준 ../../../../docs/nutrition/ 으로 이동:
      core/ → app/ → backend/ → diet_agent/ → docs/nutrition/
    """
    base = os.path.dirname(os.path.abspath(__file__))  # backend/app/core
    return os.path.normpath(
        os.path.join(base, "..", "..", "..", "docs", "nutrition",
                     "식품성분표_10개정판.csv")
    )


def _default_chunks_path() -> str:
    """
    BM25(sparse) 검색용 청크 캐시 기본 경로.
    build_rag.py가 인덱싱 시 청크를 여기에 저장하고,
    retriever가 런타임에 로드해 하이브리드 검색에 사용.
    위치: backend/app/rag/chunks.pkl
    """
    base = os.path.dirname(os.path.abspath(__file__))  # backend/app/core
    return os.path.normpath(os.path.join(base, "..", "rag", "chunks.pkl"))


class Settings(BaseSettings):
    food_catalog_enabled: bool = True
    typesafe_api_key: str = ""
    jev_model: str = "jev-1.13.0"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_vision_model: str = "gemini-3.8-flash"
    gemini_eval_model: str = "gemini-3.8-flash"
    # Only verified read-only follow-ups; 'default' omits the provider override.
    coaching_thinking_level: Literal['default', 'low'] = 'low'
    model_timeout_seconds: float = 30
    eval_model_timeout_seconds: float = 90
    model_max_retries: int = 0
    agent_max_model_calls: int = 12
    agent_max_tool_calls: int = 20
    agent_max_replans: int = 2
    agent_max_validation_attempts: int = 3
    agent_timeout_seconds: float = 120
    deep_agent_max_model_calls: int = 20
    deep_agent_max_tool_calls: int = 30
    deep_agent_timeout_seconds: float = 180
    pinecone_namespace: str = "metadiet-gemini-v1"
    supabase_url: str
    supabase_service_key: str
    supabase_jwt_secret: str
    supabase_db_url: str = ""
    pinecone_api_key: str
    pinecone_index_name: str = "diet-agent-rag"

    # 임베딩 모델 (하드코딩 회피 — 모델/차원 변경 시 여기만 수정).
    # large는 cross-lingual(한국어 질의) 검색 정밀도가 small보다 높음.
    embedding_model:     str = "gemini-embedding-2"
    embedding_dimension: int = 3072

    # RAG 신뢰도 임계값 (dense-only 폴백 시 cosine relevance 기준).
    # 최고 score가 이 값 미만이면 grounded=False → 추측 차단. eval로 보정.
    rag_score_threshold: float = 0.35

    # 하이브리드 검색 + 리랭킹 파라미터 (모두 eval로 보정하는 튜닝값, 하드코딩 회피)
    rag_candidate_k:      int   = 20      # 리랭킹 전 dense+sparse 후보 수
    rag_use_rerank:       bool  = False   # 최종 평가 채택값: Hybrid + 리랭커 없음
    rag_rerank_threshold: float = 0.15    # 리랭크 최고 점수 임계값(grounded 판정)
    rag_rerank_model:     str   = "ms-marco-MiniLM-L-12-v2"  # FlashRank 로컬 모델
    rag_chunks_path:      str   = ""      # 비우면 _default_chunks_path 사용

    # 청킹 빌드 파라미터 (build_rag.py에서 사용; eval로 튜닝)
    rag_min_page_chars:          int = 200
    rag_max_chunk_chars:         int = 1200
    rag_chunk_overlap:           int = 150
    rag_semantic_threshold_type: str = "percentile"

    # CSV 경로: .env의 NUTRITION_CSV_PATH 우선, 없으면 자동 계산
    nutrition_csv_path: str = ""

    langsmith_tracing: str = "true"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_api_key: str = ""
    langsmith_project: str = "diet-agent"
    environment: str = "development"
    service_timezone: str = "Asia/Seoul"
    admin_emails: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

    def get_csv_path(self) -> str:
        """
        nutrition_csv_path가 .env에 설정되어 있으면 그것을 사용,
        없으면 프로젝트 구조 기반 기본값 반환.
        """
        if self.nutrition_csv_path:
            return self.nutrition_csv_path
        return _default_csv_path()

    def get_chunks_path(self) -> str:
        """BM25용 청크 캐시 경로 (.env의 RAG_CHUNKS_PATH 우선, 없으면 기본값)."""
        if self.rag_chunks_path:
            return self.rag_chunks_path
        return _default_chunks_path()


@lru_cache
def get_settings() -> Settings:
    return Settings()
