"""
rag/retriever.py

RAG 검색의 단일 진입점. '지능'을 여기에 집중시켜 노드는 호출만 하면 되게 한다.

검색 파이프라인:
  질문 → [dense(Pinecone 임베딩) 후보] + [sparse(BM25 키워드) 후보]
       → RRF 융합(상호보완) → FlashRank 리랭킹(로컬 cross-encoder, LLM 토큰 0)
       → top-k → 최상위 리랭크 점수로 grounded 판정

견고성: 청크 캐시(BM25)나 flashrank가 없으면 자동으로 dense-only로 폴백.
        (재인덱싱 전이라도 기존 동작 유지)
"""
import pickle
from pinecone import Pinecone, ServerlessSpec
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_core.documents import Document
from app.core.config import get_settings

settings = get_settings()

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=settings.openai_api_key
)

_vector_store: PineconeVectorStore = None
_bm25 = None
_bm25_loaded = False          # 로드 시도 여부(실패 시 재시도 방지)
_reranker = None
_reranker_loaded = False


def get_vector_store() -> PineconeVectorStore:
    global _vector_store
    if _vector_store is None:
        pc = Pinecone(api_key=settings.pinecone_api_key)
        existing = [i.name for i in pc.list_indexes()]
        if settings.pinecone_index_name not in existing:
            pc.create_index(
                name=settings.pinecone_index_name,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
        _vector_store = PineconeVectorStore(
            index_name=settings.pinecone_index_name,
            embedding=embeddings,
            pinecone_api_key=settings.pinecone_api_key,
        )
    return _vector_store


def _get_bm25():
    """청크 캐시(chunks.pkl)에서 BM25 sparse 검색기 lazy 로드. 없으면 None(폴백)."""
    global _bm25, _bm25_loaded
    if _bm25_loaded:
        return _bm25
    _bm25_loaded = True
    try:
        from langchain_community.retrievers import BM25Retriever
        with open(settings.get_chunks_path(), "rb") as f:
            chunks = pickle.load(f)
        _bm25 = BM25Retriever.from_documents(chunks)
        _bm25.k = settings.rag_candidate_k
        print(f"=== BM25 로드 완료: {len(chunks)}개 청크 ===")
    except Exception as e:
        print(f"=== BM25 미사용(dense-only 폴백): {e} ===")
        _bm25 = None
    return _bm25


def _get_reranker():
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
    """RRF 융합 시 중복 제거용 키(문서+페이지+본문 앞부분)."""
    src = d.metadata.get("source_file", d.metadata.get("source", ""))
    return f"{src}|{d.metadata.get('page','')}|{d.page_content[:60]}"


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


def format_docs(docs: list[Document], max_docs: int = 3) -> str:
    """
    Document 리스트를 출처(파일명·페이지) 포함 컨텍스트 문자열로 변환.
    각 노드에 흩어져 있던 동일 포맷 로직을 한 곳으로 통합(DRY).
    """
    blocks = []
    for d in docs[:max_docs]:
        src  = d.metadata.get("source_file", d.metadata.get("source", "Unknown"))
        page = d.metadata.get("page", "N/A")
        blocks.append(f"[출처: {src}, 페이지: {page}]\n{d.page_content}")
    return "\n\n".join(blocks)


async def retrieve(query: str, k: int = 4, max_docs: int = 3,
                   use_hybrid: bool = True, use_rerank: bool = True) -> dict:
    """
    하이브리드 검색 + 리랭킹 + 신뢰도 판정을 한 번에 수행하는 단일 진입점.

    use_hybrid / use_rerank: eval 비교(ablation)용 스위치. 기본 둘 다 True.

    반환 dict:
      context   : 출처·페이지 인용 포함 컨텍스트. grounded=False면 "".
      grounded  : 근거가 충분한지(리랭크 점수 또는 dense cosine 임계값 기준).
      max_score : 최상위 점수(리랭크 우선, 폴백 시 cosine).
      docs      : 최종 top-k Document 리스트.
    """
    store  = get_vector_store()
    cand_k = settings.rag_candidate_k

    # 1) dense 후보 (+ cosine 점수: 리랭커 폴백 시 grounded 판정용)
    try:
        dense_scored = store.similarity_search_with_relevance_scores(query, k=cand_k)
        dense_docs = [d for d, _ in dense_scored]
        dense_max  = max([s for _, s in dense_scored if s is not None], default=0.0)
    except Exception:
        dense_docs, dense_max = store.similarity_search(query, k=cand_k), 0.0

    # 2) sparse 후보(BM25). 하이브리드 비활성/미가용이면 dense만 사용
    sparse_docs = []
    if use_hybrid:
        bm25 = _get_bm25()
        if bm25 is not None:
            try:
                sparse_docs = bm25.invoke(query)
            except Exception as e:
                print(f"=== BM25 검색 실패(dense만 사용): {e} ===")

    # 3) RRF 융합
    candidates = _rrf(dense_docs, sparse_docs)[:cand_k] if sparse_docs else dense_docs

    # 4) 리랭킹 → top-k (비활성이면 후보 상위 k 그대로)
    if use_rerank:
        docs, rerank_top = _rerank(query, candidates, k)
    else:
        docs, rerank_top = candidates[:k], None

    # 5) grounded 판정(리랭크 점수 우선, 없으면 dense cosine)
    if rerank_top is not None:
        grounded   = rerank_top >= settings.rag_rerank_threshold
        max_score  = round(rerank_top, 3)
    else:
        grounded   = dense_max >= settings.rag_score_threshold
        max_score  = round(dense_max, 3)

    return {
        "context":   format_docs(docs, max_docs) if grounded else "",
        "grounded":  grounded,
        "max_score": max_score,
        "docs":      docs,
    }


async def search_nutrition_knowledge(query: str, k: int = 4) -> list[Document]:
    """(하위 호환) 기존 호출부(inbody·reporter·rag_tool)용. 하이브리드 파이프라인 경유."""
    result = await retrieve(query, k=k, max_docs=k)
    return result["docs"]
