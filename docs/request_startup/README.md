# 요청 ID 기반 시작 지연 분석

## 계측 경계

클라이언트가 생성한 UUID를 `stream_run_id`와 `X-Request-ID`로 공유한다. 재연결은 같은 요청 ID와 새 `X-Attempt-ID`를 사용한다. 서버는 UUID 형식만 받아들이며 형식이 잘못되면 새 ID를 생성한다. ID는 인증이나 권한의 근거가 아니다. API 응답 헤더, 고정 이름의 준비 구간 로그와 LangSmith invocation metadata에 연결한다. 대화 원문·이메일·건강 수치·토큰은 새 계측에 넣지 않는다.

브라우저 `metadiet:request-timing` 이벤트와 `[request_timing]` 콘솔 JSON은 fetch 시작·헤더 수신·첫 서버 진행·완료·실패 및 표시 기회를 기록한다. React 화면 갱신 뒤 두 번의 requestAnimationFrame으로 측정한 것은 **paint opportunity**이며 실제 픽셀 표시 시각을 보장하지 않는다. 비활성 탭에서는 지연될 수 있어 visibility를 같이 남긴다. 브라우저와 서버의 서로 다른 시계를 직접 빼지 않는다. 서버는 ASGI 진입→헤더/첫 body 송신과 인증·잠금·복원·모델 구간을 같은 요청 ID로 연결한다.

## 고정 평가

공개 HTTPS·실제 모델·실제 DB를 사용하는 합성 계정만 사용한다. 4개 고정 질문을 각 25회, 동시성 4로 실행한다. 일반 추천/후속 질문 50건과 명시적 읽기 전용 목표/추세 검토 50건이다. 의도적으로 이전 대화에 낡은 숫자를 넣고 현재 합성 DB의 섭취·목표 숫자와 비교한다. 모든 실패·타임아웃·근거 보류를 보존한다. 비교 조건 사이 합성 데이터와 질문을 바꾸지 않으며 domain snapshot이 일치해야 한다. API 100건은 브라우저 100건 렌더링 실험이 아니다.

기존 평가 도구의 transport 실험 설정은 별도 전송 타이밍 필드를 요구해 첫 시도에서 중단됐다(`before.json`에 원본 보존). 기존 직렬 평가 시도는 수집 도구를 교체하며 중단했고 `matched/before.json`을 pilot로 보존한다. 이 pilot들은 정식 고정 100건 비교 결과와 섞지 않는다. 중단 당시 진행 중 요청의 최종 응답은 수집되지 않았으므로 그 구간으로 성공률을 산출하지 않는다.

## 후보 개선

기록을 변경하지 말라는 명시적 요청과 목표 검토/진행/근손실 위험 표현이 함께 있고, pending 제안과 기존 목표 위임이 없는 경우에만 목표 전문 Agent로 바로 연결한다. 목표 Agent는 기존의 프로필·섭취·측정·근거 조회 도구를 가지며 쓰기 도구를 주지 않는다. Supervisor 선택/중계 모델 왕복을 제거하되, 동일 실행 예산·위임 카운터·최종 근거 정책을 유지한다. 전략 변경 요청과 불명확한 요청은 기존 Supervisor 경로다. 후보 채택은 고정 100건 전후 비교 뒤 결정한다.

## 해석 원칙

첫 서버 진행과 답변 완료를 구분한다. 20초 이상 걸리는 답변이 있더라도 첫 진행까지 20초 지연을 재현한 것으로 해석하지 않는다. 숫자 일치와 무변경 검사는 제한된 품질 지표이며 임상적 타당성·전체 답변 품질 평가가 아니다. 기동 직후/휴면 복구 성능과 실제 사용자 평균을 보장하지 않는다.

공식 문서: [FastAPI 미들웨어·CORS 헤더](https://fastapi.tiangolo.com/tutorial/middleware/), [MDN requestAnimationFrame](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame), [ESLint no-loop-func](https://eslint.org/docs/latest/rules/no-loop-func). 빌드에서 no-loop-func가 계측 콜백의 외부 let 참조를 검출했으며 const 상태 객체로 바꾼 뒤 재빌드했다. 경고를 비활성화하지 않았다.
