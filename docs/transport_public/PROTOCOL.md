# 외부 호출 transport 관측과 버퍼형 스트리밍 비교 — 사전 기준

2026-10-14. 기존 200건을 재사용하지 않고 새 공개 before 100건과 after 100건을 측정한다. 동일 `budget_public100.py`의 4질문×5개 실제 DB 상태×5반복, 합성 계정, Gemini 3.8 Flash/low, read tools, 최신 DB 조회, pipeline=true, client_reuse=false를 유지한다. stale 대화값 대신 확정·수정·삭제·목표 변경·전날 기록의 현재 DB 값 반영과 미저장을 검증한다.

양쪽 `COACHING_TRANSPORT_TIMING=true`로 같은 HTTPX 통신 경로를 사용한다. 현재 기본 aiohttp와 이번 before 결과를 직접 성능 비교하지 않는다. before=invoke, after=buffered_stream이며 나머지 모델·프롬프트·도구·저장 정책은 동일하다. 버퍼형 스트림은 기존 최종 검증 뒤 전달한다. 첫 모델 text 수신과 사용자 첫 표시를 구분한다.

## 관측 경계

- connect: DNS+TCP 연결 합계. DNS 개별 시간은 현재 HTTPX trace에서 분리하지 않는다.
- tls: TLS 협상.
- send_headers/body: 요청 전송.
- wait_headers: 응답 헤더 수신까지 대기. 네트워크·서버 큐·prefill·추론·생성 일부가 섞이며 순수 서버 대기가 아니다.
- receive_body: 본문 수신. 스트림에서는 생성 중 대기가 포함된다. invoke와 이 구간만 직접 비교하면 잘못된 해석이다.
- provider_roundtrip: 양쪽 공통 외부 호출 전체 경계. 중첩 timer를 합산하지 않는다.
- 서버의 순수 추론/생성 시간은 API에 공개된 별도 duration이 없어 미측정으로 남긴다. thinking 토큰 수나 첫 text 시간으로 역산하지 않는다.

가장 큰 관측 구간을 before 100건에서 확인한다. wait_headers가 지배적인 경우 버퍼형 스트리밍을 후보로 검증하되 헤더가 빨라진 것만으로 개선 판정하지 않는다.

## 동결 판정

전후 각100건, 모든 실패·타임아웃 분모 유지, 완료/최신값/미저장 100/100, proposal 0, 동일 Gemini 3.1 Pro judge 5기준 각100건 완료 및 비회귀, 전체 중앙값≥5% 개선, 전체 p95 비회귀, provider_roundtrip 중앙값≥10% 개선, 실패율 비회귀. source SHA·고정 사례·build 확인. 계측 누락은 채택 차단한다. 순차 시간대·20조건 반복·자동 judge 한계를 기록한다. 미달하면 invoke 및 transport_timing=false로 복구한다.

## 공식 근거와 구현 제한

[HTTPX trace extension](https://www.python-httpx.org/advanced/extensions/), [custom transport](https://www.python-httpx.org/advanced/transports/), [Google SDK](https://googleapis.github.io/python-genai/), [Gemini thinking](https://ai.google.dev/gemini-api/docs/thinking).

설치 버전 google-genai 2.29.0 / langchain-google-genai 4.4.0 / HTTPX 0.28.1 / httpcore 1.0.9. SDK는 custom transport 지정 시 aiohttp 대신 HTTPX를 사용한다. LangChain은 같은 client_args를 동기·비동기 client에 전달하므로 두 transport 인터페이스를 구현한다. 내부 표준 client로 CA·환경 proxy·request timeout extension을 유지하며 재시도를 추가하지 않는다. trace info의 URL/header/body/exception 내용은 읽거나 저장하지 않는다. 고정 label과 duration만 기존 요청별 sink에 전달한다.
