# MetaDiet AI

베타 사용자에게 공유하기: [사용 안내와 피드백 보내는 방법](docs/BETA_USER_GUIDE.md).

운영자용: [관리자 피드백 검토·담당자 필터·미처리 건수·변경 이력](docs/ADMIN_FEEDBACK.md).

일반 음식 입력 개선: [김치찌개·불고기 기본 1인분과 직접 계산 카드](docs/DEFAULT_SERVING_FIX.md).

외부 호출 계측: [새 공개100쌍·오류·품질·복구](docs/transport_public/README.md). 연결32.55ms/TLS16.89ms보다 헤더 대기2749.39ms가 컸습니다. 스트리밍은 전체 중앙값 **8.384→8.455초**, p95 **10.421→11.375초**로 개선되지 않아 복구했습니다. 양쪽 품질·최신값100/100, 후보500 오류1건은 제한 재시도로 복구했습니다.

SDK 준비 분리 실험: [새 공개 전후100건·품질·복구·원본](docs/sdk_phase_public/README.md). 준비 **514.69→0.03ms**, 전체 중앙값 **7.918→7.406초**, p95 **11.021→9.662초**. 양쪽 품질·최신값 유지에도 가장 큰 외부 호출 중앙값은3.22%만 감소해 사전10% 기준 미달로 재사용 후보를 비활성화했습니다. 계측은 배포된 상태입니다.

모델 병목 공개 실험: [기존 200건 분석과 Flash-Lite 100건 비교](docs/model_followup_public/README.md), [선택적 도구 생략 100건 비교](docs/tool_free_followup_public/README.md). 기존 중앙값/p95 **7.821/9.551초**, Flash-Lite **6.334/10.727초**, 도구 생략 **7.884/9.707초**. p95·품질 또는 속도 기준 미달로 두 후보를 채택하지 않았습니다. 동일 baseline 100건을 재사용했으며 총 신규 공개 요청은 300건입니다.

공개 재검증 완료: [오류 복구 보완·전후100건·원본·배포 캡처](docs/budget_public_v2/README.md). 저장 중앙값 **2.500→1.762초(29.5%↓)**, 전체 응답 **8.378→7.642초(8.8%↓)**. 양쪽 완료·최신값·미저장100/100, 품질 기준 유지로 공개 pipeline을 활성화했습니다. p95는10.018→10.360초로3.4% 증가했습니다.

공개 예산 저장 비교: [Render 전후 각 100건·오류 로그·배포 캡처](docs/budget_public/README.md). 저장 중앙값 **2.497→1.800초**, 정상 응답 완료 **8.236→7.807초**를 관측했습니다. 기존 요청의 Gemini 504 1건도 보존했으며, 당시 사전 완전성 기준 미달로 적용을 보류했습니다. 현재 상태는 위 재검증 결과를 따릅니다.

실행 예산 저장 실험: [단계별 분석과 동일 조건100쌍](docs/budget_pipeline/README.md). 저장 단계는27.6% 줄었지만 전체 응답 개선은0.7%로 당시 채택 기준에 미달해 적용을 보류했습니다.

최신 병목 실험: [후속 코칭 프롬프트 축소 전후 각 100건](docs/compact_coaching/README.md). 입력 토큰은 줄었지만 중앙값은 4.323→4.413초로 개선되지 않아 후보를 활성화하지 않았습니다.

최신 성능 실험: [조건별 100건 코칭 비교·배포 버전·SSE 복원·공개 화면 검증](docs/latency100/README.md). 이전 소표본 실험은 역사적 기록으로 유지하며 이번 100건 비교와 구분합니다.

MetaDiet AI는 식사 기록, 체중·인바디 추세, 장기 목표와 영양 근거를 함께 사용하는 **LangGraph 기반 멀티에이전트 식단 코칭 서비스**입니다. 자연어와 사진 입력을 분석하되 실제 저장과 전략 변경은 사용자가 확인한 proposal만 반영합니다.

- 공개 베타 UI: [metadiet-web.onrender.com](https://metadiet-web.onrender.com)
- 베타 사용·피드백 수집 안내: [BETA_USER_GUIDE.md](docs/BETA_USER_GUIDE.md)
- 상세 구조: [ARCHITECTURE.md](ARCHITECTURE.md)
- 평가 방법과 전체 원본 결과: [EVALUATION.md](EVALUATION.md)
- 포트폴리오 핵심 결과: [PORTFOLIO_RESULTS.md](PORTFOLIO_RESULTS.md)
- 포트폴리오 사례: [PORTFOLIO_CASE_STUDY.md](PORTFOLIO_CASE_STUDY.md)
- 제한 베타 종료 체크리스트: [BETA_RELEASE_CHECKLIST.md](BETA_RELEASE_CHECKLIST.md)
- 베타 릴리스 노트: [BETA_RELEASE_NOTES.md](BETA_RELEASE_NOTES.md)
- GitHub prerelease: [beta-v1.1.0](https://github.com/Kim-Du-Yeon/MetaDiet-AI/releases/tag/beta-v1.1.0)
- 무료 베타 운영 절차: [deploy/RENDER_BETA.md](deploy/RENDER_BETA.md)
- 국내 가공식품 DB 보강: [수입·검증·실패 해결 기록](docs/food_catalog/IMPLEMENTATION.md)
- 식품 DB 통합 검증: [버전 복구·공개 브라우저·Agent 18회 비교](docs/food_catalog/VERIFICATION_RESULTS.md)

## 지원용 자료 다운로드

현재 포트폴리오 기준(2026-10-12)의 구현 기능, 실험 결과, 실패 원인과 해결 과정, 공개 배포·관측을 정리했습니다. 실제 사용자 피드백과 건강 효과는 미측정으로 구분합니다.

- [발표자료 다운로드 (PPTX, 12장)](https://raw.githubusercontent.com/Kim-Du-Yeon/MetaDiet-AI/refs/heads/main/docs/portfolio/MetaDiet_AI_Presentation.pptx): 편집 가능한 표와 발표자 노트 포함, 약 10분 발표용
- [제출용 포트폴리오 다운로드 (PDF, 7쪽)](https://raw.githubusercontent.com/Kim-Du-Yeon/MetaDiet-AI/refs/heads/main/docs/portfolio/MetaDiet_AI_Portfolio.pdf): 평가 조건·수치·한계와 실패 해결 과정 상세 설명
- [저장소에서 PDF 미리보기](docs/portfolio/MetaDiet_AI_Portfolio.pdf)

## 간단한 식사 입력

`닭가슴살 밥 한공기 김치`처럼 입력하면 앱 기본 분량으로 음식별 영양값과 확인 카드를 표시합니다. 분량을 바로 수정하고 **이대로 기록**으로 저장할 수 있습니다. 정확한 제품 찾기는 보조 기능입니다. [구현·경로 비교·실패 해결 기록](docs/simple_meals/RESULTS.md)을 확인하세요.

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
- **제품 분석:** 관리자 DAU/WAU·가입 cohort 전환·상담 응답 완료율·p95, 개인정보를 최소화한 이벤트와 실제 LangSmith trace ID 연결
- **체중·체성분:** 일상 체중과 완전한 인바디를 분리하고 사용자 확인 후 기록, 대시보드 즉시 갱신
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
| 백엔드 회귀 | **389 passed, 1 skipped** |
| 프론트엔드 회귀 | **58 passed**, production build 성공 |
| 독립 RAG 20문항 | 지정 근거 Recall@4 85%, 대체 유효 근거 포함 evidence support 95% |
| Ragas 독립 평가 | faithfulness 1.00, context recall 0.95 |
| Agent 독립 흐름 | 목표 달성 8/8, 정책 위반 0, 승인 전 write 0 |
| kind rolling restart | `/health` 400/400, 실패 0, p95 5.86ms |
| 공개 제한 부하 | health 50건·인증 조회 30건·Agent 2건 오류 0 |
| 호출 최적화 (개발 8개 재시험) | p95 24.92→13.69초, 모델 호출 35→30, 목표 달성 8/8 유지 |
| 공개 관리자·관측 | 실제 관리자 기간 조회·새로고침, 일반 사용자 403, SSE·제품 이벤트·LangSmith ID 일치 |
| 공개 브라우저 | 스트리밍·proposal 복원·중복 방지·401/500/연결 중단 UI 검증 |

문서 기준일은 2026-10-12이며 실제 사용자 피드백은 추후 추가합니다. 개발셋 전후 비교는 독립 최종 평가와 별도입니다.

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

일반 음식 표준값·제품 선택 카드: [구현 및 검증 기록](docs/food_catalog/SELECTION_POLICY.md).

### 일상 음식 간단 입력 확장

`고구마 사과 우유`, `계란후라이 식빵 두장 플레인 요거트`, `오트밀 바나나 아몬드`도 앱 기본 분량으로 바로 확인 카드를 만듭니다. 분량은 카드에서 수정하고 확정해야 저장됩니다. 조리 형태 포함 35개 매핑의 [기본 분량·지원 범위·검증 결과](docs/simple_meals/EXPANSION.md)를 확인할 수 있습니다.
### 반복 질문을 줄인 식사 입력

밥 한 공기는 200g, 삼겹살은 대표 구이 기준, 라이스페이퍼는 장당 10g으로 바로 계산합니다. 미등록 음식은 버튼으로 대표 기준 사용·기입·제외를 선택하며 스킵·취소할 수 있습니다. [구현·검증 결과](docs/simple_meals/BUTTON_FIRST.md)

빵·피자·만두 등 기본 계산 매핑을 53개로 확대했습니다. 소보로/메론빵, 도미노/냉동피자, 물만두/군만두도 기본 분량으로 진행하며 유사·일반 기준임을 표시합니다. [분량·별칭·검증 결과](docs/simple_meals/EVERYDAY_CATEGORIES.md)


## 음식군 대표 기준 확장 (2026-10-13)

기존 개별 음식 연결에 18개 음식군 대표 규칙을 추가해 질문을 줄이고, 계산 카드에 음식별 제외·되돌리기를 연결했습니다. 고정 합성 평가 1/18 → 18/18, 백엔드 567 passed·1 기존 skipped, 프론트 71 passed와 빌드 성공. 대표값의 오차와 미지원 음식군을 구분합니다. [구현·실패 해결·검증 상세](docs/simple_meals/FOOD_GROUPS.md).


## 후속 식단 코칭 성능 개선

후속 실험에서는 단어별 표시 지연을 제거하고 실제 이전 메시지를 포함한 공개 다중 턴 24개 요청을 평가했습니다. 첫 답변 이후 완료 중앙값 **2.00→0.39초**, 전체 완료 **23.06→21.80초**, 첫 답변 **21.20→21.41초**였습니다. 최신 기록 회귀 100개와 공개 수정·확정·취소·중복 검증, 전후 화면도 기록했습니다. [측정 조건·원본·캡처·남은 병목](docs/answer_delivery/README.md).

단계별 계측 후 실행 예산 저장의 반복 DB 연결을 재사용했습니다. 별도 동일 문맥 24요청에서 예산 저장 중앙값 **6.86→3.90초**, 전체 완료 **21.36→18.45초**를 관측했습니다. 모델 합산은 **10.12→10.58초**로 개선되지 않았습니다. 실제 스트리밍 probe와 동시 예약·최신 기록 검증까지 [단계별 병목 실험](docs/coaching_stages/README.md)에 공개합니다.

이후 단순 후속 코칭을 읽기 전용 전문 Agent에 직접 연결했습니다. 후속 6건씩의 완료 중앙값 **19.28→12.07초**, 모델 호출 중앙값 **1.5→1회**를 관측했고, 최신성 회귀 200건과 공개 최신 섭취 반영을 확인했습니다. [전후 품질 검토·원본·캡처·제한 사항](docs/direct_followup/README.md).

후속 코칭의 추론 수준도 별도로 실험했습니다. 실제 Gemini·합성 DB 교차 비교 9쌍에서 중앙값 **8.72→5.06초**, 최신 섭취·목표 반영 **9/9 유지**를 확인해 단순 후속 경로에만 `low`를 적용했습니다. [공개 전후 측정·품질 평가·배포 증거](docs/coaching_thinking/README.md).

요청 단위 조회 결과 재사용, Supervisor·전문 Agent의 최신 컨텍스트 공유, 짧은 후속 답변과 한 줄 진행 표시를 적용했습니다. 통제 실험의 반복 DB 조회는 6→3회, 위임 코칭 모델 호출은 3→2회입니다. 일반 요청의 최신 DB 조회 3회와 사용자 확인 저장 정책은 유지합니다. [공개 측정·화면 캡처·실패 해결 기록](docs/coaching_performance/README.md).
