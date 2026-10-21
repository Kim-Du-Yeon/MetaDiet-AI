**성능 하락 정성 분석:** [회귀10건의4유형·공통 실패 분리·문맥 조립6건 재현·미채택 판단](../agentic_rag/20261021-controlled-hybrid-analysis/README.md). 수치3/시간조건3/전체보류2/목록누락2건으로 분류했다. 인접 청크 우선·6,000자 문맥 한도에 의한 핵심 표현 탈락은 오프라인6/6 동일 문맥 재현으로 확인했다. 새 답변 품질 개선을 뜻하지 않으며,신규 유료 호출 없이 면접 설명·개선 검증 기준까지 정리했다.

# RAG 조합 실험과 채택 판단

파서·청킹·임베딩·검색·리랭킹 실험에 **Agentic RAG를 추가 제어 방식 후보**로 연결한다. Agentic은 임베딩이나 검색기의 이름이 아니라, 검색 후 충분성 판단→질의 재작성→제한된 재검색을 수행하는 제어 루프다. 따라서 Hybrid와 양자택일 기술로 설명하지 않는다. 최신 통제 비교는 양쪽 모두 Hybrid를 강제하며,아래 과거 dense 비교와 구분한다.

## 최신: 동일 조건 Hybrid vs Hybrid+Agentic100시도씩 비교

[통제 비교 전체 결과·오류·비용·채택 판단](../agentic_rag/20261021-controlled-hybrid-v14/README.md). 같은 최종 프롬프트·Flash 모델·Hybrid 설정·환경에서 새200답변과Pro200판정을 완료했다. 정답89%→80%,이진 근거 충실성100%→99%,중앙값6.435→9.709초,p95 10.663→15.477초,모델+임베딩 추정/100시도$0.293046→$0.399767. Agentic이 기존 오답1건을 회복했지만 정답10건을 놓쳤다. **기존 Hybrid/no-reranker 유지·Agentic 운영 미채택**으로 판단했다. 구현·비교 실험 완료와 운영 적용X를 구분한다.

40질문/20사실그룹 반복 개발셋이며 독립100문항·사용자 성공률이 아니다. 같은 정적 답변 지침을 양쪽에 적용하고 Agentic의 동적 답변 지침은 제거했다. 충실성은 Pro 이진 판정으로 Ragas와 혼용하지 않는다. 모든 보류를 분모에 남겼고,요청 실패·출력 잘림은0건이었다. 아래 과거 dense 비교와 독립20문항 평가 기록은 서로 다른 평가 범위의 보존 자료다.

## 기존 실험 이력

| 실험 축 | 비교한 후보 | 근거와 판단 |
|---|---|---|
| 파서·청킹 | PyPDF/recursive, pdfplumber/page, Docling/page 및 다른 보존·청킹 조합 | [전체 코퍼스 조합](full_recipe_summary_v1.json), [통제 파서 실험](controlled_parser_summary_v1.json). 기존 PyPDF/recursive 유지. 전역 최적이라고 주장하지 않음 |
| 임베딩 차원 | Gemini embedding 768/1536/3072 | [차원 실험](dimension_full_summary_v1.json). 선택 namespace의 3072차원 유지, 다른 벡터 공간과 혼합하지 않음 |
| 검색 | Dense, BM25, Hybrid | [검색 모드 비교](search_modes_summary_v1.json). 개발40문항의 PyPDF/recursive 페이지 적중은75/27.5/80%, 핵심구절 적중67.5/25/75%. 후보 비교이며 독립 최종 품질 수치 아님 |
| 리랭킹 | 없음, FlashRank, Jev | [검색·Jev 결과](search_modes_summary_v1.json), [평가 상세](../../EVALUATION.md). Jev는 개발40문항에서800모델 호출, recall 증가의 불확실성과 비용·지연을 고려해 미채택. 기본 no-reranker 유지 |
| 검색 제어 | Hybrid 단일 검색, Hybrid+Agentic 평가·재작성·재검색 | [동일 조건100시도씩 통제 비교](../agentic_rag/20261021-controlled-hybrid-v14/README.md). 정답89→80%,충실성100→99%,중앙값6.435→9.709초,생성 추정 비용$0.293046→$0.399767. 기존 Hybrid/no-reranker 유지,Agentic 운영 미채택 |

### 기존 Ragas 비교: 동일 개발40문항

| 조합 | Ragas faithfulness | Ragas context recall | 보류 |
|---|---:|---:|---:|
| PyPDF/recursive + Hybrid + 리랭킹 없음 | 0.996875 | 0.7750 | 4/40 |
| Docling/page + Hybrid + 리랭킹 없음 | 0.964286 | 0.6000 | 11/40 |
| PyPDF/recursive + Hybrid + Jev | 0.968750 | 0.8125 | 2/40 |

원본은 [search_modes_summary_v1.json](search_modes_summary_v1.json).40문항/20사실그룹의 단일 개발 실행으로,100개 독립 표본 또는 새 성능 검증으로 확대하지 않는다. Jev의 context recall 차이 +0.0375에 대한 사실그룹 bootstrap95% 구간은 -0.125~0.2다. 근거는 있으나 명확한 우월성으로 단정할 수 없어 호출·지연 부담을 함께 고려했다.

## 선택된 기존 방식의 독립 평가

[독립 최종20문항](RAG_FINAL_EVALUATION_V1.md)의 선택 조합은 PyPDF/recursive + Gemini embedding3072 + Dense/BM25 Hybrid + no-reranker다. source-reviewed 정답19/20, strict source-page Recall@4 17/20, 대체 근거 판정 support19/20, Ragas faithfulness1.00/context recall0.95였다. 저메모리 원격 환경의 dense fallback은 Hybrid 실험과 구분한다.

## 과거 dense 비교: Agentic RAG

동일한 반복 개발100사례씩으로 기존 일반 dense RAG와 현재 v14 Agentic dense를 평가한다. 기존 일반 RAG100답변, 현재 후보의 이미 실행한23답변을 재사용하며 개별 보류·실패도 분모에 남긴다. Pro paired judge 정답/충실성, 보류율, 근거 페이지 적중, 재검색 비율, 요청 지연, 모델 사용 비용을 기록한다. **이 평가의 이진 충실성 판정은 Ragas 점수가 아니다.** Agentic의 Ragas 점수를 측정하지 않았다면 비워 두며 기존1.00과 직접 비교하지 않는다.

일반 RAG 기준선은 과거 실행이며 QA 프롬프트와 worker수가 다르다. 같은 질문·모델·corpus를 사용해도 순수한 Agentic 루프만의 인과적 ablation으로 해석하지 않는다. 기존 독립20문항과 이번 개발100시도도 합산하지 않는다. Agentic 후보가 개발40질문에 반복 튜닝된 이력을 공개한다.

### 100시도씩 최종 비교 완료

| 지표 | 일반 dense RAG | Agentic dense v14 |
|---|---:|---:|
| Pro 내용 정답률 |85%|88%|
| Pro 이진 근거 충실성 |99%|97%|
| 한국어 정답 |45/50|43/50|
| 정확한 무근거 보류 문구 |8/100|4/100|
| 근거 페이지 적중 |79%|78%|
| 정상 STOP 종료 확인 + 정답 |과거 미수집|84/100|
| 관측 p50/p95 |11.507/18.987초|15.469/25.737초|
| 알려진 생성 모델 토큰 비용/100시도 |$0.530120|$0.756793|

Agentic에는 외부 요청 실패2건, 출력 한도 도달5건이 있었다. 출력 한도5건 중4건은 핵심 사실이 맞아 내용 정답으로 채점됐지만 완결된 응답으로 보장할 수 없어 정상 종료 포함 정답84/100을 별도로 공개한다. 기존 기준선은 종료 메타데이터가 없어 이84%와 직접 비교하지 않는다. 모든 실패를 분모100에 남겼고, 채점 실패0건·생성 실패3건(일반1/Agentic2)의 판정도 기록했다.

**채택 판단: 기존 PyPDF/recursive +3072차원 +Hybrid/no-reranker 유지, Agentic 운영 미채택.** Agentic은 영어 내용 정답80→90%·보류 감소의 장점이 있었지만 한국어90→86%, 충실성99→97%, 근거 페이지79→78%로 일관된 우위가 없었다. 내용 정답88%도 사전95% 품질 기준에 미달했다. 관측 지연·호출 부담과 출력 완결성 한계까지 고려해 전체 서비스에 추가 루프를 켜지 않았다. 현재 선택된 Hybrid 조합 자체와의 통제 비교를 한 것처럼 설명하지 않는다.

**이력서/포트폴리오 표현:** “기존 Parser·Chunking·Embedding·Hybrid·리랭킹 실험에 Agentic RAG를 추가하고, 동일40질문 반복100시도씩을 실패 포함 평가했다. 내용 정답85→88%와 보류 감소를 확인했으나 한국어·충실성·출력 완결성 및 지연/비용의 trade-off를 근거로 기존 Hybrid/no-reranker를 유지했다.” 운영 적용 또는 독립100문항 우월성으로 표현하지 않는다.

전체200답변·200Pro 판정, 오류 사례와 비교 한계는 [완료 보고서](../agentic_rag/20261021-rag-vs-agentic-v14-complete100/README.md)에 보존했다. 이전 조기 중단 보고서는 당시 상태의 원본으로 유지하고 완료 결과로 연결한다.
