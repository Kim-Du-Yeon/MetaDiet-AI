# 통제 비교 방법

기존 Hybrid RAG와 Hybrid+Agentic RAG를 비교하는 읽기 전용 실험이다. 운영 DB·식사 기록을 읽거나 수정하지 않는다. 기존 실행의 답변·채점은 새 비교에 섞지 않는다.

- 같은 동결100사례: 한국어50/영어50,40개 질문·20개 사실그룹 반복. 독립100문항 또는 실제 사용자 정확도가 아니다. 이전 Agentic 개발에 사용된 질문이므로 개발셋에 대한 탐색적 비교다.
- 동일 프로세스·Python·패키지·코퍼스·namespace,3개 pair worker. 사례별 AB/BA 교대로50회씩. BM25와 vector store를 먼저 초기화하고 타이머를 시작한다. 전용 무부하 장비가 아니며 오프라인 테스트가 일부 구간에 동시 실행됐다. 두 조건이 같은 환경을 공유하고 순서를 균형화했지만 운영 부하·cold start 성능으로 일반화하지 않는다.
- 두 조건 모두 Dense+Kiwi BM25+RRF Hybrid를 강제한다. k4/candidate20,리랭커 없음. dense fallback을 Hybrid 성공으로 인정하지 않는다.
- 최종 QA 프롬프트와 정적 ANSWER_GUIDANCE를 양쪽에 동일하게 사용한다. Agentic이 만든 동적 답변 지침은 제거한다. 근거 포맷도 같은 `_scoped_context`(최대8개/6000자)다. Agentic의 근거 선택·인접 청크·재검색만 다르다. 완전한 운영 Agentic 전체 패키지 또는 루프의 각 구성요소별 독립 ablation은 아니다.
- 답변 모델 gemini-3.8-flash,temperature0,thinking LOW,4096출력 토큰. 번역은 동일 Lite256,Agentic 제어자는 Lite512. max2검색/35초 루프 제한,요청90초. SDK 총 시도1회·모델 재시도0회로 숨겨진 재시도를 제한한다.
- 두 조건 모두 finish_reason과 원시 임베딩 사용량을 수집한다. LLM을 호출하지 않은 grounded 가드 보류는 NOT_CALLED_GUARD로 구분한다.
- 개별 오답·보류·출력 잘림·시간 초과를100시도 분모에 유지한다. 정답률100%를 완주 조건으로 삼지 않는다. 인증·크레딧·사용량 정산 불능 같은 캠페인 실행 불능만 별도 확인한다.
- Pro paired judge가 조건 이름을 가린 A/B 답변을 독립 평가한다. A/B 배치도 균형화한다. 같은 GOLD,각 답변 자체의 문맥,같은 rubric·2048/LOW·Native Batch를 사용한다. 두 조건 모두 새로 채점하며 이전 점수를 재사용하지 않는다. 이진 충실성 판정은 Ragas 점수가 아니다.
- 정답률은 GOLD 필수 사실·수치·적용 범위 충족,충실성은 전달된 문맥의 지지 여부다. 정답+STOP을 별도로 집계해 잘린 답변을 완결된 정답으로 혼동하지 않는다. 페이지 적중은 사전에 지정된 source/page 일치이며 대체 근거도 오답처럼 보일 수 있어 정답률과 동일하지 않다.
- 지연은 검색·제어·생성 전체 요청 시간이며 채점은 제외한다. p95는 nearest-rank,실패 시간도 포함한다. 비용은 provider 사용 토큰×동결된 요율 추정이며 청구서 실결제액이 아니다. 추론 토큰을 포함하고 임베딩·채점 비용을 분리한다. 미확인 사용량은0으로 간주하지 않는다.
- 기존 누적 비용 장부를 유지한다. 사용자의 기존 $5 중단 조건 철회 이후,이번 명시적 유료 실험 프로세스에만 $15 안전 한도를 적용한다. 운영 설정·기본 $5 설정을 바꾸지 않는다.

실행:

```powershell
backend/venv/Scripts/python.exe backend/scripts/eval/benchmark_controlled_hybrid.py --output docs/agentic_rag/20261021-controlled-hybrid-v14 --defer-judge --allow-paid --budget-ledger tmp/eval-budget.sqlite
backend/venv/Scripts/python.exe backend/scripts/eval/grade_controlled_hybrid.py pairs --directory docs/agentic_rag/20261021-controlled-hybrid-v14 --job docs/agentic_rag/20261021-controlled-hybrid-v14/grading.json --chunk-size 100 --allow-paid --budget-ledger tmp/eval-budget.sqlite
# 이후 같은 job에 advance 반복: 생성 재실행 없음
backend/venv/Scripts/python.exe backend/scripts/eval/summarize_controlled_hybrid.py --directory docs/agentic_rag/20261021-controlled-hybrid-v14
```

API 키는 git-ignored backend/.env만 참조하며 파일·로그·프로토콜에 싣지 않는다. 같은 output에 생성 재실행은 거부한다.
