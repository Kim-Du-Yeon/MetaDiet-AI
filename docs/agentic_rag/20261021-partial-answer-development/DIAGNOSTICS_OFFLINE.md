# Controller 출력 진단 보강 — 오프라인 검증

2026-10-21. 신규 유료 호출 0건, 모델·512토큰 출력 한도·6000자 근거 한도·검색 반복 수·예산 정책 변경 없음.

## 추가한 진단

`model_assessment`는 기존 `include_raw=True` 응답에서 다음 값만 허용 목록으로 추출해 `rag_assessment_diagnostic` JSON 로그를 남긴다. 성공은 INFO, 실패는 WARNING이다. 구조화 로거에서도 `assessment_diagnostic` 필드를 사용할 수 있다.

| 항목 | 값 / 의미 |
|---|---|
| failure_reason | `output_truncated`, `parsing_error`, `missing_parsed`, `schema_validation_error`, `invalid_envelope`, `provider_error`; 성공은 null |
| finish_reason | 알려진 공급자 종료 코드, `MISSING`, `UNRECOGNIZED`; 임의 문자열은 남기지 않음 |
| parsing_error_present/type | 파싱 오류 동반 여부와 허용된 예외 유형만 기록. MAX_TOKENS와 동시 발생해도 둘 다 확인 가능 |
| usage_status | `complete`, `partial`, `missing`, `invalid` |
| usage | input/output/total/reasoning의 음수가 아닌 정수만 기록. 없는 값은 null이며 0으로 추정하지 않음 |
| prompt_version/hash | 기존 controller-v10과 동일한 프롬프트 식별자 |
| context_chars/output_token_limit | 평가한 근거 길이와 기존 512토큰 한도 |

파싱 예외의 메시지·원시 JSON·질문·검색 문맥·답변·자격 정보는 로그에 넣지 않는다. `OutputParserException` 등 직접 발생한 파싱 예외도 안전한 진단으로 바꾼다. 일반 공급자 예외는 기존 402/429/auth 판정을 유지하며 메시지를 추가 로깅하지 않는다. 예산 중단·취소는 새 재시도나 호출을 일으키지 않는다.

출력 검증 실패의 진단은 `AssessmentOutputError(ValueError)`에 담기고, 검색 결과의 `agentic.assessment_failure`에도 남긴다. 기존 `stop_reason=controller_error`와 근거 차단 동작은 유지한다. 파싱된 값은 `Assessment`로 재검증해 잘못된 dict가 뒤 단계에서 AttributeError를 내는 경로도 막았다.

## 오프라인 검증과 보존

새 `test_assessment_diagnostics.py` 16개는 잘림+파싱 동시 발생, 파싱 실패, 빈 parsed, 스키마 실패, 잘못된 응답 envelope, usage 누락·부분·음수·bool·문자열, 직접 발생 파싱 예외, 공급자 quota 오류, 민감 정보 비노출을 재현한다. 외부 모델은 전부 mock이며 테스트 삭제·skip 추가 없음.

관련 회귀 **181 passed, 1 existing skipped, 3 deprecation warnings**. 저장된 최소 실측 결과와 `tmp/eval-budget.sqlite`는 해시로 보존 여부를 확인한다. 장부는 **$2.056964/$5**, 단계 한도 probe $0.10 / development $0.25 / comparison $3 / judge $1 / browser $0.15이며 기존 보수적 예약액도 그대로 둔다.

전체 backend 회귀도 **1591 passed, 1 existing skipped, 3 deprecation warnings**로 통과했다. 실측 원본과 장부 20개 파일의 SHA256이 동일하며 장부 SHA256은 `eacb4ae95f7f1c8185762deb2b2dfb85fa474f7760aa167b3ab63abb9b1abfc5`다.

기존 ag-022 실패 실행은 원시 파싱 결과·종료 코드가 저장되지 않았으므로 이 변경으로 과거 원인을 소급 확정할 수 없다. 다음에 별도로 승인된 단일 실측을 할 때부터 세부 원인을 확인할 수 있다. 이번에는 그 호출을 하지 않았다. 실제 원인 해결·새 후보 품질 통과·운영 배포로 해석하지 않는다.
