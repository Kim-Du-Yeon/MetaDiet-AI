# 초기 유지 기준선의 온보딩·HITL 연결 — 2026-10-10

## 변경과 적용 범위

이전 신규 온보딩은 BMR×1.4±400 및 별도 단백질 계산값을 확인 없이 `diet_strategies`에 저장했다. 이제 `POST /users/onboarding`은 활동 수준·일반 성인 자기보고·목표를 검증하고, 프로필과 pending 전략 제안을 한 SQL 트랜잭션으로 저장한다. 초기 전략은 기존 `/proposals/decision`에서 명시적으로 확정한 후에만 활성화한다.

- KR, 19~64세 일반 성인 자기보고의 유지 EER 기준선만 지원한다. 자기보고/원문 대조를 임상 승인이라고 표현하지 않는다.
- 감량·증량 목표/목표 체중·목표일은 장기 프로필에 저장한다. 현재 숫자는 **유지 기준선**이고 목표별 제한·증량은 미적용임을 확인 카드에 명시한다. 전날 과식의 고정 차감도 없다.
- `nutrition_policy_context`에 성별·활동·적용대상·계산 입력을 저장한다. 성별은 이 JSON이 계산의 단일 출처다. Agent 조회에도 전달한다.
- 공식 KDRI2025 유지 계산식·영양소 비율 4 claims를 원문 대조 후 등록했다. 에너지 범위는 모두 같은 고정 kcal가 아니라 각 사용자 EER의 1배인 `maintenance_ratio`로 검사한다. 코드 버전·입력·목표·catalog SHA를 receipt에 보존한다.
- 승인 직전에 최신 프로필과 catalog로 receipt를 재계산한다. 확인 대기 중 체중·목표·활동 또는 정책이 바뀌면 저장을 차단한다. macro 허용오차 .01%p는 g 소수2자리 반올림 오차용이다.
- 기존 활성 전략은 온보딩 제안 생성만으로 교체되지 않는다. `GET /users/onboarding`은 기존 전략 또는 유효 pending 제안을 반환한다. 기존 사용자는 새 적용대상 조건에 답하지 않고도 기존 전략으로 진입 가능하다.
- 화면의 확정·취소는 제안 ID/버전으로 처리한다. 오래된 제안은 입력 수정/재생성 가능. 기능 연결만 변경했고 Cue 전면 디자인은 후속 단계다.
- 레거시 `/users/setup`은 기존 전략 조회만 허용한다. 신규 직접 저장과 오류 반환 후 프로필 변경을 제거했다.

## 원문 검토와 범위 결정

[한국영양학회 KDRI2025/정오표](https://kns.or.kr/fileroom/fileroom_view.asp?BoardID=Kdr&idx=167), 로컬 1권 PDF58/59/8과 앞 단계의 표 렌더링을 근거로 유지 식과 비율을 등록했다. 원문 excerpt·문서SHA·출처·판본을 catalog/제안에 보존한다.

감량은 기존 [대한비만학회 2022 요약본](https://general.kosso.or.kr/html/user/core/view/reaction/main/kosso/inc/data/guideline2022_vol8.pdf) PDF6에서 **개인 특성과 의학적 상태에 따른 개별화** 조건을 확인했다. 저열량식500~1000kcal 제한 문구를 모든 사용자에게 그대로 적용하지 않는다. 더 최신 지침 검토와 목표별 적용 조건은 미완료이며 감량·증량 자동 처방 완료로 주장하지 않는다. 공개 연구 지침의 전문가 적용 조건을 단순 사용자 클릭으로 우회하지 않는다.

## 실제 DB 검증

공식 CLI로 생성한 `20261010065145_nutrition_policy_context.sql`의 additive JSONB 컬럼을 실제 DB에 적용했다. 기존 사용자 데이터/전략은 수정하지 않았다.

`backend/scripts/check_onboarding.py`는 합성 사용자로 다음을 검증하고 전체 합성 데이터 트랜잭션을 롤백한다:

1. 프로필+pending 생성 직후 활성 전략0건, GET 상태로 pending 복구.
2. 취소 후 재제안 및 확인 성공.
3. 중복 확정에도 전략1건.
4. 재온보딩에서 기존 전략 보존/조회 가능.
5. 확인 전 프로필 변경 차단.
6. 제안 생성 실패를 주입하면 새 프로필도 함께 롤백.

실제 사용자 JWT를 이용한 브라우저 전체 E2E 또는 임상 결과 검증으로 해석하지 않는다.

## 실패 로그 → 공식 자료 → 해결

- `npx --offline supabase --help`: ENOTCACHED. 오프라인 캐시에 CLI 패키지가 없었으며 공식 CLI 안내를 확인한 후 정상 npx 호출로 해결. `migration new --help` 후 파일 생성. https://supabase.com/docs/guides/local-development/cli-workflows
- UI 테스트의 `findByText`가 제목/설명 두 항목을 찾아 실패: 공식 쿼리 문서 확인 후 의미 있는 heading role로 지정. https://testing-library.com/docs/queries/about/
- 다음 UI 테스트에서 mock의 반환값 undefined: CRA/Jest resetMocks로 테스트 전 implementation이 초기화됨. 공식 문서 확인 후 각 테스트에서 mockResolvedValue 설정, 성공. https://jestjs.io/docs/mock-function-api
- 리뷰: 기존 사용자 접근 제한, 만료 제안 회복 부재, 오류 반환 후 레거시 프로필 변경 발견. 접근/변경 회귀 테스트 RED 확인 후 기존 조회 우선·별도 재생성·레거시 read-only로 수정. 재리뷰에 추가 material issue 없음.
- 보조 `rg` 경로 glob os123은 `-g` 필터로 수정. 실험/DB 영향 없음.
- 기존 Python real-location 진단, Pydantic/LangChain3개 deprecation 경고와 Node fs.F_OK deprecation은 남지만 실행 결과가 성공함을 확인했다. 정책/저장 실패 로그는 없다.

재현: backend venv로 `pytest -q --basetemp artifacts/<new-folder>` 및 `scripts/check_onboarding.py`; frontend `CI=true npm test -- --watchAll=false --runInBand`, `npm run build`. DB 스크립트는 additive migration을 적용하고 합성 데이터를 롤백하므로 실행 효과를 인지한 후 사용한다.

## 다음 단계

목표별 조정의 최신 자료/대상 검토와 새로운 독립 통합 시나리오가 남는다. 이후 실제 streaming → Weekly Deep Agent/MCP → 컨테이너/kind → 기능 검증 후 Cue UI 순서를 유지한다.
