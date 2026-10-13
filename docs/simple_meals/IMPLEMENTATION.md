# 간단 식사 입력 구현 ledger

Binding brief: 사용자 승인 계획(2026-10-13). BASE: 21cc2ac.

1. 기본 분량·대표 항목·서버 계산과 엄격한 음식 파싱
2. LangGraph 내 빠른 기록 경로, proposal 수정·복원
3. 음식별 수정 카드·남은 칼로리·추천 버튼, 제품 선택 이유 표시
4. 전체 회귀·고정 요청 전후 비교·공개 흐름·GitHub 반영

Ruling: 사용자가 main 반영·공개 검증을 기존 세션에서 승인했으므로 현재 checkout을 재사용하고 기존 scratch는 보존한다.
Ruling: 음식 입력이 완전히 해석되는 경우에만 모델 없는 기록 경로를 사용한다. 모르는 항목을 조용히 버리지 않는다.
Ruling: 라이스페이퍼는 MFDS의 검토된 무브랜드 대표 항목 P108-007000300-0013을 검증해 사용하고 제조사 제품 확정으로 표현하지 않는다. 기본 1장 10g은 앱 가정으로 표시한다.
Ruling: 밥200g·익힌 닭가슴살100g·김치40g은 앱 기본값이며 공식 보편 분량이나 의학 권고로 표현하지 않는다.
Pre-flight: meal metadata는 기존 dict에 추가해 저장 호환을 유지한다. 수정 endpoint는 사용자·version 검증 후 새 proposal을 생성하고 checkpoint를 동기화해야 한다.

Completion: 1~4 완료. 기능 902fb1e / 대표값 수정 bbeb58c, 전체 backend 434 passed·1 existing skipped, frontend 65 passed·build passed, 공개 입력·수정·복원·확정·취소·코칭 및 DB 행 수 확인. 상세 조건은 RESULTS.md와 원본 JSON에 기록.
