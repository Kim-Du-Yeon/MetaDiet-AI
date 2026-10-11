# MetaDiet AI beta-v1.1.0

MetaDiet AI의 무료 제한 베타 릴리스입니다. 공개 웹에서 가입·온보딩·식사 기록·식단 제안·인바디 및 목표 관리·HITL 확정·상태 복원·베타 피드백을 사용할 수 있습니다.

- 공개 베타: [metadiet-web.onrender.com](https://metadiet-web.onrender.com)
- 운영 범위: 일반 성인 체중 관리 정보 서비스
- AI·RAG: Gemini 기반 LangGraph 멀티에이전트, Pinecone + Kiwi BM25 Hybrid RAG
- 저장 경계: versioned proposal을 사용자가 확정한 뒤에만 실제 데이터를 변경
- 관측·평가: LangSmith trace, Ragas, Agent/tool/HITL 독립 평가

## 검증 결과

| 항목 | 결과 |
|---|---:|
| 백엔드 회귀 | 376 passed, 1 skipped |
| 프론트엔드 회귀 | 42 passed |
| 프로덕션 빌드 | 성공 |
| 독립 RAG evidence support | 95% |
| Ragas faithfulness / context recall | 1.00 / 0.95 |
| Agent 독립 흐름 | 8/8, 정책 위반 0 |
| kind rolling restart | health 400/400, 실패 0 |
| 공개 제한 부하 | health 50건·인증 조회 30건·Agent 2건, 오류 0 |

## 이번 베타에서 확인한 운영 경계

- 무료 Render API는 15분 이상 휴면 뒤 첫 요청에 실제 측정 기준 약 53초가 걸릴 수 있습니다. 기동 후 `/health` 20회 중앙값은 236.2ms였습니다.
- 실제 식단 상담은 Gemini·RAG·도구 호출·검증을 포함하므로 health 응답보다 오래 걸립니다.
- 근거를 찾지 못한 질문에는 출처를 만들지 않고 답변을 보류합니다.
- 의료 진단·치료·응급 대응 서비스가 아니며 AI 추정값과 전략 변경은 사용자가 확인해야 합니다.
- 피드백에는 대화·식사·인바디·이메일을 자동 첨부하지 않습니다.

## 운영 확인

- Render 공개 API와 정적 웹 HTTP 200
- Git push 자동 배포 확인
- 장애 알림: Email + Only failure notifications
- 개인정보처리방침·베타 이용 안내·계정 삭제 제공
- API 500, SSE 중단, 인증 만료, 피드백 503 오류 화면 검증

전체 실험 조건과 실패 분석은 [EVALUATION.md](EVALUATION.md), 포트폴리오 요약은 [PORTFOLIO_RESULTS.md](PORTFOLIO_RESULTS.md)를 참고합니다.
