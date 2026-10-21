# 표 해석·부분 답변·필수 조건 보존 — 개발 중

상태: 후보 구현 완료, 새 실측 대기. 검증 키의 최소 임베딩 호출이 HTTP402 RESOURCE_EXHAUSTED로 실패했다. 사용자가 크레딧 또는 검증 키를 반영한 뒤 알려주기로 했다. 현재 전후 실측은 0건이며 품질·속도·비용 개선을 주장하지 않는다. 운영 기본 OFF 및 배포 보류.

## 변경

- Controller v2: 표 행·열·단위·범례·각주를 함께 읽고, 확인된 핵심과 미확인 추가 요구를 분리한다. 관련 없는 근거는 통과하지 않는다.
- 후보 recipe table-constraints-v3: sufficient로 판정된 근거에만 답변 지침을 전달한다. QA와 실제 DietTeam 검색 도구 모두 적용한다. 기존 v1 QA 기본 프롬프트는 유지한다.
- 필수 대상·적응증·예외·권고 강도·날짜/버전·계산식 출처와 변경 전후를 빠뜨리지 않도록 안내한다. 빈칸/절단만으로 없다고 단정하거나 다른 집단 값을 옮기지 않는다.
- 점수 게이트, 최초 근거 보존, 8문서/6000자, 2회 검색·2회 평가·기본35초·공유 예산 및 오류 시 보류는 유지한다.
- 비교 baseline은 a2ba3ba4의 근거 보존 v2 소스와 그 안의 v1 assessor로 고정한다. 후보 정책을 baseline assessor에 공통 주입하지 않는다.
- SDK 변환에서 누락되는 원본 usageMetadata.promptTokenCount를 비교 도구에서 관찰한다. 없으면 비용 미완료이며 바이트 프록시를 실제 비용으로 취급하지 않는다.

## 별도 개발셋

[12개 합성 개발 fixture](development/cases.json)는 기존 평가 40질문의 문구와 겹치지 않는다. 실제 의학 권고가 아닌 가상의 표·개정 메모로 메커니즘을 검사한다. 긍정 8개, 근거 부족 4개이며 모델 품질 검증은 실제 호출 후 판정한다. pytest mock 통과를 모델 품질 통과라고 기록하지 않는다.

## 고정 실측과 배포 조건

[cases.json](cases.json)은 기존 100시도와 바이트 동일하다. 개발40문항의 반복이며 독립100질문/사용자가 아니다. [protocol.json](protocol.json)에 검색·모델·A/B Pro 평가·비용 및 기존 배포 게이트를 고정했다. 정답률95% 및2%p개선, 충실도·근거·실패 비열등, 지연1.5배이내, 비용완료 및2배이내를 모두 통과해야 운영 적용한다. 402 상태로200회 호출해 무의미한 실패를 만들지 않는다.

완료 통보 후 최소 호출 → 개발셋 → 후보 동결 → 새 전후100시도씩 → 전체100쌍 Pro Batch → 게이트 판단 순으로 진행한다. 통과한 경우만 배포·실제 브라우저 검증한다. 실패 시 결과와 원인도 원본 그대로 남긴다. 운영 사용자 DB는 변경하지 않는다.

공식 근거: [Agentic RAG 평가/재작성 패턴](https://docs.langchain.com/oss/python/langgraph/agentic-rag), [임베딩 API의 usageMetadata](https://ai.google.dev/api/embeddings), [Gemini Batch 평가·별도 할당량](https://ai.google.dev/gemini-api/docs/batch-api).

## 로컬 검증 완료

전체 백엔드 1,512 passed, 기존 1 skipped, 3 deprecation warnings. 관련 37개 테스트 통과 및 새 실행 스크립트 py_compile 통과. 독립 정적 리뷰에서 추가 actionable finding 없음. 테스트는 외부 호출을 mock한 회귀 검증이며 실제 모델 품질 개선의 증거가 아니다. 코드·개발 fixture·프로토콜은 [skip render] 커밋으로 보존하고 운영 배포하지 않는다.
