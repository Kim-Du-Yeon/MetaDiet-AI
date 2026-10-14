# 통신 경계 조사와 공개 검증 작업 로그

## 사전 조사·구현

- 기존 `provider_roundtrip`은 연결·서버 처리·SDK 직렬화/파싱·callback을 포함해 순수 추론 시간으로 해석할 수 없었다.
- 설치 SDK를 조사했다. Google SDK는 aiohttp 사용 시 HTTPX hooks를 실행하지 않는다. LangChain 4.4.0은 같은 client_args를 동기/비동기 SDK client에 전달한다. 공개 custom transport 경로를 이용해 두 인터페이스를 구현했다. private SDK monkey patch나 인증/SSL 우회는 하지 않았다.
- HTTPX 공식 trace의 시작/완료/실패 이벤트에서 고정 stage label과 duration만 기록한다. info에 들어 있는 header, URL, body, exception 내용은 읽거나 보관하지 않는다. 연결에는 DNS가 합쳐져 있고, 헤더 대기와 본문 수신은 서버 내부 추론/생성 시간과 다르다.
- 새 테스트는 구현 전 3건 실패를 확인했다. 실제 설치 SDK 호환 테스트는 회귀 suite의 live Gemini 차단 fixture 때문에 최초 실패했다. 실제 호출을 허용한 것이 아니라 synthetic key·MockTransport만 쓰도록 모델 경계를 명시적으로 대체해 네트워크 없이 재검증했다.
- 통신/기존 client 재사용 16 tests 통과. 전체 backend 1046 passed, 기존 1 skipped, 기존 deprecation warnings 3개. Frontend 23 suites/77 tests·build 통과.
- 독립 검토에서 재귀 없는 delegate transport, timeout extension, 환경 proxy/CA, 고정 numeric trace, per-attempt 격리를 확인했다. 스트림의 헤더/본문 timer 이동을 성능 향상으로 오해하지 말라는 검토 의견을 평가 기준에 반영했다.
- runtime commit `20f3cfd84baa585c94079c12d0d4066305ae0094`를 main에 푸시했다. 선택적 flag는 기본 false다. 공개 실험에서는 true로 저장·재배포했고 Live 전환 후 별도 사전 요청을 실행했다. 사전 요청 완료·최신값·미저장·transport timing을 확인한 뒤 새 정식 before 100건을 시작했다.

## 증거 제한

Render 환경 설정의 AX 상태와 공개 응답을 확인했지만 현재 탭 screenshot은 `Cannot take screenshot with 0 width`로 실패했다. 화면 크기를 임의로 바꾸거나 증거 이미지를 만들어 대체하지 않았다. 캡처 없는 사항은 문서와 원본 API 결과로 구분한다.

API에는 현재 사용 경로에서 서버 큐/추론/생성 각각의 duration이 없으므로 네 구간의 정확한 분해를 완료했다고 주장하지 않는다. [사전 기준](PROTOCOL.md)의 observable transport 경계와 별도 첫 text 시간을 측정한다.

## 새 기준 100건 완료

전체 중앙값8384.22ms/p95 10420.69ms, provider 2864.86/4571.18ms. connect 중앙값32.55ms, TLS16.89ms, 헤더 대기2749.39ms, 본문 수신0.52ms. 100건 모두 완료·최신값·미저장, 오류/보류/proposal 0. 최장 요청 pair87의14.09초 중 헤더 대기8.424초, connect28.45ms/TLS5.78ms, 모델1회였으므로 이 요청을 반복 모델 호출·연결 협상 병목으로 설명하지 않는다.

기준100건 품질 평가를 시작하고 후보 설정을 buffered_stream으로 바꿨다. 양쪽 같은 runtime commit/HTTPX 경로와 나머지 모델·DB·저장 설정을 유지한다. 후보는 아직 채택하지 않았다. 사전 기준에 따라 비교한다.

## 후보 100건 완료·성능 미달·오류 분석

전체 중앙값8454.92ms/p95 11374.91ms, provider 3099.12/5712.84ms. 헤더 대기 중앙값2102.67ms로 줄었지만 본문 수신833.93ms로 늘고 전체 provider는 느려졌다. 모델 첫 text 중앙값2142.70ms는 최종 답변 전달 시간8377.62ms와 구분한다. 성능 기준 미달이므로 품질 평가 완료를 기다리는 동안에도 invoke/transport_timing=false 복구 배포를 시작했다.

후보100건 모두 완료·최신값·미저장, 최종 실패/보류/proposal 0. 다만 pair87에서 GoogleAPIError retry=true 1건을 확인했다. LangSmith trace `5ade5b76-577f-4ed2-94d5-09abe03e9ad3`의 실패한 LLM child에서 **500 INTERNAL**을 확인했고 root는 정상 완료했다. [안전하게 추출한 근거](recovered_failure.json). [Gemini 공식 장애·재시도 문서](https://ai.google.dev/gemini-api/docs/troubleshooting)는 5xx 등의 일시 오류에 제한 재시도를 권고한다. 기존 read/model 전용 최대1회 jitter backoff가 복구했으며 저장 전체나 write tool을 재실행하지 않았다. 응답11.07초와 오류를 원본에서 제외하지 않았다. 해당 요청의 모델 budget 계수는2회, 나머지는1회였고 read tool 계수는양쪽모두2회였다. 서버 내부 500 원인을 애플리케이션 로그만으로 확정하지 않는다.

최장 후보 pair65는22.07초, connect13.54ms/TLS12.03ms/헤더 대기15.77초/provider16.72초였다. 최종 오류가 없는 긴 지연과 일시500 재시도 사례를 구분한다.

임시 통계 출력 명령에서 external_failures가 숫자가 아닌 list인데 sum으로 직접 더해 TypeError가 났다. 원본 shape와 [Python 공식 sum/len](https://docs.python.org/3/library/functions.html#sum)을 확인하고 list 길이를 합산하도록 명령을 수정했다. 서비스 실패가 아니며 원본 측정값은 변경하지 않았다. 양쪽 기록된 외부 오류는0→1건이다.

## 최종 검증·복구·정리

동일 Gemini 3.1 Pro judge를양쪽100건씩 완료했고 5기준각100/100이었다. source_sha256·고정 사례·배포 commit·phase 완전성 검증 후 summary의adopt=false를 확인했다. 중앙값/p95/provider 개선 기준이 모두미달했다. 복구 Live 후 rollback/before_probe.json에서invoke·transport timer 없음·최신 열량/목표·미저장을 확인했다. 이 단일 복구 요청을100건 성능 통계에 넣거나 복구 성능의 대표값으로 사용하지 않는다.

마지막 집계 코드 변경 후 전체 backend1046 passed·기존1 skipped를 다시 확인했다. 일회용 합성 계정을 기존 공개 계정삭제 흐름으로 삭제했고 users row 없음과 git-ignored 자격증명 파일 삭제를 확인했다. 실제 사용자 계정은 변경하지 않았다.

보고서 작성 중 README patch가부분 문장만 exact match로 지정돼 실패했다. 파일의 실제전체행을 다시 읽고 제목을 기준으로 patch를 적용했다. 보고서 생성과README 수정은 재확인했으며 측정 원본은 변경하지 않았다.
