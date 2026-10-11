# 근거 정책 통합 — 2026-10-10

이번 단계는 기존 `resolve_claims`의 최신 판본·지역/기관 우선순위·동순위 충돌 판정을 실제 전략 제안과 확정 저장에 연결한다. LLM의 승인이나 사용자의 확인 버튼은 코드의 근거 정책 차단을 해제할 수 없다.

## 연결된 경계

1. 서버가 검토한 claim catalog를 로드한다. 모델이 추출한 문장이나 자체 `approved` 표시는 승인 근거가 아니다.
2. 일반 성인 적용 대상/조건이 명시적으로 확인된 사용자만 대상이다. 나이만으로 적용 조건을 추정하지 않는다.
3. 같은 family/대상/조건에서는 최신 연도·정오표 판본을 선택하고 지역 및 기관 우선순위를 적용한다. 동순위 권고 충돌은 평균/교집합으로 합치지 않고 보류한다.
4. 실제 인용한 source/page/document SHA/excerpt가 선정 근거와 연결되는지 확인한다. 누락·구판 인용은 거절한다.
5. kcal/day, g/day, g/kg, percent energy의 명시적 변환과 목표 범위를 검사한다. 확인된 체중이 없으면 체중당 변환은 거절한다.
6. 통과하면 정책 버전·catalog SHA·선정/충돌 근거를 proposal payload에 넣고 Validator에 전달한다. 선정 이유와 충돌 IDs는 기존 확인 카드의 전략 설명에 표시한다.
7. 확정 직전 같은 트랜잭션에서 catalog/사용자 정보를 다시 읽는다. 제안 이후 정책 변경·철회·대상 변경이 있으면 쓰기 전에 거절한다. 기존 proposal payload가 감사 원본이다.

구형 `update_strategy_tool` 직접 저장은 차단했다. 재온보딩은 현재 확정 전략을 보존한다. 신규 가입자의 최초 계산은 이번 범위에서 변경하지 않았으며, 초기 계산 정책 검증은 다음 정비 대상이다.

## 운영 활성화 한계

`backend/app/rag/reviewed_strategy_claims.json`은 의도적으로 비어 있다. 이번 테스트의 수치 범위는 합성 fixture이며 실제 식단 권고로 복사하지 않는다. 운영 PDF를 다운로드/임베딩한 것과 개인의 목표 수치를 승인할 정책을 검토한 것은 다르다.

따라서 **현재 자동 숫자 전략 변경은 보류**된다. 기존 확정 목표를 이용한 추천·기록·분석은 그대로 동작한다. 다음에는 실제 자료의 수치/식/적용 조건을 원문과 대조한 catalog 및 초기 에너지 정책을 만들고, 검토된 적용 대상의 저장/입력 경로를 마련해야 한다. 현재 profile에 `policy_population`/`policy_conditions`가 없으면 안전하게 차단하며, 새 DB 컬럼이나 임상 적격성을 자동 생성했다고 주장하지 않는다.

catalog claim 필드: id/claim_key/family/authority/region/population/conditions/year/revision_date/status/unit/low/high/source/page/excerpt/document_sha256/review_status/reviewer. 승인 대상 keys는 daily_calories/protein_g/carbs_g/fat_g이다. energy 정책을 하나의 보편적 kcal 범위로 단순화하지 말고 개인 계산식·대상·활동 수준과의 연결을 다음 단계에서 설계한다. 승인 claim이 없는 경우 자동 근거 추출로 대체하지 않는다.

## 검증·오류 결정

- Docling 최초 native 원인 미확정/Jev 최초 invalid_response는 현재 운영 기본 경로(PyPDF/Gemini)를 막지 않아 이번 단계 재실험하지 않았다.
- Gemini 일시 504는 이전 1회 재확인 성공으로 기록된 상태다. 재발 가능성은 남으며 공급사 무장애를 주장하지 않는다.
- 신규 테스트에서 적용 조건 누락과 우회 저장을 재현했고, 코드로 차단했다. 근거 충돌·구판·해시·단위·범위·대상·정책 변경·실제 Agent→Validator 경계를 검사한다.
- 실제 외부 API/운영 DB는 이번 단계에서 호출·변경하지 않았다. 테스트는 합성 catalog와 mocked DB다. 실제 DB 재시작/동시성/스트리밍 최종 품질 검증은 남아 있다.
- 공식 guardrails/HITL 자료를 검토하되 새 프레임워크로 전면 교체하지 않았다: https://github.com/langchain-ai/docs/blob/main/docs/src/oss/langchain/guardrails.mdx

이후 순서: 수치 정책·초기 계산·적용 대상 등록 → 실제 DB/HITL 통합 검증 → 실제 스트리밍 → Weekly Deep Agent·MCP → 컨테이너/kind → 기능 검증 후 Cue 참고 UI.
