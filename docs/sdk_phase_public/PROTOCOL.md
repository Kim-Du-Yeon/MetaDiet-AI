# SDK 준비·외부 호출 병목 실험

2026-10-14. 기존 200건과 후속 300건에서 모델 timer의 SDK 생성 위치가 달라 세부 원인을 확정하지 못했다. 이번에는 동일 계측 코드로 새 baseline 100건을 먼저 측정하고 가장 큰 구간을 근거로 후보 하나만 선택한다. 기존100건의 시간을 baseline으로 재사용하지 않는다.

## 계측

- `sdk_prepare_meal`: lazy provider 생성. API 키·모델·timeout 검증과 SDK/HTTP client 준비 포함.
- `tool_bind_meal`: 허용된 read tool 스키마 변환·binding.
- `provider_roundtrip`: `ainvoke` 또는 buffered stream의 SDK 호출 전체. 직렬화·연결·네트워크 대기·서버 추론 및 생성·응답 파싱 포함. 순수 서버 생성 또는 순수 네트워크 시간이라고 주장하지 않는다.
- 기존 `model_meal`, DB read, durable budget, graph, 전체 응답 시간도 함께 보존. 중첩 timer를 합산하지 않는다. 실패에서도 finally로 elapsed를 남긴다. 원문·health 값·credential을 timing payload에 넣지 않는다.

## 조건과 채택

기존 질문4개×현재 DB상태5개×5반복, fresh 읽기, 과거300/2200의 stale history, 동일 synthetic 계정, warm 직렬 공개API. 양쪽100시도 이상으로 완료/실패/timeout/blocked를 모두 남긴다. Gemini3.8 Flash / low / default answer / read tools / invoke / budget pipeline 그대로 유지. 품질은 동일 Gemini judge 5기준을 blind 평가하고 완료된 낮은 점수를 재평가하지 않는다. 기록 확정·수정·삭제·목표 변경·전날 기록 상태가 응답의 current 값에 반영되는지 확인하고 식사·목표의 미변경도 비교한다.

전체 중앙값5% 이상 개선, p95 비회귀, 실패율 비회귀, 각 품질 항목 비회귀, 양쪽100건 최신값·미저장 검증을 만족할 때만 적용한다. 실패·judge 누락은 숨기지 않는다. 후보 변경 전 측정 근거·단일 변경을 이 폴더에 기록한다. 단일 반복 합성셋, 순차 시간대, 자동 judge라는 제한을 명시한다.

사용자 영양 정보의 요청 간 캐시는 도입하지 않는다. 후보가 client 연결 재사용이면 요청 메시지·응답·도구 binding·사용자 상태를 캐시하지 않고 loop/config/key 변경과 종료 lifecycle을 검증한다. 후보가 기준 미달이면 복구하고 이유를 GitHub·포트폴리오에 남긴다.

공식 근거: [Google SDK client](https://googleapis.github.io/python-genai/), [Google SDK source](https://github.com/googleapis/python-genai/blob/main/google/genai/_api_client.py). 새 계측에서도 provider 내부 thinking·생성·네트워크를 완전히 분리하지 못하면 이를 명시한다.
