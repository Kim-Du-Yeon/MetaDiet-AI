# Routing / RAG Evaluation Summary

이 문서는 보고서에 바로 옮길 수 있도록 routing evaluation과 RAG evaluation 결과를 정리한 것이다. 원본 결과 파일은 다음 두 개다.

- `backend/scripts/eval/routing_report.json`
- `backend/scripts/eval/eval_report.json`

## 1. 평가 목적

| 평가 | 목적 | 확인하고 싶은 것 |
|---|---|---|
| Routing evaluation | Supervisor Agent가 사용자 의도를 올바른 Agent로 분기하는지 확인 | intent classification과 실제 graph route가 기대값과 일치하는지 |
| RAG evaluation | 영양지식 RAG가 정답 문서와 페이지를 잘 찾고, 출처 기반 응답을 생성하는지 확인 | source/page hit, citation, faithfulness, grounded quality |

## 2. Routing Evaluation

### 평가 설정

`routing_report.json`은 사용자가 실제로 입력할 법한 문장을 intent별로 구성하고, Supervisor의 intent 판단과 LangGraph route 결과가 기대 Agent와 일치하는지 평가한다.

| 항목 | 값 |
|---|---:|
| 평가 케이스 수 | 18 |
| Intent accuracy | 1.00 |
| Route accuracy | 1.00 |
| Confusion | 없음 |

### Intent별 케이스 분포

| Expected intent | 케이스 수 | 목적 |
|---|---:|---|
| `diet_logger` | 5 | 먹은 음식 기록, 이전 대화 기반 기록 |
| `meal_plan` | 2 | 하루 식단 계획 생성 |
| `strategy` | 3 | 식단 조언, 칼로리/영양 전략 질문 |
| `confirm` | 3 | 식단 후보 확정/수정/취소 |
| `edit` | 2 | 이미 저장된 식단 수정/삭제 |
| `inbody` | 1 | 인바디 결과 분석 및 전략 갱신 |
| `reporter` | 2 | 주간/월간 식단 리포트 |

### 평가에 사용한 문장

| Expected intent | 평가 문장 |
|---|---|
| `diet_logger` | 닭가슴살 200g 먹었어 |
| `diet_logger` | 오늘 점심에 김치찌개랑 공기밥 먹었어 |
| `diet_logger` | 방금 아메리카노 한 잔 마셨어 |
| `diet_logger` | 그거 그대로 기록해줘 |
| `diet_logger` | 위에서 말한 저녁으로 기록 |
| `meal_plan` | 내일 하루 식단 좀 짜줘 |
| `meal_plan` | 다이어트용으로 하루치 식단 계획 세워줘 |
| `strategy` | 단백질은 하루에 얼마나 먹어야 해? |
| `strategy` | 지금 칼로리 남았는데 뭐 먹으면 좋을까? |
| `strategy` | 살 빼려면 탄수화물 줄이는 게 맞아? |
| `confirm` | 응 확정해줘 |
| `confirm` | ok 그대로 기록 |
| `confirm` | 점심을 치킨샐러드로 바꿔줘 |
| `edit` | 아까 기록한 저녁 메뉴 삭제해줘 |
| `edit` | 어제 저장한 점심 칼로리 좀 수정해줘 |
| `inbody` | 인바디 결과 분석해서 전략 업데이트 해줘 |
| `reporter` | 이번 주 식단 리포트 보여줘 |
| `reporter` | 최근 한 달 단백질 섭취 통계 알려줘 |

`confirm` 케이스는 확인 대기 중인 pending 식단이 있는 상태를 가정했다. `그거 그대로 기록해줘`, `위에서 말한 저녁으로 기록`은 직전 대화 context를 참고해 `diet_logger`로 분기되는지 확인하기 위한 케이스다.

### 해석

Routing evaluation에서는 18개 케이스 모두에서 Supervisor의 intent와 최종 route가 기대값과 일치했다. 이는 Multi-Agent 구조에서 각 Agent의 역할이 분리되어 있고, 사용자의 요청이 적절한 node로 전달되는지 확인하기 위한 기본 안정성 검증이다.

다만 이 평가는 synthetic dataset 기반이므로, 실제 사용자의 오타, 구어체, 사진 업로드 후 후속 발화 같은 edge case는 별도의 smoke test로 보완했다. 수동 smoke test에서는 식단 기록, 식단 계획, 리포트, 수정, confirm 취소, pending 없는 "아니야" fallback, 비이미지 업로드 거절 흐름을 확인했다.

## 3. RAG Evaluation

### 평가 설정

`eval_report.json`은 영양지식 PDF에서 생성한 QA 케이스에 대해 검색 모드별 성능을 비교한다. 각 모드는 `k=4`, 평가 질문 수 `n=10`으로 측정했다.

| 모드 | 설명 |
|---|---|
| `dense` | Pinecone dense vector search only |
| `hybrid` | Dense search + BM25 sparse search + RRF |
| `full` | Hybrid retrieval + FlashRank reranking + grounded/citation pipeline |

### 주요 지표 설명

| 지표 | 의미 |
|---|---|
| Source hit | 정답 PDF 파일을 검색 결과에 포함했는지 |
| Page hit | 정답 페이지를 검색 결과에 포함했는지 |
| Excerpt hit | 정답 근거 문단에 가까운 excerpt를 찾았는지 |
| Avg score | 검색 및 reranking 후 평균 관련도 점수 |
| Refusal rate | 근거 부족으로 답변을 거절한 비율 |
| Citation rate | 응답에 출처가 포함된 비율 |
| Faithfulness | 응답이 검색 근거에 충실한지 평가한 값 |

### 결과 표

| 모드 | k | n | Source hit | Page hit | Excerpt hit | Avg score | Refusal rate | Citation rate | Faithfulness |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dense | 4 | 10 | 1.00 | 0.80 | 0.70 | 0.817 | 0.00 | 1.00 | 1.00 |
| hybrid | 4 | 10 | 1.00 | 1.00 | 0.90 | 0.817 | 0.00 | 1.00 | 1.00 |
| full | 4 | 10 | 1.00 | 1.00 | 0.90 | 0.978 | 0.00 | 1.00 | 1.00 |

### 개선 효과

| 비교 | 개선 내용 |
|---|---|
| dense -> hybrid | Page hit가 0.80에서 1.00으로 상승, Excerpt hit가 0.70에서 0.90으로 상승 |
| hybrid -> full | Page/source/excerpt hit는 유지하면서 Avg score가 0.817에서 0.978로 상승 |
| dense -> full | Source hit 1.00 유지, Page hit +0.20, Excerpt hit +0.20, Avg score +0.161 |

### 해석

Dense search만 사용해도 정답 PDF 파일은 모두 찾았지만, 정확한 페이지와 근거 문단을 찾는 성능은 hybrid/full 구성에서 더 안정적이었다. 특히 full 모드는 hybrid retrieval 이후 FlashRank reranking을 적용하여 평균 score가 가장 높았다. Citation rate와 faithfulness가 1.00으로 유지된 점은 RAG 응답이 출처 기반으로 생성되고 있음을 보여준다.

단, 현재 평가는 synthetic QA 10개 기준이므로 전체 일반화 성능을 보장하지는 않는다. 보고서에서는 "제한된 평가셋에서 hybrid retrieval과 reranking 적용 후 근거 검색 품질이 개선되었다"라고 표현하는 것이 정확하다.

## 4. 보고서용 요약 문장

Routing evaluation에서는 18개 intent routing case에 대해 intent accuracy와 route accuracy가 모두 1.00으로 측정되었다. RAG evaluation에서는 dense 단독 검색 대비 hybrid/full 구성에서 page hit가 0.80에서 1.00으로, excerpt hit가 0.70에서 0.90으로 개선되었고, full 모드의 평균 score는 0.978로 가장 높았다. 이를 통해 Supervisor 기반 Multi-Agent routing의 안정성과, hybrid retrieval 및 reranking을 적용한 RAG 검색 품질 개선을 확인했다.
