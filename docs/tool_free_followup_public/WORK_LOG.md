# 작업·실패 기록

- 기존200건 모델 지연 분석 → 출력 토큰에 thinking이 포함됨을 설치 SDK로 확인해 답변 길이 가설 수정.
- 기존100건 기준 측정·품질100건을 동결. Flash-Lite100건은 중앙값 개선에도 p95·actionable 품질 기준 미달. 원래 모델 복구 후 도구 생략100건을 별도 측정.
- 도구 생략100건의 종단 중앙값/p95 모두 기준 미달. judge100건·5항목100/100은 유지했으나 채택하지 않음.
- allowlist 검토에서 질환·브랜드 문구가 도구 생략 대상으로 들어갈 위험을 수정. 누락 모델 시간을 비교하던 TypeError를 finite-positive 검사로 보완. 전체1028 passed, 기존1 skipped 및 마지막 정책·평가29 passed.
- `FOLLOWUP_MODEL=default`, `FOLLOWUP_TOOLS_ENABLED=true` 저장 후 재배포. 첫 복구 probe는 응답 완료·최신값·미저장이었지만 `tool_policy=none`으로 실패했다. 원본 [rollback/before_probe.json](rollback/before_probe.json)을 보존한다. 같은 커밋의 환경변수 배포 중 기존 인스턴스가 응답했으므로 health의 commit만으로 설정 반영을 판단하지 않는다.
- [Render 공식 환경변수 문서](https://render.com/docs/configure-environment-variables)와 [배포 문서](https://render.com/docs/deploys)를 확인하고 Live 배포 이후 별도 probe로 재검증한다. 실패한 probe는 정식100건에 포함하지 않는 배포 확인 요청이며 삭제하거나 성공 결과로 덮어쓰지 않는다.
- Live 후 두 번째 [probe](rollback_verified/before_probe.json)도 기존 `none` 정책이었다. 새 페이지에서 저장값 `true`를 재확인했으므로 단순 입력 누락으로 단정하지 않는다. 같은 커밋 설정 배포의 정확한 반영 지연 원인은 확정하지 못했으며 문서 커밋의 새 자동 배포 후 다시 검증한다.

모델 생성·SDK 준비·네트워크 시간을 아직 분리하지 못했다. 새로운 최적화를 성공으로 주장하지 않고 실패한 두 후보를 복구하며, 다음 실험의 계측 한계를 명시한다.

## 최종 복구

새 자동 배포 `0395fe564135753eb66e248775c9f37bb1cab2c3`에서 [probe](rollback_new_build/before_probe.json)가 성공했다. Gemini 3.8 Flash / low / invoke / default / read 정책, 현재600kcal·목표2000kcal, 미저장 확인. 같은 커밋 설정 배포에서 이전 정책이 응답한 정확한 원인은 확정하지 못했다. 최초 새 코드 probe 명령은 전체 SHA를 잘못 전달해 측정 전에 Deployment mismatch로 중단됐으며 `git rev-parse HEAD`와 공개 health를 비교해 올바른 SHA로 실행했다.

프론트 전체 테스트는 sandbox TEMP 경로 realpath의 EPERM으로 시작하지 못했다. [Node 공식 os.tmpdir 문서](https://nodejs.org/download/release/v22.10.0/docs/api/os.html#ostmpdir)에 따라 Windows TEMP 경로 문제로 분류하고 승인된 일반 환경에서 재실행해 23 suites / 77 tests 통과했다. 테스트의 의도적인 네트워크 실패 로그는 실제 실패로 세지 않는다.

프론트 production build도 Compiled successfully로 통과했다. 합성 계정은 공개 삭제 API로 정리하고 사용자 행 부재를 확인했으며 git-ignored env 자격증명도 삭제했다. [cleanup.json](cleanup.json)의 tombstone_cleanup_pending=false를 확인했다.
