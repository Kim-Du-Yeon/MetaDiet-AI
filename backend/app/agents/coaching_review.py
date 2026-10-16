"""Verified request facts only, without unsupported new prescriptions."""
import math


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def build_review(*, profile, intake, measurements, assessment, reason):
    lines = ['### 확인된 기록 분석']
    target = ((profile or {}).get('strategy') or {}).get('daily_calories')
    if _number(target):
        lines.append(f'- 현재 확정된 하루 목표: **{target:,.0f} kcal** (변경하지 않았어요)')
    if intake is not None and _number(intake.get('calories')):
        calories = intake['calories']
        lines.append(f'- {intake["date"]} 기록된 섭취량: **{calories:,.0f} kcal**')
        if _number(target):
            gap = target - calories
            lines.append(f'- 기록 기준 목표까지 남은 양: **{gap:,.0f} kcal**' if gap >= 0
                         else f'- 기록 기준 목표 초과량: **{-gap:,.0f} kcal**')
        names = [str(row.get('food_name','음식')).replace('\n',' ')[:80] for row in (intake.get('meals') or [])[:8]]
        if names:
            lines.append('- 확인한 음식: ' + ', '.join(names))
        lines.append('- 기록된 식사만 집계했어요. 미기록 식사를 먹지 않았다고 가정하지 않습니다.')
    else:
        lines.append('- 이번 요청에서 오늘 섭취 기록을 확인하지 못해 합계나 남은 양을 추정하지 않았어요.')
    if measurements is not None:
        lines.append(f'- 확인된 체성분 측정: **{len(measurements)}회**. 측정만으로 근손실을 단정하지 않습니다.')
    if _number((assessment or {}).get('weight_loss_pct')):
        lines.append(f'- 확정 체중 기록 간 관측 변화: **{assessment["weight_loss_pct"]:.1f}% 감소** '
                     f'({assessment["days"]}일 간격). 새로운 감량 목표를 뜻하지 않습니다.')
    optional = 'measurements' if (assessment or {}).get('status') == 'insufficient_data' else None
    if optional:
        lines.append('- 체중 변화 추세를 판단할 기록이 부족해 추세 판단은 보류했어요. 추가 입력은 선택입니다.')
    reason_line = ('- 검색된 공식 문서에서 끼니별 고정 에너지 배분 비율을 확인하지 못했어요.'
                   if reason == 'unsupported_claim' else
                   ('- **근거 검색 도구 오류**로 공식 자료를 확인하지 못했어요.' if reason == 'search_unavailable'
                    else '- 검색된 자료가 필요한 근거 기준을 충족하지 못했어요.'))
    lines += ['\n### 보류한 부분', reason_line,
              '- 새로운 목표 칼로리·영양 비율 변경 권고만 보류합니다. 위 수치는 기존 확정 기록의 요약이며 새 처방이 아닙니다.']
    return '\n'.join(lines), {'reason':reason, 'optional_input':optional}
