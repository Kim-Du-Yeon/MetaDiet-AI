# 단순 후속 코칭 모델 비교 — 사전 기준

2026-10-14. 기존200건과 답변길이 가설의 초기 기록은 삭제하지 않는다.

## 원인 분석과 가설 수정

기존200건은 모델호출중앙값2.596초/p954.378초, 최대17.144초이며 모델호출수는1이다. 반복도구조회/재시도로 길어진 것은 아니다. SDK가 기록한 output_tokens는 **답변+추론 토큰**이다. 실제답변길이와모델시간 r=.0565(답변길이중앙값172.5자/p95217자), 결합토큰과모델시간 r=.4557. 따라서 긴답변을줄이는가설은근거가약해활성화하지않는다. 기존brief프로토콜을수정해숨기지않고 [초기기록](../brief_followup_public/WORK_LOG.md)에남긴다.

기존SDK소스는 candidates_token_count+thoughts_token_count를output_tokens로저장하며output_token_details.reasoning을제공하지만이전로그는그상세항목을보존하지않았다. 추론·네트워크·공급자대기 각각의원인은확정할수없다. 이번에검증할변수는 **단순·읽기전용·최신문맥확인된후속코칭의 모델 하나**이다.

후보 gemini-3.5-flash-lite, 기존 gemini-3.8-flash. 양쪽thinking_level=low, 동일프롬프트/도구/최신조회/BUDGET_PIPELINE=true/invoke/예산/재시도. 첫추천·복잡한계획·기록·확정·근거검색라우팅에는기존모델을유지한다. 답변길이flag와compact prompt는false.

호출smoke에서후보응답을확인했다. SDK는Flash-Lite가fixed sampling defaults를사용하므로temperature를무시한다고경고했다. 코드설정은양쪽0이지만효과적인샘플링까지동일하다고주장하지않는다. 이는모델교체에내재한차이이며결과및한계에포함한다.

공식출처:
- https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite — 저지연·subagent용모델, function calling 지원
- https://ai.google.dev/gemini-api/docs/thinking — 두모델모두low지원, 작은hardtoken상한은답변을잘라낼수있음

## 동일조건 100시도씩

기존측정은 f42e4a3/default 모델에서 이미시작됐으나 답변길이flag는false이며 실제동작을바꾸지않았다. 이100건을그대로보존해기존조건으로사용한다. 후보커밋은모델override설정/선택/모델용평가검증만추가하며 동일질문·상태·프롬프트·추론·모델호출상한·저장경로를유지한다. 두런타임커밋및diff를보고한다.

- 네질문×다섯실제DB상태×다섯반복=전후100각각, 같은합성계정·순서·dataset SHA256·오래된300/2200대화. 최신600/2000·850/2000·0/2000·600/1800·0/1900각검증.
- 준비/읽기는계측밖. 준비요청은별도파일. 기존before원본복사시해시동일성확인. 실패/timeout/blocked는교체/삭제하지않고분모100유지.
- 각응답build+followup_direct/low/invoke/default style/해당모델명을확인. 실제모델·도구호출수와외부실패를보고한다.
- 같은blindGemini judge의relevant/actionable/no_invented_intake/no_false_save_claim/concise 기준. 누락된judge만원본보존후같은모델로별도보완가능, 완료된낮은등급재평가금지.

## 채택 기준 (이전답변길이실험의수치기준유지)

양쪽100완료·최신값·미저장·judge100완료, proposal0,5품질항목각각비악화; 실패포함전체시도중앙값≥5%감소; p95비악화; 모델시간중앙값≥10%감소; 모든시간finite-positive및매칭조건충족. 어느하나불충족하면 FOLLOWUP_MODEL=default로복원. 실패를가리는추가요청으로100성공을맞추지않는다.

합성계정은작업후삭제,자격증명은gitignored env만사용. 시간대순차비교/20반복조건/동일제공자judge의한계. 실제사용자평균·부하·임상정확성인증아님. 공개100건실험전외부모델키/이름노출없는단일provider smoke는기능확인으로만분류한다.
