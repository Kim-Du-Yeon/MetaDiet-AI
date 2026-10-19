# 프롬프트 버전 관리

2026-10-19. Git에 포함한 로컬 릴리스로 **주요 시스템 템플릿 8개**를 관리합니다.
기존 문구를 그대로 옮겼으며 코드 검토에서 원본과의 일치를 확인했습니다.
LangSmith Prompt Hub에 게시하거나 모든 프롬프트를 외부화했다는 의미는 아닙니다.

## 구성

- `backend/app/prompts/releases/v1.json`: ID·의미 버전·원문·SHA-256.
- `backend/app/core/prompts.py`: 릴리스 경로·버전·해시 검증, 불변 캐시, 조회.
- `PROMPT_RELEASE=v1`: 환경변수로 선택. 기본 v1, **서버 재시작 필요**.
- 미등록 릴리스나 변조된 해시는 실패 처리합니다. 외부 네트워크 다운로드는 없습니다.
- [원본에서 옮긴 위치와 해시](migration.json).

등록 ID는 `team.base`, `team.compact_followup`, `team.role.meal`, `team.role.goal`,
`team.role.evidence`, `legacy.intent_classification`, `legacy.food_extraction`,
`rag.query_translation`입니다. OCR·Ragas 라이브러리 내부 템플릿과 일부 인라인
보조 지시는 이번 레지스트리의 범위 밖이며 해당 코드/패키지 버전도 함께 고정해야 합니다.

v1 번들 해시:
`4c40f46e4c2aa01b5ba7c78f456cff11b11907a4730e697288f796694ec7a741`.

## 변경·평가·복구

1. 기존 v1은 수정하지 않고 v2.json을 새로 만듭니다. 변경한 ID의 버전과 원문 해시를 갱신합니다.
2. 단위 검사 후 동결 사례로 조건별 100건 이상 비교합니다. 실패·타임아웃도 포함하고
   속도·품질·최신 기록 반영이 유지되는지 확인합니다.
3. 통과하면 패키지에 새 릴리스를 포함하고 `PROMPT_RELEASE=v2`로 설정해 재시작합니다.
4. 문제가 생기면 패키지에 남겨둔 `PROMPT_RELEASE=v1`로 되돌리고 재시작합니다.

모델 메타데이터에는 릴리스·번들 해시·작업·역할을 붙이고 Agent 실행에는 실제 조합된
시스템 지시의 해시도 붙입니다. 이 새 메타데이터에 대화 원문·건강 수치를 추가하지 않습니다.
기존 추적의 본문 수집 정책은 별도입니다. LangSmith 키가 없으면 클라우드 추적 확인을
보장하지 않으며, 이번 작업으로 원격 Prompt Hub를 생성하지 않았습니다.

향후 중앙 협업이 필요하면 [LangSmith prompt commits/tags](https://docs.langchain.com/langsmith/manage-prompts)를
사용할 수 있습니다. 운영에서는 이동 가능한 latest 태그보다 검증된 커밋을 고정하는 방식이 적합합니다.
