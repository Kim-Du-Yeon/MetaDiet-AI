# MetaDiet AI Portfolio Case Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 현재 `beta-v1.1.0`에서 검증된 기술 결과만 사용해 채용 검토자가 읽을 수 있는 포트폴리오 사례를 만들고 GitHub PR로 공개한다.

**Architecture:** 새로운 서비스 기능은 추가하지 않는다. README·발표 구성안·평가 문서의 검증 결과를 하나의 사례 문서로 연결하고, 실사용 데이터와 합성·독립 평가 결과를 명시적으로 구분한다.

**Tech Stack:** Markdown, Mermaid, Git, GitHub Pull Request

**Spec:** `BETA_RELEASE_NOTES.md`, `PORTFOLIO_RESULTS.md`, `EVALUATION.md`

## Global Constraints

- 임상 효과나 실제 사용자 만족도를 주장하지 않는다.
- 모든 수치는 커밋된 평가·부하·브라우저 검증 결과와 일치해야 한다.
- 비밀값, 사용자 식별자, 합성 계정 자격증명을 포함하지 않는다.
- 기존 `beta-v1.0.0`과 `beta-v1.1.0` 태그를 변경하지 않는다.

## Review Focus

- 운영 구성과 탈락한 실험 구성을 혼동하지 않는가.
- health 지연과 실제 Agent 응답 지연을 혼동하지 않는가.
- Ragas와 자체 Agent 평가의 역할을 구분하는가.
- 실제 사용자 성과가 아직 없다는 한계를 명시하는가.
- README, 릴리스 노트, 사례 문서의 테스트 수치가 일치하는가.

---

### Task 1: 포트폴리오 사례 문서

**Files:**
- Create: `PORTFOLIO_CASE_STUDY.md`
- Modify: `README.md`

- [x] 문제, 구조, 실험, 실패 분석, 결과, 한계를 검증 수치와 함께 작성한다.
- [x] README에서 사례 문서와 `beta-v1.1.0` 릴리스를 연결한다.
- [x] Markdown 링크 존재 여부와 오래된 테스트 수치를 검사한다.

### Task 2: 발표 구성안 최신화

**Files:**
- Modify: `PPT_OUTLINE.md`

- [x] 운영 리랭커가 없다는 결론과 최종 RAG 지표를 반영한다.
- [x] LangSmith 환경변수와 현재 Gemini 전용 구성을 반영한다.
- [x] 과거 GPT/OpenAI 운영 설명과 reranking 우위 표현이 없는지 검색한다.

### Task 3: 검증과 GitHub 반영

**Files:**
- Verify: repository documentation and existing test suites

- [x] `git diff --check`와 문서 링크 검사를 통과한다.
- [x] 백엔드 376 passed/1 skipped, 프론트 42 passed, production build를 직렬 실행한다.
- [x] 변경을 커밋·푸시하고 `main` 대상 PR을 생성한다.
