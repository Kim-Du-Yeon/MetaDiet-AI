# 후속 질문 의미 평가 실행·승인 v2

2026-10-22. 기존 LangSmith 비공개 프롬프트와 signed v1은 유지한다. 후보는 `../../followup-question-candidate/candidate.json`의 불변 8개 커밋이며, 변경 범위는 `team.compact_followup` 하나다.

## 구현과 비교 범위

- 실제 `DietTeam.execute()`를 사용한다. 강제 라우팅 없이 바로 답변50건은 compact 후속 경로, 필수 질문50건은 supervisor 대조 경로로 실행한다. RAG/모델 라우팅/쓰기 도구는 동일 조건으로 제한하고 합성 기록만 읽는다.
- 원래 balanced-v1의 대화 이력이 compact 경로 조건과 맞지 않아 원본을 보존하고, 유료 출력 생성 전에 v2 입력을 동결했다. `revision.json`과 원본 SHA를 보존한다. 5개 일반 질문 틀을 서로 다른 기록에 반복한 합성 사례이며 독립 실제 사용자100명이 아니다. 개발셋도 같은 질문 유형을 공유한다.
- 물음표 개수 대신 Pro가 불필요한 요구·필수 질문·부족 정보 단정·정확성·충실성·최신값을 평가한다. 실패/타임아웃/미완료는100 분모에 남긴다. 최신값은 의미 채점, 쓰기 없음과 실제 경로는 런타임 관측이다.
- 입력·기록·프롬프트 8개 ID/해시·모델·SDK·실행 코드·답변 해시·rubric·블라인드 AB/BA를 연결한다. 새 입력과 의미 기준이 달라 과거200답변/39쌍 점수를 이번 비교로 전용하지 않는다.
- 새 suite 전용 검증기가 원본 증거와 사전 기준을 재계산한 뒤 기존 receipt/서명 절차로 넘긴다. 기존 승인 기준을 느슨하게 바꾸지 않았다. 비용·사용량 불명/크레딧/한도 중단은 파일로 남겨 자동 재호출하지 않는다.

## 사전 채택 기준

각 조건100건 완전 생성·완전 채점, correct+faithful98/100 이상과2pp 비열등성, 최신값/쓰기 없음100%, 실제 compact50건, 필수 질문48/50 이상과 기존 대비1건 초과 악화 금지, 불필요 요구5건 이상 감소, 근거 없는 확정0건, 후보 p95·생성비 기존1.25배 이내. 전 조건 통과 때만 Staging/운영 승격을 검토한다. 실제 사용자 A/B는 OFF다.

## 예산 재배분

기존 장부 `D:/AX/diet_agent/tmp/eval-budget.sqlite`를 그대로 사용한다. 과거 비용/보수 예약 $8.735208을 삭제하거나 정산 초기화하지 않는다. 원래 전체 상한 $17.139139 및 더 낮은 캠페인 상한 $10.324354를 유지한다.

| 단계 | 과거 사용/예약 | 새 단계 상한 | 이번 잔여 배정 |
|---|---:|---:|---:|
| 개발 | $0.025021 | $0.145021 | $0.120000 |
| 생성 비교 | $3.727260 | $4.277260 | $0.550000 |
| Pro 채점 | $3.824450 | $4.574450 | $0.750000 |
| 최소 확인 | $0.158477 | $0.178477 | $0.020000 |
| 브라우저 | $1.000000 | $1.149146 | $0.149146 |

예상 추가 $0.8~1.2는 추정이며 보장 견적이 아니다. 실제 usage 기반 추정과 장부 예약을 구분한다. 한 번의 Pro 성공은100건 잔여 할당량을 보장하지 않는다. 한도는 프로젝트·모델별이고 RPD는 태평양 자정에 갱신된다. [공식 한도](https://ai.google.dev/gemini-api/docs/rate-limits), [요금](https://ai.google.dev/gemini-api/docs/pricing).

## 실행·재개

저장소 루트에서 프로젝트 Python으로 다음을 실행한다. 유료 명령은 예산·성공한 probe·오프라인 audit를 모두 확인한다. 모델/코드/후보가 바뀌면 과거 증거를 재결합하지 않는다.

```powershell
$py='D:/AX/diet_agent/backend/venv/Scripts/python.exe'
$run='docs/prompt_control/clarification-balanced/execution-v2/run-final'
& $py backend/scripts/eval/run_clarification_comparison.py audit --folder $run
& $py backend/scripts/eval/run_clarification_comparison.py probe --folder $run --allow-paid
& $py backend/scripts/eval/run_clarification_comparison.py generate --folder $run --allow-paid
& $py backend/scripts/eval/run_clarification_comparison.py judge --folder $run --allow-paid
& $py backend/scripts/eval/run_clarification_comparison.py summary --folder $run
```

같은 run에서 probe를 반복하지 않는다. fatal/unknown 사용량의 `stop.json`은 자동 해제하지 않는다. 재개는 원인·장부·기존 결과를 먼저 검토한다. 일반 개별 실패는 분모에 유지한다. 검증기는 미완료를 승인하지 않는다. 승인 CLI의 `evaluate`에 이 결과 폴더를 전달한 뒤에만 서명 publish가 가능하다. publish와 태그 승격은 별도 절차다.

## 실행 증거

`run/`은 잘못된 eval model override가 외부 호출 전에 거부된 기록이다. 사용액 증가0. 평가 역할의 환경설정을 사용하도록 수정하고 회귀 테스트를 추가했다. `run-final/route-audit.json`의200회는 실제 경로+가짜 모델의 오프라인 검사이며 품질/속도 실측이 아니다. `run-final/pro-probe.json`은 Pro 성공과 정산 $0.000886을 기록한다. 최종 실측 결과는 해당 폴더 원본과 아래 결과 절에 기록한다.

## 최종 결과 — 생성 완료 / 품질 채점 한도 차단

| 지표 | 기존 v1 | 후보 v2 |
|---|---:|---:|
| 생성 시도/완료 | 100/100 | 100/100 |
| 생성 실패율 | 0% | 0% |
| 실제 compact 적용 | 50/100 | 50/100 |
| 쓰기 없음 | 100/100 | 100/100 |
| 전체 응답 평균 | 6.307초 | 6.336초 |
| 전체 응답 p95 | 10.862초 | 12.188초 |
| 생성 usage 기반 비용 추정 | $0.183533 | $0.196821 |
| Pro 완전 채점 | 4/100 | 4/100 |
| 품질·최신값 검증 | 미완료 | 미완료 |

후보 p95는 약12.2%, 생성비는 약7.2% 증가했다. 생성 응답의 속도·비용만 보면1.25배 조건 안이지만, 품질 개선 증거가 없으므로 채택하지 않는다. 첫 응답 지연은 이번 invoke 비교에서 따로 측정하지 않았으며 위 지연은 전체 응답이다. 4쌍은 모두 correct+faithful로 채점됐지만 이를 전체 정확도100%라고 보고하지 않는다. 미채점96건에는 실패1쌍·미시도95쌍이 포함된다. 필수 질문 대조군은 아직 Pro 채점되지 않았다. 실패/미완료를 제외한 품질 통과율로 채택하지 않는다.

Pro 최소 확인은 성공했지만 채점5번째 요청에서 `GoogleRateLimitError / quota_exhausted`가 발생했다. 현재 저장된 안전 오류에는 quota metric/ID가 없어 이번 오류가 RPM/TPM/RPD 중 어느 것인지 확정할 수 없다. 이전 날짜의 RPD 진단을 이번 오류의 원인으로 전용하지 않는다. 공식 문서의 모델·프로젝트별 제한에 따라 용량이 변하며 단일 성공 호출이100쌍 여유를 증명하지 않는다. 추가 probe/재시도·다른 프로젝트 우회는 하지 않았다.

현재 장부 **$9.183194**(기존$8.735208 유지, 이번 추가 예약/정산$0.447986), 낮은 상한 잔여 **$1.141160**이다. 생성·성공 채점의 usage 기반 비용 합계와 장부는 다르다. 실패 호출 사용량이 없어 해당 최대 예약을 유지했고, 마이크로달러 반올림도 적용된다. stage별 장부는 comparison$4.107724/judge$3.891086/probe$0.159363/development$0.025021/browser$1.000000이다. 예약은 실제 청구서 확정액이 아니다.

승인 CLI `evaluate`는 실제 미완료 결과를 `Missing/duplicate grades`로 거부했다. 후보 등록·Staging 승격·Production 승격·배포·새 공개 브라우저 검증은 하지 않았다. 운영은 기존 signed v1이며, 실제 사용자 A/B는 OFF다. 유료 실행은 `stop.json`으로 차단되어 자동 재개하지 않는다. 이후 용량과 예약을 검토하고 승인된 재개 절차를 마련할 때도200개 답변과4개 채점을 보존해야 한다. 아직 남은 것은95쌍 신규 채점과 실패1쌍의 제한적 재검증이며 답변 재생성이 아니다.

오프라인 검증: unit1541 passed; security/RAG/integration196 passed·기존 optional1 skipped. 새 skip/삭제 없음. 최종20개 실행 계약 테스트 및 기존25개 계약 테스트 통과. 프론트/운영 동작 변경이 없어 프론트 빌드·공개 배포는 수행하지 않았다. 독립 코드 검토에서 추가 중요 결함 없음.

원본: [생성](run-final/paired.json), [채점](run-final/judges.json), [요약·해시](run-final/summary.json), [상태·비용](run-final/status.json), [중단](run-final/stop.json).

후속 채점 재개: [RPD 확정 진단·Batch 재개·예산·실행 상태](RESUME.md). 기존 run-final은 최초 중단 시점 원본으로 보존하며 이후 결과는 resume-batch에 별도 보관한다.
