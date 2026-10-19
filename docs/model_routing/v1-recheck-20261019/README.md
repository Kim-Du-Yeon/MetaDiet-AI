# v1 고정 라우팅 비교 재개 점검

2026-10-19. **현재 운영용 프롬프트 릴리스는 v1 하나, 주요 템플릿 8개입니다.**
시험용 v2는 격리된 임시 디렉터리에만 만들며 운영 릴리스로 추가하지 않습니다.

## 현재 외부 차단 사유

[최소 HTTP 사전 확인 원본](preflight.json). 세 요청은 가용성 점검이며 성능 표본이 아닙니다.

| 역할 | 결과 | 로그 근거 |
|---|---|---|
| 기존 Flash | 429 RESOURCE_EXHAUSTED | FreeTier 일일 요청 한도20, retry79412s |
| 후보 Lite | 200, 응답 있음 | 1회 최소 생성 성공 |
| Pro 평가자 | 429 RESOURCE_EXHAUSTED | FreeTier 일일·분당·토큰 quota, retry79411s |

따라서 **새로운 조건별 100건 비교는 시작하지 않았습니다.** 기존200건 실패 포함
결과는 [이전 보고서](../README.md#최종200시도-결과--활성화-보류)에 그대로 보존했습니다.
세 번의 사전 요청을 100건 검증이나 성능 개선으로 표현하지 않습니다.
현재 속도·품질·최신 기록 반영·전체 비용은 비교 불가이고 운영 채택 gate=false입니다.

[Google 공식 quota 문서](https://ai.google.dev/gemini-api/docs/rate-limits)는 제한이
키가 아닌 프로젝트 단위라고 명시합니다. 같은 프로젝트의 키 재발급·짧은 재시도로
일일 제한이 해소되지 않습니다. [AI Studio](https://aistudio.google.com/)에서 해당 키가
속한 프로젝트의 사용량·Rate limits·결제 계층을 확인해야 합니다.
[공식 결제 안내](https://ai.google.dev/gemini-api/docs/billing).
결제·요금제·프로젝트 설정은 이번 작업에서 변경하지 않았습니다.

초기 로컬 점검은 dotenv 상대 경로 때문에 필수 설정 누락으로 실패했습니다.
실행 위치와 무관하게 backend의 무시된 env 파일을 명시해 해결했습니다.
저장한 로그는 HTTP 상태·quota 식별자·usage만 포함하며 키·원본 오류 본문은 제외했습니다.
[Pydantic dotenv 동작](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#dotenv-env-support).

## v1 고정과 복구 검증

평가기 시작 시 v1 릴리스·번들 SHA-256을 확인하고 다른 버전이나 변조 번들은 외부
모델 호출 전에 차단합니다. 결과에도 실제 프롬프트 metadata를 저장합니다.
검색어 번역은 레지스트리의 v1 템플릿을 직접 사용합니다.
[준비 상태와 동일100개 사례 해시](readiness.json)를 저장했으며, 새 실행 건수는 조건별0건입니다.

별도 프로세스에서 **v1 → 합성 v2 → v1**을 읽고 실제 DietTeam 시스템 프롬프트의
해시가 복구되는지 검증합니다. 미등록 v999는 거부해야 합니다. API·DB 호출 없이
합성 설정만 전달합니다. 이것은 **로컬 프로세스 재시작 검증**이며 Render의 실제
배포·재시작이나 답변 품질 복구를 입증하지 않습니다.
[복구 실행 원본](rollback.json)의 v1 두 번은 번들·기본 시스템 프롬프트 해시가 일치하며,
시험용 v2 해시는 다르고 v999의 종료 코드는2입니다. 복구 도구의 첫 검사는 실제 상수명
`BASE_INSTRUCTION`을 `BASE_PROMPT`로 참조해 실패했고 정의와 일치시켜 재검증했습니다.
별도 리뷰에서 차단할 결함은 발견되지 않았습니다.

최종 백엔드 전체 회귀는 **1,420 passed, 기존1 skipped**입니다. 기존 경고3개는
유지했습니다. 프론트·운영 환경·실제 섭취 기록은 변경하지 않았습니다.

```powershell
backend\venv\Scripts\python.exe backend/scripts/eval/verify_prompt_restart.py --output tmp/new-rollback/report.json
```

## 외부 조건 해소 후 실행

1. Flash와 Pro의 사용 가능 quota를 확보한 뒤 최소 생성 확인. 키는 채팅에 보내지 않습니다.
2. 동일 동결100개를 조건별 실행. `PROMPT_RELEASE=v1`과 기존 모델 설정을 유지하며
   실패·timeout 포함 속도/p95·작업별 품질·최신 fixture 반영·usage 비용을 검사합니다.
3. 별도 Pro rubric 완료. 이는 Ragas 지표와 구분합니다. 반복 템플릿 합성평가로
   실제 사용자·임상적 정확도를 주장하지 않습니다.
4. 사전 gate 통과 시에만 제한 활성화·실제 배포 버전/브라우저·복구 검증을 진행합니다.

```powershell
$env:PROMPT_RELEASE='v1'
backend\venv\Scripts\python.exe -u -X utf8 backend/scripts/eval/benchmark_model_routing.py --output-dir tmp/new-v1-comparison --env-file backend/.env --interval 7 --judge
```

시작200건에 코칭 Pro 평가50건과 도구/반복 호출이 추가될 수 있으므로, 생성 모델
각100회만 가능한 quota가 전체 평가를 보장하지 않습니다. 기존 판정 기준인 작업별
비열화 없음·품질≥95%·최신값 전부 반영·비용 완전/평균10%절감·p50 5%개선·
p95 증가5%이내·평가 완료를 유지합니다. Jev는 운영에 연결하지 않습니다.
