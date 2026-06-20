"""
rag/qa.py

지식베이스(RAG) 기반 질의응답의 단일 진입점.

가드레일을 한 곳에 모아 모든 호출부(노드·eval)가 동일한 정책을 따르게 한다:
  - [근거]에 있는 내용만 답한다 (모델 일반지식으로 추측 금지)
  - 근거가 없거나 약하면(grounded=False) "자료에 없다"고 답한다
  - 모든 사실 주장에 [출처: 파일, p.페이지] 인용을 단다 → 할루시네이션 방지·추적

retrieve()가 검색·신뢰도를 책임지고, 여기선 '답변 생성 가드레일'만 담당한다(분화).
"""
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.core.config import get_settings
from app.rag.retriever import retrieve
from app.rag.region_guidance import get_region_guidance

# QA·평가는 토큰 절감을 위해 mini 사용 (판단형 작업이라 4o-mini로 충분)
_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    openai_api_key=get_settings().openai_api_key,
)

# 근거 없을 때 반환하는 고정 문구 (가드레일 ②). eval에서 이 문자열로 거절 여부 판정.
NO_EVIDENCE = "제공된 자료에서 근거를 찾지 못했습니다."

QA_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 영양학 지식베이스 QA 어시스턴트입니다.
오직 아래 [근거]에 담긴 내용만 사용해 답하세요.

[근거]
{context}

[지역 기준 우선순위]
{region_guidance}

절대 규칙(가드레일):
1. [근거]에 없는 내용은 답하지 마세요. 모델의 일반 지식으로 추측·보충 금지.
2. [근거]가 질문과 무관하거나 답을 담고 있지 않으면, 정확히 다음 문장만 답하세요:
   "{no_evidence}"
3. 모든 사실 주장 끝에 [출처: 파일명, p.페이지] 형식으로 인용을 다세요.
4. 한국어로, 군더더기 없이 답하세요."""),
    ("human", "{question}")
])


async def answer_from_knowledge(question: str, k: int = 4, user_region: str = "KR") -> dict:
    """
    가드레일이 적용된 RAG 답변.

    반환 dict:
      answer    : 답변 문자열 (근거 없으면 NO_EVIDENCE)
      grounded  : RAG 근거 기반 여부 (False면 모델 지식/거절)
      max_score : 최고 relevance score
      sources   : [{source, page}] 인용 출처 목록
      context   : 사용된 근거 원문 (eval의 faithfulness 판정용)
    """
    r = await retrieve(question, k=k)

    # 가드레일 ②: 근거가 약하거나 없으면 LLM 호출 없이 즉시 거절 (토큰 절감 + 환각 차단)
    if not r["grounded"] or not r["context"]:
        return {
            "answer":   NO_EVIDENCE,
            "grounded": False,
            "max_score": r["max_score"],
            "sources":  [],
            "context":  r["context"],
        }

    region_guidance = get_region_guidance(user_region)
    resp = await _llm.ainvoke(QA_PROMPT.format_messages(
        context=r["context"], question=question, no_evidence=NO_EVIDENCE,
        region_guidance=region_guidance,
    ))
    answer = resp.content.strip()

    sources = [
        {
            "source": d.metadata.get("source_file", d.metadata.get("source", "Unknown")),
            "page":   d.metadata.get("page", "N/A"),
        }
        for d in r["docs"][:3]
    ]

    # 출처 안전망: LLM이 인용을 빠뜨려도 검색된 실제 출처를 footer로 강제 부착.
    # (할루시네이션 방지 핵심 — 사용자가 근거 문서를 항상 추적할 수 있게)
    # 단, '근거 없음' 거절 답변에는 출처를 붙이지 않는다(모순 방지).
    if answer != NO_EVIDENCE and "[출처" not in answer:
        seen, foot = set(), []
        for s in sources:
            key = (s["source"], s["page"])
            if key not in seen:
                seen.add(key)
                foot.append(f"[출처: {s['source']}, p.{s['page']}]")
        if foot:
            answer += "\n\n📎 근거: " + " ".join(foot)

    return {
        "answer":   answer,
        "grounded": True,
        "max_score": r["max_score"],
        "sources":  sources,
        "context":  r["context"],
    }
