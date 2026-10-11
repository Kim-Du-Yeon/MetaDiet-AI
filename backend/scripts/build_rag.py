"""
build_rag.py

스마트 청킹 기반 RAG 인덱스 빌더.

청킹 전략(고정 크기 → 의미 기반 업그레이드):
  1. PyPDFLoader로 '페이지 단위' 로드 → page 메타데이터 보존(출처표시·평가에 필수)
  2. 정크 필터: 목차(점선)·참고문헌·초단문 페이지 제외(검색 노이즈 제거)
  3. SemanticChunker로 페이지 내부를 '의미 경계'로 분할
     (페이지 단위로 처리하므로 page 메타데이터가 청크에 그대로 상속됨)
  4. 과대 청크는 RecursiveCharacterTextSplitter로 크기 cap → 검색 정밀도 확보
  5. 메타데이터 강화: source_file(파일명) + title(정규화 문서명) + page

산출물:
  - Pinecone 업로드(dense 검색용) — 기본 실행은 안정적인 ID로 upsert
  - chunks.pkl 저장(BM25 sparse 검색용) — retriever가 런타임에 로드

실행:
  D:\\AX\\diet_agent\\backend\\venv\\Scripts\\python.exe scripts/build_rag.py
  (옵션) --docs_dir <경로> --clear-namespace (명시한 namespace만 비움)
"""
import sys, os, pickle, hashlib, json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from app.rag.retriever import get_vector_store, embeddings
from app.core.config import get_settings

settings = get_settings()


def citation_metadata(metadata):
    """Keep loader's zero-based index while citing one-based PDF pages."""
    page_index = metadata.get("page")
    if not isinstance(page_index, int) or page_index < 0:
        raise ValueError("PDF loader must provide a nonnegative page index")
    return {**metadata, "pdf_page_index": page_index, "pdf_page": page_index + 1, "page": page_index + 1}


def _clean_title(filename: str) -> str:
    """파일명 → 사람이 읽을 수 있는 문서 제목으로 정규화."""
    stem = Path(filename).stem
    return re.sub(r"[-_]+", " ", stem).strip()


_KOREAN_RE = re.compile(r"[가-힣]")

# 파일명은 영문이지만 내용은 한국어인 예외 케이스 보정용 매핑(우선 적용).
# 매핑에 없으면 기존 한글 포함 여부 감지로 폴백.
_FILENAME_LANG_OVERRIDES = {
    "guideline2022_vol8.pdf": "ko",  # 대한비만학회 "비만 진료지침 2022(8판)" — 한국어 문서
}


def _detect_lang(filename: str) -> str:
    """파일명 매핑 우선 적용 → 없으면 한글 포함 여부로 한국어 문서 판별(region 기반 지식 우선순위용)."""
    if filename in _FILENAME_LANG_OVERRIDES:
        return _FILENAME_LANG_OVERRIDES[filename]
    return "ko" if _KOREAN_RE.search(filename) else "en"


def _is_junk(text: str) -> bool:
    """목차·참고문헌·정크 페이지 판별(검색 노이즈 제거)."""
    t = text.strip()
    if not t:
        return True
    # 목차 점선 리더("......") 다수 → 목차 페이지
    if t.count("....") >= 3:
        return True
    # Numeric density and short length are not proof of junk: preserve tables.
    return False


def _clear_index(namespace: str | None = None):
    """기존 벡터 전체 삭제(클린 재인덱싱). 비어있으면 무시."""
    namespace = namespace or settings.pinecone_namespace
    if not namespace:
        raise ValueError("Explicit PINECONE_NAMESPACE required for --clear-namespace")
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=settings.pinecone_api_key)
        idx = pc.Index(settings.pinecone_index_name)
        idx.delete(delete_all=True, namespace=namespace)
        print("기존 벡터 전체 삭제 완료(클린 재인덱싱)")
    except Exception as e:
        print(f"기존 벡터 삭제 생략(빈 인덱스이거나 네임스페이스 없음): {e}")


def _build_identity(chunks) -> str:
    payload = {"model": settings.embedding_model, "dimension": settings.embedding_dimension,
               "chunks": [{"text": c.page_content, "metadata": c.metadata} for c in chunks]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def _select_sources(docs_path: Path) -> dict:
    manifest = docs_path / "corpus_manifest.json"
    if not manifest.exists():
        return {path: {} for path in sorted(docs_path.glob("*.pdf"))}
    result = {}
    for entry in json.loads(manifest.read_text(encoding="utf-8")):
        path = (docs_path / entry["path"]).resolve()
        if path.parent != docs_path.resolve() or path.suffix.lower() != ".pdf" or not path.is_file():
            raise ValueError("Manifest must reference existing PDFs inside the corpus directory")
        if path in result:
            raise ValueError("Duplicate corpus manifest entry")
        result[path] = entry
    return result


def build_index(docs_dir: str, clear: bool = False, chunking: str = "semantic"):
    docs_path = Path(docs_dir)
    selected = _select_sources(docs_path)
    pdf_files = list(selected)
    if not pdf_files:
        print(f"PDF 없음: {docs_path.resolve()}")
        return

    semantic = SemanticChunker(embeddings, breakpoint_threshold_type=settings.rag_semantic_threshold_type) if chunking == "semantic" else None
    capper = RecursiveCharacterTextSplitter(chunk_size=settings.rag_max_chunk_chars,
                                            chunk_overlap=settings.rag_chunk_overlap)

    all_chunks = []
    for pdf_path in pdf_files:
        source_meta = selected[pdf_path]
        title = source_meta.get("title") or _clean_title(pdf_path.name)
        lang  = source_meta.get("language") or _detect_lang(pdf_path.name)
        print(f"\n로딩: {pdf_path.name}  (title='{title}', lang='{lang}')")
        pages = PyPDFLoader(str(pdf_path)).load()
        document_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

        # 1) 정크 페이지 필터
        clean_pages = [p for p in pages if not _is_junk(p.page_content)]
        print(f"  페이지 {len(pages)} → 정크 제외 {len(clean_pages)}")

        # 2) 의미 기반 청킹(페이지 내부) → page 메타데이터 상속
        sem_chunks = semantic.split_documents(clean_pages) if semantic else clean_pages
        # 3) 과대 청크 크기 cap
        chunks = capper.split_documents(sem_chunks)

        # 4) 메타데이터 강화
        for c in chunks:
            c.metadata = citation_metadata(c.metadata)
            c.metadata.update({key: source_meta[key] for key in ("source_url", "edition", "population", "usage_notes") if key in source_meta})
            c.metadata["source_file"] = pdf_path.name
            c.metadata["title"] = title
            c.metadata["lang"] = lang
            c.metadata["document_sha256"] = document_hash
            c.metadata["parser"] = "pypdf"
            c.metadata["chunking"] = chunking
            c.metadata["embedding_model"] = settings.embedding_model
            c.metadata["embedding_dimension"] = settings.embedding_dimension
        all_chunks.extend(chunks)
        print(f"  의미청크 {len(sem_chunks)} → cap 후 {len(chunks)}개")

    print(f"\n총 {len(all_chunks)}개 청크 생성")
    if not all_chunks:
        raise ValueError("No chunks produced; active corpus remains unchanged")
    build_id = _build_identity(all_chunks)
    build_namespace = f"metadiet-gemini-{build_id}"
    if build_namespace == settings.pinecone_namespace and clear:
        raise ValueError("Cannot clear the active namespace")

    # Publish the local cache only after all vector batches succeed.
    chunks_path = str(Path(settings.get_chunks_path()).parent / "builds" / build_id / "chunks.pkl")
    os.makedirs(os.path.dirname(chunks_path), exist_ok=True)

    # Pinecone 업로드(dense)
    if clear:
        _clear_index(build_namespace)
    store = get_vector_store(for_build=True)
    for i in range(0, len(all_chunks), 100):
        batch = all_chunks[i:i + 100]
        ids = [hashlib.sha256((c.metadata["document_sha256"] + str(c.metadata.get("page"))
                              + c.page_content + settings.embedding_model).encode()).hexdigest() for c in batch]
        store.add_documents(batch, ids=ids, namespace=build_namespace)
        print(f"  업로드 {min(i + 100, len(all_chunks))}/{len(all_chunks)}")
    temporary = str(chunks_path) + ".tmp"
    with open(temporary, "wb") as f:
        pickle.dump(all_chunks, f)
    os.replace(temporary, chunks_path)
    manifest = {"namespace": build_namespace, "chunks_path": chunks_path,
                "embedding_model": settings.embedding_model, "embedding_dimension": settings.embedding_dimension,
                "chunk_count": len(all_chunks), "status": "built_not_activated"}
    Path(chunks_path).with_name("activation.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Built {build_namespace}. Validate before setting PINECONE_NAMESPACE and RAG_CHUNKS_PATH from activation.json.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    # 기본 문서 폴더 = CSV와 같은 docs/nutrition 폴더
    docs_dir = str(Path(settings.get_csv_path()).parent)
    if "--docs_dir" in args:
        docs_dir = args[args.index("--docs_dir") + 1]
    chunking = args[args.index("--chunking") + 1] if "--chunking" in args else "semantic"
    if chunking not in {"semantic", "recursive"}:
        raise ValueError("--chunking must be semantic or recursive")
    build_index(docs_dir, clear="--clear-namespace" in args, chunking=chunking)
