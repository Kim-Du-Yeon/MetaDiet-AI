**최종 완료: [v1/v2/v3 동일100건·정답99/98/100·행동99/97/97·v1 유지·추가 약$0.81](RESULTS.md).**

# 후속 상담 v2 회귀 분석과 v3 진단 비교

## 문제와 가설

기존 v1/v2 각 100건 및 Pro 100쌍의 원본은 [이전 결과](../execution-v2/COMPLETE100.md)에 보존한다. v1 통과·v2 실패였던 6건을 분석했다. 단순히 프롬프트가 짧을수록 좋아진다는 가설을 폐기하고, **바로 답할 수 있는 상담과 필수 정보가 없는 요청을 구분**하는 후보를 별도 개발셋에서 검증한다.

| 회귀 사례 | 원문에서 확인한 문제 | 개선 또는 검증 방법 |
|---|---|---|
| missing_choices-09, -05 | 없는 이전 선택지를 물어보지 않고 새 메뉴를 제시 | 누락된 두 메뉴·제품 이름을 직접 질문; 대체안 생성 금지 |
| missing_choices-10 | 두 메뉴 이름 대신 일반 취향을 질문 | 필수 필드에 집중하고 선택적 선호 질문 억제 |
| missing_portion-09 | 실제 제공되지 않은 기입·제외 버튼 안내 | 기록 요청과 읽기 전용 상담을 구분; 카드가 있을 때만 UI 안내 |
| known_intake-08, unlogged_meal-03 | 과거 judge는 끼니별 기록 없이 합계만 받아 ‘점심’ 표현을 환각으로 판정 | 실제 합성 DB fixture에는 점심 행이 있음. 평가자 문맥 누락 가능성으로 분리하고 세 조건 모두 동일 fixture truth로 재채점 |

[원래 판정 6건](regressions.json) · [합성 입력 경로 캡처](context-route-probe.json). 기존 두 버전의 전체 tool transcript는 저장되지 않았으므로, fixture 복원은 당시 도구를 읽었다는 증명이 아니다. 과거 점수를 수작업으로 올리거나 덮어쓰지 않는다.

## 고정 조건과 재사용

- [프로토콜](protocol.json), [새 개발 24건](development.json), [동일 비교 100건](frozen.json), [후보](candidate.json)를 호출 전에 동결했다.
- v1/v2의 기존 답변 200개는 입력·실행 코드·모델·프롬프트 해시와 원문 바이트를 검증해 재사용한다. 새 v3 답변은 100개만 생성한다.
- 별도 개발셋은 일반 상담·끼니 범위·명시된 선택지·누락 선택지·정확한 분량·제품표 6군 × 4건이다. 개발에서 v2/v3 각각 24건을 실행한다. 24건은 성능 우위의 본 근거가 아니다.
- 모델은 동일 Flash, 온도 0, low thinking, 출력 1,024토큰, 동시성 1, 최대 모델 3회·도구 8회·65초, 검색 OFF다. 운영 데이터는 모두 mock이며 저장하지 않는다.
- Pro 평가에 완전한 공통 fixture를 추가했으므로 과거 채점은 새 비교에 그대로 재사용할 수 없다. 원래 의미 기준을 유지하고, 개발 24쌍 및 본 100건의 세 답변을 각각 독립 평가한다. 순서는 회전시켜 블라인드한다.
- 모델 호출 실패·시간 초과·채점 형식 실패도 분모에 남긴다. 출력은 이름 있는 boolean과 원문 이유만 허용하며 점수 추정·형변환·누락값 보충을 하지 않는다.
- 일반 모델의 토큰 사용량으로 생성 비용을 계산하고 Pro Batch는 실제 usage의 Batch 요금으로 정산한다. 청구서 확정 금액과 구별한다. 예상 새 사용량 비용 $1–2이며 이전 사용액은 같은 원장에 보존한다.

## 후보의 범위와 사전 판단 기준

`team.compact_followup`과 `team.base` 두 프롬프트만 바꾼다. 후보의 commit 필드는 **로컬 내용 해시**이며 LangSmith 원격 커밋 ID가 아니다. `evaluation_only`이므로 운영 서명·승격 검증을 통과할 수 없다.

개발 24건에서 판정 완결·생성 성공·usage 완결, v2 대비 행동 통과와 안전성 비열화를 먼저 확인한다. 본 진단의 v3 선호 조건은 공동 정답·충실성 ≥98/100, 전체 행동 통과 ≥98 및 v1 이상·v2 대비 2건 이상 회복, 필수 질문 ≥49/50 및 v1 이상, 잘못된 확정 0건, 최신값·무저장 100건, 불필요 질문 v1 이하, 생성 p95와 비용 v1의 1.25배 이하다. 과거의 ‘불필요 질문 5건 감소’ 게이트는 기준 v1이 0건이라 불가능했으며, 그 원래 승인 결과는 바꾸지 않는다. 새 기준은 새 호출 전에 별도 프로토콜로 고정했다.

같은 100건은 10개 유형 × 10건이며 질문 문구는 55종, 수치·상태 변형을 포함한다. 이미 오류를 본 **반복 진단셋**이다. 독립 일반화 성능이나 실제 사용자 만족도로 표현하지 않는다. v1/v2 지연은 저장된 이전 실행이고 v3는 새 실행이며 일부 생성 중 로컬 회귀 검사를 병행했다. 소프트웨어·모델·입력 설정은 같지만 CPU 부하와 원격 서버 상태는 완전히 통제되지 않았으므로 지연은 관측값이며 엄격한 속도 개선 인과 증거가 아니다. 이 비교가 좋아도 신선한 holdout과 두 프롬프트 변경에 대한 승인 어댑터 검증 없이 운영에 승격하지 않는다.

## 실행·복구

```powershell
# 프로젝트 venv 사용, worktree 루트에서 실행
python backend/scripts/eval/run_clarification_v3.py offline --folder docs/prompt_control/clarification-balanced/v3-candidate-20261022
python backend/scripts/eval/run_clarification_v3.py generate --folder docs/prompt_control/clarification-balanced/v3-candidate-20261022 --development --allow-paid
python backend/scripts/eval/run_clarification_v3.py submit --folder docs/prompt_control/clarification-balanced/v3-candidate-20261022 --development --allow-paid
python backend/scripts/eval/run_clarification_v3.py collect --folder docs/prompt_control/clarification-balanced/v3-candidate-20261022 --development --allow-paid
```

개발 통과 후 `--development`를 빼고 본 생성·제출·수집을 실행한다. 세 답변 JSON 형식은 첫 2건으로 확인한 뒤 나머지 98건을 제출한다. 두 건도 본 100건에 포함한다. pending Batch는 재제출하지 않으며 실제 사용량을 멱등 정산한다. 용량·과금 불명 상태는 원본과 예약액을 보존하고 자동 재개하지 않는다. 오프라인 모의 결과는 유료 답변 파일과 분리했다.

실행을 완료했으며 결과와 미채택 판단은 위 RESULTS.md에 기록했다. 아래 프로토콜은 호출 전 고정한 설계다.

## 공식 자료

- [Gemini 요금표 및 Batch 요금](https://ai.google.dev/gemini-api/docs/pricing)
- [Batch 생성·조회·결과](https://ai.google.dev/gemini-api/docs/batch-api)
- [구조화 출력](https://ai.google.dev/gemini-api/docs/structured-output)

모델·실행 설정은 protocol.json에 고정한다. SDK가 도구 스키마의 additionalProperties를 무시한다는 경고는 원래 실행 경로에서도 발생하며, 최종 채점 JSON의 추가 필드는 로컬 엄격 파서가 거부한다. 경고를 성공 지표로 숨기지 않는다.

## 개발셋 결과

| 지표 | v2 | v3 |
|---|---:|---:|
| 행동 기준 통과 | 22/24 | 24/24 |
| 정답·충실성 공동 통과 | 22/24 | 24/24 |
| 필수 질문 | 11/12 | 12/12 |
| 근거 없는 확정·가짜 UI | 2 | 0 |
| 최신값·무저장 | 24/24 | 24/24 |
| 생성 평균 | 7.940초 | 6.791초 |
| 생성 p95 | 12.693초 | 13.400초 |
| 생성 usage 비용 | $0.048315 | $0.046078 |

[개발 요약](development/summary.json) · [회복 2건 원문](development/recoveries.json) · [채점 원본](development/judges.json). 24쌍 모두 엄격 형식 검증에 통과했다. 가짜 메뉴 생성과 가짜 UI 안내 두 실패가 회복됐고, v3 p95는 증가했다. 소규모 개발 결과를 속도 개선 증거로 해석하지 않는다. 추가 튜닝 없이 이 후보를 본 비교에 고정했다.

## 실행기 정산 수정

개발 Batch 1건에서 모듈 import 별칭이 달라 선불 예약 ContextVar가 전달되지 않아 로컬 예약이 두 번 잡혔다. API 제출은 1건이고 24개 결과의 실제 usage는 $0.097255다. [정산 증거](duplicate-reservation-reconciliation.json)와 [수정 전후 실행기 해시](runner-accounting-fix.json)를 보존했다. 이번에 생긴 중복 예약만 0으로 정산했으며 과거 비용 행은 변경하지 않았다. 실제 사용량으로 정산된 원래 Batch 티켓은 그대로다.

정의된 함수의 globals에 ContextVar를 연결하는 회귀 테스트를 추가해 10개 관련 테스트 및 전체 1,787개 테스트가 통과했다(기존 선택 테스트 1개 skipped, 라이브 결과를 뜻하지 않음). 이 수정은 Batch 예약 경로만 바꾸며 후보·사례·모델·최종 답변 생성 코드와 채점 기준은 바꾸지 않는다. 수정 전 실행 프로세스의 답변 파일은 원본을 별도 보존하고, 행 동일성을 검증한 메타데이터 이행 기록을 남긴다.

정산 원인 확인에 [Python import module cache](https://docs.python.org/3/reference/import.html#the-module-cache)와 [ContextVar 객체·set/reset](https://docs.python.org/3/library/contextvars.html) 공식 문서를 참고했다. 모듈 이름이 다른 전역 변수 참조를 같은 것으로 가정하지 않고, 실제 호출 함수가 참조하는 ContextVar 객체를 연결했다.
