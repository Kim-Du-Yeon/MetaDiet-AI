# Agentic RAG 비교 · 2026-10-20

**판정: 운영 적용 보류.** 평가·질의 재작성·재검색 루프를 구현했지만 사전 게이트를 통과하지 못했다. `AGENTIC_RAG_ENABLED=false` 유지, GitHub 반영은 `[skip render]`로 자동 배포도 건너뛴다. 후보의 공개 배포·실제 브라우저 검증은 미실시이며 기존 공개 버전을 유지한다.

## 동일 조건100시도씩

| 지표 | 기존 검색 | Agentic 후보 |
|---|---:|---:|
| 시도 |100|100|
| 생성 완료 |99|100|
| 외부 호출 실패율 |1%|0%|
| 중앙값 |11.507초|14.370초|
| p95 |18.987초|22.402초|
| 정답 근거 페이지 적중 |79/100|76/100|
| 알려진 모델 토큰 비용 추정 |US$0.53012025|US$0.57199950|
| 임베딩 바이트 기반 상한 대용치 |US$0.00324120|US$0.00382220|
| 동일 설정 Pro 평가 완료 |50/100|50/100|
| 최종 답변 품질 개선 |미확정|미확정|

**개발40질문 반복100시도(40×2+앞20)**이며100개 독립 질문이나 실제 사용자 결과가 아니다. EN/KO 각50시도, 원문 질문·답변 프롬프트·모델·namespace·k4·no reranker 고정, 조건 순서 교대, 로컬3worker. 검색부터 QA 생성까지의 지연이며 Pro 평가·DB·인증·브라우저 대기는 제외했다.512MiB 운영의 remote dense fallback에 해당하는 dense-only 범위이며 대형 호스트의 hybrid와 같다고 주장하지 않는다. 운영 데이터 쓰기/인덱스 변경은 없었다.

실패·타임아웃은 분모100에 유지했다. 기존 ag-025 GoogleAPIError도 교체하지 않았다.1건/0건으로 일반적인 신뢰성 개선을 보장하지 않는다. 근거 페이지 적중은 source-reviewed alternative page 일치이며 답변 정확도 자체가 아니다. 최신 사용자 기록은 이 문헌 QA 경계 실험의 대상이 아니므로 검증했다고 주장하지 않는다.

## 동작과 미채택 원인

후보100회 중14회가 두 번째 검색을 수행했다.96회는 충분 판정,4회는2회 상한 종료였다. 추가 판단·재검색으로 지연과 알려진 모델 비용이 증가했고 근거 페이지 적중은 낮아졌다. 관련성 판정만으로 최종 답변의 핵심 수치·대상·조건 완전성을 보장하지 못했다. 확인 가능한 정의와 근거 없는 특정 수치를 함께 묻는 경우 전체 보류도 발생했다.

향후 후보는 원문 결과와 재검색 결과의 합성, 질문 요소별 충족도 및 부분 답변 구분이다. 이번 결과를 보고 같은 평가셋에 맞춘 뒤 독립 성능이라고 주장하지 않는다. 별도 개발셋에서 보강하고 새 동결100시도씩으로 재검증한다.

## 실패 조사·수정·재검증

- **평가자 출력 잘림:** 최초 Pro512 output-token 한도가 추론으로 소진돼 parsed=None이 발생했다. [공식 문서](https://ai.google.dev/gemini-api/docs/thinking)는 추론과 최종 출력이 한도에 함께 포함됨을 설명한다. 양쪽 저장 답변 전체를2048/low 동일 설정으로 재평가하도록 수정했다. 답변 재생성·실패 표본 교체는 하지 않았다.
- **평가자429:** `GenerateRequestsPerDayPerProjectPerModel`, 일일250회 한도를 확인했다.402 크레딧 소진이 아니다. [사용 한도 문서](https://ai.google.dev/gemini-api/docs/rate-limits)에 따라 분당/일일 제한을 구분했다. 복구 평가 프로세스는 중단했고 향후 runner에는 일일 quota 회로 차단을 추가했다. 이미 로드된 원래 runner의 후반 평가429는 원본에 남아 있다.
- **품질 평가 불완전:** 복구 평가 정상 완료는 각각50건이다. 기존은 평가오류15·미시도34·생성실패1, 후보는 평가오류16·미시도34. 미시도는 API 실패를 꾸민 것이 아니다. `quality-status.jsonl`에 전체 상태를 명시했다. summary의 correctness/faithfulness는null이며 미평가를 실제 오답률로 제시하지 않는다. 보수적 하한만 별도 필드다.
- **리뷰 수정:** 평가 범위 밖 발췌가 노출될 가능성을 막아 정확히 평가한 발췌만 메타데이터와 함께 넘긴다. 검색/컨트롤러 오류·타임아웃은 근거 부족과 구분하고 다음의 서로 다른 질의도 억제한다. 실패 테스트 재현→수정→회귀→재리뷰했다.
- **테스트 환경:** Windows 공용 임시 폴더 권한으로38 fixture error가 발생했다. 테스트를 제거하지 않고 작업공간 내 `--basetemp`로 해결했다. 기존 skip1개는 유지했다.

[구현 검증](implementation-verification.json) · [quota 진단](quota-diagnostic.json) · [평가자 복구 규약](judge-recovery-protocol.json) · [컨텍스트 호환성](context-compatibility.json).

## 비용·게이트

모델 비용은 실제 usage_metadata와 고정 단가 기반 추정이며 청구서가 아니다. 임베딩 SDK 응답 metadata=None이라 과금 토큰을 확인하지 못했다. 입력 UTF8 바이트의 보수적 대용치는 실제 임베딩 과금으로 합치지 않는다. 오류의 알 수 없는 과금도0으로 확정하지 않는다. Pinecone/호스팅은 제외했다.

최초 평가자 알려진 비용은 기존US$0.679814/후보US$0.649814, 복구 평가자는US$0.383308/US$0.374106으로 서비스 비용과 별도다. 총 알려진 모델·평가자 비용US$3.189162는 최종 청구액이 아니다.

사전 게이트: 정답률≥95% 및≥2%p 개선, 근거 적중·실패율 비열등, p50/p95≤1.5배, 완전한 비용 비교≤2배. **근거 적중 비열등·품질 평가 완료·비용 완전성 미충족**으로 활성화하지 않았다. 지연이 허용 상한 안이라는 이유로 개선을 주장하지 않는다.

## 남은 재검증

Pro 일일 한도 초기화 후 **저장한200답변**을 동일2048/low로 전부 재평가할 수 있다. 모델·한도·키를 바꾸지 않고, 기존 파일을 덮어쓰지 않는다.

```powershell
backend/venv/Scripts/python.exe backend/scripts/eval/rejudge_agentic_rag.py --output docs/agentic_rag/20261020 --grades-name judges-after-reset.jsonl
backend/venv/Scripts/python.exe backend/scripts/eval/analyze_agentic_rag.py docs/agentic_rag/20261020 --grades-name judges-after-reset.jsonl
```

재평가가 근거 페이지 적중 저하를 자동으로 해결하지는 않는다. 공개 활성화 전에는 개선 후보의 별도100쌍 비교와 실제 브라우저 검증이 남아 있다.

## 원본·재현 범위

[사전 계획](../../plans/2026-10-20-agentic-rag.md) · [동결 규약](protocol.json) · [고정 사례](cases.json) · [원본200시도](attempts.jsonl) · [복구 평가 실제 호출](recovered-judges.jsonl) · [전체 품질 상태](quality-status.jsonl) · [집계/게이트](summary.json) · [모델·프롬프트](identity.json) · [코퍼스 해시](corpus-identity.json).

생성 실험 중 별도 리뷰로 발췌 제한·오류 분류·추적 메타데이터를 보강했다. [생성 당시 컨트롤러](controller-experiment-source.py.txt)와 [runner](benchmark-experiment-source.py.txt)를 보존한다. 현재 안전성 수정본의 새100쌍 성능 실험이라고 표기하지 않는다. 비어 있지 않은 후보 context96개의 입력 호환성은 별도 확인했다.

공개 기존 버전 확인: API health 재확인200, API·웹 commit `7dfbda0f14e556c7def56a16138597db68d123d5`. 최초 API health30초 타임아웃은 보존했고 원인은 확정하지 않았다. 후보의 배포/브라우저 검증 결과로 취급하지 않는다. [원본](public-baseline.json).
