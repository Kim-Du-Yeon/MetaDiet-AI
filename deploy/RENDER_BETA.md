# Render 무료 공개 베타 배포

`render.yaml`은 다음 두 서비스를 만든다.

- `metadiet-api`: Docker 기반 무료 FastAPI Web Service. 무료 플랜에서 별도 worker를 둘 수 없으므로 scheduler도 이 단일 프로세스에서 실행한다.
- `metadiet-web`: React production build를 제공하는 무료 Static Site.

Weekly Deep Agent가 사용하는 MCP 도구는 API 프로세스에서 읽기 전용 함수로 직접 호출한다. 별도 MCP 공개 포트나 세 번째 Render 서비스는 필요하지 않다.

## 1. Blueprint 생성 시 입력할 값

API 서비스의 비밀 환경변수:

| 키 | 입력값 |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio 키 |
| `SUPABASE_URL` | Supabase Project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service-role key |
| `SUPABASE_JWT_SECRET` | 프로젝트 JWT secret. JWKS 검증이 가능한 구성에서도 레거시 fallback용으로 유지 |
| `SUPABASE_DB_URL` | Supabase direct/session-pooler Postgres URL |
| `PINECONE_API_KEY` | 활성 `diet-agent-rag` 인덱스 접근 키 |
| `LANGSMITH_API_KEY` | beta trace 프로젝트에 사용할 키 |
| `CORS_ORIGINS` | 실제 정적 사이트 URL. 예: `https://metadiet-web.onrender.com` |

프론트 정적 사이트의 build 환경변수:

| 키 | 입력값 |
|---|---|
| `REACT_APP_API_URL` | 실제 API URL. 예: `https://metadiet-api.onrender.com` |
| `REACT_APP_SUPABASE_URL` | API와 같은 Supabase Project URL |
| `REACT_APP_SUPABASE_ANON_KEY` | 브라우저용 Supabase anon/publishable key |

비밀값은 `render.yaml`에 기록하지 않는다. `sync: false` 항목은 Blueprint 생성 화면에서 입력한다. 서비스 이름이 이미 사용 중이라 URL이 예시와 달라지면 실제 URL로 `CORS_ORIGINS`와 `REACT_APP_API_URL`을 수정하고 두 서비스를 다시 배포한다.

## 2. 배포 순서

1. 현재 변경을 GitHub 배포 브랜치에 push한다.
2. Render Dashboard에서 **New → Blueprint**를 선택하고 저장소의 `render.yaml`을 지정한다.
3. 위 `sync: false` 값을 입력하고 Blueprint를 적용한다.
4. API의 `/health`가 200인지 확인한다.
5. 정적 사이트에서 회원가입·온보딩·채팅 스트리밍·HITL 확정·새로고침 복원·회원 탈퇴를 실행한다.
6. LangSmith `metadiet-beta` 프로젝트에서 같은 요청의 Supervisor 위임, 도구 호출, 재시도와 완료 trace를 확인한다.

기존 서비스를 공개 Git URL clone으로 만든 경우 GitHub App을 설치한 것만으로 해당 서비스의 webhook이 연결되지 않을 수 있다. 서비스의 **Settings → Build & Deploy → Git Credentials**에서 연결된 GitHub credential을 선택하고 **Auto-Deploy = On Commit**인지 확인한다. 새 커밋 뒤 deploy가 생성되지 않으면 서비스별 **Manual Deploy → Deploy latest commit**으로 먼저 배포하고, deploy 로그에서 저장소 접근 경고가 사라졌는지 확인한다.

## 3. 배포 후 필수 확인

```powershell
Invoke-RestMethod https://<api-host>/health
```

- 브라우저 개발자 도구에 CORS 오류가 없어야 한다.
- `기록만 해줘` 요청은 승인 전 DB를 바꾸지 않고 proposal 카드를 보여야 한다.
- 같은 proposal을 두 번 승인해도 실제 식사 row는 한 건이어야 한다.
- SSE가 중간에 끊기면 같은 run ID로 재접속하고 완료된 실행은 다시 수행하지 않아야 한다.
- 계정 삭제 뒤 이전 JWT로 보호 API를 호출하면 401이어야 한다.

## 4. 장애 알림

Render Dashboard의 **Workspace → Integrations → Notifications**에서 다음을 설정한다.

- Notification Destination: `Email`
- Default Service Notifications: `Only failure notifications`
- `metadiet-api`와 `metadiet-web`에 `None` override가 없는지 확인

이 설정은 build/deploy 실패, 실행 중 service unhealthy, Blueprint sync 실패를 이메일로 알린다. API는 `render.yaml`의 `healthCheckPath: /health`로 상태를 판정한다. 무료 베타에서는 Render 내부 장애 알림을 기본으로 사용하고, 외부 사용자가 실제로 접근 가능한지 확인하는 별도 uptime probe는 후속 선택 작업으로 둔다.

## 5. 무료 플랜 한계

- 무료 API는 15분 동안 요청이 없으면 sleep할 수 있어 첫 요청이 느릴 수 있다.
- 단일 API 인스턴스이므로 로컬 kind에서 검증한 다중 Pod 교차 복구를 그대로 재현하지는 않는다. 체크포인트·HITL·중복 저장 방지는 그대로 유지한다.
- scheduler는 API와 함께 sleep하므로 정시 실행을 보장하지 않는다. 제한 베타에서는 사용자가 요청하는 주간 분석이 주 경로이며, 정시 알림이 필요해지면 유료 worker 또는 외부 cron을 사용한다.
- 512MB 안에서 FlashRank는 사용하지 않는다. 최종 평가에서 더 정확하고 메모리 사용이 낮았던 Hybrid + 리랭커 없음 구성을 유지한다.

실제 제한 베타 부하 시험은 공개 URL에서 실행하고 p50/p95, 오류율, cold start, Gemini/Pinecone/Supabase 외부 호출 실패율을 별도 artifact로 남긴다.

## 6. 공개 E2E와 제한 부하 재현

로컬 `backend/.env`의 서비스 키를 사용하며, 합성 사용자와 데이터는 각 스크립트의 `finally` 경로에서 삭제한다. 비밀값은 출력이나 artifact에 기록하지 않는다.

```powershell
C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe backend\scripts\check_render_beta.py `
  --base-url https://metadiet-api.onrender.com

C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe backend\scripts\check_render_load.py `
  --base-url https://metadiet-api.onrender.com `
  --health-requests 50 --read-requests 30 --agent-requests 2
```

`check_render_beta.py`는 온보딩, 전략 확정, SSE, 동일 run 재생, proposal 복원, 중복 확정 방지를 검사한다. `check_render_load.py`는 공개 health, 인증된 읽기, 실제 Agent SSE를 서로 다른 제한 동시성으로 측정한다. 실패 시 같은 호출을 반복하기 전에 Render 로그와 LangSmith trace의 예외 유형을 확인한다.
