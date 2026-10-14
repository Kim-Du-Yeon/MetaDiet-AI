# 외부 호출 계측과 버퍼형 스트리밍 공개 100쌍

**연결보다 응답 전 대기가 컸다. 스트리밍 후보는 전체 시간·p95를 개선하지 못해 채택하지 않았다.** 기존 측정200건을 재사용하지 않고 새 기준100건과 후보100건을 같은 runtime commit `20f3cfd84baa585c94079c12d0d4066305ae0094`에서 측정했다.

| 지표 | HTTPX 일반 응답100건 | HTTPX 버퍼형 스트림100건 |
|---|---:|---:|
| 전체 응답 중앙값 | 8.384초 | 8.455초 |
| 전체 응답 p95 | 10.421초 | 11.375초 |
| 사용자 첫 표시 중앙값 | 8.311초 | 8.378초 |
| 외부 호출 중앙값/p95 | 2.865/4.571초 | 3.099/5.713초 |
| 연결(DNS+TCP) 중앙값 | 32.55ms | 10.68ms |
| TLS 중앙값 | 16.89ms | 5.37ms |
| 헤더 대기 중앙값 | 2749.39ms | 2102.67ms |
| 본문 수신 중앙값 | 0.52ms | 833.93ms |
| 모델 첫 text 수신 | 미측정 | 중앙값2.143초/p95 4.571초 |
| 최종 실패·보류 | 0/100 | 0/100 |
| 외부 오류를 경험한 요청 | 0/100 | 1/100, 재시도로 복구 |
| 최신 섭취·목표 열량 반영 | 100/100 | 100/100 |
| 식사·목표 미변경/proposal | 100/100·0 | 100/100·0 |
| 동일 judge 품질5기준 | 각100/100 | 각100/100 |

전체 중앙값 약0.84%, p95 약9.16%, 외부 호출 중앙값 약8.18%가 증가했다. 헤더가 빨라져도 생성 중 대기가 본문 수신에 포함되므로 전체 개선으로 해석할 수 없다. 내부 첫 text 수신은 최종 검증 후 전달하는 사용자 첫 표시와 다르다. 중첩 timer와 각 구간 중앙값을 더하지 않는다.

## 병목·오류 근거

기준 최장 pair87은14.09초 중 헤더 대기8.42초였다. 후보 최장 pair65는22.07초 중 헤더 대기15.77초, 연결·TLS 합계약26ms였다. 두 요청의 모델 budget 계수는1회였다. 이 사례의 주원인을 연결 협상이나 반복 모델 위임으로 설명하지 않는다. **내용이 도착하기 전 대기**가 지배적이지만 서버 큐·prefill·추론·생성 각각의 비율은 현재 API로 확인할 수 없다.

별도 후보 pair87에서 GoogleAPIError retry=true를 기록했고 LangSmith 실패 LLM child의 **500 INTERNAL**을 확인했다. 기존 최대1회 backoff가 복구했고 root 정상 완료·최신값·미저장을 확인했다. 해당11.07초와 오류를 원본에서 제외하지 않았다. 기준은모든 요청 모델1회, 후보는99건1회·1건2회였다. read tool 계수는양쪽모두2회다. [추출한 안전한 오류 근거](recovered_failure.json), [Gemini 공식 재시도 지침](https://ai.google.dev/gemini-api/docs/troubleshooting). 제공자 내부 500 원인까지 확정한 것은 아니다.

## 구현·판정·원본

[HTTPX trace](https://www.python-httpx.org/advanced/extensions/)와 [custom transport](https://www.python-httpx.org/advanced/transports/)를 사용했다. 설치 Google SDK는 custom transport가 있으면 aiohttp 대신 HTTPX를 사용한다. 양쪽 같은 경로로 비교하며 **기존 aiohttp 운영 수치와 이번 기준을 직접 비교하지 않는다.** LangChain은 client_args를 동기·비동기 client에 함께 전달하므로 두 인터페이스와 종료를 검증했다. CA·환경 proxy·timeout을 유지하고 header/URL/body/exception 내용은 계측에 저장하지 않는다.

모델·프롬프트·thinking/low·read tools·현재 DB 조회·budget pipeline을 유지했다. 요청 간 건강정보 캐시나 HITL 저장 변경은 없다. 전체5%·외부 호출10% 개선과 p95 비회귀라는 [사전 기준](PROTOCOL.md)에 미달해 [adopt=false](summary.json)다. 공개 설정을 invoke/transport_timing=false로 복구하고 [공개 복구 요청](rollback/before_probe.json)으로 확인했다. 계측 코드는 기본false의 선택적 기능으로 남는다.

[기준100건](before.json), [후보100건](after.json), [기준 품질](before_quality.json), [후보 품질](after_quality.json), [기준 단계 분석](baseline_phases.json), [판정](summary.json), [작업·오류 해결](WORK_LOG.md), [계정 정리](cleanup.json).

```powershell
backend\venv\Scripts\python.exe backend/scripts/eval/summarize_sdk_phases.py --folder docs/transport_public --experiment transport
```

전체 backend1046 passed·기존1 skipped, frontend23 suites/77 tests·build 통과. 설치 SDK MockTransport 호환·안전한 실패 timing·동시 trace 격리와 기존 client reuse 회귀를 검증했다. raw JSON은 개행을 변환하지 않아 judge source_sha256을 유지한다.

## 한계와 다음 단계

- 4질문×5개 DB 상태×5반복의 직렬 합성 평가다. 100명의 평균/p95, 임상 정확도, 동시 부하를 입증하지 않는다. 순차 시간대·자연 트래픽·제공자 캐시/부하 차이는 완전히 통제하지 못한다.
- 서버 큐·순수 추론·순수 생성 duration은 현재 응답·SDK에서 확인할 수 없다. 첫 text 시간이나 thinking 토큰으로 역산하지 않는다. 헤더 대기·본문 수신도 순수 서버 계산시간이 아니다.
- 최종 실패0건과 복구된 외부 오류1건을 구분한다. 장애율 개선을 주장하지 않는다. 동일 Gemini 3.1 Pro 자동 judge가 사람 평가나 임상 검증을 대체하지 않는다.
- 선택적 HTTPX 계측은 통신 경로·SDK 준비 비용을 바꾼다. 계측 성공을 운영 성능 개선으로 주장하지 않는다. 운영은 기본 통신을 복구했다.
- 브라우저0width 오류로 설정 캡처를 저장하지 못했다. 설정 상태·Live·공개 원본은 확인했고 증거 이미지를 만들어 대체하지 않았다.
- 다음 후보는 제공자 대기 상한·안전한 fallback 또는 읽기 전용 답변 전달 방식의 별도 설계가 필요하다. 현재 근거로 서버 내부 원인을 단정하거나 검증 전 부분 답변을 공개하지 않는다. 조건별100건 이상·최신값·품질·미저장을 다시 검증한다.
