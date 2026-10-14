# 작업 기록

- 이전 실제 로그의 Gemini 504/HTTPX ReadError를 기준으로 제한 재시도 범위를 결정했다. 공급자 내부 원인은 확인되지 않았다.
- `retry_external`: 일시 네트워크/408/429/일부5xx에만 1회(1초+jitter), 모델 재시도도 durable model budget 예약. 읽기만 감싸며 쓰기·전체 Agent 재실행 금지. 전체 deadline과 취소 유지.
- 코드 검토에서 실패 SSE에 진단 정보 누락 발견: 실패 체크포인트와 SSE에 안전한 오류 유형·재시도 여부·단계 시간을 보존. 원문/건강 수치/비밀값은 추가하지 않았다.
- 실패 주입 테스트는 실패 프레임 이후 task 예외도 전파하는 기존 계약을 처음에 놓쳤다. Python asyncio 공식 문서와 실제 스택을 확인해 예외 전파도 검증하도록 테스트를 수정했다. https://docs.python.org/3/library/asyncio-task.html
- 전체 회귀에서 구형 스트림 저장 형식까지 바뀐 1개 회귀를 발견했다. v2에만 추가 진단을 저장하도록 제한하고 재실행: **987 passed, 기존 1 skipped, 3 deprecation warnings**. 테스트 삭제/추가 skip 없음.
- 공개 평가 코드와 사전 프로토콜 커밋: `b7f79abf86def6453843349b3b2267e88f68b463`. 양쪽 동일 커밋/오류 복구 정책, 예산 pipeline flag만 비교.
- 자격증명은 git-ignored env에 저장하고 별도 합성 계정만 사용한다.
- 기존100: completed/fresh/no-write 모두100, 외부 오류 이벤트0. 후보100도 모두100, 외부 오류 이벤트0. 서비스 자연 발생 오류 재시도는 이번 표본에서 관측되지 않았으며, 오류 복구 효과의 인과적 입증은 아니다.
- 첫 후보 준비 요청은 `Mode mismatch`로 중단됐다. Render Live만 보고 측정하지 않고 실행 계측을 확인해 잡아냈다. 환경변수 UI에 false가 남아 있었으며, 값 표시를 켜고 편집한 true를 확인한 뒤 저장·재배포했다. 첫 준비 원본은 `after_probe_wrong_mode.json`, 올바른 준비 원본은 `after_probe.json`. 둘 다100건 밖이다. https://render.com/docs/configure-environment-variables
- 기존 답변 judge에서 GoogleAPIError504 두 배치(총10개 평가)가 실패했다. `before_quality.json` 원본을 보존하고 기존 `--retry-failed` 옵션으로 같은 모델의 누락 결과만 `before_quality_retry.json`에 보완했다. 모두 완료됐다. 이미 완료된 낮은 점수를 덮어쓰지 못하게 source hash·모델·실패 인덱스 일치를 검사하는 보완 집계 테스트를 추가했다. 최초90/100과 보완100/100을 따로 보고한다. 속도 표본/분모는 바꾸지 않는다.
- 후보70번째 응답22.15초 중 model_meal17.14초, budget_storage1.765초, 모델1호출, 재시도0. 느린 표본도 그대로 유지했다.
- 최종 후보judge100/100 완료, 다섯 기준각100/100. 기존 보완 결과도각100/100. 자동 판정 모든gate 통과해Render true를 유지하고render.yaml에도true를 명시했다. 최종 설정 캡처 `render-adopted-true.png`와 후보100건 실행 계측으로 확인했다.
- 최종 전체 회귀988 passed, 기존1 skipped. 공개 합성 계정 삭제/연결행 제거 및 임시자격증명 삭제 완료(`cleanup.json`).
