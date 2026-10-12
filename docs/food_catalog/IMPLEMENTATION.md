# 국내 가공식품 카탈로그 구현 기록

승인 계획: 식약처 국내 가공식품 수집, 버전 관리, 공통 조회, 영양표 HITL, 전체 검증과 공개 배포.

- Ruling: 기존 checkout의 codex/food-catalog 브랜치 사용. main에 직접 구현하지 않음; 기존 venv와 환경 사용.
- Ruling: CSV는 고유 식품코드 기반 ID, 신규 가공식품은 mfds:제품코드 사용. 이미 저장된 proposal은 그대로 호환.
- 원본: K-FIND 2026-09-29 가공식품 DB. 실제 323,197행으로 전체 건수 일치. SHA256과 제외 사유는 MFDS_IMPORT_REPORT.json 참고.
- Task 1: 정규화/누락/충돌 테스트 작성. RED 검증 진행.
- Task 2: backend 전용 버전 카탈로그 및 원자적 활성화.
- Task 3: Agent/API/MCP 공통 조회와 영양표 quote, metadata 저장/표시.
- Task 4: 전체 테스트/합성 평가/공개 검증, docs 업데이트.

## 검증 결과 (2026-10-12)

- 원본 323,197행 중 계산 가능 281,583행. 기준량 불명확 41,576행, 비정상 영양값 37행, 필수 단백질 누락 1행 제외. 중복·충돌 0. 실제 Supabase 반영 건수 281,583행과 일치, mfds-20260929 활성화.
- 테이블 RLS 적용, anon/authenticated 접근권한 제거. 공용 식품 데이터 수정 API 없음.
- 고정 조회 4종 × CSV 단독/식약처 추가 비교: 일반 밥 조회 유지, 라이스페이퍼·돼지바는 미등록에서 복수 제품 후보로 개선. 미등록 평가 제품은 계속 미등록. LOOKUP_EVALUATION.json은 읽기 전용 조회 실험이며 Agent 목표 달성률·사용자 성과로 해석하지 않는다.
- 백엔드 404 passed / 1 skipped (기존 skip 유지), 프론트 60 passed, 프로덕션 build 통과.
- 공개 API 합성 계정 검증 9개 통과: 모호한 제품 계산 보류, 확인 전 미저장, 동일 요청 동일 제안, pending 복원, 명시적 확정, 중복 확정 한 번 저장, 출처 메타데이터 저장, 완료 상태 복원, 취소 미저장. 테스트 계정은 삭제했다. 결과: PUBLIC_SMOKE.json. 실제 사용자 성과나 전체 브라우저 E2E로 해석하지 않는다.
- 단일 부분 일치도 제품 선택 전에는 계산하지 않는다. 정확 일치·검증 별칭과 부분 일치의 match_type을 구분하며 Agent와 공개 API 모두 적용한다.

## 실패와 해결

1. Windows pytest 임시폴더 권한 오류(WinError 5): pytest 공식 tmp_path 문서를 확인해 프로젝트 전용 새 --basetemp 경로로 재실행. 테스트 삭제·추가 skip 없이 통과.
2. 영양 조회 빈 배열이 422로 바뀐 호환성 회귀: Pydantic 목록 min_length 동작을 확인하고 최소 개수 제한을 제거, 최대 30개 제한은 유지.
3. 영양표 API 테스트가 실제 DB 연결을 시도해 ProactorEventLoop 오류: psycopg 공식 async 문서에서 Windows Selector 요구사항 확인. 운영 루프 설정을 유지하고 테스트 DB/lock 경계를 mock 처리.
4. 새 UI 테스트의 window.crypto 부재: Jest 공식 mock 문서를 확인하고 테스트 전역 경계를 mock. 운영은 HTTPS crypto.randomUUID를 사용하며 재시도 ID는 유지, 입력 변경 때 새 ID 생성.
5. 공개 재요청 HTTP 500: Render 로그에 `langgraph.errors.InvalidUpdateError: Ambiguous update, specify as_node` 확인. 실제 MemorySaver 그래프로 동일 재요청 실패를 재현했다. LangGraph 공식 update_state 문서에 따라 외부 제안 상태 갱신의 as_node를 save_chat으로 명시하여 재실행 없이 체크포인트만 갱신한다. [공식 문서](https://reference.langchain.com/python/langgraph/pregel/main/Pregel/update_state).

공식 참고: [pytest 임시경로](https://docs.pytest.org/en/stable/how-to/tmp_path.html), [psycopg async](https://www.psycopg.org/psycopg3/docs/advanced/async.html), [Jest mock](https://jestjs.io/docs/29.7/jest-object).

## 남은 검증

- 버전 재수입·복구/부분 수집 거부의 통합 검증 보강
- 공개 브라우저의 전체 제품 선택→Agent 제안→확정 흐름 추가 검증 (공개 API 영양표 경로와 읽기 전용 후보 UI는 검증 완료)
- Agent 모델/도구 호출 수와 실제 응답 지연 전후 비교 (현재 조회 지연만 측정)

리뷰 보완: 모델이 product_confirmed만으로 복수 후보를 선택하지 못하도록 실제 사용자 메시지의 단일 `제품 선택: food_id`를 확인한다. UI 제품 검색에서 선택하면 이 문구가 입력란에 들어간다. 체크포인트에 제안 포인터가 없어도 소유자·thread로 SQL pending 제안을 복원한다. 두 경로를 회귀 테스트에 추가했다.
