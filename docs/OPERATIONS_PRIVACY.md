# MetaDiet AI 운영 개인정보·관측 기준

## 공개 베타 안내

- React 화면은 로그인 전과 계정 설정에서 개인정보처리방침과 베타 이용 안내를 제공한다.
- 공개 안내에는 Supabase, Google Gemini, Pinecone, LangSmith, Render의 역할과 처리 데이터 범위, 계정 삭제 경로를 표시한다.
- 무료 베타는 의료 진단·치료 서비스가 아니며 AI가 추정한 수치와 변경안은 저장 전에 사용자가 확인해야 한다.
- 확정되지 않은 보존 기간이나 법률 준수를 약속하지 않는다. 운영 범위가 바뀌면 시행일, 보존 기간, 문의 수단을 함께 갱신한다.
- 공개 오류 제보에는 건강정보, 이메일, 키 등 민감정보를 남기지 않도록 안내한다.

## 데이터 경계

- 식사·체중·인바디·목표·대화 내용은 건강 관련 사용자 데이터로 취급한다.
- 운영 stdout/stderr에는 사용자 메시지, 답변 본문, OCR 원문·보정값, 음식명, 검색 질의, 검증 근거 본문을 기록하지 않는다.
- 운영 LangSmith trace는 `LANGSMITH_HIDE_INPUTS=true`, `LANGSMITH_HIDE_OUTPUTS=true`를 기본으로 한다.
- LangSmith `thread_id` metadata에는 내부 사용자 UUID를 보내지 않고 안정적인 가명 hash만 사용한다.
- 입력·출력이 필요한 평가 trace는 공개 합성 fixture 전용 실행기에서만 명시적으로 허용한다.

## 허용 운영 관측값

- 실행 ID, 가명 thread ID, Agent·도구 이름, 성공/실패 여부, 오류 유형
- 모델·도구 호출 수, 실행 시간, 토큰·비용, 재시도·fallback·HITL 상태
- RAG 점수와 grounded 여부. 질의와 근거 본문은 운영 로그에서 제외한다.

## 저장과 삭제

- 대화는 사용자와 `thread_id`로 분리하고 RLS를 적용한다.
- proposal은 ID/version과 상태로 관리하며 확인 전 domain write를 만들지 않는다.
- `DELETE /users/me`는 명시적인 `DELETE` 확인값을 요구한다. 앱 데이터는 트랜잭션으로 제거하고, 사용자 FK가 없는 LangGraph checkpoint는 내부 사용자 ID thread prefix로 제거한다.
- 대화 실행은 사용자 단위 shared advisory lock을, 계정 삭제는 같은 키의 exclusive lock을 사용한다. 삭제 뒤 lock을 얻은 대기 요청은 사용자 존재를 다시 확인해 checkpoint 재생성을 막는다.
- Supabase Auth 삭제는 Postgres commit 뒤 수행한다. Auth 장애 시 `auth_deletion_pending`으로 재시도하며 삭제된 앱 데이터는 재생성하지 않는다.
- 계정 삭제는 JWT 발급 시각이 아니라 password AMR timestamp 5분 이내 여부와 활성 `auth.sessions` 행을 확인한다. 자동 token refresh는 재인증으로 인정하지 않는다.
- 삭제 시작부터 Auth 삭제 완료까지 auth ID SHA-256 tombstone을 유지한다. onboarding은 같은 lifecycle advisory lock 안에서 tombstone을 확인하므로 삭제와 경합해 프로필을 다시 만들 수 없다. Auth 삭제 성공 뒤 tombstone cleanup만 실패하면 안전하게 차단 상태를 유지한다.
- 온보딩처럼 새 앱 상태를 만드는 endpoint는 Auth `/user`를 다시 확인해 삭제된 Auth 사용자의 아직 만료되지 않은 JWT를 거절한다.
- 이메일·비밀번호 이외 provider는 해당 provider의 재인증 흐름을 구현하기 전까지 UI에서 계정 삭제를 시작하지 않는다.
- service-role Admin client에는 사용자 로그인을 수행하지 않는다. 합성 E2E도 관리자 client와 로그인 client를 분리한다.
- 실제 경로 합성 검증은 `backend/scripts/check_account_deletion.py`, 집계 결과는 `backend/artifacts/account-deletion-v1.json`에 보존한다.
- 실제 보존 기간, 사용자 삭제 요청의 전파 범위, 백업 삭제 기한은 출시 국가의 법률 검토와 제품 정책 확정 후 수치로 고정한다.
- 정책이 확정되기 전에는 보존 기간이나 법적 준수를 완료했다고 표시하지 않는다.

## 운영 전 확인

1. Supabase backup·PITR·로그 보존 설정과 제품 정책 일치 여부
2. LangSmith 프로젝트 접근 권한과 기존 민감 trace 삭제 여부
3. Pinecone metadata에 사용자 식별자나 원문 건강정보가 없는지 확인
4. 계정 삭제 시 사용자 행·식사·인바디·전략·대화·proposal·checkpoint 삭제 전파 시험
5. 오류 수집 도구를 추가할 때 같은 redaction 정책 적용
6. Supabase Security Advisor ERROR 0건 유지. service-only/no-policy INFO는 공개 grant가 없는지 함께 확인
7. Auth leaked-password protection 사용 가능 여부를 요금제·로그인 정책 확정 시 결정
