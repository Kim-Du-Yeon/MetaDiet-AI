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
  - Pinecone 업로드(dense 검색용) — 기존 벡터는 클린 삭제 후 재적재
  - chunks.pkl 저장(BM25 sparse 검색용) — retriever가 런타임에 로드

실행:
  D:\\AX\\diet_agent\\backend\\venv\\Scripts\\python.exe scripts/build_rag.py
  (옵션) --docs_dir <경로>  --keep   (--keep: 기존 벡터 삭제 안 함)
"""
import sys, os, pickle
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from app.rag.retriever import get_vector_store, embeddings
from app.core.config import get_settings

settings = get_settings()


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
    if len(t) < settings.rag_min_page_chars:
        return True
    # 목차 점선 리더("......") 다수 → 목차 페이지
    if t.count("....") >= 3:
        return True
    # 숫자·기호 비중이 과도(표·참고문헌 목록)
    alpha = sum(c.isalpha() for c in t)
    if alpha / max(len(t), 1) < 0.45:
        return True
    return False


def _clear_index():
    """기존 벡터 전체 삭제(클린 재인덱싱). 비어있으면 무시."""
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=settings.pinecone_api_key)
        idx = pc.Index(settings.pinecone_index_name)
        idx.delete(delete_all=True)
        print("기존 벡터 전체 삭제 완료(클린 재인덱싱)")
    except Exception as e:
        print(f"기존 벡터 삭제 생략(빈 인덱스이거나 네임스페이스 없음): {e}")


def build_index(docs_dir: str, clear: bool = True):
    docs_path = Path(docs_dir)
    pdf_files = sorted(docs_path.glob("*.pdf"))
    if not pdf_files:
        print(f"PDF 없음: {docs_path.resolve()}")
        return

    semantic = SemanticChunker(embeddings, breakpoint_threshold_type=settings.rag_semantic_threshold_type)
    capper = RecursiveCharacterTextSplitter(chunk_size=settings.rag_max_chunk_chars,
                                            chunk_overlap=settings.rag_chunk_overlap)

    all_chunks = []
    for pdf_path in pdf_files:
        title = _clean_title(pdf_path.name)
        lang  = _detect_lang(pdf_path.name)
        print(f"\n로딩: {pdf_path.name}  (title='{title}', lang='{lang}')")
        pages = PyPDFLoader(str(pdf_path)).load()

        # 1) 정크 페이지 필터
        clean_pages = [p for p in pages if not _is_junk(p.page_content)]
        print(f"  페이지 {len(pages)} → 정크 제외 {len(clean_pages)}")

        # 2) 의미 기반 청킹(페이지 내부) → page 메타데이터 상속
        sem_chunks = semantic.split_documents(clean_pages)
        # 3) 과대 청크 크기 cap
        chunks = capper.split_documents(sem_chunks)

        # 4) 메타데이터 강화
        for c in chunks:
            c.metadata["source_file"] = pdf_path.name
            c.metadata["title"] = title
            c.metadata["lang"] = lang
        all_chunks.extend(chunks)
        print(f"  의미청크 {len(sem_chunks)} → cap 후 {len(chunks)}개")

    print(f"\n총 {len(all_chunks)}개 청크 생성")

    # BM25용 청크 캐시 저장(sparse 검색)
    chunks_path = settings.get_chunks_path()
    os.makedirs(os.path.dirname(chunks_path), exist_ok=True)
    with open(chunks_path, "wb") as f:
        pickle.dump(all_chunks, f)
    print(f"청크 캐시 저장(BM25용): {chunks_path}")

    # Pinecone 업로드(dense)
    if clear:
        _clear_index()
    store = get_vector_store()
    for i in range(0, len(all_chunks), 100):
        store.add_documents(all_chunks[i:i + 100])
        print(f"  업로드 {min(i + 100, len(all_chunks))}/{len(all_chunks)}")
    print("완료!")


if __name__ == "__main__":
    args = sys.argv[1:]
    # 기본 문서 폴더 = CSV와 같은 docs/nutrition 폴더
    docs_dir = str(Path(settings.get_csv_path()).parent)
    if "--docs_dir" in args:
        docs_dir = args[args.index("--docs_dir") + 1]
    keep = "--keep" in args
    build_index(docs_dir, clear=not keep)
