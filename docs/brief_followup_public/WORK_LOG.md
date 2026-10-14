# 작업·실패 기록

2026-10-14. 사용자 요청: 기존200건에서 모델 처리 병목을 분석하고 한 변경만 실험, 공개 전후100시도씩 속도/p95/실패율/품질/최신값을 비교한 뒤 기준 충족 시 채택.

1. 기존 budget_public_v2 전후200개 원본 SHA256을 고정해 분석했다. 모델시간 중앙값2596.38ms/p954378.37ms, 출력길이와시간 r=.456. 기록0조건에 긴출력이 있으나17.14초/99토큰 요청은 설명하지 못한다.
2. 공식Gemini thinking 문서에서3.8flash가low/medium/high만지원하고max_output_tokens가추론도포함해잘릴수있음을 확인했다. 기존low를유지하며 답변길이 지시만추가한다.
3. 실패테스트에서 answer_style metadata 누락 KeyError를확인한후 flag와범위제한을구현했다. 최초RED4실패→후속코칭범위테스트22통과. 샌드박스pytest는출력없이멈춰 승인된일반실행환경에서재실행했다.
4. 리뷰에서 모델단계finite-positive 시간과환경설정동일성검사누락을지적받아 model_name/route/reasoning/delivery와정확한judgeindex를검사하도록보완했다. 재시도모델호출은1회로강제하지않고실제건수보고로유지한다.
5. 전체백엔드996passed, 기존1skipped,3기존deprecation warnings. 실험코드기본false로커밋f42e4a3을main에푸시했다. 프론트코드/의존성변경없음.
6. 별도합성계정을생성하고자격증명을gitignored backend/.env.budget-public에만저장했다. 공개health가f42e4a3인것을확인한후준비요청before_probe.json을정식100건밖에보존했다.

7. SDK소스를추가확인하니output_tokens가답변+추론합계였다. 실제답변길이와시간상관r=.0565로매우낮았다. 답변길이flag를활성화하지않고모델전환가설로변경했다. [수정분석·사전기준](../model_followup_public/PROTOCOL.md)을참고한다. 이미시작된기존조건100건은행동변경없이완료해모델비교의기존조건으로사용하며 원본은보존한다.

정식비교결과·채택여부·정리는모델비교보고서에추가한다. 준비요청과100건실패는교체하거나지우지않는다.
