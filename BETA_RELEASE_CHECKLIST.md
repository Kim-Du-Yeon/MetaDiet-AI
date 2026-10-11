# MetaDiet AI 제한 베타 종료 체크리스트

기준 브랜치: `codex/metadiet-agent-upgrade`  
공개 UI: <https://metadiet-web.onrender.com>  
공개 API health: <https://metadiet-api.onrender.com/health>

이 문서는 무료 공개 제한 베타의 출시 범위, 검증 근거와 남은 운영 확인을 한곳에서 검토하기 위한 진입점이다. 앱스토어, 결제와 무제한 상용 트래픽은 이번 완료 범위에 포함하지 않는다.

## 1. 출시 판정

| 영역 | 상태 | 확인 근거 |
|---|---|---|
| 공개 API·정적 UI | 완료 | Render API와 React Static Site 배포, `/health` HTTP 200 |
| 인증·멀티유저 격리 | 완료 | Supabase JWT, 소유권·삭제 보안 회귀 테스트 |
| LangGraph 멀티에이전트 | 완료 | Supervisor 위임, 전문 Agent tool calling, 실패 복구·예산 제한 평가 |
| HITL·상태 복원 | 완료 | 승인 전 write 0건, proposal 멱등 확정, 체크포인트·새로고침 복원 |
| RAG·평가 | 완료 | 파서·청킹·임베딩·검색 비교, Ragas와 독립 근거 평가 |
| 관측 | 완료 | LangSmith trace에서 위임·도구·재시도·비용·지연 연결 |
| Streaming UI | 완료 | 실제 SSE 진행 단계, 재연결, proposal·근거 카드, 오류 상태 |
| 제한 부하·복구 | 완료 | 공개 제한 부하 오류 0건, kind Pod 재시작·중복 저장 방지 |
| 개인정보·베타 안내 | 완료 | 로그인 전·계정 설정에서 공개, 계정 삭제 검증 |
| 자동 배포 | 완료 | API·Web `autoDeployTrigger: commit`, GitHub provider 재연결 및 배포 확인 |
| 장애 이메일 알림 | 완료 | Render Notifications에서 Email + Only failure notifications, 서비스별 override 없음 확인 |

출시 차단 코드 결함은 확인되지 않았다. 무료 베타 공개를 유지할 수 있으며, 필수 운영 확인을 모두 완료했다.

## 2. 성능과 안정성 기준선

| 항목 | 결과 | 해석 범위 |
|---|---:|---|
| 휴면 뒤 첫 `/health` | 53,022.0ms | Render 무료 API의 scale-to-zero 복구 포함 |
| warm `/health` | n=20, 중앙값 236.2ms, p95 949.9ms, 203.9~1,272.4ms | 경량 생존 확인 요청 |
| 실제 Agent SSE 첫 이벤트 | 4,317.4ms / 4,450.3ms | Gemini·RAG·도구·검증을 포함한 동시 2건 |
| 실제 Agent SSE 전체 wall time | 32.48초 | 동시 2건 완료까지의 벽시계 시간이며 요청별 중앙값이 아님 |
| 공개 제한 부하 | health 50건·인증 조회 30건·Agent 2건, 오류 0 | 작은 제한 베타 표본이며 최대 처리량이 아님 |
| kind rolling restart | health 400/400, p95 5.86ms | 로컬 Kubernetes 환경 |
| 백엔드 회귀 | 360 passed, 1 skipped | 외부 서비스는 테스트 fixture로 격리 |
| 프론트엔드 회귀 | 35 passed, production build 성공 | React UI 회귀와 번들 생성 |

무료 인스턴스가 깨어난 뒤의 `/health` 시간과 실제 상담 시간을 혼동하지 않는다. 첫 응답 지연을 안정적으로 없애야 하면 keep-alive 우회 대신 휴면하지 않는 Render 인스턴스로 전환한다.

## 3. 최종 운영 확인

Render Dashboard에서 다음 항목을 확인했다.

- Workspace → Integrations 또는 Notifications
- Destination: Email
- Default Service Notifications: 실패 알림 활성화
- `metadiet-api`, `metadiet-web`에 알림을 끄는 override가 없는지 확인

서비스별 Notification Overrides 영역은 표시되지 않았으며, 별도 예외가 없는 workspace 기본 설정으로 확인했다.

```text
Render 장애 이메일 알림 확인: 완료
확인 일시: 2026-10-11 (Asia/Seoul)
확인 방법: 인증된 Render Dashboard 캡처에서 Email + Only failure notifications 및 override 없음 확인
```

## 4. 재현 명령

비밀값은 git-ignored `backend/.env`와 `frontend/.env`에만 둔다.

```powershell
cd backend
venv\Scripts\python.exe -m pytest --basetemp=.pytest-release
```

```powershell
cd frontend
npm test -- --runInBand --watchAll=false
npm run build
```

공개 환경의 합성 사용자 검증은 다음 스크립트를 사용한다. 실제 자격증명과 API 키는 출력 또는 artifact에 남기지 않는다.

```powershell
backend\venv\Scripts\python.exe backend\scripts\check_render_beta.py `
  --base-url https://metadiet-api.onrender.com

backend\venv\Scripts\python.exe backend\scripts\check_render_load.py `
  --base-url https://metadiet-api.onrender.com `
  --health-requests 50 --read-requests 30 --agent-requests 2
```

상세 평가 조건과 실패 분석은 [EVALUATION.md](EVALUATION.md), 핵심 비교 결과는 [PORTFOLIO_RESULTS.md](PORTFOLIO_RESULTS.md), 배포 절차는 [deploy/RENDER_BETA.md](deploy/RENDER_BETA.md)를 사용한다.

## 5. 알려진 한계와 후속 선택 작업

- 무료 API는 15분 이상 유휴 시 첫 요청이 약 1분 늦을 수 있다.
- 독립 영어 RAG 사례 1건은 근거를 찾지 못해 안전하게 답변을 보류한다.
- 장기간 실제 사용자 건강 효과와 임상 정책 승인은 소프트웨어 평가와 별도다.
- `react-scripts` 전이 개발 의존성은 Vite 전환으로 후속 정리할 수 있다.
- 앱스토어, 결제, React Native 전환은 이번 제한 베타 범위에서 제외한다.

이 문서가 반영된 기준 커밋을 검증한 뒤 제한 베타 완료 태그를 생성한다.
