"""
rag/retriever.py

RAG 검색의 단일 진입점. '지능'을 여기에 집중시켜 노드는 호출만 하면 되게 한다.

검색 파이프라인:
  질문 → (한국어면 영어로 번역) → [dense(Pinecone 임베딩) 후보] + [sparse(BM25 키워드) 후보]
       → (번역이 일어났으면 원본 한국어 쿼리로도 추가 검색 → 위 결과와 RRF 재병합)
       → RRF 융합(상호보완) → FlashRank 리랭킹(로컬 cross-encoder, LLM 토큰 0)
       → top-k → 최상위 리랭크 점수로 grounded 판정

견고성: 청크 캐시(BM25)나 flashrank가 없으면 자동으로 dense-only로 폴백.
        (재인덱싱 전이라도 기존 동작 유지)

cross-lingual: 코퍼스가 영어 문서뿐이라 한국어 질의는 그대로 검색하면 성능이
        떨어진다(EVALUATION.md 7장). _translate_to_english()가 진입부에서
        한국어를 감지해 영어 쿼리로 변환 + 원본 쿼리도 함께 검색(dual query
        expansion)해서 번역 누락을 보완한다. 영어 입력은 기존 동작과 100% 동일.
"""
import pickle, re, json, asyncio
import hashlib
import logging
from threading import RLock
from pathlib import Path
from pinecone import Pinecone, ServerlessSpec
from app.core.llm import get_chat_model
from app.core.prompts import get_prompt
from app.core.embeddings import GeminiEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_pinecone import PineconeVectorStore
from langchain_core.documents import Document
from app.core.config import get_settings

settings = get_settings()

embeddings = GeminiEmbeddings()

_translate_llm = get_chat_model(temperature=0, task='query_translation')
_KOREAN_RE = re.compile(r"[가-힣]")
from app.core.prompts import RegisteredChatPrompt
_TRANSLATE_PROMPT = RegisteredChatPrompt('rag.query_translation', '{query}')


async def _translate_to_english(query: str) -> str:
    """한국어 포함 쿼리를 영어 검색 쿼리로 변환. 한국어가 없으면 그대로 반환."""
    if not _KOREAN_RE.search(query or ""):
        return query
    try:
        resp = await _translate_llm.ainvoke(_TRANSLATE_PROMPT.format_messages(query=query))
        return resp.content.strip() or query
    except Exception as e:
        print(f"=== 쿼리 번역 실패(원본 유지): {e} ===")
        return query

_vector_store: PineconeVectorStore = None
_bm25 = None
_bm25_loaded = False          # 로드 시도 여부(실패 시 재시도 방지)
_reranker = None
_reranker_loaded = False
_kiwi = None
_initialization_lock = RLock()


def _get_kiwi():
    """Kiwi 형태소 분석기 모듈 레벨 싱글턴(매 토크나이즈 호출마다 재생성 방지)."""
    global _kiwi
    if _kiwi is None:
        from kiwipiepy import Kiwi
        _kiwi = Kiwi(num_workers=1)
    return _kiwi


def kiwi_tokenize(text: str) -> list[str]:
    """BM25용 한국어 형태소 토크나이저. 영어 텍스트도 그대로 토큰화되어 영향 최소.
    분석 실패 시 기존 공백 분리(text.split())로 폴백."""
    try:
        return [t.form for t in _get_kiwi().tokenize(text)]
    except Exception:
        return text.split()


def get_vector_store(*, for_build: bool = False) -> PineconeVectorStore:
    with _initialization_lock:
        return _load_vector_store(for_build=for_build)


def _load_vector_store(*, for_build: bool = False) -> PineconeVectorStore:
    global _vector_store
    if not for_build:
        manifest_path = Path(settings.get_chunks_path()).with_name("activation.json")
        if not manifest_path.is_file():
            raise ValueError("Gemini RAG build is not activated; rebuild and select activation.json settings")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {"namespace": settings.pinecone_namespace,
                    "embedding_model": settings.embedding_model,
                    "embedding_dimension": settings.embedding_dimension}
        if any(manifest.get(key) != value for key, value in expected.items()):
            raise ValueError("RAG manifest does not match the configured Gemini embedding build")
    if _vector_store is None:
        if not settings.pinecone_namespace.startswith("metadiet-gemini-"):
            raise ValueError("Select a rebuilt metadiet-gemini- namespace; legacy vectors are incompatible")
        pc = Pinecone(api_key=settings.pinecone_api_key)
        existing = [i.name for i in pc.list_indexes()]
        if settings.pinecone_index_name in existing:
            description = pc.describe_index(settings.pinecone_index_name)
            if description.dimension != settings.embedding_dimension:
                raise ValueError("Pinecone dimension mismatch; use a separate compatible index")
        if settings.pinecone_index_name not in existing:
            if not for_build:
                raise RuntimeError(
                    "Configured Pinecone index does not exist; runtime retrieval is read-only"
                )
            pc.create_index(
                name=settings.pinecone_index_name,
                dimension=settings.embedding_dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
        _vector_store = PineconeVectorStore(
            index_name=settings.pinecone_index_name,
            embedding=embeddings,
            pinecone_api_key=settings.pinecone_api_key,
            namespace=settings.pinecone_namespace or None,
        )
    return _vector_store


def _get_bm25():
    with _initialization_lock:
        return _load_bm25()


def _memory_limit_bytes() -> int | None:
    """Read container hard limits; never use host RAM as the container budget."""
    limits = []
    for path in ("/sys/fs/cgroup/memory.max",
                 "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            value = int(Path(path).read_text(encoding="ascii").strip())
            if 0 < value < 2**60:
                limits.append(value)
        except (OSError, ValueError):
            continue
    return min(limits) if limits else None


def _load_bm25():
    """청크 캐시(chunks.pkl)에서 BM25 sparse 검색기 lazy 로드. 없으면 None(폴백)."""
    global _bm25, _bm25_loaded
    if _bm25_loaded:
        return _bm25
    _bm25_loaded = True
    limit = _memory_limit_bytes()
    if limit is not None and limit <= 512 * 1024 * 1024:
        # Kiwi's measured initialization alone exceeds this container budget.
        # Keep remote dense retrieval and its grounding gate available.
        logging.getLogger(__name__).warning(
            "rag_sparse_unavailable reason=memory_budget limit_bytes=%s", limit
        )
        _bm25 = None
        return None
    try:
        from langchain_community.retrievers import BM25Retriever
        with open(settings.get_chunks_path(), "rb") as f:
            chunks = pickle.load(f)
        if any(c.metadata.get("embedding_model") != settings.embedding_model
               or c.metadata.get("embedding_dimension") != settings.embedding_dimension
               for c in chunks):
            raise ValueError("BM25 corpus belongs to a different embedding build")
        _bm25 = BM25Retriever.from_documents(chunks, preprocess_func=kiwi_tokenize)
        _bm25.k = settings.rag_candidate_k
        print(f"=== BM25 로드 완료: {len(chunks)}개 청크 ===")
    except Exception as e:
        print(f"=== BM25 미사용(dense-only 폴백): {e} ===")
        _bm25 = None
    return _bm25


def _get_reranker():
    with _initialization_lock:
        return _load_reranker()


def _load_reranker():
    """FlashRank 로컬 리랭커 lazy 초기화. 없으면 None(폴백)."""
    global _reranker, _reranker_loaded
    if _reranker_loaded:
        return _reranker
    _reranker_loaded = True
    try:
        from flashrank import Ranker
        _reranker = Ranker(model_name=settings.rag_rerank_model)
        print(f"=== FlashRank 로드 완료: {settings.rag_rerank_model} ===")
    except Exception as e:
        print(f"=== 리랭커 미사용(폴백): {e} ===")
        _reranker = None
    return _reranker


def _doc_key(d: Document) -> str:
    """RRF identity normalizes Pinecone numeric pages and hashes the full text."""
    src = d.metadata.get("source_file", d.metadata.get("source", ""))
    page = d.metadata.get("page", "")
    if isinstance(page, float) and page.is_integer():
        page = int(page)
    digest = hashlib.sha256(d.page_content.encode("utf8")).hexdigest()
    return f"{src}|{page}|{digest}"


def _rrf(dense: list, sparse: list, c: int = 60) -> list:
    """Reciprocal Rank Fusion: dense·sparse 순위를 점수로 합산해 재정렬."""
    score, dmap = {}, {}
    for rank, d in enumerate(dense):
        key = _doc_key(d); dmap[key] = d
        score[key] = score.get(key, 0.0) + 1.0 / (c + rank + 1)
    for rank, d in enumerate(sparse):
        key = _doc_key(d); dmap[key] = d
        score[key] = score.get(key, 0.0) + 1.0 / (c + rank + 1)
    return [dmap[k] for k in sorted(score, key=score.get, reverse=True)]


def _rerank(query: str, docs: list, top_k: int):
    """FlashRank로 후보 재정렬. 반환: (top_k 문서, 최상위 점수 또는 None)."""
    ranker = _get_reranker()
    if ranker is None or not docs:
        return docs[:top_k], None
    from flashrank import RerankRequest
    passages = [{"id": i, "text": d.page_content} for i, d in enumerate(docs)]
    ranked = ranker.rerank(RerankRequest(query=query, passages=passages))
    out = [docs[r["id"]] for r in ranked[:top_k]]
    top_score = float(ranked[0]["score"]) if ranked else None
    return out, top_score


def _format_context(docs: list[Document], max_docs: int, max_chars: int):
    if max_docs < 1 or max_chars < 1:
        raise ValueError("Context limits must be positive")
    blocks, included, used = [], [], 0
    for doc in docs[:max_docs]:
        source = doc.metadata.get("source_file", doc.metadata.get("source", "Unknown"))
        header = f"[출처: {source}, 페이지: {doc.metadata.get('page', 'N/A')}]\n"
        separator = 2 if blocks else 0
        remaining = max_chars - used - separator
        if remaining <= len(header):
            break
        block = header + doc.page_content[:remaining - len(header)]
        blocks.append(block)
        included.append(doc)
        used += separator + len(block)
    return "\n\n".join(blocks), included


def format_docs(docs: list[Document], max_docs: int = 4, *, max_chars: int = 6000) -> str:
    """
    Document 리스트를 출처(파일명·페이지) 포함 컨텍스트 문자열로 변환.
    각 노드에 흩어져 있던 동일 포맷 로직을 한 곳으로 통합(DRY).
    """
    return _format_context(docs, max_docs, max_chars)[0]


def _dense_search(store, query: str, cand_k: int):
    """dense 후보 (+ cosine 점수: 리랭커 폴백 시 grounded 판정용)."""
    try:
        dense_scored = store.similarity_search_with_relevance_scores(query, k=cand_k)
        dense_docs = [d for d, _ in dense_scored]
        dense_max  = max([s for _, s in dense_scored if s is not None], default=0.0)
    except Exception:
        dense_docs, dense_max = store.similarity_search(query, k=cand_k), 0.0
    return dense_docs, dense_max


def _sparse_search(query: str, *, strict: bool = False) -> list:
    """sparse 후보(BM25). 캐시 미가용/검색 실패면 빈 리스트(dense-only 폴백)."""
    bm25 = _get_bm25()
    if bm25 is None:
        if strict:
            raise RuntimeError("BM25 unavailable")
        return []
    try:
        return bm25.invoke(query)
    except Exception as e:
        if strict:
            raise
        print(f"=== BM25 검색 실패(dense만 사용): {e} ===")
        return []


async def retrieve(query: str, k: int = 4, max_docs: int = 4,
                   use_hybrid: bool = True, use_rerank: bool | None = None,
                   strict_components: bool = False) -> dict:
    """
    하이브리드 검색 + 리랭킹 + 신뢰도 판정을 한 번에 수행하는 단일 진입점.

    use_hybrid / use_rerank: eval 비교(ablation)용 스위치. 리랭커를 명시하지
    않으면 최종 평가로 선정한 ``RAG_USE_RERANK`` 운영 설정을 사용한다.

    반환 dict:
      context   : 출처·페이지 인용 포함 컨텍스트. grounded=False면 "".
      grounded  : 근거가 충분한지(리랭크 점수 또는 dense cosine 임계값 기준).
      max_score : 최상위 점수(리랭크 우선, 폴백 시 cosine).
      docs      : 최종 top-k Document 리스트.
    """
    use_rerank = settings.rag_use_rerank if use_rerank is None else use_rerank
    store  = await asyncio.to_thread(get_vector_store)
    cand_k = settings.rag_candidate_k
    if strict_components:
        if use_hybrid and await asyncio.to_thread(_get_bm25) is None:
            raise RuntimeError("BM25 unavailable")
        if use_rerank and await asyncio.to_thread(_get_reranker) is None:
            raise RuntimeError("Reranker unavailable")

    # 0) 한국어 쿼리는 영어로 번역. 이미 영어면 그대로(기존 호출부는 동작 불변).
    translated = await _translate_to_english(query)

    # 1~2) dense+sparse 후보 → RRF 융합 (번역 쿼리 기준)
    dense_docs, dense_max = await asyncio.to_thread(_dense_search, store, translated, cand_k)
    sparse_docs = await asyncio.to_thread(_sparse_search, translated, strict=strict_components) if use_hybrid else []
    candidates = _rrf(dense_docs, sparse_docs)[:cand_k] if sparse_docs else dense_docs

    # 2b) Dual query expansion: 실제로 번역이 일어난 경우(원문이 한국어)에만
    #     원본 쿼리로도 검색해서 후보를 보강(번역 누락 보완) → 두 결과를 RRF로 재병합.
    #     _rrf는 _doc_key 기준으로 합치므로 동일 청크 중복도 여기서 자동 제거됨.
    if translated != query:
        dense_docs2, dense_max2 = await asyncio.to_thread(_dense_search, store, query, cand_k)
        sparse_docs2 = await asyncio.to_thread(_sparse_search, query, strict=strict_components) if use_hybrid else []
        candidates2 = _rrf(dense_docs2, sparse_docs2)[:cand_k] if sparse_docs2 else dense_docs2
        candidates  = _rrf(candidates, candidates2)[:cand_k]
        dense_max   = max(dense_max, dense_max2)

    # 3) 리랭킹 → top-k (비활성이면 후보 상위 k 그대로). FlashRank가 영어 전용
    #    cross-encoder라 리랭크 쿼리는 항상 translated(영어) 사용.
    if use_rerank:
        docs, rerank_top = await asyncio.to_thread(_rerank, translated, candidates, k)
    else:
        docs, rerank_top = candidates[:k], None

    # 4) grounded 판정(리랭크 점수 우선, 없으면 dense cosine)
    for doc in docs:
        page = doc.metadata.get("page")
        if isinstance(page, float) and page.is_integer():
            doc.metadata["page"] = int(page)
    if rerank_top is not None:
        grounded   = rerank_top >= settings.rag_rerank_threshold
        max_score  = round(rerank_top, 3)
    else:
        grounded   = dense_max >= settings.rag_score_threshold
        max_score  = round(dense_max, 3)

    context, context_docs = _format_context(docs, max_docs, 6000) if grounded else ("", [])
    return {
        "context":   context,
        "context_docs": context_docs,
        "grounded":  grounded,
        "max_score": max_score,
        "docs":      docs,
        "retrieval_mode": "hybrid" if use_hybrid and _bm25 is not None else "dense_fallback" if use_hybrid else "dense",
    }


async def search_nutrition_knowledge(query: str, k: int = 4) -> list[Document]:
    """(하위 호환) 기존 호출부(inbody·reporter·rag_tool)용. 하이브리드 파이프라인 경유."""
    result = await retrieve(query, k=k, max_docs=k)
    return result["docs"]
