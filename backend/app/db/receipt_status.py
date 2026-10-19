"""Read-only reconciliation of historical receipts with owner-scoped meal IDs."""
import logging

logger = logging.getLogger(__name__)


def format_receipt(proposal):
    payload = proposal['payload']
    meals = payload['meals']
    labels = {'breakfast':'아침', 'lunch':'점심', 'dinner':'저녁', 'snack':'간식'}
    types = list(dict.fromkeys(labels[m['meal_type']] for m in meals if m.get('meal_type') in labels))
    lines = ['섭취 기록을 저장했습니다.', ' · '.join([payload['log_date'], '·'.join(types)]).rstrip(' ·')]
    items = []
    for meal in meals:
        name = ((meal.get('nutrition_metadata') or {}).get('portion') or {}).get('display_name') or meal['food_name']
        items.append(f"- {name} · {meal['quantity_g']:g}g · {meal['calories']:.0f} kcal")
    lines.extend(['\n'.join(items), f"합계 {sum(m['calories'] for m in meals):.0f} kcal"])
    return '\n\n'.join(lines)


def annotate_receipts(messages, proposals, current_meals):
    current = {str(m['id']): m for m in current_meals}
    notices = {}
    for proposal in proposals:
        meals = proposal.get('payload', {}).get('meals', [])
        ids = (proposal.get('result') or {}).get('meal_ids', [])
        if not meals or len(ids) != len(meals):
            continue  # Legacy receipts without IDs cannot be attributed safely.
        deleted = sum(str(mid) not in current for mid in ids)
        modified = any(any(current[str(mid)].get(k) != meal.get(k)
                           for k in ('food_name','quantity_g','calories','protein_g','carbs_g','fat_g','meal_type'))
                       for mid, meal in zip(ids, meals) if str(mid) in current)
        notice = ('삭제된 섭취 기록입니다. 현재 섭취량에 포함되지 않습니다.' if deleted == len(ids)
                  else '일부 삭제된 섭취 기록입니다. 남아 있는 음식만 현재 섭취량에 반영됩니다.' if deleted
                  else '수정된 섭취 기록입니다. 현재 섭취량에는 수정된 값이 반영됩니다.' if modified else None)
        key = format_receipt(proposal)
        if key in notices and notices[key] != notice:
            notices[key] = '동일한 저장 내역이 여러 건 있습니다. 현재 기록은 캘린더에서 확인해주세요.'
        else:
            notices[key] = notice
    output = []
    for message in messages:
        notice = notices.get(message.get('content')) if message.get('role') == 'assistant' else None
        output.append({**message, 'content':notice + '\n\n아래는 저장 당시 내역입니다.\n\n' + message['content'].removeprefix('섭취 기록을 저장했습니다.\n\n')}
                      if notice else message)
    return output


def reconcile_receipts(sb, user_id, thread_id, messages):
    if not any(m.get('role') == 'assistant' and m.get('content', '').startswith('섭취 기록을 저장했습니다.') for m in messages):
        return messages
    try:
        proposals = (sb.table('agent_proposals').select('payload,result').eq('user_id',user_id)
                     .eq('thread_id',thread_id).eq('kind','intake').eq('status','confirmed')
                     .order('resolved_at',desc=True).limit(100).execute().data)
        contents = {m.get('content') for m in messages if m.get('role') == 'assistant'}
        proposals = [p for p in proposals if format_receipt(p) in contents]
        ids = list({mid for p in proposals for mid in (p.get('result') or {}).get('meal_ids',[])})
        if not ids:
            return messages
        rows = []
        for start in range(0,len(ids),200):
            rows.extend(sb.table('meal_logs').select('id,food_name,quantity_g,calories,protein_g,carbs_g,fat_g,meal_type')
                        .eq('user_id',user_id).in_('id',ids[start:start+200]).execute().data)
        return annotate_receipts(messages,proposals,rows)
    except Exception as error:
        logger.warning('receipt_reconciliation_failed error_type=%s',type(error).__name__)
        return [{**m, 'content':'현재 기록 상태를 확인하지 못했습니다. 아래는 저장 당시 내역입니다.\n\n'
                 + m['content'].removeprefix('섭취 기록을 저장했습니다.\n\n')}
                if m.get('role') == 'assistant' and m.get('content','').startswith('섭취 기록을 저장했습니다.')
                else m for m in messages]
