# 미평가31쌍: 원문 분석·출력 계약 후보·오프라인 비용 검증

2026-10-22. 이번 작업은 **불필요한 후속 질문을 줄이는 프롬프트 후보의 비교 평가를 마무리하기 위한 채점기 출력 계약 개선**이다. LangSmith 버저닝/승격 기능 자체를 새로 만드는 작업도, Agentic RAG 비교를 다시 생성하는 작업도 아니다. 기존 승인v1은 계속 운영하고 새 후보는 미채택 상태다.

## 현재 어디까지 됐는가

- 기존v1/후보v2의 합성 답변은 각각100개, 총200개 생성 완료다.
- 이전 재평가 후69/100쌍만 유효 채점이며31쌍은 형식 실패다. 모델이 생성한 식단 답변31개가 모두 오답이라는 뜻이 아니다.
- 현재까지 운영 승인 조건은 충족되지 않았다. 기존 signed v1 유지, 실제 사용자 A/B OFF, 이번 운영 배포/브라우저 변경 검증 없음.
- 이번에는 저장 원문과 별도 개발용 형식 fixture만 사용했다. **새 유료 호출0, 예약/정산/장부 쓰기0**, 원래 점수·기준·상한 유지.

## 31개 원문에서 확인한 실패 경계

[사례별 분석](format-contract-offline/verified/analysis.json)의31건 모두 `FinishReason.STOP`, 정상 JSON, 최상위a/b 각각이 **지표명이 없는 배열**이다. 기존 모든 원문을 새 파서에서도 거부했다. 순서로 correct/faithful 등을 추측하거나 문장으로 boolean을 유추하지 않았다. 따라서 오프라인 추가 복구0, 유효69/실패31은 그대로다.

설치된 Google GenAI SDK의 native Batch 직렬화를 **API 호출 없이** 확인했다. 기존 중첩 JSON 스키마는 실제 요청에 남아 있었다. 따라서 “코드가 스키마를 전송하지 않았다”는 설명은 지지되지 않는다. 확인한 경계는 **스키마가 포함된 요청 → 스키마를 따르지 않은 모델 응답**이다. 공급자 내부에서 왜 무시됐는지는 원문과 로컬 직렬화만으로 확정할 수 없다. 출력 잘림·RPD/RPM·메모리 부족으로도 분류하지 않는다. 배열41/42건 등 과거 다른 실행의 실패 수를 이번31건과 혼합하지 않는다.

## 별도 출력 계약 후보

`clarification-grade-flat-v1`은 기존 의미 rubric의 byte/hash를 유지하고 출력 지시만 뒤에 추가한다. a/b 중첩 대신 `a_correct` 등12개boolean과 `a_reason`/`b_reason`을 포함한 **평면14필드 객체**로 단순화했다. 출력 상한2048·Pro 모델·temperature0·thinking low·기존 질문/답변·AB/BA는 유지한다. 중첩 축소와 필드명 명시가 형식 안정성을 높일 것이라는 **가설**이며 실제 모델 효과는 아직 미검증이다.

- 필수14필드·strict boolean/string·추가 키 금지·중복 JSON 키 금지.
- 배열/중첩a/b/누락/null/문자열 boolean/알 수 없는 필드를 모두 거부한다.
- 긍정 점수 예시를 프롬프트에 넣지 않으며 불리한 판정도 동일 기준으로 평가한다.
- [별도 개발20 fixture](format-contract-offline/verified/development20.json)는 직접 만든 혼합 boolean/설명 형식 데이터다. 답변이나 실제Pro 채점이 아니다. round-trip에서 명시된 값이 그대로 보존되는지 검사했으며 모델 정확도/형식 성공률100%의 증거로 쓰지 않는다.
-31개 저장 실패가 계속 거부되는 회귀 검사와 잘못된 필드/타입/중복/형태 거부 검사를 추가했다.
- native SDK가31개 후보 요청에서 필드 스키마·원래 입력·키·system instruction·temperature·출력 상한·low thinking을 유지하는지 검증했다. schema/thinking이 빠지거나 HIGH로 바뀌면 실패한다. 독립 리뷰가 찾은 thinking 직렬화 검증 누락도 RED→GREEN으로 보완했다.

코드: [계약](../../../../backend/scripts/eval/clarification_grade_contract.py), [오프라인 분석 도구](../../../../backend/scripts/eval/audit_clarification_contract.py).

새 계약은 별도 모듈이며 기존 재평가 명령/운영 경로/서명 승인 도구에 자동 적용하지 않았다. 미래 유료 재평가는 계약 버전·실제 system hash·원래 semantic rubric hash·answer binding을 함께 기록해야 한다. 형식 지시가 바뀌었다는 사실을 숨기고 이전 채점과 완전히 같은 system prompt라고 주장하지 않는다.

## 남은$0.108478로 가능한가

[오프라인 예산 계산](format-contract-offline/verified/budget-plan.json). 동일31개 원문의 관측 usage를 기준으로 계산했으며 새 모델 호출/유료 token-count 없이 수행했다.

| 계산 | 금액 | 의미 |
|---|---:|---|
| 같은31쌍의 과거 Batch 사용량 | $0.090193 | 과거 관측값, 새 실행 가격 확약 아님 |
| 새 형식 토큰 증가 가정 | **$0.106104** | 지시문/필드명 bytes÷4 proxy를 더한 시나리오 |
| 과거 최대 사례 비용 기반 높은 사용량 시나리오 | $0.136718 | 남은 한도 초과 가능성을 보여주는 가정 |
|31쌍 전체 최대 예약 계산 | $0.605915 | 보수적 byte 입력+출력 상한, 실제 예상 비용과 다름 |
| 첫2쌍 최대 예약 | $0.038894 | 잔여 한도 안에서 선행 확인 가능 |

**평균에 가까우면 가능할 수 있지만,31쌍 완료를 보장할 수는 없다.** 형식 증가 시나리오 여유는$0.002374뿐이며 토큰 분포·thinking·설명 길이는 달라질 수 있다. 사용량이 큰 경우 초과한다.31쌍 전체 예약을 미리 넣거나 기존 상한을 높이는 방식은 사용하지 않는다. 과거 비용 기반 시나리오에는 새 계약이 실제로 성공한다는 가정이 포함되어 있으므로 live 확인 전 완료 예상으로 단정하지 않는다.

후속 유료 실행을 승인받는 경우에만31쌍 중2쌍부터 형식·answer binding·usage를 확인하고, 통과하면 남은29쌍을 최대5개씩 순차 제출·정산할 수 있다. 첫2쌍은31개 안에 포함해 중복 호출하지 않는다. 다음 최대 예약이 잔액보다 크면 크기를 줄이거나 신규 호출 전에 중단해야 한다. 실패 사례 추가 재시도/새 답변 생성/새 평가모델로 교체/출력 상한 축소를 예산 맞추기 수단으로 쓰지 않는다. 실제 Pro 가용 할당량은 이번에 새로 조회하지 않았다.

기존 누적 **$9.674849**, 추가 잔여 **$0.108478**, 좁은 실행 상한$9.783327·캠페인$10.324354·원래 전체$17.139139·단계별 예산 모두 유지. judge 단계 여유는$0.312739이므로 이번에는 추가$0.108478 경계가 더 좁다. 비용은 청구서 확정액이 아니며 원래 장부의 보수적 예약도 보존했다.

공식 근거: [Gemini 구조화 출력](https://ai.google.dev/gemini-api/docs/generate-content/structured-output?hl=en)은 스키마와 명확한 지시·애플리케이션 검증을 설명한다. [Batch API](https://ai.google.dev/gemini-api/docs/batch-api)는 native 요청의 비동기 평가와 일반 대비50%요금을 설명한다. [Pro 가격표](https://ai.google.dev/gemini-api/docs/pricing?authuser=1)의200k 이하 Batch 입력$1/출력·thinking$6 per1M을 기존 동결 요율과 대조했다. OpenAI 호환 Batch의 별도 제한을 native SDK 장애 원인으로 가져오지 않았다.

## 재현·보존·다음 단계

```powershell
# 새 출력 폴더를 사용해야 하며 기존 증거를 덮어쓰지 않는다.
& D:/AX/diet_agent/backend/venv/Scripts/python.exe backend/scripts/eval/audit_clarification_contract.py --out tmp/new-format-audit
& D:/AX/diet_agent/backend/venv/Scripts/python.exe -m pytest backend/tests/unit/test_clarification_grade_contract.py -q --basetemp=D:/AX/diet_agent/tmp/new-format-tests
```

감사 도구는 real key 대신 placeholder client를 사용하고 SDK request/async_request 및 socket 연결을 차단한다. 장부는SQLite mode=ro로만 읽으며 provider submit/token count API를 제공하지 않는다. 기존69채점·200답변·31원문·동결 사례 해시와 비용 행 해시가 전후 일치한다. [최종 보존 증명](format-contract-offline/verified/preservation.json). `format-contract-offline/` 최상위는 리뷰 전 최초 오프라인 기록이며 `verified/`가 thinking 검증 보강 후 최종 기록이다.

남은 작업은 **유료 최소2쌍으로 공급자의 실제 형식 준수 확인 → 예산 안에서 남은29쌍 → 전체 품질 승인 재판정**이다. 이번에는 실행하지 않았다. 전체 품질을 통과한 뒤에만 Staging/서명·승격·운영 검증을 검토하며, 현재 운영 변경은 없다.


검증 결과: 전체 backend pytest **1,771 passed·기존 optional1 skipped**. 새 형식 계약10개 테스트는 결함 재현 후 통과했고, 기존 점수/서명 기준 변경 및 새 skip/삭제는 없다. 현재 수정은 오프라인 평가 도구이므로 프론트 빌드·운영 배포는 수행하지 않았다.
