# 계산 모드 구분 v4: 분량 환산과 개별 레시피

## 가설과 범위

직전 [v3 비교](../v3-candidate-20261022/RESULTS.md)는 정답·충실성100/100을 달성했으나, 분량만 필요한 고정 기준에서 조리 정보까지 물은3건 때문에 행동 통과97/100이었다. v4는 **‘정확히/실제’라는 표현만으로 레시피 정밀 계산을 가정하지 않고, 요청한 기준을 먼저 구분**한다.

| 요청 | 필요한 정보 | 질문 경계 |
|---|---|---|
| 표준 성분표/제품표에 먹은 양을 곱하는 환산 | 기준값·섭취량 | 기준이 있으면 빠진 섭취량만 요청. 표준값을 실제 레시피의 절대 정확값으로 보장하지 않음 |
| 직접 만든 음식의 재료·기름별 정밀 계산을 명시, 표준값 거부 | 재료별 양·기름/양념·필요 시 완성 총량과 먹은 양 | 실제 빠진 레시피 정보만 요청. 이미 준 섭취량은 반복 질문하지 않음 |
| 기준값·분량 모두 있음 | 추가 입력 없음 | 바로 계산 |
| 제품/이전 선택지 자체가 없음 | 해당 식별 정보 | 메뉴를 만들거나 일반 취향을 묻는 것으로 대체하지 않음 |

수치 계산·저장 승인·소유권·반복 제한·LangGraph·운영 프롬프트는 바꾸지 않는다. `team.base`와 `team.compact_followup`의 평가 전용 로컬 후보만 바꾼다. LangSmith 원격 커밋이나 승인된 릴리스가 아니며 운영에 자동 적용하지 않는다.

## 개발과 사전 기준

새 개발24건은 표준 환산6·개별 레시피6·이미 주어진 기준/분량6·제품/선택지6이다. 동결100건의 질문을 복사하지 않았다. **모델에 calculation_mode 같은 정답 라벨을 전달하지 않는다.** 질문 문구와 제공한 기준표·분량 정보로 구분하게 한다. 개발 기준값은 계산 경로 확인용 합성 수치이며 실제 해당 음식의 영양성분 검증 자료가 아니다.

개발 v3/v4 각24건에서 모든군 정확성·충실성6/6, 필요한3군의 필수 질문6/6, 모든군 추가 질문0, 근거 없는 확정0, 전건 채점·usage 완결을 요구한다. v4 행동 통과가 v3보다 낮으면 본 비교로 진행하지 않는다. 단순히 아무것도 묻지 않는 답변은 통과가 아니다.

본 비교는 기존과 동일100건(10유형×10건,55질문 문구)을 그대로 쓴다. v1/v3 답변200개를 해시·입력·모델·실행 코드로 확인해 재사용하고 v4만100개 새로 생성한다. 기존 v2를 포함한300개 답변과 이전 Pro 원문은 source 복사본으로 보존한다. 답변 조합이 달라졌으므로 v1/v3/v4를 같은 문맥·의미 기준으로 새 Pro 채점하고, 과거 점수를 유리하게 골라 합치지 않는다.

본 v4 선호 기준은 정답·충실성 각각100/100 유지, 행동≥98 및 v1/v3 이상, 필수 질문50/50, 근거 없는 확정0, 최신값·무저장100/100, 전체 불필요 질문이 v3보다 줄고 v1 이하, 생성 p95/비용이 v1의1.25배 이하, 전건 생성·채점·usage 완결이다. 기준·사례·후보·코드는 호출 전에 protocol.json으로 동결한다. 실패·시간 초과·채점 실패를 분모에서 빼지 않는다.

## 실행·재사용·비용

동일 Flash 모델·온도0·low thinking·출력1,024토큰·모델3/도구8회·65초·동시성1·검색OFF를 유지한다. Pro는 동일 Batch·flat named fields 엄격 파서를 사용한다. 기존 v3 실행기는 수정하지 않고 평가 전용 v4 어댑터가 함수 바인딩을 일시 교체·복원해 검증된 Batch 제출·수집·정산·중복 방지 경로를 재사용한다. 이 어댑터를 동시 실행/운영 라이브러리로 사용하지 않는다.

신규 계획은 개발48개 답변, 본 v4 답변100개, Pro 개발24쌍·본100건×3답변이다. 사례1개가 모델1호출은 아니다. 예상 usage 비용 $0.7–1.3. 이전 사용액과 같은 원장을 유지하며 새 요금제·유료 가입은 없다. 최근 Pro Batch가 정상 완료된 것을 용량 확인 자료로 재사용하고, 새 개발 호출/Batch에서 실제 가용성을 확인한다. 이는 전체 계정 할당량 보장을 뜻하지 않는다. 용량·사용량 불명은 예약/원문을 보존하고 재제출하지 않는다.

```powershell
# 프로젝트 venv로, worktree 루트에서 실행
python backend/scripts/eval/run_clarification_v4.py prepare --folder docs/prompt_control/clarification-balanced/v4-calculation-mode-20261022
python backend/scripts/eval/run_clarification_v4.py offline --folder docs/prompt_control/clarification-balanced/v4-calculation-mode-20261022
python backend/scripts/eval/run_clarification_v4.py generate --folder docs/prompt_control/clarification-balanced/v4-calculation-mode-20261022 --development --allow-paid
python backend/scripts/eval/run_clarification_v4.py submit --folder docs/prompt_control/clarification-balanced/v4-calculation-mode-20261022 --development --allow-paid
python backend/scripts/eval/run_clarification_v4.py collect --folder docs/prompt_control/clarification-balanced/v4-calculation-mode-20261022 --development --allow-paid
```

개발 통과 후 `--development`를 빼고 생성·제출·수집한다. 첫2건의 형식 확인 후98건 제출, 두 건도100분모에 포함한다. 오프라인 가짜 모델 결과는 유료 answers 파일에 저장하지 않는다.

## 해석 한계

이미 노출된100건의 반복 진단이다. 독립 holdout·실제 사용자 정확도나 임상 효과가 아니다. 프롬프트2개 조합의 효과이며 개별 문구 ablation은 아니다. 표준 성분표 환산과 실제 레시피의 영양 차이를 검증한 실험도 아니다. 과거 지연을 재사용하므로 실행 시점·원격 부하가 다르고 온도0도 결정성을 보장하지 않는다. 이번에는 본 생성 중 로컬 회귀 검사를 병행하지 않는다. LLM judge 판정 변동은 과거와 새 기준선 결과를 함께 공개한다.

[Gemini 가격](https://ai.google.dev/gemini-api/docs/pricing) · [Batch](https://ai.google.dev/gemini-api/docs/batch-api) · [구조화 출력](https://ai.google.dev/gemini-api/docs/structured-output). 비용은 실제 usage×요율 추정이며 청구서 확정액이 아니다.

## 개발 기능 검증 결과 (성능 우위의 본 근거 아님)

| 지표 | v3 | v4 |
|---|---:|---:|
| 정답·충실성 공동 | 24/24 | 24/24 |
| 전체 행동 | 23/24 | 24/24 |
| 필요한 질문 | 18/18 | 18/18 |
| 불필요 질문 | 1 | 0 |
| 근거 없는 확정 | 0 | 0 |

표준 분량 질문6/6, 개별 레시피 질문6/6, 기준·분량 제공 시 계산6/6, 제품/선택지 필수 질문6/6을 새 후보가 모두 통과했다. 기존 v3는190g×100g당200kcal=380kcal를 맞게 계산하고도 기록 여부를 추가로 요청한1건이 있었다. v4는 계산만 완료했다. [원문 회복 사례](development/recoveries.json), [개발 요약](development/summary.json), [전체 채점](development/judges.json)을 보존했다. 후보를 더 수정하지 않고 본100건에 고정했다.

## 평가 범위 메타데이터 정정

생성 완료 후 개발 요약의 `not_independent_holdout` 값이 잘못된 것을 발견해 참으로 수정했다. [수정 전 원본](scope-metadata-originals/)과 [동일성 검증](scope-metadata-correction.json)을 보존했다. 유료 생성 당시 코드 해시는 protocol의 `paid_generation_code_sha256`, 이후 보고 필드만 고친 해시는 `code_sha256`이다. 개발48개·본300개 답변 행, 프롬프트, 사례, 점수, 합격 기준은 바꾸지 않았으며 이 정정에 모델 호출은 없었다.

최종 결과는 [RESULTS.md](RESULTS.md)에 기록한다.
