# LangSmith 입력·출력과 모델 비용 관측

## 정책

- HTTP 서버는 항상 `production` 정책이다. 기존 `LANGSMITH_HIDE_INPUTS/OUTPUTS=true`는 정책 클라이언트 밖의 경로에 대한 안전한 기본값으로 유지한다.
- 실제 사용자 자유문·식사·체중·도구 인수는 전송 전에 `[REDACTED]`로 치환한다. 메시지 구조와 실행 노드, 익명 thread ID, 프롬프트 커밋·해시, 모델·사용량을 남긴다. 이름만 정규식으로 지우는 방식이 아니다. 운영의 문장 단위 의미 분석은 불가능하며 합성 재현으로 보완한다.
- 로컬 개발/합성 데이터는 `TRACE_DATA_MODE=synthetic`, `TRACE_SYNTHETIC_ONLY=true` 두 조건과 `synthetic_trace_context("metadiet-synthetic-...")`의 명시적 사용이 필요하다. 환경변수만으로 기존 모든 평가 스크립트가 원문 공개로 바뀌지는 않는다. 실제 사용자 데이터 사용 금지. Render/production/staging에서는 원문 모드가 거부된다.
- 비밀 키·자격정보 필드는 합성 모드에서도 제거한다. 합성 모드가 임의의 개인 문장에 대한 완전한 개인정보 탐지기를 제공한다는 뜻은 아니다.
- 서명 프롬프트 레지스트리용 Client는 기존 완전 숨김을 유지한다. 프롬프트 승인·운영 모델 선택·HITL 저장 승인에는 변경이 없다.

## 모델별 숫자의 의미

LangChain의 실제 LLM child span을 사용한다. root에 같은 토큰 비용을 다시 적지 않는다. 모델명, 시작/종료시각, usage를 같은 run에 연결하고 thread_id를 자식으로 전파한다. 지연은 네트워크·직렬화·제공자 처리 등을 포함하며 순수 모델 연산 시간이나 화면 첫 표시 시간과 같지 않다.

SDK `output_tokens`에는 thinking이 이미 포함되므로 reasoning을 다시 더하지 않는다. 입력은 `(input-cache_read)*입력단가 + cache_read*캐시단가`로 계산한다. `cost_basis`는 `standard_text_list_price_estimate_2026-10-23`다. Google 청구서 확정 금액이 아니다. 명시적 캐시 보관료·검색 도구료·세금·별도 임베딩 비용은 포함하지 않는다. Batch/Flex 호출에 이 표준 가격을 적용하지 않는다.

관측한 사용량이 없거나 가격·유효기간·합계가 맞지 않으면 `unknown_or_unsupported`로 표시하며 0원으로 추정하지 않는다. 2026-12-31 이후 단가 재검토가 필요하다. 실패 요청이 제공자에서 과금되었지만 usage를 반환하지 않은 경우 비용을 복원할 수 없다. SDK 내부 자동 재시도의 숨은 사용량 또한 별도 청구 대조가 필요하다.

## 사용

```python
# 합성 데이터만 사용하는 개발 프로세스의 환경변수로 위 두 값을 설정한 후:
from app.core.trace_policy import synthetic_trace_context
with synthetic_trace_context('metadiet-synthetic-example'):
    # 기존 LangGraph / ConfiguredChatModel 호출
    ...
```

```powershell
# backend 작업 디렉터리. 실제 짧은 모델 호출 4회, 운영 DB 접근 없음.
$env:PYTHONPATH='.'
& D:/AX/diet_agent/backend/venv/Scripts/python.exe scripts/verify_trace_policy.py --live --output ../docs/observability/trace-smoke.json
```

스크립트는 지정한 backend/.env를 우선한다. 키를 문서·CLI 인자로 전달하지 않는다. HTTP 서버의 기존 환경변수 우선순위는 바꾸지 않았다. 이전 숨김 trace의 원문은 소급 복원되지 않는다.

LangSmith → Tracing Projects → 해당 프로젝트 → run → LLM child → Input/Output 및 Metadata를 확인한다. 모델별 지연/토큰/비용은 child의 숫자이고 root/thread는 집계다. 합성 프로젝트와 운영 프로젝트를 섞어 성능 통계를 내지 않는다.

## 검증 상태

오프라인 테스트와 실제 합성 업로드·배포 검증 결과는 이 문서의 후속 결과 절과 `trace-smoke.json`을 기준으로 확인한다. 소수 smoke는 기능 검증이며 성능 향상 근거가 아니다.

## 공식 근거

- [LangSmith 마스킹](https://docs.langchain.com/langsmith/mask-inputs-outputs)
- [LangSmith 비용/토큰 집계](https://docs.langchain.com/langsmith/cost-tracking)
- [Gemini 가격: 출력에 thinking 포함, 캐시 읽기 별도 단가](https://ai.google.dev/gemini-api/docs/pricing)

## 복구

`LANGSMITH_TRACING=false`면 추적만 중지하고 상담 기능은 유지한다. 원문 공개로 롤백하지 않는다. 변경 전 커밋으로 서버를 재배포하면 기존 전체 숨김 정책으로 복원된다. trace 데이터는 LangSmith 접근권한/보존기간 정책의 관리 대상이다. 이 변경은 과거 trace 삭제나 사용자 계정 삭제와 LangSmith 삭제의 자동 연동을 구현하지 않는다.
