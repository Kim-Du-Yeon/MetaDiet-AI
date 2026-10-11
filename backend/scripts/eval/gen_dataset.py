"""
scripts/eval/gen_dataset.py

RAG 평가용 합성 QA 데이터셋 생성기 (하드코딩 없이 코퍼스에서 자동 생성).

원리:
  1. 코퍼스 PDF를 청킹 → 충분히 긴 청크만 후보로 (목차·참고문헌 같은 정크 제외)
  2. 무작위 N개 청크 샘플 → 각 청크로 답할 수 있는 질문을 LLM이 1개 생성
  3. {question, gold_source, gold_page} 저장
     → gold_page가 검색 결과에 들어오는지로 retrieval 정확도를 정량 측정

결과는 qa_dataset.json에 캐시. 이미 있으면 재생성 안 함(토큰 절감).
재생성하려면 --force, 개수는 --n.

실행:
  python scripts/eval/gen_dataset.py            # 기본 10개, 캐시 우선
  python scripts/eval/gen_dataset.py --n 15 --force
"""
import sys, os, json, asyncio, random, argparse
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.core.llm import get_chat_model
from app.core.config import get_settings

OUT_PATH  = Path(__file__).parent / "qa_dataset.json"
DOCS_DIR  = Path(__file__).resolve().parents[3] / "docs" / "nutrition"
MIN_CHARS = 350   # 이보다 짧은 청크는 QA 후보에서 제외 (정크 회피)

llm = get_chat_model(temperature=0.3, role="eval")


def load_candidate_chunks() -> list:
    """코퍼스를 청킹해 QA 후보 청크(충분히 길고 내용 있는 것)만 반환."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    cands = []
    for pdf in sorted(DOCS_DIR.glob("*.pdf")):
        print(f"로딩: {pdf.name}")
        for c in splitter.split_documents(PyPDFLoader(str(pdf)).load()):
            text = c.page_content.strip()
            # 정크 휴리스틱: 너무 짧거나 표/참고문헌처럼 보이는 것 제외
            if len(text) < MIN_CHARS:
                continue
            if text.lower().count("http") > 2 or text.count(".....") > 0:
                continue
            c.metadata["source_file"] = pdf.name
            cands.append(c)
    print(f"QA 후보 청크: {len(cands)}개")
    return cands


async def make_question(chunk_text: str) -> str | None:
    """청크로 답할 수 있는 구체적 질문 1개 생성. 부적합하면 None.
    질문은 영어로 생성한다 — 코퍼스가 영어이고, 프로덕션 노드도 쿼리를
    영어로 번역해 검색하므로, 영어 질문이 실제 검색 경로를 공정하게 측정한다."""
    resp = await llm.ainvoke(
        f"""From the nutrition document excerpt below, write ONE specific question
that can be clearly answered using the excerpt.
- Ask about a concrete fact in the excerpt (recommendation, threshold, definition, figure).
- Do NOT ask something answerable by general knowledge without the excerpt.
- If the excerpt lacks factual content, output exactly "SKIP".

[EXCERPT]
{chunk_text[:1500]}

Output only the question (in English) or SKIP:"""
    )
    q = resp.content.strip()
    return None if q.upper().startswith("SKIP") or len(q) < 8 else q


async def main(n: int, force: bool):
    if OUT_PATH.exists() and not force:
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        print(f"캐시 존재 ({len(existing)}개). 재생성하려면 --force. 경로: {OUT_PATH}")
        return

    cands = load_candidate_chunks()
    if not cands:
        print("후보 청크 없음. PDF 경로 확인.")
        return

    # 재현성을 위해 고정 시드로 샘플 (여유분 확보 후 SKIP 걸러 n개 채움)
    random.seed(42)
    random.shuffle(cands)

    dataset = []
    for c in cands:
        if len(dataset) >= n:
            break
        q = await make_question(c.page_content)
        if not q:
            continue
        dataset.append({
            "question":    q,
            "gold_source": c.metadata.get("source_file"),
            "gold_page":   c.metadata.get("page"),
            "gold_excerpt": c.page_content.strip()[:300],
        })
        print(f"  [{len(dataset)}/{n}] {q[:60]}  ← {c.metadata.get('source_file')} p.{c.metadata.get('page')}")

    OUT_PATH.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장 완료: {len(dataset)}개 → {OUT_PATH}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    asyncio.run(main(args.n, args.force))
