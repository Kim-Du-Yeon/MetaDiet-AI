## 최신: 기준선 실패 분리 후 v4 운영 적용 (2026-10-22)

[정책 개정·원문 보존·실제 Staging/운영·브라우저·비용](docs/prompt_control/clarification-balanced/v4-approval-policy-v2-20261022/RESULTS.md). 기존100쌍/이전 미통과 기록을 보존하고 후보 자체의 안전·품질 기준을 분리했다. **결과를 본 뒤의 명시적 정책 개정**이며 새 사전등록 검증으로 표현하지 않는다. 기존200답변/Pro100쌍 재사용, 추가Flash8회/Pro0회로 약$0.022 추정. 서명릴리스8f4014f9를 실제Staging→Production 승격하고 공개2요청의 실제사용커밋을 확인했다. 전체pytest1825통과/기존skip1. Staging1건의 선택적 마무리 제안 재발은 한계로 보존하며 실제 사용자A/B는 계속 비활성이다.

아래 이전 holdout 미승격 문단은 당시 사전 기준의 역사적 판단이며 원본 그대로다.

## 최신: v4 신규 합성 holdout·두 프롬프트 승인 경로 (2026-10-22)

새100질문에서 v1/v4 각100시도·Pro100쌍 완료. 정답98→100%, 충실성97→100%, 행동92→100%, 불필요 질문5→0, 필수 질문50/50 유지. v4의 회귀0건이었다. 후보 성능 기준은 충족했으나 사전 기준의 **기준선까지 전건 정상 완료** 조건을 v1 blocked2건이 충족하지 못해 서명·Staging·운영 승격은 하지 않았다. 평가 기준 설계의 한계도 별도 기록했다. [결과·회복8건·비용·승인 제한](docs/prompt_control/clarification-balanced/v4-independent-20261022/RESULTS.md)

## 분량·레시피 질문 구분 비교 (2026-10-22)

별도 개발24건 후 동일100건에서 v4는 정답·충실성100/100 유지, 불필요 질문3→0, 필수 질문50/50을 확인했다. 평가 후보로 채택했고 운영 승격은 수행하지 않았다. [실험 결과·사례·비용·한계](docs/prompt_control/clarification-balanced/v4-calculation-mode-20261022/RESULTS.md)

후속 상담 v3 회귀 개선·비교 완료: [별도 개발24쌍·동일100건·정답99/98/100·행동99/97/97·v1 유지·추가 약$0.81](docs/prompt_control/clarification-balanced/v3-candidate-20261022/RESULTS.md). 평가 문맥 누락과 모델 오류를 구분하고 기존200답변을 재사용했습니다.

후속 질문 프롬프트 비교 완료: [v1/v2 각100건·Pro100쌍 완료·정답98%/96%·충실성100%/96%·후보미채택 및 원문/비용](docs/prompt_control/clarification-balanced/execution-v2/COMPLETE100.md).

채점 형식 후속 분석: [남은31쌍 원문·별도 출력 계약·오프라인 검증·잔여$0.108478 재평가 가능성](docs/prompt_control/clarification-balanced/execution-v2/FORMAT_CONTRACT.md). 새 유료 호출0회.

최신 후속 질문 후보 평가: [추가 $0.141522로45쌍 재평가·69/100 유효·31 형식 실패·기존 v1 유지](docs/prompt_control/clarification-balanced/execution-v2/RETRY_025.md).

추가 질문 평가셋: [바로 답변50·필수 질문50·개발20·저장 사례10·Pro RPD 차단과 재개 조건](docs/prompt_control/clarification-balanced/README.md).

후속 상담 새 후보 비교: [기존 v1 재사용·추가 질문 감소 가설·Pro429 중단·미승격 이유](docs/prompt_control/followup-question-candidate/README.md).

새 후보 승인 절차: [커밋 선택 → 기존 평가 재사용/새 비교 → 검증 receipt → 서명 → 수동 승격](docs/prompt_control/release_workflow/README.md). 미검증 후보는 운영에 적용되지 않습니다.

최신 프롬프트 운영 제어: [LangSmith 비공개8개·원자적 서명 릴리스·HITL 고정·v1/v2각100건·캐시100쌍 비교·실제 승격/롤백·채택 판단](docs/prompt_control/README.md). 실제 사용자A/B와 명시적 캐시는OFF이며, 구현/비교/운영 검증 상태를 구분합니다.

**성능 하락 정성 분석:** [회귀10건의4유형·공통 실패 분리·문맥 조립6건 재현·미채택 판단](docs/agentic_rag/20261021-controlled-hybrid-analysis/README.md). 수치3/시간조건3/전체보류2/목록누락2건으로 분류했다. 인접 청크 우선·6,000자 문맥 한도에 의한 핵심 표현 탈락은 오프라인6/6 동일 문맥 재현으로 확인했다. 새 답변 품질 개선을 뜻하지 않으며,신규 유료 호출 없이 면접 설명·개선 검증 기준까지 정리했다.

## 최신: 동일 조건 Hybrid vs Hybrid+Agentic100시도씩 비교

[통제 비교 전체 결과·오류·비용·채택 판단](docs/agentic_rag/20261021-controlled-hybrid-v14/README.md). 같은 최종 프롬프트·Flash 모델·Hybrid 설정·환경에서 새200답변과Pro200판정을 완료했다. 정답89%→80%,이진 근거 충실성100%→99%,중앙값6.435→9.709초,p95 10.663→15.477초,모델+임베딩 추정/100시도$0.293046→$0.399767. Agentic이 기존 오답1건을 회복했지만 정답10건을 놓쳤다. **기존 Hybrid/no-reranker 유지·Agentic 운영 미채택**으로 판단했다. 구현·비교 실험 완료와 운영 적용X를 구분한다.

40질문/20사실그룹 반복 개발셋이며 독립100문항·사용자 성공률이 아니다. 같은 정적 답변 지침을 양쪽에 적용하고 Agentic의 동적 답변 지침은 제거했다. 충실성은 Pro 이진 판정으로 Ragas와 혼용하지 않는다. 모든 보류를 분모에 남겼고,요청 실패·출력 잘림은0건이었다. 아래 과거 dense 비교와 독립20문항 평가 기록은 서로 다른 평가 범위의 보존 자료다.

RAG 조합 실험·채택 판단(최종): [Parser·Chunking·Embedding·검색·Jev·Agentic 비교 인덱스](docs/rag_experiments/RAG_RECIPE_DECISIONS.md). 일반 RAG/Agentic 조건별100시도 완료, Pro 내용 정답85%/88%, 정상 종료 확인 Agentic 정답84%. 일관된 운영 우위가 없어 기존 Hybrid/no-reranker 유지. [전체 결과·오류·한계](docs/agentic_rag/20261021-rag-vs-agentic-v14-complete100/README.md).

Agentic RAG 인접 청크·한국어 표 후속 (2026-10-21): [구현·별도 개발20문항 검증·전후100시도씩 원본과402 중단](docs/agentic_rag/20261021-adjacent-table/README.md). 합성 개발 Pro 정답16/20→20/20, 충실도20/20 유지. 본 비교는 크레딧 소진으로 요청 완료53/54건·최종 평가와 비용 미완료여서 운영 개선을 주장하지 않는다. 기본OFF·미배포. 이후 실패 사례 소규모 확인·저장 답변 재채점·사전 비용 상한을 우선한다.

Agentic RAG 핵심 수치·적용 범위 재검증 (2026-10-21): [별도 개발12개·새 전후100시도씩·Pro200평가와 남은 검색 한계](docs/agentic_rag/20261021-core-scope/README.md). 정답률89→95%, 충실도100→100%, p95 17.029→21.410초, 모델+임베딩 API 추정/100시도$0.597061→$0.688828. 적용 범위 누락4건 회복, 다만 근거 페이지80→76%로 사전 게이트 미통과. 기본OFF·공개 배포 보류.

Agentic RAG 표·부분 답변 재검증 (2026-10-21): [별도 개발12개·새 전후100시도씩·Pro200건 평가와 미채택 이유](docs/agentic_rag/20261021-v3/README.md). 정답률89→89%, 충실도99→100%, 근거 페이지76→80%, p95 21.203→20.300초, 모델 API 비용/100건$0.570576→$0.609175(임베딩 실제 토큰 포함). 품질 기준 미달로 운영OFF·배포 보류.

Agentic RAG 근거 보존 후속 검증 (2026-10-21): [기존 200건 Pro 평가 완료·근거 보존 전후 100시도씩·미채택 판단](docs/agentic_rag/20261021/README.md). 기존 단일→v1 정답률 87→91%; 새 v1→v2는 89→89%, 근거 페이지 74→75%, p95 22.983→21.720초. 정답률 기준·전체 비용 검증 미통과로 기본OFF·운영 적용 보류. 아래 이전의 품질 평가 미완료 기록은 당시 상태이며 후속 문서에서 완료 결과를 확인할 수 있다.

Agentic RAG 후보: [검색 평가·질의 재작성·재검색 구현과 전후100시도씩·미채택 원인](docs/agentic_rag/20261020/README.md). 근거 페이지 적중79→76%, 중앙값11.507→14.370초. Pro 일일250회 제한으로 품질 평가각50/100 완료, 운영 활성화·배포 보류.

자연스러운 근거 요청: [‘영양학적으로·근거해서’ 선행 검색과 검색 상태 구분](docs/food_catalog/natural-evidence-20261020/README.md).

기술 포트폴리오: [Parser·Chunking·Embedding·RAG·Jev·모델 라우팅·멀티 Agent·Kubernetes — 구현 / 비교 실험 / 운영 적용·결과·한계](docs/TECHNOLOGY_PORTFOLIO.md).

선택적 RAG 설계: [단순 추천은 상시 검색을 강제하지 않고, 근거 요청은 검색 가능한 경로로·질문/실행 단계/출처 원본 캡처](docs/food_catalog/selective-rag-20261019/README.md).

답변 출처·기록 근거 표시: [공개 배포·저녁 추천 브라우저 검증·검색 정책 오류 수정·캡처](docs/food_catalog/answer-basis-20261019/README.md).

식사 변경 응답 최적화: [집계·버전 동봉·격리 PostgreSQL 전후 120건씩·정합성·실패/복구](docs/food_catalog/intake-snapshot-20261019/README.md). 정상 흐름 HTTP 4→1회, 합성 데이터 준비 p95 772.977→157.741ms. 운영 성능과 구분.

식사 기록 수정·삭제와 화면 일관성: [상단 집계 갱신·대화의 삭제/수정 표시·검증과 한계](docs/food_catalog/intake-sync-20261019/README.md).

# MetaDiet AI

식사 입력 화면 정리: [제품 기능은 확인 카드 안으로·추천은 기록 완료 후·검증과 캡처](docs/food_catalog/contextual-actions-20261019/README.md).

장소가 붙은 식사 입력·제외 UX 수정: [한식뷔페 음식 분리·일부 제외·기록 없이 닫기·검증 근거](docs/food_catalog/place-context-20261019/README.md).

유료 계층 v1 고정 비교: [동일100쌍·Pro50건·속도/품질/최신값/비용·제한 적용](docs/model_routing/tier1-v1-20261019/README.md). 중앙값4.226→2.010초, p95 7.050→5.158초, 생성 비용55.88% 감소. 양쪽 계약검사100/100·합성 최신값25/25, 사전 채택 기준 통과.

이전 무료 계층 점검: [당시 quota 차단 근거·프롬프트 재시작 복구](docs/model_routing/v1-recheck-20261019/README.md). 이후 Tier1 비교는 위 새 결과를 따릅니다.

모델 선택 비교와 프롬프트 관리: [규칙·Jev 각 100건 결과와 채택 보류](docs/model_routing/JEV_COMPARISON.md) · [프롬프트 v1·해시·환경변수·복구](docs/prompt_versioning/README.md).

모델 라우팅: [역할별 모델 선정표·원본 이미지·환경변수·동일 사례 비교 및 채택 조건](docs/model_routing/README.md). 기본 비활성이며 Pro 평가 완료와 작업별 품질 검증 전에는 운영에 활성화하지 않습니다.

독립 검증: [2시간 메모리720건·원격/하이브리드각120건·402 제외 범위와 원본](docs/rag_memory_quality/README.md). 메모리 중앙값100.19→102.35MiB, 검색 근거 페이지 적중75%/80%로 동등 품질을 주장하지 않습니다.

운영 메모리 장애·근거 보류 개선: [실제 OOM 이벤트, 100쌍 토크나이저 실험, 512MB 보호 및 기록 분석 유지](docs/coaching_review/README.md).

통계 조회 연결 복구: [ReadError 원인 범위·공개 상담/최신값 전후100건·배포·브라우저 확인](docs/public_stats_recovery/README.md). 상태 변경 통계 반환84→100/100, 누락13→0건·요청 실패3→0건. 정상 통계 중앙값은0.304→0.600초로 늘어 신뢰성과 비용을 함께 기록했습니다.

요청 시작 지연 계측: [요청 ID·브라우저 표시 기회·API/Agent 연결·공개 고정 평가](docs/request_startup/README.md).

공개 브라우저 검증: [최신 배포·기본 분량·수정·제외·취소·새로고침 복구와 캡처](docs/food_catalog/REPRESENTATIVES_PUBLIC_BROWSER.md).


일반 음식 자동 입력 보강: [동일 100종 자동 카드 57→100건·대표 연결·잘못된 대체 수정·크레딧 한계](docs/food_catalog/COMMON_REPRESENTATIVES_IMPROVEMENT.md).


일반 음식 100종 점검: [자동 카드 57건·모델 결제 오류 43건·원인과 보완 계획](docs/food_catalog/COMMON_FOODS_100.md).


베타 사용자에게 공유하기: [사용 안내·복사할 초대 문구·피드백 보내기](docs/BETA_USER_GUIDE.md) · [10~15분 테스트 시나리오·결과 양식](docs/BETA_TEST_SCENARIOS.md).

제육볶음 입력 개선: [식약처 가정식 대표값·기본 200g·기입 질문 제거와 검증](docs/food_catalog/JEYUK_DEFAULT.md).

운영자용: [관리자 피드백 검토·자동 갱신·오래된 미처리·담당자·이력](docs/ADMIN_FEEDBACK.md).

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
- 베타 테스트 시나리오·수정/제외/취소/확정·재로그인·피드백 확인: [BETA_TEST_SCENARIOS.md](docs/BETA_TEST_SCENARIOS.md)
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

관리자 운영 검증: [동시 수정100회·1만 건 조회·자동 갱신 결과와 캡처](docs/admin-feedback/SCALE_CONCURRENCY.md).

관리자 안정성 검증: [실제 인증 세션·10분 지속 조회·DB 연결 장애 복구](docs/admin-feedback/SOAK_RECOVERY.md).

독립 무료 Render 검증 완료: [2시간·720건 조회, 실제 DB 재시작, 동시 수정 100라운드, 직접 백업 복구와 Supabase 차이](docs/admin-feedback/RENDER_RECOVERY_VALIDATION.md). 전체 조회 720/720, 중앙값 530.63ms·p95 753.94ms. 복원 후 데이터/제약/인덱스/RLS hash 일치·조회 100/100. 합성 인증과 관리자 API 범위이며 운영 Supabase 전체 복구 결과는 아닙니다. 검증 웹·DB는 정지했습니다.

후속 질문 의미 평가의 실제 실행·승인 연결: [실행 조건·사전 게이트·예산·원본 결과](docs/prompt_control/clarification-balanced/execution-v2/README.md).

[Pro RPD 진단 및 저장 답변의 Batch 채점 재개](docs/prompt_control/clarification-balanced/execution-v2/RESUME.md).

[후속 채점 오프라인 복구와 남은45쌍 비용 제안](docs/prompt_control/clarification-balanced/execution-v2/OFFLINE_RECOVERY.md).
