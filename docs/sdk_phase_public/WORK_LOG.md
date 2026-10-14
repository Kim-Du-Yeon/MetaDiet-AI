# 작업·가설·실패 기록

## 계측부터 시작

기존 timer가 SDK 준비를 경로에 따라 포함/제외하던 문제를 분리했다. `sdk_prepare_meal`, `tool_bind_meal`, `provider_roundtrip`을 추가했고 실패 시에도 finally로 시간을 남긴다. 개인정보·메시지·credential은 계측 payload에 넣지 않는다. 전체1030 passed, 기존1 skipped를 확인하고 `3fc5aed` 계측 코드를 공개 배포했다. 이번 기준100건은 이 코드로 새로 측정하며 과거100건을 재사용하지 않는다.

첫 배포 확인 probe는 6.34초 후 답변 없이 종료됐다. LangSmith trace `3ba6d856-23d4-4dde-bd1a-5fc826037721`는 provider 응답 대기 중 `CancelledError`였다. 모델504나 입력검증 오류로 단정하지 않는다. [실패 probe](before_probe.json)를 보존하고 [Render 배포 공식 문서](https://render.com/docs/deploys)를 확인한 뒤 안정화된 별도 [probe](preflight_retry/before_probe.json)를 실행했다. 이 요청은 정상 완료·최신값·미저장과 phase 라벨을 확인했다. 정확한 취소 발신자는 확정하지 못했다. 둘 다 정식100건 밖의 배포 확인이다.

Render 배포 로그의 Live 시각은13:45:54 KST, 실패 probe 시작은13:45:44였다. `/health`에 새 commit이 보여도 전체 트래픽 전환 완료와 같다고 판단하지 않는다. 배포 중 요청이라는 시간상 근거는 있지만 취소의 정확한 메커니즘을 증명한 것은 아니다.

## 연결 재사용 후보의 근거와 범위

측정 중 외부 호출 구간이 가장 컸고 SDK 준비에도 수백ms가 들었다. 설치된 LangChain은 모델 객체마다 Google Client/HTTP 연결 풀을 생성한다. 요청마다 새 client를 만들면 HTTP 연결 풀을 재사용할 수 없다는 [HTTPX 공식 가이드](https://www.python-httpx.org/async/)를 확인했다. 모델·prompt·thinking·영양 기록 캐시를 바꾸지 않고 **provider와 그 HTTP client를 재사용하는 한 변경**으로 SDK 준비와 외부 연결 비용을 줄일 수 있는지 실험한다. 외부 호출 중 순수 네트워크와 생성 시간을 분리해 입증한 것은 아니며 cold connection 기여는 아직 가설이다.

후보는 기본 비활성 `COACHING_CLIENT_REUSE=false`이며, 최신 request DB 문맥이 검증된 직접 후속 코칭에만 적용한다. 첫 추천·Supervisor·복잡한 요청·Vision·eval은 기존 provider 생성 경로다. 단일 provider 슬롯에 모델·역할·temperature·max_tokens·thinking·timeout·retry·credential hash·provider class와 실행 loop를 비교한다. 설정이나 loop가 다르면 재사용하지 않고 새 provider를 만든다. 슬롯 수가 누적되지 않으며 환경 변경은 배포에서 새 프로세스로 적용된다. 사용자 메시지·응답·도구 binding·수치는 저장하지 않는다. `bind_tools`는 요청별로 다시 만든다.

[SDK 준비 로컬100+100](local_preparation100.json)은 합성 키와 실제 SDK 객체로 네트워크 없이 실행했다. 새 생성 중앙값1.004초, warm 재사용은0.01ms 미만이다. 서버와 다른 Windows 로컬 환경의 준비 비용일 뿐 공개 응답 개선 근거로 대체하지 않는다. 최초 코드 검토에서 direct native client close가 LangChain cleanup flag를 건너뛰는 문제를 지적받았다. [공식 aclose API](https://reference.langchain.com/python/langchain-google-genai/chat_models/ChatGoogleGenerativeAI)와 설치 소스를 확인하고 `await provider.aclose()`로 수정·재검증했다. owning loop의 lifespan 종료에서만 해제한다.

동시10개 메시지/config 격리, binding 분리, 설정7종 변경, role/sync/loop 경계와 종료 tests를 추가했다. 기준100건이 끝나기 전 후보를 공개 활성화하거나 속도 개선이라고 주장하지 않는다. 전체 중앙값5% 개선·p95 비회귀·모델 단계10% 개선·품질5항목 비회귀 등 [사전 기준](PROTOCOL.md)을 유지한다.

## 기준100건 완료 후 후보 선택

[기준 phase 보고서](baseline_phases.json): 전체 중앙값7.918초/p95 11.021초, SDK 준비0.515초/p95 0.681초, tool binding0.002초, provider roundtrip2.760초/p95 5.066초. 완료·최신값·미저장100/100, 실패0건. 가장 긴 provider 호출의 cold 연결 비용을 재사용으로 줄일 수 있는지 검증한다. SDK 준비도 같은 client 생성에서 발생하는 비용이지만 이를 가장 큰 구간이라고 표현하지 않는다. 순수 생성 자체의 개선은 주장하지 않는다.

후보 코드는 `bf37eda`이며 기본 flag는false다. 모델·prompt·추론 설정·tools·budget·현재 DB 조회는 변경하지 않고 단일 provider 재사용만 활성화해 별도100건을 측정한다. 준비·binding·provider timer 경계는 기준 코드와 동일하다. 추가된 cache hit 진단과 lifecycle은 후보의 동작 검증에 사용한다. SDK role/설정/loop·요청 격리·종료를 검토 후 전체1042 passed, 기존1 skipped; 프론트77 passed·production build 통과했다.

## 최종 결과와 복구

[summary.json](summary.json)의 adopt=false. 전체 중앙값6.46%·p95 12.33% 감소, 준비514.69→0.03ms, 외부 호출2760.21→2671.29ms였다. 외부 호출의 약3.22% 개선은 사전 모델 단계10% 기준에 미달한다. 전체 개선이 없다고 표현하지 않으며, 가장 큰 외부 호출 구간을 충분히 해결했다고도 표현하지 않는다. 후보 최장20.64초에서도 provider15.51초가 남았다. 기준·후보 모델호출은 모두 요청당1회로 추가 왕복 원인이 아니며 외부실패0건으로 오류처리 효과도 입증하지 않는다.

서비스 양쪽100완료·최신값·미저장, 후보 cache hit100/100. 품질 judge 양쪽100완료·5항목 각각100/100. 누락 judge 보완이나 낮은 점수 재평가 없이 완료했다. 모델구간 gate 외의 동결 기준은 통과했다.

Render flag를false로 복구하고 Live 후 [rollback/before_probe.json](rollback/before_probe.json)에서 Gemini3.8/low/invoke/default/read, client_reuse=false, provider_constructions=1, 최신600/2000·미저장을 확인했다. Render 환경변수의 저장값false도 AX에서 재확인했다. 복구 과정에서 CDP 클릭이 timeout되어 최신 AX 상태를 읽고 문서화된 element 클릭으로 완료했다. 복구 후 화면 캡처는 브라우저 표시 폭0 오류로 실패했으며 표시 capability 확인 후에도 동일했다. 결과를 조작한 캡처를 만들지 않고 후보의 실제 [캡처](candidate-settings.png)와 복구 API 원본을 구분한다. 기존 브라우저 표시 설정도 복원했다.

합성 계정과 git-ignored env는 [cleanup.json](cleanup.json)의 status=deleted/tombstone_cleanup_pending=false와 users 행 부재를 확인한 뒤 정리했다. 결과 문서는 검증된 runtime bf37eda를 유지하도록 `[skip render]`로 게시한다. 문서 게시로 다시 서비스를 재시작하지 않으며 이후 코드 main push의 자동 배포 설정은 유지한다.

Git core.autocrlf=true 환경에서 judge source_sha256가 원본 byte에 대응하도록 이 폴더의 JSON은 [Git 공식 attributes 문서](https://git-scm.com/docs/gitattributes)에 따라 `-text`로 보존한다. 원본 byte와 staged Git blob의 SHA256가 같은지 게시 전에 검사한다. 전역 Git 설정이나 이전 실험 원본은 변경하지 않는다.
