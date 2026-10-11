# Agent 의사결정·안전 비교

## 고정 범위

`gold_agent60_v2.json`은 결정 30개, 흐름 10개, 안전 계약 20개다. 개발 44개/미사용 Agent 최종 평가 16개를 시나리오 그룹으로 분리했다. 결정은 동일 사례 3회, 흐름은 1회 파일럿으로 비교한다. 반복 3개를 독립 문항 3개로 해석하지 않는다. 원문·임상 승인 평가셋이 아닌 합성 행동 계약이다.

Gemini와 Jev를 Supervisor/전문 Agent 도구 선택에서 각각 비교한다. Jev confidence 0.9, 기존 권한·스키마·HITL·공유 예산을 유지한다. Jev가 선택하고 Gemini가 인자를 생성하므로 Jev 한 번의 응답 시간은 전체 요청 지연과 다르다. 낮은 confidence로 Gemini에 넘긴 성공과 Jev 자체 선택 정확도를 따로 기록한다.

## 실행 (backend 기준)

```powershell
venv/Scripts/python.exe scripts/eval/run_agent_comparison.py --dataset ../docs/agent_experiments/gold_agent60_v2.json --domain decision --split dev --repeats 3 --output artifacts/agent-decision-dev-v2
venv/Scripts/python.exe scripts/eval/run_agent_comparison.py --dataset ../docs/agent_experiments/gold_agent60_v2.json --domain flow --split dev --repeats 1 --output artifacts/agent-flow-dev-v2
venv/Scripts/python.exe scripts/eval/run_agent_safety.py
venv/Scripts/python.exe scripts/eval/analyze_agent_comparison.py --directory artifacts/agent-decision-dev-v2
```

heldout은 동일 명령에서 split과 출력 디렉터리만 변경한다. 설정·코드·골드 SHA가 다르면 기존 실험을 재개하지 않는다. 원본 바이트 snapshot, 요청별 결과, provider usage, fallback, 도구 결과, LangSmith trace를 보존한다. provider 오류는 즉시 중단하고 원인 확인 후 제한적으로 재시도한다.

AgentEvals 0.0.9/openevals 0.2.0은 `backend/artifacts/agentevals-runtime`에 격리 설치했다. 공식 trajectory subset/superset는 허용 경로/필요 도구를 검사하고, 인자·정책·최종 상태는 자체 계약으로 검사한다. 생성/평가에 OpenAI API는 사용하지 않는다.

## 해석 범위와 제외 결과

- v1 평가 wrapper가 tool binding을 변경해 후속 finish에 이전 schemas를 남겼다. 회귀 테스트 재현 후 새 binding wrapper로 수정했고 **v1을 채택 근거에서 제외**, v2 전체 재실행했다.
- 누락 양 질문 검사는 단어 포함 대신 명시적 요청 여부로 수정했다. Validator 구조화 응답은 raw usage까지 수집하도록 고쳤다.
- 개발 oracle 2개는 유효한 조회 선행 경로를 허용하도록 수정했다. heldout 문항은 수정하지 않았다.
- untouched flow v2에서 밥 100g 계획을 Validator가 CSV 영양값의 RAG 근거 누락으로 거절했다. 식품 DB 수치와 지침 근거를 구분하는 지시를 보강하고 v3로 재실행했다. v2 실패는 남기고 v3는 수정 후 회귀로 표시한다.
- 실제 Agent 루프는 실행하지만 DB/검색 IO는 합성 fixture다. DB 원자성·재시작·SSE 성능을 이 결과로 주장하지 않는다.
- 안전 20개는 악성 scripted model replay다. 실제 LLM의 모든 공격에 대한 안전성이나 임상 적합성을 보장하지 않는다.
- RAG 60개와 합쳐 120개 목록을 만들었지만, 기존 RAG heldout 20개는 앞선 임베딩 실험에 사용됐다. 전체 120개가 새로운 독립 최종 평가라는 주장은 하지 않는다.
- 토큰·호출 수를 기록한다. 공급사 실제 청구 금액을 검증하지 않은 상태에서 달러 비용 개선을 단정하지 않는다.

최종 결과는 `summary_v1.json`, 자세한 원본은 `backend/artifacts/agent-*-v2/analysis.json`에 기록한다.

## 실제 오류와 제한된 재확인

- flow v3 Jev-tools 식사 기록에서 Gemini provider `504 DEADLINE_EXCEEDED`가 발생했다. LangSmith child trace로 원인을 확인했고 원래 실패는 보존했다. 합성 IO에서 1회 재확인은 성공했다. 공급사 일시 장애가 다시 발생하지 않는다는 보장은 아니다. 공식 오류 안내: https://ai.google.dev/gemini-api/docs/api-errors
- 개발 v3 Jev Supervisor 1건은 `invalid_response`로 계약 검증을 통과하지 못했다. Gemini fallback은 성공했다. 원응답이 당시 저장되지 않아 최초 실패 필드는 미확정이다. 공식 Choice 계약을 대조하고 공개 합성 입력 1회 진단에서 원응답을 보존했으며 정상 선택/confidence0.97을 확인했다. 이는 최초 요청과 동일 재현이 아니다. https://docs.typesafe.ai/primitives/choice
- 중단된 개발 v3는 원본 fallback 행을 그대로 남긴 상태에서 코드 SHA를 확인하고 미실행 행만 별도 진단 스크립트로 이어갔다. 원실패를 성공 행으로 교체하지 않았다.
- PowerShell 인용 오류로 trace 확인 명령이 SyntaxError가 났을 때 파일 실행으로 바꿨다. UTF-8 artifact를 기본 cp949로 읽던 진단 오류는 명시적 UTF-8로 수정했다. C 임시 경로에 의존한 테스트 실행은 종료하고 D 경로 지정으로 전체 검증했다.
- SDK `additionalProperties` 경고에도 서버 Pydantic strict schema 검증은 유지한다. 두 Google 키 변수 경고와 달리 adapter는 설정의 Gemini 키를 명시적으로 전달한다. 비밀값은 보고서에 기록하지 않는다.
