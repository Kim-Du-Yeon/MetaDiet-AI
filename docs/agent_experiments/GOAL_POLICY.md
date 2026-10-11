# 목표별 적용 조건·보류 정책 — 2026-10-10

## 이번 결과와 제한

목표별 **적용 가능 여부와 보류 이유**를 코드로 연결했다. 감량·증량 칼로리 조정은 아직 활성화하지 않았다. 이 결과를 맞춤 감량 처방 구현 완료 또는 임상 유효성 검증이라고 표현하지 않는다.

| 목표 | 상태 | 숫자 처리 |
|---|---|---|
| 유지 | maintenance_ready | 기존 KDRI2025 유지 EER |
| 감량 | adjustment_deferred / latest_diet_source_unverified | 유지 기준선, 차감0 |
| 증량 | adjustment_deferred / bulk_applicability_unverified | 유지 기준선, 추가0 |

2024 KSSO 갱신 논문은 진단·약물치료를 다루므로 제목의 최신 연도만 보고 이전 식사치료 수치를 업데이트했다고 판단하지 않는다. 식사치료 전문은 원문 대조 미완료다. [2024 갱신 논문](https://doi.org/10.7570/jomes25042). 기존 [2022 요약본](https://general.kosso.or.kr/html/user/core/view/reaction/main/kosso/inc/data/guideline2022_vol8.pdf)의 개별화 조건도 유지한다.

증량의 [2023 원저](https://doi.org/10.1186/s40798-023-00651-y)는 저항운동 경험이 있는 참가자 대상이다. 검색 결과의5%/15%/보수적 surplus 문구를 일반 성인 전체의 공식으로 등록하지 않는다. 본 서비스의 운동 경험·프로그램 조건 검증도 미완료이며 해당 연구를 활성 numeric claim catalog에 추가하지 않았다.

## 구현

- `goal_policy.assess_goal`: 체중·목표 체중·목표일의 유효성, 감량/증량 방향 모순, 유지 목표와 다른 체중 목표, 과거/잘못된 날짜를 차단한다.
- 목표 기간과 요구 주간 체중 변화는 산술로 반환한다. `requested_rate_is_recommendation=false`이며 안전 속도 판정이나 달성 가능성 보장이 아니다. 70→65kg/100일은 요청 기준−0.35kg/주이지 추천 속도가 아니다.
- 초기 프로필 구성에 이번 요청의 목표 체중·날짜·우선순위를 반영한다. 이전 프로필의 값을 잘못 사용하지 않는다.
- 정책 receipt에 goal_assessment를 저장하고 승인 때 재계산한다. 목표 체중·날짜 변경도 오래된 제안 승인을 차단한다.
- Agent가 유지 기준선을 '완료된 감량 처방'이라고 작성할 수 있음을 RED 테스트로 재현했다. 보류 상태에서는 서버가 전략 설명을 유지 기준선/보류 이유로 대체해 Validator·HITL에 전달한다. 프롬프트만으로 이 경계를 보장하지 않는다. [LangChain guardrails](https://docs.langchain.com/oss/python/langchain/guardrails).
- 새 DB 컬럼·새 외부 의존성·모델 설정 변경은 없다. 기존 EER·Agent·제안/HITL 구조를 유지한다.

## 실패 로그와 조치

- 첫 테스트는 모듈 미구현으로 ModuleNotFoundError(의도된 TDD RED), 구현 후 GREEN.
- Agent 설명의 처방 완료 오표기는1failed/12passed로 재현 후 서버 표시 교정, 전체 재검증 성공.
- PMC 원문 접근은 reCAPTCHA 화면, 학회 일반 홈페이지 및 DOI 조회는 web Internal Error. 우회하지 않고 공개 검색의 학회 갱신 논문/저자 기관 원저 결과를 확인했다. **전체 원문 식사 정책을 확인했다는 주장은 하지 않으며** 자동 조정 보류를 유지한다. 이것은 Python 파싱 오류나 DB 오류가 아니다.
- 이번 코드의 실제 DB 실행은 실패0. 합성 사용자의 목표 변경 차단 검증을 추가하고 전체 합성 데이터를 rollback했다. 기존 경고3개는 남았다.

## 검증 및 재현

백엔드 **272 passed /1 skipped /3 warnings**, `backend/artifacts/goal-release.log`. 새 목표 정책 테스트13개. 실제 DB `backend/artifacts/goal-db.log`: 상태 복구·취소재시도·중복·기존전략 보존·프로필 및 목표 변경 차단·프로필/제안 원자적 rollback 성공. 합성 데이터는 삭제 명령 없이 outer transaction rollback으로 제거했다.

```
cd backend
venv\Scripts\python.exe -m pytest -q --basetemp artifacts/<new-folder>
venv\Scripts\python.exe scripts/check_onboarding.py
```

DB script는 기존 additive migration을 확인/적용하며 합성 데이터는 롤백한다. 구문 검사·diff whitespace 검사 통과. 프론트 변경이 없어 직전 프론트8tests/build 결과를 이번 새 실행 결과라고 주장하지 않는다. 정적 재리뷰 material issue 없음.

## 남은 일

자동 조정 활성화에는 정식 식사치료 원문·판본·적용대상 검토, 증량 조건 입력과 근거 수준 검토가 필요하다. 이를 확보하기 전에는 보류 계약을 포함한 독립 통합 평가를 진행할 수 있다. 이후 streaming/Weekly Deep Agent/MCP/컨테이너·kind/Cue UI 계획은 유지한다. Ragas는 근거 충실도 평가이며 이 검토를 대신하는 임상 승인 수단이 아니다.

## v2 — 검토된 일반 성인 감량 조정과 4주 점검 (2026-10-10)

대한비만학회 2022 진료지침 요약본 PDF 6쪽의 식사치료 원문을 대조했다. 적용 대상은 과체중 또는 비만 성인이며 제한 정도는 개인 특성과 의학적 상태에 따라 개별화한다. 저열량식의 500~1,000 kcal 감소 범위 중 서비스는 가장 보수적인 500 kcal만 사용한다. 2024 지침의 2025년 논문은 진단·약물치료 개정이므로 2022 식사치료 절을 폐기한 새 식사 수치로 취급하지 않는다.

자동 조정은 KR, 19~64세 일반 성인 적용 확인, BMI 23 이상, 감량 방향의 목표 체중과 미래 목표일, KDRI 유지 에너지 계산이 모두 확인된 경우에만 제안한다. 113 kg 미만은 1,200 kcal, 이상은 1,500 kcal 서비스 하한을 사용한다. 유지 에너지에서 500 kcal를 뺀 결과가 하한보다 작으면 더 작은 임의 deficit을 만들지 않고 보류한다. 800 kcal 이하 초저열량식은 의료 감독 영역으로 서비스가 만들지 않는다. `speed` 선택이나 공격적인 목표일도 500 kcal를 늘리는 근거가 아니다.

PDF 8쪽의 “1개월 이내 2.5% 미달 시 생활습관 중재 강화 고려”를 28~42일 확정 체중 기록의 점검 신호로 구현했다. 미달이어도 칼로리를 자동으로 더 줄이지 않고 기록 완전성·실행 가능성·상태 검토를 권고하며, 전략 변경은 기존 proposal→Validator→HITL→승인 직전 재검증 경계를 거친다. 증량은 17명 완료자의 8주 저항운동 연구를 일반 성인에게 일반화하지 않고 계속 보류한다.

근거 catalog에는 원문 PDF SHA, canonical PDF page, 적용 대상과 단위를 저장했다. Agent 검색 근거는 내부 0-based page보다 `pdf_page`를 우선하며, PDF 탭·개행은 공백 정규화 후 catalog 원문과 비교한다. 의료·임상 승인이나 질환별 처방을 완료했다는 의미는 아니다.

실제 Supabase에서는 합성 사용자로 승인 전 전략 0건, 취소·재제안, 확정, 중복 확정 1건 유지, 기존 전략 보존, 프로필·목표 변경 시 승인 차단, 제안 생성 실패 시 프로필 롤백을 확인했고 합성 데이터는 모두 롤백했다.

근거: 대한비만학회 2022 요약본 `https://general.kosso.or.kr/html/user/core/view/reaction/main/kosso/inc/data/guideline2022_vol8.pdf`, 2024 진단·약물치료 개정 `https://pubmed.ncbi.nlm.nih.gov/40819841/`, 증량 적용 한계 연구 `https://pubmed.ncbi.nlm.nih.gov/37914977/`.
