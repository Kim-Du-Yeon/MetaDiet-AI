# RPD 진단과 남은96쌍 채점 재개

2026-10-22. 모델·프롬프트·동결100사례·200개 답변·기존 완료4쌍·비용 장부를 유지했다. 기존 실패1쌍도 원본과 prior-attempts에 보존한다. 새 전송은 남은96쌍만 대상으로 한다.

## 원인 확인

AI Studio 실제 브라우저에서 Tier1 Pro 한도 RPM25/TPM2M/RPD250을 확인했다. 1일 최대 사용량은13/25·26.21K/2M·246/250으로 표시됐으며 최대15분 보고 지연이 있다. 별도 짧은 probe가 성공했으나, 실제 실패 쌍 재채점에서 HTTP429와 `generativelanguage.googleapis.com/generate_requests_per_model_per_day`·`GenerateRequestsPerDayPerProjectPerModel`이 반환되어 **RPD 초과를 확정**했다. RPM/TPM 초과로 추정해서 재시도를 반복하지 않았다. 과거 오류 원문을 복원한 것은 아니며, 재현한 현재 오류의 명확한 metric이다. 계정·프로젝트 ID·키·오류 원문은 저장하지 않았다.

[안전한 API 진단](resume-1/quota-diagnostics.json), [UI 관측](quota-ui-observation.json), [최소 probe](resume-diagnostic.json). 한도는 프로젝트별이며 RPD는 태평양 자정에 갱신된다. [공식 한도](https://ai.google.dev/gemini-api/docs/rate-limits).

## 재개 방식

기존 동기 중지 결과를 삭제하지 않고 새로운 결과 폴더를 만들었다. 원본 raw SHA를 코드에 고정해200개 답변을 그대로 복사하고, 완료4쌍의 점수·usage·answer binding을 그대로 보존했다. 원래 실패1쌍은 attempts 이력으로 남기고 최종 판단100분모와 전송 실패 이력을 구분한다. 입력·rubric·실제 모델·AB/BA 순서는 변경하지 않았다.

재개 동기1회도 RPD로 막혀 추가 동기호출을 중단했다. 공식적으로 동기와 별도 한도를 사용하는 **Gemini native Batch** 경로로 남은96쌍을 넘긴다. 기존 제출 intent·예약·idempotent 정산 로직을 재사용한다. 모델·system instruction·user payload·temperature0·thinking low·출력 상한2048·JSON schema는 유지하지만, 첫4쌍은 동기/나머지는 Batch라는 전송 차이가 있다. 같은 모델이라도 전송 방식의 결과 동등성을 별도 보장하는 것은 아니다. 생성 응답 지연은 기존200개 생성 실측이며 Batch 대기 시간을 거기에 섞지 않는다.

8쌍씩 최대 비용을 예약해 제출하고 완료 usage를 실제 Batch 단가로 정산한다. 응답은 반환 순서가 아니라 key로 결합하며 누락·중복·usage 불명은 예약을 유지하고 영속 accounting-stop으로 신규 제출을 막는다. 모호한 제출 결과는 자동 재제출하지 않는다. 이미 제출한 key는 다음 제출에서 제외한다. 같은 완료 결과를 재수집해도 중복 청구 정산이나 점수 추가가 없다.

Batch 목표 처리 시간은24시간이고 더 빨리 끝날 수도 있다. 완료 전에는 품질 비교 완료로 표현하지 않는다. [공식 Batch](https://ai.google.dev/gemini-api/docs/batch-api).

## 예산

기존 누적$9.183194에서 시작했다. 짧은 probe 정산$0.001030과 RPD 실패 호출의 보수 예약$0.037560을 보존해 Batch 전 누적은$9.221784이다. 실패를 무료로 처리하지 않았다. 원래 전체$17.139139 및 낮은 캠페인$10.324354 상한을 유지했다. comparison 잔여 중$0.12를 judge로 옮겨 comparison cap$4.157260/judge cap$4.694450으로 조정했으며 총 stage cap 합계는 같다. 다른 단계는 유지했다. 최초 history floor도 유지한다.

Batch 예약은 실제 비용이 아니다. 최대 bound 때문에96쌍 전체를 한 번에 예약할 수 없으므로 묶음 정산 후 다음 묶음을 제출한다. usage의 표준 단가 환산과 실제 할인 Batch 비용을 구분한다. 기존 summary의 judge_known_usage_estimate_usd는 표준 단가 환산이며 Batch 실제 청구 추정은 각 job actual_batch_cost_usd와 장부에 기록한다.

## 명령어

```powershell
$py='D:/AX/diet_agent/backend/venv/Scripts/python.exe'
$run='docs/prompt_control/clarification-balanced/execution-v2/resume-batch'
# 이미 prepare한 폴더를 덮어쓰지 않는다.
& $py backend/scripts/eval/batch_clarification_resume.py collect --folder $run --allow-paid
& $py backend/scripts/eval/batch_clarification_resume.py submit --folder $run --chunks 1 --allow-paid
```

collect는 기존 job을 조회하고 알려진 usage만 정산한다. submit은 key 재사용·회계 중지·원본 SHA·기존 grade·예산을 검사한다. 원본 run-final/resume-1은 변경하지 않는다.100쌍 완전 채점 후 원래 사전 기준과 서명 CLI를 통과할 때만 Staging/Production 검증을 진행한다. 운영 v1과 실제 사용자 A/B OFF는 유지한다.

## Batch 출력 형식 진단과 재사용

초기72개 native Batch 요청의 직렬화된 JSON schema에 `$defs/$ref`가 남아 있었고, 실제 응답에 중첩 object 대신 flat 이름 필드·이름 없는 배열 등이 섞여 나왔다. SDK 소스에서 동기 structured output의 JSON schema 경로를 확인했으며, 전송별 표현 차이가 관측됐다. `$ref`가 모든 실패의 유일 원인이라고 단정하지 않는다. 마지막24요청은 같은 필수 필드를 참조 없이 인라인한 schema로 전달해 차이를 확인한다. 질문·답변·채점 기준·모델·temperature/thinking/output cap은 유지한다.

원문 text·finish reason·usage는 raw-grades에 보존한다. 명시적 `a_correct` 등14필드가 모두 있고 정확한 타입일 때만 중첩 object로 구조 변환한다. root a/b의 bool/null 요약 플래그는 품질 지표로 사용하지 않는다. 필드 없는 배열, 누락, 문자열 boolean, 추가 미지 필드는 추측하거나 보정하지 않는다. 파싱 실패 후 구조만 복구한 경우 원래 실패 행을 parse-history에 남기며 모델 재호출/중복 정산 없이 원문을 재검증한다. 해당 변환이 모델 의미 판단의 정답을 보장하는 것은 아니다.

검토: 원본 binding·완료4쌍 보존·중복 정산·회계 중지·엄격한 구조 변환을 독립 코드 검토했다. 실제 사용자 A/B나 운영 품질 성과로 표현하지 않는다.

## 최종 실행 결과

남은96쌍을 native Batch12묶음으로 모두 제출·수집·실사용량 정산했다. **새 답변 생성0회**, 원본200답변·기존 완료4쌍·과거 실패/비용을 보존했다. 최종100쌍 중 유효54쌍/형식 검증 실패46쌍/미시도0쌍이다. 모든 유료 job은 terminal이고 미정산 예약 job은 없다. 과거 실패 호출의 보수 예약은 그대로 유지한다.

| 항목 | v1 | v2 |
|---|---:|---:|
| 생성 완료 | 100/100 | 100/100 |
| 최종 유효 Pro 채점 | 54/100 | 54/100 |
| 채점 형식 실패 | 46/100 | 46/100 |
| correct+faithful 확인 | 53/100 | 53/100 |
| 필수 질문 확인 | 25/50 | 24/50 |
| 불필요 요구(채점된 사례) | 0 | 0 |
| unsafe_commitment 라벨(채점된 사례) | 0 | 1 |
| 최신값 확인 | 54/100 | 54/100 |
| 실제 쓰기 없음 | 100/100 | 100/100 |

53/100은 확인된 정답 수이며 나머지46개를 오답으로 확정한 실제 정확도가 아니다. 53/54≈98.1%도 형식 통과 부분집합의 값이므로 전체 정확도로 일반화하지 않는다. 필수 질문 수치도 미채점 사례를 포함한 확인 하한이다. 형식 통과 표본에 선택 편향이 있고, 합성·반복 템플릿이며 임상 평가/실제 사용자 만족도가 아니다. 이름 없는 배열은 필드 순서를 추측하지 않고 실패로 유지했다. 참조 없는 schema 적용 후에도24개 중13개만 유효했으므로 `$ref` 제거만으로 해결됐다고 주장하지 않는다. 추가 유료 재시도는 하지 않았다.

`cb2-eval-missing_choices-09`에서 Pro는 v2의 대체 메뉴 제안을 unsafe_commitment로 표시했다. 실제 원문은 이전 선택지가 없음을 밝히고 새 메뉴를 **대체**로 표시해, 과거 선택지를 사실처럼 꾸몄다는 해석은 과하다. 다만 필요한 두 선택지를 다시 묻지 않아 요청을 충족하지 못한 점은 확인된다. 이 사례는 **변경 compact 프롬프트가 실행되지 않은 supervisor 대조군**이라 후보 텍스트가 원인이라고 단정할 수 없다. temperature0에서도 두 생성 결과가 다를 수 있다. [원문과 수동 검토](resume-batch/qualitative-review.json). 자동 점수/기준을 결과에 맞춰 수정하지 않았다.

100쌍 완전 품질 판정과 사전 개선 조건을 충족하지 못해 **v2 미채택, signed v1 유지**다. 실제 승인 CLI도 `Judge answer binding/incomplete`로 거부했다. Staging·Production 승격/새 배포·공개 상담 재검증은 수행하지 않았다. 실제 사용자 A/B는 계속OFF다. 이 결과는 '96쌍 채점 시도·정산 완료'이며 '100쌍 품질 검증 완료'가 아니다.

최종 누적 장부 **$9.533327**, 이번 추가 **$0.350133**, 캠페인 잔여 **$0.791027**이다. 원래 전체$17.139139 및 낮은$10.324354 상한 모두 유지했다.96쌍 Batch usage 기반 비용은 **$0.311543**이며 나머지는 짧은 확인$0.001030과 사용량 미확인 RPD 실패 예약$0.037560이다. 실제 청구서 금액과 동일하다고 보장하지 않는다. 최초 생성/채점 사용액을 삭제·재설정하지 않았다.

검증은 unit1552 passed, security/RAG/integration196 passed·기존 optional1 skipped다. 새 테스트 삭제/skip 없음. 원본 바이트 해시·블라인드 binding·누락/추가 필드·엄격한 타입·역순 Batch key·중복 정산·회계 불명확 영속 중지를 검증했다. 독립 검토의 지적을 수정했고 최종 중요 지적은 없었다.

원본: [최종 상태/비용](resume-batch/status.json), [채점/usage](resume-batch/judges.json), [100분모 요약](resume-batch/summary.json), [형식 실패 목록](resume-batch/judging-failures.json), [파싱 실패 보존](resume-batch/parse-history.json), [원문](resume-batch/raw-grades/). 다음 개선은 별도 개발셋에서 평가자 출력 안정성을 검증하는 것이며, 이번 결과를 임의로 보정하거나 유료 재시도를 자동 반복하지 않는다.

46쌍의 후속 오프라인 분석에서는 점수 추측 없이1쌍만 추가 복구해 유효55/100이 됐다. 기존 결과는 덮어쓰지 않았다. [복구·45쌍 보류 사유·유료 호출 전 비용 제안](OFFLINE_RECOVERY.md).
