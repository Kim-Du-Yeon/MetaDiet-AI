# RAG 실험 계획 — 자료 확보부터 순서 복원

## 1. 코퍼스 확보와 판본 확인

기존 7개에 새 PDF 8개를 추가했다. 보관 폴더에는 15개가 있으며,
비교 코퍼스는 `../nutrition/corpus_manifest.json`에 명시한 10개다.
폴더 전체 glob으로 구판을 함께 재색인하지 않는다.

| 언어 | 선정 자료 | 수 |
|---|---|---:|
| 한국어 | 2025 KDRIs 정오표 적용본: 에너지·다량영양소 / 비타민 / 무기질 | 3 |
| 한국어 | 대한비만학회 2022 요약 지침: 기존 파일, 최신판·이용 조건 검토 대상 | 1 |
| 영어 | WHO 탄수화물 / 총지방 / 포화·트랜스지방 2023 | 3 |
| 영어 | WHO 당류 2015 / 나트륨 2012 | 2 |
| 영어 | ISSN Protein and Exercise 2017 | 1 |

한국어 질의를 유지하고 영어 근거는 보완한다. 영문 자료를 임의 번역한
문장을 원문 근거처럼 저장하지 않는다. 요약본은 원본과 중복 색인하지 않는다.
식품 영양값은 기존 구조화 CSV에서 계산한다.

공식 출처:
- [KDRIs 2025 및 정오표](https://kns.or.kr/fileroom/fileroom_view.asp?BoardID=Kdr&idx=167)
- [WHO carbohydrate](https://www.who.int/publications/i/item/9789240073593)
- [WHO total fat](https://www.who.int/publications/i/item/9789240073654)
- [WHO saturated/trans fat](https://www.who.int/publications/i/item/9789240073630)
- [WHO sugars](https://www.who.int/publications/i/item/9789241549028)
- [WHO sodium](https://www.who.int/publications/i/item/9789241504836)
- [ISSN protein/exercise](https://doi.org/10.1186/s12970-017-0177-8)

`corpus_inventory.json`에 SHA256, PDF 실제 페이지 수, 판본, 적용 대상과
이용 조건을 기록한다. 공개 다운로드와 서비스 상용 이용 허용은 별도로
확인한다. 자료 확보만으로 운영 인덱스를 활성화하지 않는다.

## 2. 판본과 의견 충돌 정책

같은 기관·주제·대상·조건의 신판이 구판을 대체하면 신판을 사용한다.
2025 KDRIs를 사용하는 실험에 2020 KDRIs를 혼합하지 않는다.
연도만 같아도 개정/정오표 버전이 다르면 공식 수정본을 선택한다.
철회·초안 자료는 제외한다. 다른 주제 또는 운동선수/질환 대상인 최신
자료는 일반 성인 지침을 대체하지 않는다. 구판은 회귀·과거 설명용으로 남긴다.

충돌 판정은 문서 전체가 아니라 정규화된 개별 주장 단위로 한다:
`claim_key / 수치·범위 / 단위 / 적용 대상 / 조건 / 권고 강도 /
문서·판본·페이지·원문 / 검토 상태`를 기록한다.

판단 순서:
1. 적용 대상·조건·단위를 확인한다. 불일치하면 같은 수치로 비교하지 않는다.
2. 해당 지침 계열의 최신 유효 개정판만 남긴다.
3. 한국 사용자에는 해당 항목에 적용 가능한 국가 KDRIs를 우선하고 WHO는
   보완한다. 국제 사용자에는 WHO/해당 국가 기준을 우선한다.
   영양소 기준은 KDRIs, 비만의 생활습관 치료는 해당 대상의 비만학회 지침,
   운동인구 단백질은 해당 대상의 운동영양 지침처럼 주제별로 적용성을
   먼저 판단한다. KDRIs가 모든 임상·스포츠 질문을 대체하는 것은 아니다.
4. 같은 적용 범위에서는 공공 공식 지침 → 학회 지침 → 체계적 문헌고찰 →
   단일 연구 순으로 판단하되, 권고 조건·근거 수준을 함께 검토한다.
5. 동일 우선순위의 불일치는 임의 평균·교집합·LLM의 취향으로 해결하지
   않는다. 출처와 차이를 표시하고 수치 전략 적용을 보류한다.

`evidence_policy.py`는 검토된 수치 주장에 대한 결정적 선택기를 제공한다.
원문에서 주장 추출·단위 환산·권고 강도 검토는 별도 검토 단계다.
자동 추출 결과를 곧바로 정책에 등록하지 않는다. 활성화 전 기존 지역
프롬프트와 함께 Evidence Agent → Validator → HITL에 판정 결과를 전달하고,
불해결 상태에서 쓰기 도구가 차단되는 통합 평가까지 완료해야 한다.
현재 코드는 선택기 단위 검증 단계이며 실서비스 통합 완료를 뜻하지 않는다.

골드에는 구판/신판, 정오표, KDRIs/WHO 충돌, 일반성인/운동인구,
단위 불일치, 동순위 불해결, 근거 없는 과식 보상 차감을 포함한다.
의견을 채택한 이유·배제된 근거·정책 버전을 전략 이력과 추적에 남긴다.

## 3. 파서 3종 비교

PyPDF / PDFPlumber / Docling. 동일 원본과 `parser_pages.json`의 동일 24개
PDF 페이지를 사용한다. 이 페이지 목록은 파일 기준 1-based이며
아직 사람 검토 전인 파일럿이다. 본문·표·다단·그림·스캔 유형으로
분류하고 원본 렌더링과 대조한 뒤 최종 24페이지 검토셋을 확정한다.

공통 블록 JSON에 페이지·종류·텍스트·출처를 보존한다. Docling 원본
구조 JSON과 표 HTML, 그림 이미지, 검토 Markdown도 남긴다.
PyPDF/PDFPlumber의 그림 위치 메타데이터는 이미지 이해/OCR 성공이 아니다.
스캔 비교는 Docling + Tesseract kor/eng를 별도 레시피로 기록한다.
OCR 엔진·언어 데이터가 없으면 실패/미실행으로 기록한다.

Windows 파일럿에서 Docling의 기본 docling-parse 백엔드가 무기질 PDF에서
네이티브 access violation을 냈다. 오류는 그대로 보존한다. 공식 지원하는
PDFium 백엔드를 명시한 별도 레시피로 전체 동일 10문서를 다시 비교한다.
서로 다른 백엔드를 성공한 문서마다 조용히 섞지 않는다. 종료 코드가 0이어도
네이티브 오류 로그가 있으면 성공 표본으로 채택하지 않는다.

정확도는 검토된 원문으로 CER/핵심 수치·단위 보존/표 셀 정확도/읽기
순서/페이지 정합성을 평가한다. 추출 글자 수·표 개수만으로 승자를 정하지 않는다.

## 4. 청킹 3종 비교

- 페이지: 페이지 전체를 검색/문맥 단위로 사용한다. 큰 문맥 비용도 측정한다.
- Parent–Child: 1800자 부모 / 400자 자식 / 50자 겹침. 자식을 검색하고
  부모를 중복 제거 후 반환한다. 검색 hit와 반환 context 지표를 분리한다.
- 제목·문단/구조 블록: 1200자 기준, 제목 정보를 유지하고 표를 단일
  블록으로 보존한다. 과대 표는 그대로 유지하고 문맥 비용을 측정한다.

공통 출처·페이지를 유지한다. 파서가 제목을 감지하지 못한 경우 그 제약을
기록한다. 기존 semantic+cap 청킹 결과는 이전 기준선으로 별도 보관한다.

## 5. 통제 실험과 평가

먼저 3×3 파일럿의 실행 가능성과 파싱 오류를 확인한다. 파서 하나를 고정해
청킹 효과를, 청킹 하나를 고정해 파서 효과를 비교한다. 최종 후보에서
Gemini 임베딩의 차원 설정 후보와 Dense/Hybrid/Reranking을 비교해 변수 효과를 구분한다.
OpenAI API는 새 실험에서 호출하지 않는다. 과거 OpenAI 결과는 과거 모델·코퍼스·
평가 조건을 표시한 참고 기록으로만 보존하고 동일 조건의 신규 비교로 해석하지 않는다.
같은 질문·동일 문맥 예산·k·생성 모델·평가 모델을 사용한다.
Parent 확장 문맥을 Ragas와 생성 모델에 동일하게 전달한다.

검토된 RAG 골드 및 전체 평가 120개(개발/최종 분리), 파서24페이지를 준비한다.
Recall/MRR/nDCG·출처/페이지/핵심 구절·Ragas faithfulness/context recall·
지연·임베딩/문맥 토큰·비용을 기록한다. LangSmith dataset/experiment에는
코퍼스 SHA·파서/청킹/임베딩/검색/정책 버전을 연결한다.
검토 전 예제나 파싱 통계는 최종 품질 점수로 발표하지 않는다.

실행:
```
backend\venv\Scripts\python.exe backend\scripts\eval\compare_rag_recipes.py --docling-backend pdfium --output backend/artifacts/rag-matrix-new-run
```
스크립트는 별도 `backend/artifacts/parser-runtime`의 선택적 의존성을 사용하고,
결과는 `backend/artifacts/rag-matrix`에 저장한다. 읽기 전용 파일럿으로서
Pinecone/Supabase/활성 BM25를 변경하지 않는다.
이후 기존 계획의 실제 streaming → Deep Agent/MCP → kind → Cue UI 순서를 유지한다.

## 6. 서비스 모델과 평가 모델 역할 분리

이전 GPT-4o-mini 서비스 / GPT-4o Ragas 구성의 목적은 실행 비용·지연과
평가 품질을 분리하는 것이다. Ragas는 모델이 아니라 평가 라이브러리이며,
서비스가 만든 답변과 실제 검색 문맥·검토된 참조 답변을 judge 모델에 전달한다.
운영 중 Validator는 응답/제안 수정에 참여하는 서비스 구성 요소다.
오프라인 Ragas/Agent 평가 judge와 구분한다.

| 역할 | Gemini 구성 | 검증 원칙 |
|---|---|---|
| 실제 Supervisor/전문 Agent·답변 생성 | Gemini 3.8 Flash | 실제 도구·구조화 출력·지연·비용 검증 |
| Vision·운영 Validator | Gemini 3.8 Flash 기본 | OCR 원문 확인 및 결정적 수치·권한 검사 유지 |
| 최종 Ragas/Agent LLM judge | Gemini 3.1 Pro Preview 후보 | 계정 접근/구조화 출력/Ragas 호환과 채점 보정 후 채택 |
| 수치·권한·라우팅/도구/HITL 검증 | 코드 기반 테스트 | LLM 점수로 통과 여부를 대체하지 않음 |

확인 근거: [공식 모델 목록](https://ai.google.dev/gemini-api/docs/models).
3.8 Flash는 Stable, 3.1 Pro는 Preview이다. 모델 이름이나 Pro 등급만으로
judge가 더 정확하다고 가정하지 않는다. 최신성과 평가 적합성은 별도로 검증한다.
우선 사람/원문으로 검토한 20~30개 채점 기준 사례에서 판단 일치도와
오류 유형을 비교한다. 동일 Gemini 계열의 편향은 블라인드 평가와
독립 검토로 보완한다. 운영 모델·평가 모델·프롬프트·Ragas 버전을 고정한다.

설정은 기존 GEMINI_MODEL / GEMINI_VISION_MODEL / GEMINI_EVAL_MODEL을 사용한다.
현재 기본값은 모두 gemini-3.8-flash로 같으며, 역할별 호출 경로만 분리되어 있다.
Pro 후보를 검증한 뒤 GEMINI_EVAL_MODEL만 변경한다. 이번 문서 갱신으로
기존 개인 .env나 모델 기본값을 바꾸지는 않았다. Judge 실패는 평가 실패로
기록하고 다른 모델로 조용히 대체해 같은 실험에 혼합하지 않는다.

파서·청킹·임베딩 비교에서 답변 생성 모델은 서비스 모델로 고정하고
동일한 최종 judge로 모든 후보를 평가한다. 평가 대상 Agent의 답변,
확장된 실제 검색 문맥, 검토된 참조 답변을 보존한다. LangSmith에는
서비스/평가 역할, 모델 ID, 토큰·비용·지연, 데이터셋·정책·레시피 버전을
분리해 기록한다. 최종 점수에는 judge ID를 반드시 함께 표시한다.

## 7. Gemini 전용 실행 조건 (사용자 확정)

생성·Vision·운영 Validator·오프라인 judge·검색 및 평가용 임베딩을 모두
Gemini로 구성한다. OpenAI 키를 요구하거나 자동으로 OpenAI에 폴백하지 않는다.
retriever는 Gemini Embedding 2 전용 adapter로 전환했다. Ragas에도 Gemini
임베딩을 명시적으로 주입하고 OpenAI 키 설정과 직접 의존성을 제거했다.
기존 벡터는 새 Gemini 빌드 manifest와 일치하지 않으면 검색에서 차단한다.
전체 코퍼스 재색인과 활성화는 별도로 검증해야 한다.

다음 RAG 품질 평가보다 먼저 Gemini 임베딩 adapter와 명시적 provider 설정,
평가 스크립트의 생성/judge/임베딩 주입 경로를 정비한다. 계정에서 지원하는
Gemini 임베딩 모델·차원을 검증하고 선정 자료 10개를 별도 인덱스/namespace와
BM25 산출물로 재구축한다. 같은 차원이어도 OpenAI 벡터와 Gemini 질의 벡터를
혼합하지 않는다. provider/model/dimension/코퍼스 버전을 manifest로 검증한다.
OpenAI 키가 없고 관련 API 호출이 차단된 조건에서 검색·Ragas·Agent 평가가
동작하는 것을 확인한 후 새 인덱스를 활성화한다. 기존 키를 유지해야 하는
실행 경로는 허용하지 않는다.

권장 역할 분리 후보는 GEMINI_MODEL=gemini-3.8-flash,
GEMINI_VISION_MODEL=gemini-3.8-flash,
GEMINI_EVAL_MODEL=gemini-3.1-pro-preview이다. Pro는 검증 전 후보이며,
채점 기준 사례 비교에서 적합하지 않으면 검증된 Gemini judge로 확정한다.
개인 .env는 이번 계획 수정에서 변경하지 않는다. 사용자는 OPENAI_API_KEY를
삭제하거나 빈 값으로 둘 수 있으나 전환 전 기존 RAG 실행은 실패할 수 있다.
.env의 모델 ID 끝에는 역슬래시를 붙이지 않는다.

이후 검토 골드셋 → 파서/청킹/임베딩/검색 통제 실험 → 근거 충돌 정책 연결 →
Ragas·Agent·LangSmith 통합 평가 → 실제 streaming·Deep Agent/MCP·kind →
기능 검증 후 Cue 참고 UI의 기존 순서를 유지한다.

## 8. 2026-10-09 실행 결과에 따른 다음 검증

Gemini 전용 10문서/4139청크 인덱스를 재구축하고 1-based 페이지/벡터 개수를
검증해 활성화했다. Recursive 청킹은 전환 기준선이며 비교 승자가 아니다.
20문항/2출처의 파서·청킹 BM25/Ragas 파일럿과 40문항/4출처의 실제
Dense/Hybrid/Full 검색 비교를 완료했다. LangSmith에는 공개 40문항과
3개 artifact replay 실험(각 40실행/160개 피드백)을 저장하고 실제 저장을 확인했다.
모델 trace와 측정 결과 replay를 구분한다. 후자의 실행 시간은 API 지연이 아니다.

엄격한 검색 비교의 지정 PDF 페이지 적중률은 0.75/0.725/0.30이었다.
다른 페이지의 동일 근거를 배제한 지표이므로 답변 정확도 또는 리랭커의
임상적 부정확성으로 단정하지 않는다. 먼저 대체 정답 페이지/실제 근거 구절을
검토하고, 한국어·영어 문맥에 적합한 리랭커 후보를 같은 골드/후보군에서 비교한다.
최종 선정 전에 페이지 순위와 답변·출처 적합성을 함께 확인한다.

Ragas 초기 한 조합 API 실패와 별도 재실행을 보존한다. 서로 다른 생성
프롬프트 버전의 결과를 동일 9조합 점수로 합치지 않는다. 후속 평가는 채점
유효 개수·전체 개수, generation/judge/프롬프트 버전 및 고유 산출물을 기록한다.
Judge 후보는 20개 쉬운 사실 판정에서 일치했으나 최종 보정 완료가 아니다.
개인 환경의 역할 설정은 서비스 3.8 Flash / judge 3.1 Pro Preview이며,
최종 도입 판단은 어려운 충돌·범위·거절 사례를 추가해 수행한다.

원문 검토 40문항을 출발점으로 전체 120문항(RAG·Agent·멀티턴·계산/안전)을
확정하고, 판본/충돌 정책의 실제 쓰기 차단을 연결한다. 이후 실제 진행·검증된
답변 streaming과 재연결, Weekly Deep Agent/MCP, API/worker 컨테이너와
kind 재시작을 검증한다. 모든 기능 검증 후
[Cue 참고 UI](https://seo.tbwakorea.com/blog/what-is-naver-cue/)로 업그레이드한다.
