# 원격 검색·하이브리드 120쌍 및 독립 메모리 검증

## 목적과 운영 격리

512MB Render에서 사용 중인 원격 dense fallback의 검색 근거 품질과 장시간 메모리를 점검한다. 이 실험은 **운영 API·Supabase·사용자 대화·식사·측정·전략을 읽거나 변경하지 않는다.** 별도 로컬 Python 프로세스가 공개 영양 문서의 기존 Pinecone namespace에 검색만 수행한다. `for_build=False` 경로라 인덱스 생성/업서트도 하지 않는다.

검증 프로세스에는 Gemini/Pinecone의 허용된 설정만 전달한다. Supabase URL은 `.invalid`, 키는 동작하지 않는 검증용 문자열로 덮고 DB URL을 비운다. `app.db`, `app.api`, `app.agents`, Supabase/psycopg import도 차단한다. 실제 키는 git-ignored `backend/.env.rag-validation`에만 두며 공개 자료에는 없다. LangSmith 입력 전송도 끈다. 결과에 사용자 건강 정보는 없다.

## 실행 환경 문제와 수정

1. Docker Linux engine 파이프의 sandbox 권한 오류 뒤 elevated version/image-list 요청이 각각30초 timeout이었다. [공식 Docker Desktop CLI](https://docs.docker.com/reference/cli/docker/desktop/start/)의 start명령은 이미 실행 중이라고 답했다. 다른 로컬 작업을 중단할 수 있는 엔진 재시작은 하지 않았다. 이를 Linux/Render 실험 완료로 포장하지 않는다.
2. 대안은 **Windows Job Object가 실제 강제하는512MiB private-commit 제한**의 독립 프로세스다. Linux cgroup과 다른 한도이므로 RSS512MiB 컨테이너와 동등하지 않다. production guard에 넘기는512MiB 입력은 평가 프로세스에서만 주입한다. [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects), [ProcessMemoryLimit의 정확한 의미](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information).
3. 첫 두 프로세스는 `OpenBLAS error: Memory allocation still failed after10 retries`로 시작 중 종료됐다. [NumPy 스레드 설정](https://numpy.org/doc/stable/reference/global_state.html), [OpenBLAS 시작 환경변수](https://www.openmathlib.org/OpenBLAS/docs/runtime_variables/)를 확인하고 검증 프로세스의 OPENBLAS/OMP/MKL 스레드를1로 제한했다. 재실행에서는 초기화가 통과했다. 운영 설정을 변경한 것은 아니다.
4. 실제 Gemini embedding 호출은 **HTTP402**, `Your prepayment credits are depleted`였다. 상속된 GOOGLE_API_KEY를 제거한 단일 확인도 같은402였다. [Google 공식 billing 문서](https://ai.google.dev/gemini-api/docs/billing#prepay)는 잔액0일 때402가 나고 충전 전까지 키가 중단된다고 설명한다. 사용자가 충전 없이 가능한 검증만 진행하도록 지정해 신규 답변 생성·독립 judge는 하지 않았다. [비식별 공급자 오류](provider_failure.json), [초기 실패](preflight_failures.json), [중단한 실시간 임베딩 검사](blocked-live-embedding-soak.json)를 보존한다.

## 동일 조건과 분모

- 사전 계획: [프로토콜·판정 기준](../superpowers/plans/2026-10-16-rag-memory-quality.md).
- 검토된 development40 질문(20 사실군, 한국어20/영어20)을3회 반복해 **조건별120건**, 총240건이다. 120개 독립 질문이나 실사용자120명으로 표현하지 않는다. final20/heldout20은 이 실험에 사용하지 않았다.
- 기존 active Gemini namespace,3072차원,4,139개 release 청크, k4/candidate20, no reranker, grounded threshold0.35를 동일하게 유지했다. 한국어 번역도 기존 검토 실험의 고정 번역을 양쪽에 동일하게 제공했다.
- 모델 잔액 문제를 우회해 새 답변을 만든 것이 아니다. 같은 `gemini-embedding-2`/검색 지시 형식으로 이미 생성된 질문 벡터60개를 파일 SHA-256·3072차원·유한값·정규화 검증 후 재사용했다. Pinecone 검색 자체는 새로 실행했다. [고정 질문·번역](frozen.json), [재현용 벡터 압축](frozen-query-vectors.json.gz). 임베딩 API·번역·답변 생성 시간은 아래 검색 시간에 포함되지 않는다.
- 원격 조건은 실제 no-load guard를 적용해 `dense_fallback`을 확인한다. 하이브리드는 별도1.5GiB 프로세스에서 Kiwi/BM25를 실제 로드하고 `hybrid`를 확인한다. 하이브리드 로드 실패를 fallback 성공으로 계산하지 않는다. 두 조건은 메모리 제한이 다르므로 서비스 전체 성능의 공정한 인프라 비교는 아니다.
- 두 동시 요청, 반복별 교차 순서/역순을 사용했다. BM25 초기화는 요청 시간 밖이다. 실패·timeout은 분모120에 남기며 judge 미실행은 `null`로 기록한다. [엄격 집계](summary.json).

## 검색 근거 품질 결과

| 지표 | 원격 dense fallback | 기존 하이브리드 |
|---|---:|---:|
| 실제 검색 완료 / 시도 |120/120|120/120|
| 실패·timeout |0/120|0/120|
| 정답 근거 페이지 hit@4 |90/120 (75%)|96/120 (80%)|
| 정답 발췌 포함 |90/120 (75%)|93/120 (77.5%)|
| 한국어 페이지 hit@4 |45/60 (75%)|54/60 (90%)|
| 영어 페이지 hit@4 |45/60 (75%)|42/60 (70%)|
| MRR (문서/페이지 중복 제거) |0.625|0.5604|
| grounded gate 통과 |120/120|120/120|
| 검색 구간 p50/p95 |0.420/0.540초|0.490/0.725초|
| 독립 답변 정확성·충실성 |미검증 (402)|미검증 (402)|

원격 검색은 전체 페이지 적중이 **5%p 낮고**, 특히 한국어에서15%p 낮았다. 사전의 전체 개발 점검 한계(-5%p)에는 걸쳐 있지만 **동등 품질·통계적 비열등성·임상 정확도를 입증하지 않는다.** 20개 사실군의 반복이라 독립 표본120개로 계산한 신뢰구간/p값을 제시하지 않는다. grounded100%도 정답100%를 의미하지 않는다.

차이4질문 중 한국어3개(`energy_balance-ko`, `eer_rounding-ko`, `activity_reference-ko`)는 하이브리드가 KDRI의 정확한 표현/기준 페이지를 가져왔고 dense는 관련된 다른 에너지 표 페이지를 가져왔다. 영어 `comorbidity_screen-en`은 dense만 해당 한국어 지침 페이지를 가져왔으며 하이브리드 RRF가 다른 문서를 올렸다. [질문별 실제 출처 차이](summary.json). 단순히 모든 질문을 BM25로 바꾸는 것도 해답은 아니다. 근거 페이지를 찾지 못한 경우 새 수치 변경을 보류하는 경계는 유지해야 한다.

이 비교만으로 기존20문항 Ragas/정답률을 원격 fallback에 전용하거나, 지연이0.07초 줄었다고 실제 상담40초가 해결됐다고 표현하지 않는다. 이 작업에서는 운영 검색 정책을 변경하지 않았다. 한국어 정확 용어를 보완하는 가벼운 키워드/원격 sparse 후보는 향후 별도 개발셋에서 설계하고, 같은100건 이상 비교와 메모리 검증을 거쳐야 한다.

별도 코드 검토는 운영 DB 접근 경로가 없음을 확인하고, 양쪽 모두 실패해도 상대 차이0으로 통과할 수 있는 집계 결함을 발견했다. 이를 실제120실패×2 fixture로 먼저 실패시킨 뒤 최소100완료·조건별 실패율≤2% 조건을 추가했다. 현재240건 완료 결과는 이 수정으로 달라지지 않는다. 최종 백엔드 전체 회귀 **1380 passed/기존1 skipped**, 새 도구 테스트9개 통과. 프론트·운영 코드 변경은 없어 새 배포/프론트 테스트는 이 작업 범위에 없다.

도구의 남은 작은 한계: frozen identity가 corpus/설정 전체를 자동 연결하거나 soak identity를 자동 대조하지는 않는다. 이번 여섯 파일의 cached/retrieval-only·모델·namespace·조건별 메모리 설정과 corpus/vector 해시는 직접 검사해 [실험 환경 기록](experiment_identity.json)에 남겼다. 다른 실험의 파일을 임의로 섞어 재집계하면 안 된다.

## 장시간 메모리 검사

2026-10-16 **17:14:43~19:14:43 KST**, monotonic 기준 **7,200.016초**를 실제 실행했다. 20초 주기·동시2개 원격 검색, 약0.1 retrieval/초의 낮은 부하다. [전체360개 관측·원본](memory-soak.json), [최종 엄격 판정](summary.json).

| 항목 | 관측 결과 |
|---|---:|
| 완료 / 시도 |720/720|
| 검색 실패·timeout |0/720|
| MemoryError·프로세스 비정상 종료 |0 · 종료 코드0|
| 메모리 관측 수 |360|
| 프로세스 peak RSS |131.13MiB|
| 최대 관측 private commit |102.35MiB|
| warm-up 뒤 첫15분 private 중앙값 |100.19MiB|
| 마지막15분 private 중앙값 |102.35MiB|
| 중앙값 증가 |**2.16MiB**|
| Kiwi/BM25 로드 |전 관측에서 없음|

사전의2시간·최소300관측/600요청·실패율≤1%·관측 private<512MiB의90%·중앙값 증가≤32MiB 조건을 통과했다. private 메모리는 **조금 증가했으며 완전히 동일하지 않다.** 실제 강제된 것은 Windows의 private-commit512MiB 한도다. 관측 사이의 순간 private peak와 Linux cgroup/RSS를 동일시하지 않는다. Raw 프로세스 판정 뒤 최종 집계에서 최소600요청 조건도 확인했다. 분석 코드 검토 때 지적된 soak identity 연결은 이번 frozen identity와 직접 대조해 일치를 확인했다. 검증용 키 파일은 종료 후 삭제했다.

이 결과는 Windows surrogate·고정 벡터·낮은 부하의 RAG 구성요소 검사다. **Linux Render·Gemini 클라이언트 생명주기·전체 API·DB·대규모 동시성·모든 메모리 누수 부재는 입증하지 않는다.** 식품 DB 영양값 정확도 검사도 아니다. 운영 코드를 변경하거나 실험을 위해 운영 배포를 교체하지 않았다.

## 재현

키를 채팅/소스에 넣지 말고 검증용 env에 Gemini/Pinecone 설정만 둔다. 루트에서 프로젝트 venv를 사용한다. 벡터 압축을 `backend/artifacts/dimension-full-dev-v1/queries3072.json`으로 풀면 원래 SHA-256 `52cca3fc4b4e06fe90e45654fd2f99552c5efaaa7f2460775d78dc218a653a8a`와 일치해야 한다. 기존 결과 폴더를 덮어쓰지 말고 새 폴더에 frozen.json을 복사한다.

```powershell
backend\venv\Scripts\python.exe -X utf8 backend/scripts/eval/rag_memory_quality.py quality --output <새폴더> --frozen <새폴더>/frozen.json --mode dense_fallback --repeat 0 --cached-vectors --retrieval-only
backend\venv\Scripts\python.exe -X utf8 backend/scripts/eval/rag_memory_quality.py quality --output <새폴더> --frozen <새폴더>/frozen.json --mode hybrid --repeat 0 --memory-mib 1536 --cached-vectors --retrieval-only
# repeat1/2도 양쪽 수행. 기존 결과를 덮어쓰지 않는다.
backend\venv\Scripts\python.exe -X utf8 backend/scripts/eval/rag_memory_quality.py soak --output <새폴더> --frozen <새폴더>/frozen.json --seconds 7200 --cached-vectors
backend\venv\Scripts\python.exe -X utf8 backend/scripts/eval/analyze_rag_memory_quality.py --folder <새폴더>
```
