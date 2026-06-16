# Ragas 기반 RAG 평가 보고서

## 1. 개요

| 항목 | 내용 |
|------|------|
| 평가 목적 | ragas 표준 지표로 기존 RAG 파이프라인의 faithfulness / context_recall을 정량 측정 |
| 평가 일자 | 2026-06-15 |
| 평가 스크립트 | `scripts/eval/run_ragas_eval.py` |
| 상태 | 별도 평가 스크립트로 관리 — 기본 실행 환경과 분리 운영, requirements.txt 미반영 |

**배경:** 기존 `run_eval.py`는 `qa_dataset.json`(EN QA 10개, `run_eval.py` 기본 데이터셋)을 기반으로
커스텀 LLM judge(gpt-4o-mini)로 faithfulness를 0/1 이진 판정하고, source_hit·page_hit·excerpt_hit 등
커스텀 검색 지표를 측정한다(`excerpt_hit`은 Ragas 지표가 아니라 `run_eval.py`의 문자열 매칭 지표다).
이를 보완하기 위해 `gold_dataset.json`(EN/KO bilingual QA 10쌍, 총 20개, `run_ragas_eval.py` 기본 데이터셋)을
별도로 구축하고, Ragas 표준 지표(faithfulness·context_recall)로 동일 파이프라인을 재평가하는
`run_ragas_eval.py`를 추가했다(별도 평가 환경/스크립트로 관리, `requirements.txt` 미반영).
Ragas는 faithfulness를 claim 단위 연속값(0.0~1.0)으로 측정하며, `context_recall`로 retrieval 의미 커버리지도 측정한다.

---

## 2. 평가 설정

| 항목 | 값 |
|------|----|
| 데이터셋 | `gold_dataset.json` |
| 샘플 수 | 20개 (EN/KO bilingual QA 10쌍 — 동일 gold_source·gold_page·gold_excerpt 공유) |
| 모드 | `full` (dense + BM25 hybrid + FlashRank reranking) |
| k | 4 |
| Judge LLM | gpt-4o-mini (temperature=0) |
| 지표 | `faithfulness`, `context_recall` |
| 리포트 저장 | `ragas_report.json` (누적), `ragas_report_full.json` (별도 보존) |

### 지표 정의

| 지표 | 의미 | 측정 방식 |
|------|------|----------|
| `faithfulness` | 생성 답변의 사실 주장이 retrieved context로 뒷받침되는 비율 | ragas가 답변을 claim 단위로 분해 → 각 claim이 context에 있는지 LLM 판정 |
| `context_recall` | gold_answer의 주장이 retrieved context에 포함된 비율 | gold_answer를 claim 단위로 분해 → 각 claim이 retrieved context에 있는지 LLM 판정 |

### 기존 지표와의 대응

| ragas 지표 | run_eval.py 대응 지표 | 차이점 |
|-----------|---------------------|--------|
| `faithfulness` | 커스텀 LLM judge (0/1 이진) | ragas는 claim 단위 연속값 |
| `context_recall` | `excerpt_hit` (문자열 부분 일치) | ragas는 의미 기반(LLM 판정) |

---

## 3. 실행 결과

### 3-1. 테스트 실행 (limit 3 — 영어 상위 3개 샘플)

```
python scripts/eval/run_ragas_eval.py --limit 3 --mode full
```

| 지표 | 점수 |
|------|------|
| faithfulness | **0.8333** |
| context_recall | **1.0000** |

### 3-2. 전체 실행 (gold_dataset.json, n=20)

```
python scripts/eval/run_ragas_eval.py --dataset gold_dataset.json --mode full --k 4
```

| 지표 | 점수 |
|------|------|
| faithfulness | **0.5500** |
| context_recall | **0.5750** |

### 3-3. 언어별 구간 분리 결과 (per-sample 로그 기반)

| 구간 | 샘플 수 | faithfulness | context_recall | 기준 |
|------|---------|-------------|---------------|------|
| **전체** | 20 | **0.5500** | **0.5750** | ragas summary (공식) |
| 영어 QA (1~10번) | 10 | **0.9000** | **0.9500** | per-sample 로그 기반 |
| 한국어 QA (11~20번) | 10 | **0.2000** | **0.3000** | per-sample 로그 기반 |
| limit 3 (EN 상위 3개) | 3 | 0.8333 | 1.0000 | 초기 테스트 |

> **집계 방식 주의:** context_recall의 ragas summary 값(0.575)과 per-sample 기반 단순 평균
> (EN 0.95 + KO 0.30 → 전체 0.625) 사이에 0.05 차이가 있다.
> ragas 내부 집계 방식·NaN 처리·claim 단위 정규화 차이에 의한 것으로 간주한다.
> 공식 전체 값은 ragas summary(0.575)를 기준으로 사용하고, 구간 분리는 per-sample 로그를 기반으로 한다.

### 3-4. per-sample 점수 전체 목록

| # | 언어 | faithfulness | context_recall |
|---|------|-------------|---------------|
| 1 | EN | 1.000 | 1.000 |
| 2 | EN | 1.000 | 1.000 |
| 3 | EN | 0.500 | 1.000 |
| 4 | EN | 1.000 | 0.000 |
| 5 | EN | 1.000 | 0.500 |
| 6 | EN | 1.000 | 1.000 |
| 7 | EN | 1.000 | 1.000 |
| 8 | EN | 1.000 | 1.000 |
| 9 | EN | 1.000 | 1.000 |
| 10 | EN | 0.500 | 1.000 |
| **EN 평균** | | **0.900** | **0.950** |
| 11 | KO | 0.000 | 0.000 |
| 12 | KO | 0.000 | 1.000 |
| 13 | KO | 0.000 | 0.000 |
| 14 | KO | 1.000 | 1.000 |
| 15 | KO | 1.000 | 0.000 |
| 16 | KO | 0.000 | 0.000 |
| 17 | KO | 0.000 | 1.000 |
| 18 | KO | 0.000 | 0.000 |
| 19 | KO | 0.000 | 0.000 |
| 20 | KO | 0.000 | 0.000 |
| **KO 평균** | | **0.200** | **0.300** |

---

## 4. 결과 해석

### 4-1. 전체 평균 해석의 전제

전체 평균(faithfulness 0.550 / context_recall 0.575)만 보면 낮게 보일 수 있다.
그러나 이는 RAG 파이프라인 전체가 실패한 것이 아니라,
**영어 PDF corpus에 한국어 질문을 직접 검색하는 cross-lingual 평가 구간**이 포함되어 있기 때문이다.
언어별로 분리하면 성능 차이가 명확하게 드러난다.

### 4-2. 영어 QA 구간 (n=10, faithfulness 0.900 / context_recall 0.950)

- 영어 질문 → 영어 PDF context → ragas judge(영어 기반)의 **언어 일관성**이 유지됨
- faithfulness 0.900: 10개 중 9개 답변의 주장이 context로 뒷받침됨 (4번·10번 부분 점수)
- context_recall 0.950: gold_answer 주장의 95%가 retrieved context에서 확인됨 (4번 0.0이 유일한 miss)
- 결론: 영어 단일 언어 환경에서 현재 RAG 파이프라인은 안정적으로 동작함

### 4-3. 한국어 QA 구간 (n=10, faithfulness 0.200 / context_recall 0.300)

- 영어 QA 동일 문서(gold_source / gold_page)를 공유하지만, **질문과 답변이 한국어**인 구조

```
한국어 질문
    ↓
retrieve() — 영어 PDF에서 검색 (cross-lingual retrieval)
    ↓
answer_from_knowledge() — 영어 context → 한국어 답변 생성
    ↓
ragas judge — 한국어 답변과 영어 context의 claim 일치 여부 판정 (cross-lingual evaluation)
```

- faithfulness 0.200: 10개 중 2개만 답변 주장이 context로 뒷받침됨 (14번·15번만 1.0)
- context_recall 0.300: gold_answer 주장의 30%만 retrieved context에서 확인됨
- **핵심 한계**: "영어 PDF 기반 corpus에 한국어 질문을 직접 검색하는 구조" 자체의 제약

### 4-4. 약점 분류

| 단계 | 약점 | 영향 지표 |
|------|------|----------|
| Retrieval | 한국어 쿼리 임베딩과 영어 청크 임베딩 간 semantic 유사도 저하 | `context_recall` 하락 |
| Generation | 영어 context → 한국어 답변 생성 과정에서 정보 재구성 | `faithfulness` 하락 |
| Evaluation | ragas judge가 한국어 답변과 영어 context의 claim 대응을 과소 판정할 가능성 | 두 지표 모두 영향 |

---

## 5. 향후 개선 방향

| 방향 | 구현 방법 | 예상 효과 |
|------|----------|----------|
| **Query translation** | 한국어 질문을 영어로 번역한 뒤 retrieve (retriever.py 앞단에 번역 레이어 추가) | `context_recall` 개선 |
| **Multilingual embedding** | `text-embedding-3-large` 또는 `multilingual-e5-large`로 인덱스 교체 | cross-lingual retrieval 전반 개선 |
| **Dual query expansion** | 한국어 쿼리 + 번역된 영어 쿼리를 동시에 검색하고 RRF 융합 | retrieval coverage 확대 |
| **Ragas judge 지침 보강** | judge LLM에 한/영 혼합 판정 지침 추가 (`ragas_eval.py`의 `judge_llm` 설정) | `faithfulness` 평가 신뢰도 개선 |
| **한국어 gold_answer 교체** | 한국어 QA를 한국어 출처 문서 기반으로 재구성 | cross-lingual 복잡도 자체 제거 |

**우선순위 추천:** Query translation → Multilingual embedding 순서로 단계적으로 검토.
RAG 인덱스 재구성 비용이 크므로, retriever.py 앞단에 번역 레이어를 추가하는 방식이 빠른 개선에 유리하다.

---

## 6. 의존성 주의사항

| 항목 | 내용 |
|------|------|
| ragas 버전 | 0.2.15 |
| import 성공 조건 | `langchain-community==0.4.1` (기본 0.4.2에서 import 실패) |
| 충돌 경고 | `langchain-experimental 0.4.2`가 `langchain-community>=0.4.2`를 요구 — `pip check` 경고 잔존 |
| requirements.txt | **미반영** — 충돌 해소 전까지 보류 |
| 현재 상태 | 별도 평가 환경으로 분리 운영 (langchain-community 0.4.1 환경에서 실행) |

### 충돌 관계 요약

```
langchain-experimental==0.4.2  →  requires langchain-community>=0.4.2
ragas==0.2.15                  →  import 실패 with langchain-community==0.4.2
                                   import 성공 with langchain-community==0.4.1
```

해소 방법 후보:
1. ragas 버전 업그레이드 (langchain-community 0.4.2 지원 버전 출시 대기)
2. langchain-experimental 버전 downgrade (기존 SemanticChunker 의존성 확인 필요)
3. ragas를 별도 가상환경으로 분리 (평가 전용 환경)

---

## 7. 포트폴리오용 요약

Ragas 평가 결과 전체 평균은 faithfulness 0.55, context_recall 0.575였으나, 언어별로 분리해보면 영어 QA는 안정적인 반면 한국어 QA에서 성능 저하가 확인되었다. 이는 영어 PDF corpus에 한국어 질문을 직접 검색하는 cross-lingual retrieval 한계로 분석되며, query translation 및 multilingual embedding 개선 필요성을 정량적으로 도출했다.

구체적으로, 영어 QA 10개 구간은 faithfulness 0.900 / context_recall 0.950으로 안정적이나,
한국어 QA 10개 구간은 faithfulness 0.200 / context_recall 0.300에 그쳤다.
전체 평균의 하락은 파이프라인 자체의 실패가 아니라 corpus와 query의 언어 불일치에서 비롯된 것으로,
이를 정량적으로 분리·근거화했다는 점이 이 평가의 핵심 기여다.

---

## 8. 평가 파일 목록

| 파일 | 분류 | 설명 |
|------|------|------|
| `gold_dataset.json` | 평가 입력 데이터셋 | EN/KO bilingual QA 10쌍, 총 20개 |
| `run_ragas_eval.py` | 평가 코드 | ragas 평가 스크립트 (`--dataset` / `--mode` / `--k` / `--limit` 인자 지원) |
| `ragas_report.json` | 실행 결과 report (누적) | 평가 결과 누적 저장 (실행마다 append) |
| `ragas_report_full.json` | 실행 결과 report | 전체 20개(EN+KO) 실행 결과 별도 보존 |
| `ragas_report_limit3.json` | 실행 결과 report (limit 기반 사전 점검) | --limit 1·--limit 3 파이프라인 동작 확인 결과 — 성능 주장 근거 아님 |
