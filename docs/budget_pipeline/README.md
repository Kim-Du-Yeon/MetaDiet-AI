# 실행 예산 저장 병목: PostgreSQL pipeline 실험

2026-10-14. 기존 공개100건에서 실행 예산 저장 중앙값2.455초를 확인하고 내부 단계를 분석했다. SQL1.053초, 연결 준비1.047초, 커밋0.354초다. 각 값은 요청 내 누적 단계의 중앙값이며 중앙값을 더해 총시간을 재구성하지 않는다. [원본 해시와 단계 집계](../compact_coaching/baseline_stages.json).

## 원인과 변경 하나

기존 방식은 `SET LOCAL` → INSERT → SELECT FOR UPDATE → UPDATE를 순차 왕복한다. SQL 구간이 가장 크고 연결 준비에도 pool health check와 트랜잭션 준비가 포함돼 있다. 이를 pool checkout과 setup으로 추가 분리했다.

[psycopg 공식 pipeline 설명](https://www.psycopg.org/psycopg3/docs/advanced/pipeline.html)에 따라 같은 트랜잭션에서 명령을 묶는다. 읽기 결과가 필요한 SELECT에서 결과를 받고, UPDATE는 pipeline 종료 시 동기화한다. **동기화와 커밋이 성공해야 예약 완료를 반환**한다. DB row lock, 호출 상한, 재시작 후 카운터, 사용자/run 범위, 최신 기록 조회와 모델 프롬프트는 바꾸지 않는다. 새로운 운영 DB 마이그레이션은 없다.

`BUDGET_PIPELINE` 기본값은 실험 중 false다. pipeline의 SQL enqueue 시간은 실제 서버 실행 완료 시간이 아니므로 기존 SQL 시간과 직접 비교하지 않는다. 채택은 커밋까지 포함한 `budget_storage`와 전체 시간으로 판단한다.

## 동일 조건 100쌍

- 실제 Gemini3.8 Flash/low와 실제 PostgreSQL 예산 저장을 사용한다. 일반 사용자·식사·목표 데이터는 합성값으로 대체한다.
- 동일한4개 질문×5개 현재 상태×5회, 조건별100건이다. 이전 대화300/2200과 다른 현재값으로 최신 기록 반영을 검증한다. 100명의 독립 사용자가 아니다.
- 매 쌍마다 기존/후보 순서를 교대한다. 실패를 제거하지 않고 기록한다. 공개 서버의 네트워크·checkpointer·SSE 비용은 포함하지 않으므로 공개 응답시간으로 주장하지 않는다.
- 평가용 비공개 스키마에 동일 예산 테이블 구조를 만들며 운영 사용자 FK는 연결하지 않는다. 종료 시 평가 스키마를 삭제한다.
- 사전 기준: 저장 중앙값20% 이상 감소, 전체 중앙값5% 이상 감소, p95 악화10% 이내, 완료·최신값·미저장·자동 품질 항목 비악화. 모두 충족해야 활성화한다.

## 100쌍 측정 결과와 결정

| 지표 | 기존100건 | pipeline100건 |
|---|---:|---:|
| 예산 저장 중앙값 | 380.64ms | 275.47ms |
| 예산 저장 p95 | 430.17ms | 304.29ms |
| 전체 응답 중앙값 | 3,966.23ms | 3,940.20ms |
| 전체 응답 p95 | 6,188.70ms | 6,213.39ms |
| 완료·최신 수치 반영 | 각각100/100 | 각각100/100 |
| 식사/제안 저장 없음 | 100/100 | 100/100 |
| 최초 품질 판정 완료·5항목 각각 통과 | 97/100 | 98/100 |
| 실패 항목 재평가 후 5항목 각각 통과 | 100/100 | 100/100 |

**저장 단계는27.6% 개선됐으나 전체 중앙값 감소는0.7%로 사전5% 기준에 미달했다.** 따라서 후보는 기본 비활성으로 유지한다. 공개2.46초와 이번381ms는 측정 위치·실행 경로·표본이 다른 결과이며, 2.46→0.275초 개선으로 표기해서는 안 된다. 이번 비교에서 전체 시간은 여전히 모델 처리의 영향이 커서 저장 단계 개선만으로 충분한 전체 개선이 입증되지 않았다. 공급자 변동과 네트워크가 각각 차지한 원인은 확정하지 않았다.

기존 방식의 pool checkout 중앙값53.29ms, SET LOCAL/트랜잭션 준비105.43ms, SQL163.19ms, commit57.49ms로 세분화했다. 후보의 SQL 구간57.01ms와 commit 구간109.80ms에는 동기화 시점 이동이 포함돼 개별 구간의 감소를 그대로 성능 향상이라고 하지 않는다. **커밋까지 포함한 저장 총시간** 감소가 검증 지표다.

### 안전성

실제 DB에서 두 조건 모두12개 동시 예약 중5개 성공·7개 상한 차단, 예산 객체 재생성 후 상한 유지, SQL 오류 시 INSERT 롤백을 확인했다. [별도 안전성 결과](safety.json). 비교 실행 전 같은 안전 검사를 다시 수행한다.

별도 [취소 검증](cancellation.json)에서 실행 중인 DB 작업을 취소한 뒤 INSERT가 롤백됐고 pool에서 다시 조회할 수 있음을 두 조건 모두 확인했다. [공식 취소 문서](https://www.psycopg.org/psycopg3/docs/advanced/async.html#interrupting-async-operations)에 따라 취소 예외 전달만 믿지 않고 DB 결과를 확인했다. 평가용 스키마는 모두 정리했다. 강제 프로세스 종료나 DB 단절은 별도의 정리가 필요할 수 있다.

전체 백엔드 회귀 **967 passed, 기존1 skipped**, 관련 동기화·판정·초기화 회귀도 통과했다. psycopg3.3.4, psycopg_pool3.3.1, libpq18.3에서 pipeline 지원을 확인했다. 프론트 변경은 없어 프론트 테스트·빌드는 재실행하지 않았다.

### 재현

```powershell
backend\venv\Scripts\python.exe backend/scripts/eval/budget_pipeline100.py
backend\venv\Scripts\python.exe backend/scripts/eval/quality100.py paired --folder docs/budget_pipeline
backend\venv\Scripts\python.exe backend/scripts/eval/summarize_budget_pipeline100.py
```

[측정 원본](paired.json) · [블라인드 자동 품질](paired_quality.json) · [판정](summary.json) · [작업 기록](WORK_LOG.md)

자동 품질은 관련성·실행 가능성·섭취 사실 비조작·허위 저장 주장 없음·간결성이다. 단일 자동 judge 결과이며 인간·임상 검증이 아니다. 날짜 변경은 합성 현재 상태로 시험하고 실제 자정 경과를 관찰하지 않는다.

코드 검토에서 계측 누락을 무시하고 중앙값을 계산하거나 두 조건의 품질 판정이 모두 실패했는데도 비악화로 판단하는 허점을 발견했다. 실패 테스트로 재현한 뒤 **100건의 저장 계측과 100건의 성공한 judge 판정**을 각 조건에 요구하도록 보완했다. 실패 원본은 삭제하지 않는다.

### 품질 평가 서비스 오류

최초 평가 중 한 묶음5건이 `GoogleAPIError`, 코드`504`로 판정되지 않았다(기존3건·후보2건). [공식 오류 문서](https://ai.google.dev/gemini-api/docs/api-errors)는504를 deadline 초과로 분류하며, [공식 문제 해결](https://ai.google.dev/gemini-api/docs/troubleshooting)은 일시적5xx에 제한된 지연 재시도를 안내한다. 전체 평가 후 실패5건만 `quality100.py paired --folder docs/budget_pipeline --retry-failed`로 별도 재평가한다. 최초 실패는 채택 판정과 원본에서 그대로 유지한다. 뒤따른 SDK coroutine 경고가504 원인이라는 근거는 없으며 운영 timeout은 변경하지 않았다.

[재평가 원본](paired_quality_retry.json)의5건은 모두 판정 완료·5개 품질 항목 통과였다. 원본 응답 파일의 SHA256과 최초 실패 index 집합이 일치하는지 확인했다. 최초 판정은 기존97/100·후보98/100으로 유지하고, 재평가를 포함하면 두 조건 모두100개 고유 답변의 품질을 확인한 것이다. 재평가가 속도 채택 실패를 뒤집지는 않는다. `summary.json`의 자동 채택 판정은 최초 실패도 계속 반영한다.
