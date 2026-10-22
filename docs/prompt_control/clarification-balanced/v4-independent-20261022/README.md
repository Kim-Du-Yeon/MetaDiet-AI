# v4 신규 합성 holdout 및 두 프롬프트 조합 승인

## 목적과 고정 조건

직전 [동일100 진단](../v4-calculation-mode-20261022/RESULTS.md)에서 v4가 분량만 필요한 사례의 과잉 질문3건을 줄였다. 이번에는 후보 본문을 변경하지 않고 새로운100질문으로 검증한다. 기존300답변·100트리플채점·개발48답변·기존 원장은 그대로 보존한다. 새 질문의 답변을 과거 답변으로 대신하지 않는다.

- 새 질문100개 문구는 기존 평가100·v3/v4 개발·초기 개발과 정확 문자열 중복0. 10유형×10건, 필수 질문50·즉시 답변50이다. 같은 개발자가 작성한 합성 대조군이므로 외부 독립 평가·100독립 사용자·임상 성과는 아니다. 같은 유형의 문구 변형은 통계적으로 완전히 독립이지 않다.
- 유료 출력 확인 전에 사례·루브릭·모델·실행 코드·v1/v4 전체8커밋·해시를 protocol에 고정한다. 내부 정답 라벨은 Agent에 주지 않는다.
- 오프라인 최초안은 모두 supervisor여서 compact 실행을 검증하지 못했다. 유료 호출0 시점에 일반 후속 질문10개와 대화 문맥을 보완했고 변경 전 protocol/사례/가짜모델 결과를 `prepaid-route-refinement/`에 보존했다. 라우터는 수정·강제하지 않았다.
- Flash `gemini-3.8-flash`, 온도0, low thinking, 출력1024토큰, 최대모델3/도구8/65초, 동시성1, AB/BA 실행 순서, 검색OFF·합성 최신 기록·읽기 전용 실제 DietTeam. Pro `gemini-3.1-pro-preview` Batch100쌍, 기존 엄격한 flat JSON 의미 기준을 유지한다. 실패/시간 초과/채점 오류도 분모에 남긴다.

## 사전 기준

각100건 생성·채점·usage 완결. v4 정답·충실성 각각98이상 및 v1보다1건 넘게 감소하지 않음, 전체 행동98이상 및 v1이상, 필수 질문49/50이상, 근거 없는 확정0, 최신값·무저장100/100, 전체 추가 질문2이하 및 v1이하, p95/생성 비용 v1의1.25배 이하. 이미 불필요 질문0인 기준선보다 반드시 더 줄이라는 불가능한 목표 대신, 별도 개발에서 개선한 문제를 신규 holdout에서 유지하는지 검사한다. 기존 노출100의 v4 게이트 통과도 별도로 요구한다. 결과를 본 뒤 기준을 바꾸지 않는다.

## 비용과 재개

예상 추가 usage $0.8–1.5. 과거 소액 상한 해제 승인 범위에서 기존 SQLite 원장을 유지하며 호출별 usage와 Batch 완료 사용량을 정산한다. 새 요금제/가입은 없다. 새200응답 및100쌍 판단이 필요하고 사례당 호출 수는 여러 번일 수 있다. 최근 정상 Pro Batch 결과를 용량 확인 자료로 보존하고 첫2건의 새 채점 형식을 확인한 뒤98건을 제출한다. 한도·크레딧·불명 사용량은 원문과 예약을 남겨 중복 제출하지 않는다.

```powershell
python backend/scripts/eval/run_clarification_holdout.py offline --folder docs/prompt_control/clarification-balanced/v4-independent-20261022
python backend/scripts/eval/run_clarification_holdout.py generate --folder docs/prompt_control/clarification-balanced/v4-independent-20261022 --allow-paid
python backend/scripts/eval/run_clarification_holdout.py submit --folder docs/prompt_control/clarification-balanced/v4-independent-20261022 --allow-paid
python backend/scripts/eval/run_clarification_holdout.py collect --folder docs/prompt_control/clarification-balanced/v4-independent-20261022 --allow-paid
```

## 승인 경로

`approve_prompt_release.py evaluate`는 이 suite일 때만 검토된 두 프롬프트 조합 어댑터로 전달한다. 다른 변경 경로의 범위 제한은 유지한다. 정확한 후보8커밋·본문·계약, 입력 해시·실제 시스템 프롬프트 적용, 양쪽 실행 경로, 답변-채점 binding, Pro 원문 엄격 재파싱·usage를 확인하고 사전 기준을 다시 계산한다. summary에 직접 쓴 `passed=true`는 승인 근거가 아니다. 두 프롬프트는 하나의 서명된8개 명세로 배포되며 개별 태그를 섞어 실행하지 않는다. 기존 요청/HITL 버전 고정·LKG·로컬 v1·캐시 분리·A/B OFF 구조를 유지한다.

통과 후 비공개 명세 등록→LangSmith Staging→실제 원격 커밋 readback 및 격리 합성 실행→Production→공개 서버 강제/주기 갱신→실제 브라우저 일반 상담·RAG 출처·멀티턴·최신 기록 확인 순서다. 운영 데이터를 추가·수정·삭제하지 않는다. Staging 태그만 움직인 것을 별도 Staging 서버 배포로 표현하지 않는다. 실제 검증 실행 형태를 결과에 적는다.

[LangSmith 승격·롤백](https://docs.langchain.com/langsmith/manage-prompts) · [불변 커밋 SDK](https://docs.langchain.com/langsmith/manage-prompts-programmatically) · [Gemini Batch](https://ai.google.dev/gemini-api/docs/batch-api) · [요금](https://ai.google.dev/gemini-api/docs/pricing).
