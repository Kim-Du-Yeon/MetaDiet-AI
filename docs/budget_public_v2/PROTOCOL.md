# 공개 예산 저장 재검증 v2 — 사전 고정 프로토콜

2026-10-14. 이전 공개 결과는 변경하지 않는다. 이번 비교는 외부 오류 복구가 동일하게 적용된 한 커밋에서 BUDGET_PIPELINE만 false → true로 전환한다. 오류 복구 자체의 속도 개선 효과로 해석하지 않는다.

- 기존 네 질문 × 다섯 최신 DB 상태 × 다섯 반복 = 조건별 100회. 같은 순서, 같은 합성 계정, 동일 모델·추론 설정·프롬프트. 준비 요청은 별도 파일.
- provider 504와 HTTPX 일시 오류는 모델 생성/읽기에 한해 최대 1회 jitter 지연 후 재시도. 모델 재시도도 durable 실행 예산에 청구하며 전체 실행 deadline을 유지한다. 도구/제안/확정/쓰기 전체를 다시 실행하지 않는다.
- 기존의 max_retries=0 SDK 설정을 유지한다. 재시도 발생·최종 오류는 안전한 유형 정보만 기록한다.
- 실패·timeout·blocked 모두 원본 100건 분모에 남긴다. 전체 시도 duration 중앙값/p95와 성공 응답 지연을 각각 보고한다. 실패 후 교체 요청을 넣지 않는다.
- 동일 Gemini judge의 5가지 품질 항목, 최신 섭취/목표 일치, 식사/전략 행 미변경을 확인한다. 실패 응답은 품질·최신값 성공으로 세지 않는다.
- 기존 채택 기준 유지: 양쪽 100건 완료·최신값·미저장 및 judge100건; 저장 중앙값 ≥20% 개선, 전체 완료 중앙값 ≥5% 개선, p95 악화 ≤10%, 품질 비악화. 추가로 실패 포함 전체 시도 중앙값 ≥5% 개선/p95 악화 ≤10%도 필요하다.
- 어느 기준이든 실패하면 false로 복원한다. 측정 종료 후 합성 계정 삭제, GitHub·포트폴리오에 원본·실패·한계 기록.
- 순차 시간대, 한 계정, 반복 합성 질문의 한계가 있다. 실제 사용자 평균이나 장애율 보장이 아니다.

## 근거와 오류 처리 범위

이전 로그: Gemini `504 DEADLINE_EXCEEDED`, HTTPX `ReadError`. 공급자 내부 원인은 알 수 없으므로 영구 해결로 주장하지 않는다. 제한된 재시도로 일시 오류에 복구 기회를 제공한다.

- https://ai.google.dev/gemini-api/docs/troubleshooting — 일시 오류만 제한 재시도, 지연·jitter
- https://www.python-httpx.org/advanced/transports/ — transport retries는 connect 오류에 한정, read 오류는 별도 처리 필요
- https://www.psycopg.org/psycopg3/docs/advanced/pipeline.html — 저장 pipeline 동기화 의미

실패 주입 테스트에서 504/ReadError 복구, 지속 실패 2회 상한, 입력 오류/취소 무재시도, 실행 예산 거부와 전체 deadline을 확인한다. 공개 자연 발생 실패와 주입 검증을 구분한다.
