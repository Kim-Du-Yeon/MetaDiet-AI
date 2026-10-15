# Render 수시간 부하·독립 DB 재시작·백업 복구 검증 준비

**상태: 인프라와 비용 확인 대기. 수시간 부하·DB 재시작·백업 복구는 아직 실행하지 않았다.** [현재 상태 원본](validation-readiness.json). 이전의 로컬 ASGI600초 결과를 이번 검증 결과로 재사용하지 않는다.

## 확인한 외부 조건

Render에는 기존 API·웹만 있고 별도 검증 서비스는 없다. 연결된 Supabase 조직은Free이고 활성 프로젝트2개를 사용 중이다. 비용 조회 도구는 `UNAVAILABLE: get_cost was not returned by tools/list`를 반환했다. 조직 정보·프로젝트 목록과 공식 요금·청구 문서로 우회 확인했다. 유료 자원 생성이나 조직 요금제 변경은 수행하지 않았다.

[공식 요금](https://supabase.com/pricing)과 [청구 FAQ](https://supabase.com/docs/guides/platform/billing-faq)에 따르면 Free 활성 프로젝트는2개 한도다. 같은 조직에3개 Micro를 한 달 유지하는 Pro 예시는 기본25달러+컴퓨팅30달러−크레딧10달러=약45달러/월(세금·추가 사용량 제외)이다. 2시간 검사의 정확한 청구액이나 조직별 확정 견적이 아니다. 기존 조직을 업그레이드하면 기존 프로젝트도 유료 조직 정책을 적용받는다. 별도 유료 조직 또는 사용자가 이미 준비한 독립 검증 프로젝트를 쓰는 선택지도 있다. 새 별도 Pro 조직의 기본 예시는 Micro1개 포함 약25달러/월이며 복원 인스턴스·PITR·사용량은 추가될 수 있다.

Render Free는 별도 서비스로 구성할 수 있으나 시간·전송량·빌드 한도가 workspace 전체에 공유된다. 실행 전 여유를 확인하고 예상 초과 시 시작하지 않는다. [무료 서비스 제약](https://render.com/docs/free), [Render 백업](https://render.com/docs/postgresql-backups). Render Free Postgres는 관리형 백업을 지원하지 않으므로 이번 Supabase 운영 구조와 동일한 관리형 복구 검증을 무료로 대체했다고 주장할 수 없다.

로컬에는 `pg_dump`·`pg_restore`가 없고 Docker는 처음에 Linux engine named pipe 부재 오류였다. [공식 시작 명령](https://docs.docker.com/reference/cli/docker/desktop/start/)을 확인해 `docker desktop start --detach`를 수행했으나 이후12초 제한 엔진 확인이 timeout됐다. WSL/가상화 문제라고 확정하지 않았고 시스템 설정을 변경하지 않았다. 대체 경로로 [PostgreSQL 공식 Windows 안내](https://www.postgresql.org/download/windows/)가 링크한 [EDB 바이너리](https://www.enterprisedb.com/download-postgresql-binaries)를 확보했다. 서버 설치 없이 작업 폴더의 pg_dump·pg_restore17.11을 `--version`으로 확인했다. 압축파일SHA256은 `80379b2c04d51c30225532e0ae04509899141e9957ed096fe749d7fd9df8f82f`다. Docker를 사용할 수 있게 됐다는 의미는 아니며 DB 접속·백업·복원은 아직 실행하지 않았다. 운영 DB에는 백업·재시작 명령을 보내지 않았다.

## 준비된 파일과 실제 준비 수준

- [별도 Render Blueprint](../../render.validation.yaml): 운영 render.yaml과 분리, 자동 배포off, 스케줄러off, 독립 환경변수. 아직 Render에서 생성·검증된 Blueprint가 아니다.
- [환경변수 예시](validation.env.example): 실제 값은 git-ignored `backend/.env.validation`에만 저장한다.
- `backend/scripts/validation_preflight.py`: 외부 요청 없는 설정 사전 검사. 기존 두 프로젝트·운영 API·프로젝트와 다른 DSN·짧은 실행 조건·과도한 요청 수를 차단한다. 비밀과 DSN을 출력하지 않는다.

```powershell
backend\venv\Scripts\python.exe backend/scripts/validation_preflight.py --env-file backend/.env.validation
backend\venv\Scripts\python.exe -m pytest backend/tests/unit/test_validation_preflight.py -q
```

이 사전 검사는 **로컬 문자열 설정 검사만** 수행한다. 원격 Render 서비스가 실제 어떤 DB에 연결됐는지 입증하지 않으며, 부하 발생기·재시작기·복원 도구도 아니다. 외부 환경이 준비된 다음 원격 설정/DB 신원을 확인하고 HTTPS 부하 runner 및 복구 orchestration을 연결·구현해야 한다.

## 실행 절차와 통과 기준

1. 독립 Supabase 프로젝트와 검증용 Render 서비스를 생성한다. 새 자격 증명을 사용하고 운영 데이터·Auth 사용자·기존 환경변수·운영 RAG namespace를 복제하지 않는다. DB schema-only 초기화는 저장소SQL과 실제 schema 차이를 먼저 감사한다. `backend/app/db/schema.sql`만으로 최신 운영 schema 전체가 재현된다고 가정하지 않는다.
2. Render에 배포한 commit을 health로 확인하고 Render 설정의 Supabase project ref/DSN과 독립 DB의 연결 신원을 대조한다. 사전 문자열 검사만으로 파괴 작업을 허용하지 않는다. 테스트 계정3개와 합성 피드백1만 건을 독립 프로젝트에서 생성한다.
3. 2시간·3세션·30초 간격으로 세션별240회, 총720회 HTTPS 조회를 실행한다. 고정100개 필터 사례를 반복하며 모든 시도를 저장한다. 오류·타임아웃·취소도 분모에 유지하고 응답 코드·시각·지연·집계 일치·버전을 기록한다. 관리자 세션 refresh와 미저장 편집 UI는 별도 확인한다. 데이터·의견 원문은 분석 로그에 남기지 않는다.
4. 중간 시점에 **검증 프로젝트 DB만 실제 재시작**한다. 재시작 전100회 이상·복구 후100회 이상을 구분하고 장애 구간 요청도 삭제하지 않는다. 기존 연결 재사용 실패·새 연결 복구·실제 쓰기/이력 원자성을 확인한다. 재시작 완료 API 응답만으로 복구를 판정하지 않고 조회·저장·이력과 연속 정상 응답을 확인한다. 재시작은1회 기능 검사이며100회 재시작 신뢰도 실험으로 해석하지 않는다.
5. 합성 데이터만 있는 검증 DB의 논리 백업을 생성한다. 아카이브SHA256·테이블별 행 수·정렬한 데이터 hash·제약/인덱스를 기록한다. 격리 대상임을 다시 확인한 후 합성 행 손실을 재현하고 백업을 복원한다. 복구 후 동일 hash·제약·사용자 소유권·버전·관리자 이력·API 읽기/저장을 검사한다. 원래 검증 DB에 복원할지 별도 복원 프로젝트에 할지는 실제 제공된 환경과 비용을 확인하고 확정한다.
6. [Supabase 공식 백업 지침](https://supabase.com/docs/guides/platform/backups)에 따라 논리 백업과 관리형 일일 백업/PITR를 분리한다. Pro 일일 백업은 새 프로젝트 생성 즉시 사용할 수 있다고 가정하지 않는다. 즉시 수행할 논리 복구와 관리형 복구가 요구하는 백업 생성 대기·유료 기능을 각각 기록한다. PITR add-on을 자동 구매하지 않는다.
7. 실제 장애 시작·첫 정상 조회·첫 정상 쓰기·복원 완료 시각으로 관측 RTO를 산출하고, 백업 시점 이후의 의도적 누락과 복원 누락을 구분해 관측 RPO를 기록한다. 정책 SLA나 무손실 보장으로 일반화하지 않는다. 검증 환경은 종료 후 정지/정리해 추가 사용량을 제한하고 모든 결과·실패 로그·해결 근거를 문서에 반영한다.

[Blueprint 공식 참조](https://render.com/docs/blueprint-spec), [PostgreSQL pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html), [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html).

## 현재 판정

현재 실제 시도는 부하0건·DB 재시작0회·복원0회다. 결과를 통과로 기록하지 않았다. 필요한 외부 조건은 독립 프로젝트 제공 또는 비용/생성 경로 승인, Supabase Dashboard 관리 접근이다. Windows 백업 클라이언트17.11은 준비했으며 실제 대상 DB에서의 동작 확인은 남았다. 사전 검사 회귀는 제품 성능 근거가 아니다.


사전 검사 단위 테스트14개와 전체 백엔드1098 passed·기존1 skipped를 확인했다. Blueprint YAML은 파싱 및 별도 서비스/자동 배포off를 확인했고 코드 리뷰의 차단 이슈는 없었다. Render 서버의 Blueprint 검증·배포나 실제 성능 검증을 통과했다는 뜻은 아니다.
