# MetaDiet AI

MetaDiet AI는 식사 기록, 체중·인바디 추세, 장기 목표와 영양 근거를 함께 사용하는 **LangGraph 기반 멀티에이전트 식단 코칭 서비스**입니다. 자연어와 사진 입력을 분석하되 실제 저장과 전략 변경은 사용자가 확인한 proposal만 반영합니다.

- 공개 베타 UI: [metadiet-web.onrender.com](https://metadiet-web.onrender.com)
- 상세 구조: [ARCHITECTURE.md](ARCHITECTURE.md)
- 평가 방법과 전체 원본 결과: [EVALUATION.md](EVALUATION.md)
- 포트폴리오 핵심 결과: [PORTFOLIO_RESULTS.md](PORTFOLIO_RESULTS.md)
- 포트폴리오 사례: [PORTFOLIO_CASE_STUDY.md](PORTFOLIO_CASE_STUDY.md)
- 제한 베타 종료 체크리스트: [BETA_RELEASE_CHECKLIST.md](BETA_RELEASE_CHECKLIST.md)
- 베타 릴리스 노트: [BETA_RELEASE_NOTES.md](BETA_RELEASE_NOTES.md)
- GitHub prerelease: [beta-v1.1.0](https://github.com/Kim-Du-Yeon/MetaDiet-AI/releases/tag/beta-v1.1.0)
- 무료 베타 운영 절차: [deploy/RENDER_BETA.md](deploy/RENDER_BETA.md)

## 구현 범위

- **멀티에이전트 오케스트레이션:** Gemini Supervisor가 전문 Agent와 도구를 선택하고 LangGraph가 상태 전이, 실패 피드백, 실행 예산과 종료 조건을 관리
- **전문 Agent:** 식사 기록, 목표 관리, 전략 조언, 식단 계획·검증, 인바디 분석, 리포트, 편집, 확인/HITL
- **Weekly Deep Agent:** 장기 상태와 최근 식사·인바디를 분석하고 읽기 전용 MCP 도구를 제한된 예산 안에서 사용
- **HITL과 원자적 저장:** 식사·인바디·전략 proposal을 ID/version으로 고정하고 승인 전 domain write 차단, 중복 승인 멱등 처리
- **장·단기 상태:** Supabase Postgres와 LangGraph Postgres checkpointer로 목표·전략·최근 실행·대화 복원 및 rollback 관리
- **RAG:** PyPDF/recursive, Gemini embedding 3072차원, Pinecone dense + Kiwi BM25 + RRF Hybrid, 출처·페이지 추적과 최신 판본·충돌 정책
- **결정적 영양 계산:** 칼로리·영양소 수치는 RAG가 아니라 국가표준식품성분표 CSV로 계산
- **평가·관측:** Ragas, 독립 gold set, Agent/tool/HITL 평가, LangSmith trace, 비용·지연·재시도 관측
- **Streaming UI:** 의도 분석 → Agent 위임 → 도구 실행 → 근거 검토 → 사용자 확인을 SSE 이벤트로 표시하고 연결 중단 시 재개
- **운영:** Docker Compose, 읽기 전용 MCP, Kubernetes kind 다중 Pod 복구, Render 무료 공개 베타와 제한 부하 시험

## 현재 운영 구성

| 영역 | 선택한 구성 | 선택 근거 |
|---|---|---|
| 생성·라우팅·Vision | Google Gemini | 운영 모델 공급자를 Gemini로 통일 |
| 임베딩 | Gemini embedding, 3072차원 | 768차원은 독립 평가에서 3072 대비 낮아 운영 미채택 |
| 파서·청킹 | PyPDF + recursive | 전체 10개 PDF의 검색 품질·안정성·문맥 잘림을 함께 비교해 유지 |
| 검색 | Dense + BM25 + RRF Hybrid | 독립 근거 평가에서 Dense 단독보다 유리 |
| 리랭커 | 없음 | FlashRank와 Jev가 품질·지연·메모리 채택 기준을 충족하지 못함 |
| Vector DB | Pinecone | 4,139개 활성 Gemini 벡터 |
| 상태·인증 | Supabase Postgres/Auth | 사용자 데이터, proposal, checkpoint와 JWT/RLS 관리 |
| 관측·평가 | LangSmith + Ragas | 실행 trace와 답변 근거 평가를 분리 |

Jev는 Supervisor·도구 선택·RAG 재정렬에서 Gemini와 비교했지만 품질 비열등성과 20% 지연/비용 개선 기준을 충족하지 못해 운영 경로에서는 비활성화했습니다. 실패 결과도 [EVALUATION.md](EVALUATION.md)에 보존했습니다.

## 검증 결과

| 범위 | 결과 |
|---|---|
| 백엔드 회귀 | **376 passed, 1 skipped** |
| 프론트엔드 회귀 | **42 passed**, production build 성공 |
| 독립 RAG 20문항 | 지정 근거 Recall@4 85%, 대체 유효 근거 포함 evidence support 95% |
| Ragas 독립 평가 | faithfulness 1.00, context recall 0.95 |
| Agent 독립 흐름 | 목표 달성 8/8, 정책 위반 0, 승인 전 write 0 |
| kind rolling restart | `/health` 400/400, 실패 0, p95 5.86ms |
| 공개 제한 부하 | health 50건·인증 조회 30건·Agent 2건 오류 0 |
| 공개 브라우저 | 스트리밍·proposal 복원·중복 방지·401/500/연결 중단 UI 검증 |

수치는 해당 gold set과 합성·제한 베타 조건의 결과이며 일반적인 임상 효과나 최대 처리량을 뜻하지 않습니다.

## 기술 스택

- Frontend: React, SSE
- Backend: FastAPI, Python
- Agent: LangGraph, LangChain, Gemini tool calling
- Data: Supabase Postgres/Auth, Pinecone, CSV nutrition DB
- RAG: PyPDF, Kiwi BM25, RRF Hybrid, Gemini Embedding
- Evaluation: Ragas, LangSmith, custom Agent/tool/HITL evaluators
- Infra: Docker, Kubernetes kind, Render

## 로컬 실행

비밀값은 저장소에 커밋하지 않습니다. `backend/.env.example`과 `frontend/.env.example`을 복사해 값을 입력합니다.

```powershell
cd backend
venv\Scripts\python.exe main.py
```

```powershell
cd frontend
npm install
npm start
```

기본 로컬 주소는 backend `http://localhost:8080`, frontend `http://localhost:3000`입니다.

## 검증 명령

```powershell
cd backend
venv\Scripts\python.exe -m pytest --basetemp=.pytest-runtime
```

```powershell
cd frontend
npm test -- --runInBand --watchAll=false
npm run build
```

Ragas는 의존성 충돌을 피하기 위해 별도 평가 환경을 사용합니다. 정확한 버전과 실행 명령은 [AGENTS.md](AGENTS.md)와 [EVALUATION.md](EVALUATION.md)를 참고합니다.

## 현재 한계

- Render 무료 API는 휴면 후 첫 요청이 실제 측정에서 약 53초 걸렸습니다.
- 독립 RAG 영어 질문 1건은 근거를 찾지 못했으며, 시스템은 인용을 만들지 않고 답변을 보류합니다.
- Render 장애 알림은 workspace Email + `Only failure notifications`로 설정했으며 서비스별 override는 없습니다.
- `react-scripts`의 빌드 전이 의존성 취약점은 정적 런타임과 분리돼 있으며 Vite 전환을 후속 선택 작업으로 남겼습니다.
- 의료 진단·치료 서비스가 아니며 일반 성인 체중 관리 정보에 한정합니다.
