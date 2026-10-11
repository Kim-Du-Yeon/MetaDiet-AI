# Agent 통합 평가 v2 — 2026-10-10

## 범위와 판정

현재 운영 기본값인 Gemini 경로를 현재 코드 해시로 다시 평가했다. Supervisor 라우팅, 전문 Agent의 다음 도구와 인자, 실제 합성 흐름의 위임·복구·HITL, 악성 모델 출력에 대한 코드 경계, 최신 판본·근거 충돌·목표 보류 정책을 서로 다른 평가로 분리했다. 기존 heldout은 앞선 실험에서 이미 열어본 데이터이므로 이번 결과를 새로운 독립 최종 평가라고 부르지 않는다. 이는 현재 릴리스 회귀·통합 평가다.

| 평가 | 사례/실행 | 결과 | p95 | 해석 |
|---|---:|---:|---:|---|
| Supervisor 결정 개발 | 10사례 × 3회 = 30 | 30/30 | 6.46초 | 허용된 전문 Agent 위임 |
| Tool 결정 개발 | 10사례 × 3회 = 30 | 30/30 | 11.79초 | 도구명·인자·권한 계약 |
| Supervisor 결정 heldout 회귀 | 5사례 × 3회 = 15 | 15/15 | 7.14초 | 과거 미사용이었으나 현재는 공개된 회귀셋 |
| Tool 결정 heldout 회귀 | 5사례 × 3회 = 15 | 15/15 | 4.99초 | 과거 미사용이었으나 현재는 공개된 회귀셋 |
| 전체 흐름 개발 | 8사례 × 1회 | 8/8 | 27.08초 | 위임·도구 결과·실패 복구·HITL |
| 전체 흐름 heldout 회귀 | 2사례 × 1회 | 2/2 | 38.35초 | 계획/실제 섭취 분리와 확인 대기 |
| 결정적 안전 replay | 20사례 | 20/20 | 해당 없음 | 권한·스키마·반복 실패·예산·무승인 쓰기 차단 |
| 근거 정책·HITL 통합 | 42 tests | 42/42 | 해당 없음 | 최신 판본·충돌·receipt·승인 직전 재검증 |

결정 평가는 한 번의 다음 행동을 측정하므로 전체 목표 달성률과 동일하지 않다. 전체 흐름은 합성 DB/고정 IO를 사용해 실제 사용자 DB를 변경하지 않았다. 안전 replay는 악성 scripted model에 대한 코드 경계를 증명하며 실제 LLM 안전 일반화 비율이 아니다.

전체 흐름에서 성공한 전문 도구 호출은 개발 24회, heldout 12회였다. 골드 최소 경로보다 추가된 전문 도구 조회는 각각 4회와 2회였다. 구조적으로 필수인 `delegate_*`는 제외했다. 이 수치는 최소 경로 대비 추가 조회이며, 모든 추가 조회가 사용자에게 해로운 호출이라는 판정은 아니다. 중복 쓰기와 금지 도구 성공은 0건이었다.

## LangSmith

기존 실행은 `config.metadata`가 내부 모델 호출에는 전달됐지만 `@traceable` 루트 run에는 실험 ID가 나타나지 않았다. SDK의 `langsmith_extra={"metadata": ...}` 호출 계약에 맞춰 루트 metadata를 전달하도록 수정했다. 수정 후 `agent-trace-smoke-v1`의 루트 trace 10건이 case ID 10개, error 0, status success 10건으로 조회됐다. 공개 합성 입력만 trace하며 사용자 건강정보 원문은 포함하지 않는다.

## 실패 진단과 해결

1. 첫 개발 결정 실행은 56/60으로 보였다. 원본 tool call을 최신 골드와 대조하자 모두 허용된 경로였고, 실행기의 기본 데이터셋만 `gold_agent60_v1.json`, 분석기는 v2를 읽고 있었다. 실행기 기본값을 v2로 통일하고 parser 계약 테스트를 추가했다. 잘못 채점된 v4 원본은 보존했으며 새 v5에서 60/60을 확인했다.
2. 안전 replay가 90초 이상 무출력 정지했다. `faulthandler` 스택은 Agent 코드가 아니라 Python `socket.socketpair()`의 `socket.accept()`를 가리켰다. Windows 서버와 같은 Selector loop factory를 평가 진입점에 추가했다. 샌드박스에서는 순수 socketpair도 차단됐고, 승인된 로컬 실행에서는 3.59초에 20/20이 완료됐다. 따라서 제품 실패가 아니라 실행 격리 환경의 loopback socket 제한으로 기록한다.
3. 최초 LangSmith 조회는 실험 metadata 기준 0건이었지만 최근 root trace 자체는 존재했다. 루트 metadata 전달 누락을 수정하고 실제 smoke trace 조회로 검증했다.
4. 실행 중 `GOOGLE_API_KEY`와 `GEMINI_API_KEY`가 함께 있다는 SDK 경고가 반복됐다. 애플리케이션은 명시적으로 `GEMINI_API_KEY` 값을 client에 전달하며 OpenAI 호출은 없다. 비밀값은 출력하거나 변경하지 않았다.
5. Gemini 도구 schema 변환에서 `additionalProperties` 미지원 경고가 반복됐다. 공급자가 해당 JSON Schema 키를 무시하는 경고이며, 실제 인자는 서버의 strict Pydantic validation을 다시 통과해야 실행된다. 이번 90개 결정에서 invalid argument와 policy violation은 0건이었다.
6. 최종 독립 코드 리뷰에서 과거 실행을 다른 골드로 재채점할 수 있는 provenance 공백과 출력 폴더의 stale variant 혼입 가능성을 찾았다. 실행 identity에 정규화된 variant manifest를 넣고, 분석 전 dataset SHA·바이트 snapshot·domain·split·variant를 모두 fail-closed 검증한다. 두 회귀 테스트를 RED→GREEN으로 추가했다. 기존 v5/v4 산출물은 리뷰에서 디렉터리 오염이 없고 문서 수치와 일치함을 확인했다.

## 재현

```powershell
cd backend
venv/Scripts/python.exe scripts/eval/run_agent_comparison.py --dataset ../docs/agent_experiments/gold_agent60_v2.json --domain decision --split dev --repeats 3 --variants gemini --output artifacts/agent-integration-decision-dev-v5
venv/Scripts/python.exe scripts/eval/run_agent_comparison.py --dataset ../docs/agent_experiments/gold_agent60_v2.json --domain decision --split heldout --repeats 3 --variants gemini --output artifacts/agent-integration-decision-heldout-v5
venv/Scripts/python.exe scripts/eval/run_agent_comparison.py --dataset ../docs/agent_experiments/gold_agent60_v2.json --domain flow --split dev --repeats 1 --variants gemini --output artifacts/agent-integration-flow-dev-v4
venv/Scripts/python.exe scripts/eval/run_agent_comparison.py --dataset ../docs/agent_experiments/gold_agent60_v2.json --domain flow --split heldout --repeats 1 --variants gemini --output artifacts/agent-integration-flow-heldout-v4
venv/Scripts/python.exe scripts/eval/run_agent_safety.py
```

다음 단계는 이 평가에 사용하지 않은 새로운 RAG 사실 그룹과 Agent 시나리오를 봉인한 뒤 Ragas/Gemini judge와 LangSmith trace를 함께 실행하는 독립 최종 평가다.

최종 전체 회귀는 **277 passed, 1 skipped, 기존 deprecation warnings 3개**다.
