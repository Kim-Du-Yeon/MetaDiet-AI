# 식사 변경 응답으로 집계·버전을 함께 반환 (2026-10-19)

## 문제와 개선

기존 화면은 수정·삭제 후 일별/월별 캘린더를 병렬 조회하고, 세션 복원을 추가 조회해 상단과 대화를 갱신했다. 한 동작에 변경 요청을 포함해 HTTP 요청 4개가 필요했고 서로 다른 시점의 값이 잠시 섞일 수 있었다.

새 클라이언트는 `include_snapshot`을 요청한다. 서버는 PostgreSQL SERIALIZABLE 트랜잭션에서 기록 소유권과 기존 기록 버전을 확인하고, 수정·삭제 및 일/월 캘린더·오늘 집계·대화의 수정/삭제 안내를 함께 계산한다. 트랜잭션 커밋에 성공한 후 `sync` 응답을 반환한다. 새 경로에는 세션 체크포인트 복원이나 모델 호출이 없다. 정상 응답이면 프론트는 후속 재조회 없이 캘린더·상단·대화에 적용한다. 구버전 응답이면 기존 재조회 경로를 유지한다.

쓰기 후 집계 읽기·검증 실패는 해당 변경까지 롤백한다. 변경 결과가 네트워크에서 유실되는 경우까지 자동 재시도를 안전하다고 간주하지는 않는다. 성공을 확인하지 못하면 재조회 안내를 제공한다.

## 버전과 동시성

- `record_version`: 분량·영양값·음식·날짜 등 기록 내용의 SHA-256 지문. 초기 캘린더 조회에도 제공하고 수정·삭제 시 서버에서 다시 비교한다. 이전 화면의 값이면 409로 거절한다. 구버전 클라이언트가 버전을 보내지 않는 경로는 유지된다.
- `sync.version`: 집계 스냅샷 내용 지문. 전역 단조 증가 순번이 아니며 hash의 대소로 신구를 판단하지 않는다.
- 브라우저의 요청 시작 순번·로그인 사용자·대화 ID를 확인해 오래된 응답 적용을 막는다. 변경 중에는 탭과 날짜 이동을 잠시 막아 다른 작업의 상태를 덮어쓰지 않도록 한다. 요청 실패 시 해제하고 재조회 선택권을 제공한다.
- SERIALIZABLE 충돌·데드락은 409로 처리한다. 무조건 덮어쓰거나 자동으로 쓰기를 반복하지 않는다.
- 다른 기기에 변경 이벤트를 보내는 구독은 이번 범위가 아니다. 응답은 트랜잭션이 읽은 일관된 상태이며, 그 뒤 다른 기기에서 생긴 변경까지 영원히 최신임을 보장하지 않는다.

## 재현과 격리

`backend/scripts/eval/benchmark_intake_snapshot.py`는 무시되는 `backend/.env.intake-validation`의 전용 DB URL만 읽는다. 127.0.0.1:55439 / `metadiet_intake_validation`만 허용하고 앱 환경도 테스트 값으로 명시한다. 실제 PostgreSQL 테이블과 트랜잭션을 사용하며 API 인증·Supabase REST 전달·체크포인터는 로컬 어댑터/합성 경계로 대체한다. 운영 데이터·모델은 호출하지 않는다.

동일한 동결 120사례를 조건별로 실행한다. 정상 사례 100개는 오늘/이전 달의 수정·삭제를 포함한다. 나머지 20개는 다른 사용자 5개, 오래된 버전 5개, 쓰기 후 DB 읽기 실패 5개, 쓰기 전 HTTP ReadTimeout 주입 5개다. 조건 순서를 사례별로 번갈아 실행하고 실패·타임아웃을 모두 분모와 지연 분포에 유지한다. HTTP 요청마다 동일한 35ms 합성 지연을 추가한다. **실제 운영 네트워크·사용자 평균·브라우저 paint 시간 측정이 아니다.** 기존 비교 경로는 현재 서버의 호환 경로와 기존 4요청 흐름이며 과거 배포 바이너리 전체를 재현한 것은 아니다.

실행:

```powershell
backend\venv\Scripts\python.exe backend/scripts/eval/benchmark_intake_snapshot.py
backend\venv\Scripts\python.exe backend/scripts/eval/check_intake_snapshot_transactions.py
```

원시 [고정 사례](cases.json), [최종 240회 로그](report.json), [초기 Repeatable Read 실험](preliminary-repeatable-read.json), [SERIALIZABLE 재검사](serializable-recheck.json), [동시 수정·롤백 기능 검사](transaction-checks.json)를 구분해 보관한다. 반복 실험을 하나의 더 큰 독립 표본으로 합치지 않는다.

## 최종 결과: 조건별 120건 (총 240건)

| 지표 | 기존 4요청 경로 | 새 스냅샷 경로 |
| --- | ---: | ---: |
| 전체 시도(실패 포함) | 120 | 120 |
| 데이터 준비 지연 p50 | 627.438ms | 103.578ms |
| 데이터 준비 지연 p95 | 772.977ms | 157.741ms |
| 정상 사례의 HTTP 요청 | 4 | 1 |
| 정상 수정·삭제 집계/대화 정합성 | 100/100 | 100/100 |
| 전체 계약 검사 통과 | 105/120 | 115/120 |
| 기존 합성 기록 보존 | 120/120 | 120/120 |
| DB 실패 또는 timeout | 10/120 | 10/120 |

전체 계약 검사에는 완료되지 않는 timeout 5건도 실패로 포함했다. 나머지 차이는 오래된 기록 버전 5건의 거절과, 쓰기 후 읽기 실패 5건의 롤백이다. 기존 경로는 버전을 강제하지 않았고 쓰기와 후속 조회가 분리돼 있었다. 새 경로는 모두 거절/롤백했다. DB 실패 5건과 timeout 5건은 주입한 장애이며 자연 발생한 운영 장애율이 아니다. 정상 100건은 양쪽 모두 정합했다.

추가 실제 PostgreSQL 기능 검사에서 같은 기록 동시 수정 10쌍은 각각 한 요청 성공·한 요청 409였고 저장 값과 성공 응답 집계가 일치했다. 쓰기 뒤 스냅샷 계산 실패도 롤백됐다. 이 10쌍을 별도 성능·정확도 비교 표본으로 주장하지 않는다.

최종 백엔드 전체 1,444 passed / 기존 1 skipped, 프론트 전체 121 passed / 34 suites, 프로덕션 빌드 통과. 지연은 합성 환경 결과로, 이전 실험과 합산하거나 공개 서비스 p95 개선율로 제시하지 않는다.

## 실패와 해결 과정

- 기존 전용 Render 검증 DB 연결은 OperationalError, Docker는 엔진 미기동/기동 대기로 사용할 수 없었다. 운영 DB로 대체하지 않고 기존에 받은 PostgreSQL 바이너리를 작업 폴더에 풀어 루프백 전용 DB로 대체했다. 초기화 기본 trust 인증은 검증 비밀번호의 SCRAM 인증으로 바꿨다.
- 최초 평가 앱 import는 필수 설정 누락으로 Pydantic ValidationError가 났다. 공식 Settings 문서에 따라 테스트용 환경값을 import 전에 명시했다. 실제 DB 접근 경로는 로컬 DB allowlist로 제한한다. 비밀값과 원문 예외는 공개 로그에 넣지 않는다.
- 초기 Repeatable Read 구현은 단일 스냅샷 일관성을 확인했지만, 여러 기록의 동시 변경까지 고려해 SERIALIZABLE로 강화했다. PostgreSQL 공식 문서에 따라 직렬화 실패를 처리하며, 409 후 재조회하도록 했다.
- 의도적으로 주입한 읽기 실패 5개는 `meal_snapshot_failed error_type=OperationalError`로 구분된다. 새 경로에서는 쓰기까지 롤백됨을 확인했다. 사용자 원문·건강 수치는 실패 분석 로그에 추가하지 않는다.

## 범위와 남은 한계

4→1회는 캘린더에서 변경 완료 후 화면용 데이터를 준비하는 요청 수다. 이후 사용자가 채팅 탭으로 이동할 때 수행되는 기존 세션 복원은 유지한다. 대기 중 제안 복구를 생략하지 않기 위해서이며, 이후 모든 화면 이동까지 네트워크 요청이 사라진다는 뜻은 아니다.

100건 평가는 합성 데이터 준비 시간은 제외하고 첫 변경 요청 시작부터 화면에 적용할 데이터를 모두 받는 시점까지 잰다. DOM 렌더 지연과 실제 Supabase Auth/REST/Render 비용은 반영하지 않는다. 단일 브라우저 검증은 별도로 기록하며 그 한 건을 성능 통계로 확대하지 않는다.

스냅샷은 사용자 기록 최대 10,000개를 읽는 명시적 상한을 갖는다. 초과하면 트랜잭션을 롤백하고 오류를 반환한다. 대량 이력에서 범위 조회·별도 집계로 개선할 여지가 있으며 이번 작은 데이터셋이 대량 성능을 입증하지 않는다. 대화 상태 대조는 이전 구현과 같이 최근 100개 확정 제안 및 식별 가능한 저장 요약에 한정된다. 새 DB 마이그레이션이나 의존성은 추가하지 않았다.

## 공식 문서

- [PostgreSQL transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html)
- [Psycopg transaction context와 rollback](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Docker Desktop 시작](https://docs.docker.com/desktop/setup/install/windows-install/#start-docker-desktop)
