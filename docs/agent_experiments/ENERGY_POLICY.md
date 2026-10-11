# 유지 에너지 계산 기반 — 2026-10-10

이번 결과는 초기 전략 전체 전환이 아니라, 유지 에너지 계산과 읽기 전용 API의 검증이다. 기존 `/users/setup` 계산·저장은 아직 이 계산기로 교체하지 않았다. 검토된 strategy claim catalog도 비어 있으므로 자동 전략 변경을 활성화한 결과로 해석하지 않는다.

## 원문과 선택

- [한국영양학회 2025 KDRI/정오표](https://kns.or.kr/fileroom/fileroom_view.asp?BoardID=Kdr&idx=167), 로컬 `KDRI_2025_vol1.pdf` SHA256 `31c99fbf3a0253f55a5b9f53964ea9a1db8a108077650d119b4841a9b11f9cad`.
- PDF58(인쇄16): 성인 EER 공식. PDF59(인쇄17): 성인 성별 활동계수. PDF8(인쇄viii): 영양소 비율. 활동계수/비율 표는 Poppler 이미지로 원문 대조했다.
- 성인 유지 에너지 추정: 남성 `662−9.53×나이+PA×(15.91×kg+539.6×m)`, 여성 `354−6.91×나이+PA×(9.36×kg+726×m)`.
- 성인 활동계수와 아동 계수를 구분한다. PA는 BMR에 곱하는 일반 활동 배수가 아니다. 활동 수준을 임의로 저활동으로 기본 설정하지 않는다.
- 2025 비율: 탄수화물50–65%, 단백질10–20%, 지방15–30%. 서비스 배분55/20/25는 범위 내 기본값이며 공식 지침이 유일하게 권고한 비율로 표현하지 않는다.
- MVP는 19세 이상65세 미만, 일반 성인 적용 가능 여부의 명시적 자기보고가 있는 입력으로 제한한다. 자기보고를 임상 승인이라고 표현하지 않는다.
- 감량/증량 및 전날 과식의 고정 차감은 적용하지 않는다. 유지 추정치를 목표별 처방으로 오해하지 않도록 API에 `is_applied=false` 및 설명을 반환한다.

## API / 검증

`POST /users/energy-preview` (Supabase Auth JWT 필요): JSON `age`, `sex`(male/female), `weight_kg`, `height_cm`, `activity`(sedentary/low_active/active/very_active), `general_adult_confirmed:true`.

프로필·전략 저장 없음. 출력은 원시/반올림 유지 kcal, 영양소 배분, 입력, PA, 정책 버전, 문서 해시·페이지를 포함한다. 입력 누락·비유한 수·미확인 적용대상·지원하지 않는 분류를 거절한다.

PDF69의 성인 계산 예시4개(약2701/2525/2087/1957kcal)를 ±1kcal 내 재현했다. 배분 에너지 합, 활동 수준 변경, DB 쓰기 없음, 잘못된 입력을 검증했다. 새 테스트17개, 전체253 passed/1 skipped/기존 warnings3 (`backend/artifacts/energy-strict-release.log`). 실제 사용자 EER 정확도나 감량 효과 검증으로 주장하지 않는다.

## 실패 원인과 조치

- 이미지 렌더링 첫 시도: 메인 venv에 pypdfium2 없음(ModuleNotFoundError). 추가 설치 대신 기존 Poppler를 발견해 렌더링 성공. 공식 렌더링 API도 확인: https://pymupdf.readthedocs.io/en/latest/page.html . 새 의존성 없음.
- 리뷰에서 Pydantic 기본 숫자 변환이 `true`를 체중·키1로 받아들이고 `Literal[True]`가 숫자1도 허용하는 문제를 재현했다(3 failed). 공식 strict mode/validator 문서 확인 후 strict 설정과 실제 boolean 확인 검사를 적용, 전체 재검증 성공. https://docs.pydantic.dev/latest/concepts/strict_mode/ https://docs.pydantic.dev/latest/concepts/validators/
- 최초 모듈 누락은 TDD 의도된 RED, 구현 후 GREEN. D temp/basetemp 사용. 가상환경의 real-location 경고는 남지만 실제 Python 실행과 테스트 exit 성공을 확인했다.

## 다음 연결 단계

1. 적용대상·활동 입력을 온보딩/DB 장기 프로필에 연결한다.
2. 목표별 조정의 실제 자료/적용 조건을 검토하고 공식 식·범위 claims를 등록한다. 유지 공식만으로 감량·증량을 승인하지 않는다.
3. 기존 신규 가입의 직접 초기전략 저장을 pending proposal→HITL→원자적 승인으로 교체한다. 기존 전략 보존, 취소/재시도, 승인 전 프로필 변경 검증 포함.
4. 실제 DB 검증 후 실행 이벤트·답변 streaming, Weekly Deep Agent/MCP, 컨테이너/kind, 마지막 Cue UI 순서를 유지한다.
