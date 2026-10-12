# 관리자 제품 분석과 LangSmith 연결

## 관리자 이메일 등록

1. MetaDiet에 로그인할 때 사용한 이메일을 확인한다. Render 또는 GitHub 로그인 이메일과 다를 수 있다.
2. [Render API 환경변수](https://dashboard.render.com/web/srv-db5i9p0473hc73b973tg/env)를 연다.
3. `ADMIN_EMAILS`를 추가하거나 수정한다. 값에는 MetaDiet 로그인 이메일만 입력한다. 여러 관리자는 쉼표로 구분한다.
4. Save, rebuild, and deploy를 실행하고 Live 상태를 확인한다.
5. MetaDiet에서 같은 계정으로 로그인한 뒤 설정의 관리자 제품 분석을 확인한다.

서버가 검증한 JWT 이메일로 권한을 판정한다. 일반 계정은 403, 로그인하지 않은 요청은 401이다. 이메일을 프론트 환경변수에 넣지 않는다. 비밀번호·API 키를 채팅에 보낼 필요가 없다.

## trace 연결

실제 그래프 실행마다 UUID를 생성하여 LangChain `RunnableConfig.run_id`에 전달한다. 같은 ID를 완료/실패 체크포인트와 SSE `trace_id`, 브라우저 `chat_completed` 제품 이벤트에 전달한다. 연결 재시도는 저장된 결과를 재사용하고 Pod 복구로 실제 실행을 다시 시작하면 별도 실행 ID를 사용한다.

LangSmith의 해당 프로젝트에서 metadata `trace_id` 또는 `stream_run_id`로 필터링해 같은 실행의 위임·도구·오류·지연을 확인한다. 공개 공유 링크는 생성하지 않는다. tracing 설정이나 키가 없으면 ID만 존재하며 LangSmith 업로드 완료를 의미하지 않는다. 서버 응답 전 네트워크 장애는 trace ID를 알 수 없으므로 null을 유지한다.

공식 구현 근거: [LangChain trace run ID 설정](https://docs.langchain.com/langsmith/trace-with-langchain).

공개 검증: `backend/venv/Scripts/python.exe backend/scripts/check_analytics_trace.py`. 임시 합성 계정을 만들어 공개 SSE → 제품 이벤트 DB → LangSmith root span의 동일 ID를 검사하고 계정을 정리한다. 출력에는 자격 증명이나 대화 내용이 없다.

## 남은 검증

운영 `ADMIN_EMAILS`에 실제 관리자를 등록한 뒤 관리자 화면을 해당 계정으로 검증해야 한다. 일반 계정 차단 테스트만으로 이 검증을 대체할 수 없다.
