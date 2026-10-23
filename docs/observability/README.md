# LangSmith 입력·출력과 모델 비용 관측

## 정책

- HTTP 서버는 기본 `production` 정책이다. 아래 본인 원문 추적 opt-in을 충족한 상담만 예외다. 기존 `LANGSMITH_HIDE_INPUTS/OUTPUTS=true`는 정책 클라이언트 밖의 경로에 대한 안전한 기본값으로 유지한다.
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
## 이번 기능 검증 결과 (2026-10-23)

- 백엔드 전체: **1851 passed / 기존 skip 1 / 기존 deprecation warnings 3** (192.42초). 마스킹 정책 전용 검사: **13 passed**. 테스트 삭제·새 skip 없음.
- 실호출: Flash-Lite와 Flash × 합성 원문/운영 마스킹 정책 = **4/4 통과**. 실제 LangSmith `total_tokens`, `total_cost`와 기록한 usage 계산값을 대조해 일치 확인. 비용 합계 **$0.00097925 추정**. 캐시 적중은 이 짧은 smoke에서 0이므로 실제 캐시 할인 성능을 검증했다고 주장하지 않는다.
- Flash의 output 121/122 토큰에는 reasoning 119/120이 이미 포함됨을 실제 저장값으로 확인. 별도 가산하지 않음.
- 처음 두 호출은 상속 프로세스의 오래된 키로 HTTP 402. backend/.env와 프로세스 키의 불일치를 원문 없이 확인하고, 검증 스크립트만 지정 .env 우선으로 수정. 실패 호출의 usage가 없으므로 비용은 미확정이며 성공 4회 합계에서 숨겨서 0원 처리하지 않는다.
- 실제 브라우저에서 합성 질문/응답, 모델별 지연/토큰/비용 툴팁 표시 확인. 마스킹 정책은 Input/Output이 `redacted_fields` 또는 `[REDACTED]`로 표시됨을 확인.
- 1차 커밋 `323c6c0fea5376cb4b8da8d9250b3e204aabd567` 공개 배포 및 health 정상 확인. 메시지 형식 표시 보완 커밋 `8ccde0caef95eb18217631cece82556ab005ee93`의 후속 검증은 아래에 기록한다.

실제 합성 trace 링크는 [원본 계측 결과](trace-smoke.json)에 보존했다. 인증된 프로젝트 멤버만 열 수 있으며 공개 공유 링크를 만들지 않았다.

### 마스킹 화면 보완

LangChain의 고정 메시지 타입과 생성자 식별자만 허용해 마스킹 후에도 Input/Output이 빈 화면처럼 보이지 않도록 했다. 사용자 ID·본문·도구 인수는 계속 제거한다. 추가 Flash-Lite 호출 1건에서 입력과 출력 `[REDACTED]`, 33토큰, 0.99초를 실제 화면으로 확인했다. 추가 추정 비용 $0.00001075, 합성 성공 호출 총 5건 $0.00099. [추가 계측](trace-render-smoke.json).

![실제 LangSmith 운영 정책 합성 검증: 입력과 출력 마스킹](trace-masked.png)

위 화면은 실제 API를 호출한 **합성 검증**이며 실제 사용자 성과나 성능 비교 결과가 아니다.

### 공개 서비스 검증

- Render 배포 `dep-dbdcfgbncjis739najcg`, `/health` status=ok 및 build commit `8ccde0caef95eb18217631cece82556ab005ee93` 확인.
- 로그인된 실제 브라우저에서 저장하지 않는 점심 추천 1건을 요청해 답변 완료와 검토 단계 표시 확인. 식사 기록 저장 버튼은 누르지 않았다.
- 운영 프로젝트 `metadiet-beta`에서 해당 요청의 LLM child 2개 모두 `trace_data_mode=production`, Input/Output `[REDACTED]` 표시 확인. 실제 사용자 입력·섭취 기록 원문은 공개 증거에 포함하지 않았다.
- Flash 호출 각각 4,917/5,462토큰, 5.34432/4.699932초, $0.00498075/$0.0052155. LangSmith 저장 `total_cost`와 usage 계산값이 일치하며 UI 툴팁에서도 입력·출력·reasoning·비용 표시 확인. 합계 **10,379토큰 / $0.01019625 추정**. 두 모델 호출의 합산 지연을 요청 전체 지연으로 해석하지 않는다.
- [운영 실행 계측](production-trace-smoke.json), 아래 실제 화면 참조. 합성 smoke와 운영 기능 검증 성공 호출의 확인 가능한 모델 비용은 총 **$0.01118625**. usage 없는 초기 실패 비용은 미확정이다.
- 프론트엔드 코드 변경이 없어 별도 프론트 빌드·배포는 하지 않았다. 이번 검증은 관측 기능 검증이며 100건 성능 개선 비교가 아니다.

![운영 LangSmith 모델별 속도·토큰·비용 툴팁](trace-production-cost.png)


## 면접용 합성 Agent 원문 시연 (2026-10-23)

[실제 시연 trace 열기](https://smith.langchain.com/o/587a2f87-e802-40a0-8d1d-2343ab07d304/projects/p/c575e3dd-75de-4d40-a578-06aeb59fcaaf/r/cfb8be3b-4371-4985-8911-cca4166627c6?poll=true).
LangSmith → Tracing Projects → **metadiet-synthetic-interview** → trace-smoke.

1. root Input에서 고정 합성 질문(점심 쌀밥 200g)을 확인한다.
2. 첫 모델 Output에서 delegate_meal 위임을 확인한다.
3. 두 번째 모델 Input의 System을 펼쳐 실제 지시문을 보고, User의 original_request/task를 확인한다. Output은 search_foods(query=쌀밥)이다.
4. 다음 호출에서 nutrition_lookup, propose_meal 인수와 Tool 결과를 확인한다.
5. 마지막 호출에서 최종 답변을 보고 root Output의 awaiting_confirmation=true를 확인한다.
6. 각 호출의 토큰 숫자에 마우스를 올려 속도·토큰·추정 비용을 설명한다.

실제 운영 DietTeam 실행기를 사용하되 **일반 운영의 단순 식사 빠른 계산 경로를 시연에서만 끈다**. 전체 HTTP/LangGraph 서비스 흐름을 재현한 것이 아니라 팀 오케스트레이션/Tool Calling 시연이다. 로컬 식품 CSV는 실제로 조회한다. 제안 저장소는 메모리 객체이며 DB 접근은 오류로 차단한다. 확정·취소 API와 운영 기록은 호출하지 않는다. 자유 입력은 받지 않아 실제 개인정보가 섞이지 않는다. 운영 HTTP 마스킹은 변경하지 않았으며 이 로컬 실행기 때문에 서버를 재배포할 필요는 없다.

```powershell
# 저장소 루트, 호출 없이 시나리오 확인
& D:/AX/diet_agent/backend/venv/Scripts/python.exe backend/scripts/demo_langsmith_agent.py
# 합성 시연 재실행: Gemini 비용 발생, backend/.env의 키 사용
& D:/AX/diet_agent/backend/venv/Scripts/python.exe backend/scripts/demo_langsmith_agent.py --live --output tmp/interview-trace.json
```

검증: 관련 테스트 **34 passed**. 실호출은 Flash 5회·도구 4회, DB 조회 0회, 확인 대기 도달. 모델 비용 합계 **$0.02128275 추정**, Agent 실행 약45.95초(루트 trace47.88초). 단일 기능 시연으로 성능 지표가 아니다. 재실행 결과/지연/비용은 달라질 수 있고 모델8회·도구12회·90초 제한을 둔다. [결과](interview-demo.json).

처음 가시성 검사는 정상적으로 제거한 Gemini thought signature까지 본문 숨김으로 오판했다. [초기 검사 기록](interview-demo-initial-check.json)을 보존하고, 서명 필드만 제외하는 테스트를 추가했다. 저장된 5개 trace를 재사용해 본문·도구 인수 표시를 확인했으며 추가 모델 호출은 하지 않았다. API 키와 제공자 서명은 합성 모드에서도 숨긴다.

![실제 합성 질문·프롬프트·도구 호출 원문](interview-demo-visible.png)


## 공개 웹사이트 본인 상담 원문 추적

사용자의 명시적 승인으로 `TRACE_OWNER_RAW_ENABLED=true`를 설정하면 **ADMIN_EMAILS에 단 하나만 등록된 관리자 계정**의 검증된 JWT에 한해 `/chat`, `/chat/resume`, `/chat/rollback` POST 원문을 `metadiet-owner-debug`로 보낸다. 복수 관리자·설정 꺼짐·다른 사용자·인증 실패·인증 확인 timeout(3초)은 기존 마스킹으로 처리한다. 클라이언트가 제출한 user_id나 모드 헤더를 신뢰하지 않는다. ADMIN_EMAILS 변경 시 원문 허용 대상도 바뀐다.

본인 요청의 프롬프트·질문·식사/목표/건강 문맥·도구 인수·답변이 LangSmith에 전송된다. 키·자격정보·제공자 서명은 제거하고 metadata는 기존 허용 목록을 유지한다. LangSmith 워크스페이스 접근자도 원문을 볼 수 있으므로 면접에서는 합성 전용 프로젝트를 권장한다. 공개 공유 링크는 만들지 않는다.

확인: LangSmith → Tracing Projects → **metadiet-owner-debug** → 최신 LangGraph → ChatGoogleGenerativeAI → Input/Output. 과거 마스킹된 trace는 복원되지 않는다. 모델을 호출하지 않는 요청에는 LLM child가 없을 수 있다.

중단: Render에서 TRACE_OWNER_RAW_ENABLED=false로 저장·재배포. 새 요청부터 마스킹하며 진행 중인 요청은 시작 정책을 유지한다. 기존 원문 trace는 자동 삭제되지 않으므로 LangSmith에서 별도 삭제/보존기간 관리가 필요하다. 저장 승인·소유권·HITL 로직은 변경하지 않는다.

검증: 전체 pytest **1858 passed / 기존 skip 1 / 기존 warnings 3**. 인증·기본 마스킹·복수 관리자 차단·동시 요청 격리·자격정보 제거 포함. 배포 및 실제 화면 결과는 아래 후속 기록을 참조한다.

### 운영 적용 확인 (2026-10-23)

- Render 배포 `b0b090d20f25249ba4b624f999f2a70917630ab6` Live 확인 후 공개 웹사이트에서 저장 없는 점심 추천을 요청했다.
- 실제 owner trace에서 Input의 질문/시스템 지시문과 Output 답변 본문이 표시되는 것을 LangSmith 브라우저에서 확인했다. 제공자 서명의 `[REDACTED]`는 본문 숨김이 아니다.
- Flash 모델 2회, 총 10,365토큰, 모델 추정비용 $0.01041075. 실제 청구서 총액이나 100건 성능 비교를 의미하지 않는다.
- [원문 없는 계측 증거](owner-live-verification.json). 실제 개인정보가 포함된 화면 캡처/본문은 GitHub에 게시하지 않는다.
- 다른 사용자 차단은 인증 mock 및 동시 요청 격리 테스트로 검증했다. 타인의 실제 계정으로 테스트하지 않았다.
