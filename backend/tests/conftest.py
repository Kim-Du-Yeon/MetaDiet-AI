import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import httpx
import pytest

from app.api.routes.main import app
from app.core.auth import get_current_auth_id, get_current_user


@pytest.fixture(autouse=True)
def block_live_gemini(monkeypatch):
    """Unit/regression tests must explicitly replace the model boundary."""
    import app.core.llm as llm_module

    def blocked(*args, **kwargs):
        raise AssertionError("Live Gemini calls are disabled in the regression suite")

    monkeypatch.setattr(llm_module, "ChatGoogleGenerativeAI", blocked)
    # Food catalog DB boundary is also mocked in ordinary regressions.
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), 'food_catalog_enabled', False)
    from unittest.mock import AsyncMock
    from app.db.proposals import ProposalRepository
    monkeypatch.setattr(ProposalRepository, 'latest_pending', AsyncMock(return_value=None))


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """table().select().eq().limit().execute().data 체인을 받아주는 가짜 쿼리 빌더.
    체인 메서드는 전부 self를 반환하고 execute()만 결과를 낸다.
    insert()/update()는 (method, table, payload)를 FakeSupabase.calls에 기록한다."""

    def __init__(self, data, table_name=None, calls=None):
        self._data = data
        self._table_name = table_name
        self._calls = calls if calls is not None else []

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def lte(self, *a, **k): return self
    def delete(self, *a, **k): return self

    def insert(self, payload):
        self._calls.append(("insert", self._table_name, payload))
        return self

    def update(self, payload):
        self._calls.append(("update", self._table_name, payload))
        return self

    def execute(self):
        return FakeResult(self._data)


class FakeSupabase:
    """table(name)별로 다른 데이터를 주는 가짜 Supabase 클라이언트.
    사용: fake_sb.tables["meal_logs"] = [{...}] 로 테스트마다 값을 바꿔 끼운다.
    fake_sb.calls 로 insert/update 호출 인자를 검증한다."""

    def __init__(self, tables: dict | None = None):
        self.tables = tables or {}
        self.calls = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.tables.get(name, []), table_name=name, calls=self.calls)


class FakeVectorStore:
    """Pinecone PineconeVectorStore 대체 — dense 검색 메서드만 흉내낸다.
    docs_scored: [(Document, score), ...] 고정 리스트 또는 query를 받는 callable."""

    def __init__(self, docs_scored=None):
        self._docs_scored = docs_scored or []

    def similarity_search_with_relevance_scores(self, query, k=20):
        if callable(self._docs_scored):
            return self._docs_scored(query)
        return self._docs_scored

    def similarity_search(self, query, k=20):
        return [d for d, _ in self.similarity_search_with_relevance_scores(query, k)]


@pytest.fixture
def fake_sb(monkeypatch):
    """app.api.routes.main의 모듈 레벨 sb를 FakeSupabase로 교체."""
    import app.api.routes.main as main_module

    fake = FakeSupabase()
    monkeypatch.setattr(main_module, "sb", fake)
    return fake


@pytest.fixture
def mock_current_user():
    """get_current_user/get_current_auth_id를 고정 user-id로 교체(JWT 검증 스킵)."""
    user_id = "test-user-id"
    app.dependency_overrides[get_current_user] = lambda: user_id
    app.dependency_overrides[get_current_auth_id] = lambda: user_id
    yield user_id
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_auth_id, None)


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
