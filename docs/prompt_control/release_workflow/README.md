# 새 후보 커밋 선택 → 평가 재사용 → 서명 → LangSmith 승격

2026-10-22. CLI를 일반화했다. 후보 이름·전체 커밋·결과 폴더를 인자로 받고, 과거 실험 파일을 수정하지 않는다. 실제 사용자 A/B와 캐시는 OFF 유지. 이 절차 검증에는 신규 Gemini 생성/채점0회이며, 기존200답변·100쌍 채점을 재사용했다.

## 1. LangSmith에서 수정하고 커밋 ID 복사

Prompts → 개별 프롬프트 → Playground 수정 → Commit → 전체64자리 커밋 ID를 복사한다. 입력 변수와 출력 계약을 유지한다. 개별 프롬프트의 Production 태그는 MetaDiet 운영을 바꾸지 않는다. 운영은9번째 `metadiet-release-manifest`의 승인된 번들을 사용한다.

## 2. 후보 선택

프로젝트venv를 활성화한 저장소 루트에서 실행한다. `<전체64자리커밋>`은 실제 값으로 교체한다. `--select`는 여러 번 지정할 수 있고 나머지는 승인된 기준 릴리스에서 상속한다. `latest`/환경 태그/짧은 커밋/중복 선택은 거부한다.

```powershell
python backend/scripts/approve_prompt_release.py prepare --base docs/prompt_control/approved-release.json --name candidate-20261022 --select "team.compact_followup=<전체64자리커밋>" --output tmp/candidate-20261022.json
```

모든8개 프롬프트는 비공개 저장소에서 실제 커밋으로 읽고 텍스트·변수·출력 계약·크기를 검증한다. 후보는 아직 서명되지 않았으며 서버에서 실행할 수 없다. 기존 후보/승인 파일을 덮어쓰지 않는다.

## 3. 기존 평가와 정확히 일치하는지 먼저 검사

```powershell
python backend/scripts/approve_prompt_release.py evaluate --candidate tmp/candidate-20261022.json --results docs/prompt_control/comparison --output tmp/receipt-20261022.json
```

8개 커밋·본문·계약이 기존 조건과 같을 때만 재사용한다. 릴리스 표시 이름만 달라진 동일 번들은 재생성 없이 재승인할 수 있다. 실제 본문/커밋이 다른 후보는 과거 점수를 빌릴 수 없다. source hash·실제100사례씩·중복/누락·행별 커밋/해시·평가 모델/루브릭·실패/비용/최신값을 검사하고 게이트를 원본에서 다시 계산한다. summary의 `selection`이나 `candidate_passed` 값을 믿고 서명하지 않는다.

신규 결과의 채점은 generation binding과 질문·확정 수치·a/b 실제 답변의 answer binding을 모두 대조한다. 같은 프롬프트라도 답변을 다시 생성했다면 과거 채점을 사용할 수 없다. binding 도입 전 자료는 코드에 고정한 원본3파일 SHA와 일치하는 역사적 비교 한 건만 허용한다. 이는 외부 모델 실행을 암호학적으로 증명하는 원격 attestation이 아니며, 서명 키를 가진 운영자의 위조를 방어하는 체계라고 주장하지 않는다.

## 4. 일치하는 평가가 없을 때만 새 비교

현재 검토된 품질 어댑터는 **compact 후속 상담**이다. 원래의 동일100사례·같은 모델/설정·AB/BA·동시성1·사전 개선 기준을 유지한다. 내부 조건명v1/v2는 기준/후보의 비교 슬롯이며 릴리스 이름과 독립적이다.

아래는 유료 모델 호출이므로 예산·할당량을 확인한 뒤 실행한다. 이번 절차 검증에서는 실행하지 않았다.

```powershell
python backend/scripts/eval/benchmark_prompt_control.py --candidate tmp/candidate-20261022.json --folder tmp/comparison-20261022 --allow-paid
python backend/scripts/eval/judge_prompt_control.py --folder tmp/comparison-20261022 --allow-paid
python backend/scripts/eval/analyze_prompt_control.py --folder tmp/comparison-20261022
python backend/scripts/approve_prompt_release.py evaluate --candidate tmp/candidate-20261022.json --results tmp/comparison-20261022 --output tmp/receipt-20261022.json
```

기존 장부와 비용 상한은 그대로 사용한다. 완료된 생성/채점은 재사용하고 다른 후보·사례의 결과 폴더와 섞지 않는다. 새 실험 ID는 후보 릴리스 이름에 연결한다. 예산·크레딧·할당량 실패는 원본/재개 지점을 보존한다. 개별 품질 실패는 분모에 남긴다. 이번 v2는 목표 오류 감소를 입증하지 못해 새 이름을 붙여도 승인되지 않는다.

**범위 제한:** 커밋 선택은8개 모두 지원하지만, 번역·목표·음식 추출 등 후속 상담에서 실행되지 않는 프롬프트의 의미 변경은 이 어댑터로 승인할 수 없다. 해당 경로의 코드 검토된 평가 어댑터·동결 사례·사전 기준이 추가되어야 한다. 단순 계약 검사 통과나 사용자가 작성한 임의의 `passed=true` 파일을 품질 검증으로 간주하지 않는다. 모든 Agent의 범용 자동 품질 평가나 화면 전용 승인 시스템을 완성했다고 표현하지 않는다.

## 5. 검증 결과 재확인 후 서명·비공개 등록

```powershell
python backend/scripts/approve_prompt_release.py publish --candidate tmp/candidate-20261022.json --results tmp/comparison-20261022 --receipt tmp/receipt-20261022.json --output tmp/approved-20261022.json
```

기존 결과를 재사용한 경우 `--results`에는3단계의 실제 결과 폴더를 사용한다. 후보·receipt·원본 결과를 다시 대조하고 원격8개 커밋을 읽어 내용이 같은지 확인한 다음 서명한다. 개인키는 ignored `backend/.env.prompt-signer`에만 보관하며 GitHub/LangSmith/Render로 전송하지 않는다. LangSmith에는 공개 서명과 불변 커밋 명세만 저장한다. **등록은 승격이 아니다. Production/Staging 태그를 자동 이동하지 않는다.**

## 6. LangSmith에서 승인된 명세만 승격·복구

`metadiet-release-manifest` → 방금 출력된 명세 커밋 → Promote → Staging. 별도 검증 인스턴스/설정에서 해당 채널을 읽어 확인한 뒤 Production으로 승격한다. Staging 태그가 검증 서버를 자동 생성하거나 품질 테스트를 실행하지는 않는다. MetaDiet 관리자 화면에서 검증된 릴리스 다시 가져오기 또는60초 갱신 후 전체 실제 커밋/해시/오류를 확인한다. 진행 중 요청/HITL은 원래 버전을 유지한다.

롤백: 명세의Production → Rollback history → 이전 승인 커밋 → 서버 갱신 확인. 현재 운영 기준v1은 `45f094b2…`다. 실제 사용자 A/B와 명시적 캐시를 켜는 단계는 포함하지 않는다.

## 이번 검증 증거

- [선택 후보](candidate.json) → [원본 재계산 승인 receipt](receipt.json) → [비공개 등록·서명 readback](approved.json). 동일한 기존v1의 표시 이름만 `workflow-reuse-v1`로 변경했다.
- [실제 LangSmith 미승인 번역 커밋으로 만든 후보](unapproved-candidate.json)는 평가 범위 부족으로 차단되었다. 승인 파일/receipt를 만들지 않았고 운영 태그를 이동하지 않았다.
- 테스트는 다른 커밋의 점수 재사용, 오래된 receipt, 원본 변조, 중복/미완료 시도, 실패v2, 다른 후보의 채점, 같은 후보의 다른 답변 채점, 다른 경로의 무근거 승인을 거부한다.
- 과거 결과를 재사용한 절차 검증이지 새로운100쌍 성능 실험이 아니다. 모델 비용 추가0, 기존 장부 불변. 운영/브라우저 최종 확인은 아래 증거 파일로 연결한다.

[LangSmith 공식 SDK 안내](https://docs.langchain.com/langsmith/manage-prompts-programmatically) · [승격/롤백 공식 안내](https://docs.langchain.com/langsmith/manage-prompts).

기존 무인자 실행/`--alias` 방식은 새 후보의 근거 연결 없이 재사용하지 않도록 중단했다. 이제 `prepare/evaluate/publish`와 명시적 파일 인자가 필요하다. 이 절차는 CLI 기반이며 LangSmith 화면만으로 평가·서명을 끝내는 관리 UI를 추가한 것은 아니다.

실제 화면에서 `f9bfaf10…`의 `workflow-reuse-v1`을 Staging으로 지정하고 원격 전체8개 커밋·서명을 검증했다. Production은 `45f094b2…`의v1로 유지했다. [실제 Staging/Production readback](staging-readback.json). 별도 Staging 웹 서버를 띄운 검증으로 표현하지 않는다. [검사·비용·실제 미승인 차단 요약](checks.json).

검증 종료 후 Staging도v1로 복구했다(Production 변경 없음). [실제 브라우저 승격·복구 상태](langsmith-ui.json)。
