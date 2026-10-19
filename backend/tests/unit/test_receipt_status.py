from app.db.receipt_status import annotate_receipts, format_receipt


def test_deleted_partial_and_modified_receipts_are_distinguished():
    meals = [dict(food_name='밥', quantity_g=10, calories=14.6, meal_type='lunch'),
             dict(food_name='김치', quantity_g=40, calories=12, meal_type='lunch')]
    proposal = dict(payload=dict(log_date='2026-10-19', meals=meals), result={'meal_ids':['a','b']})
    original = {'role':'assistant', 'content':format_receipt(proposal)}
    assert '삭제된' in annotate_receipts([original], [proposal], [])[0]['content']
    assert '일부 삭제' in annotate_receipts([original], [proposal], [dict(id='a', **meals[0])])[0]['content']
    current = [dict(id='a', **{**meals[0], 'quantity_g':20}), dict(id='b', **meals[1])]
    assert '수정된' in annotate_receipts([original], [proposal], current)[0]['content']
    assert annotate_receipts([original], [proposal], [dict(id='a', **meals[0]),dict(id='b', **meals[1])]) == [original]
    assert original['content'].startswith('섭취 기록을 저장')


def test_receipt_query_is_scoped_and_failed_read_does_not_claim_deletion():
    from app.db.receipt_status import reconcile_receipts
    from unittest.mock import MagicMock
    sb = MagicMock()
    query = sb.table.return_value
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.side_effect = RuntimeError('offline')
    original = [{'role':'assistant','content':'섭취 기록을 저장했습니다.\n\n밥'}]
    output = reconcile_receipts(sb,'owner','thread',original)
    assert '확인하지 못했습니다' in output[0]['content']
    assert '삭제된' not in output[0]['content']
    assert any(call.args == ('user_id','owner') for call in query.eq.call_args_list)
    assert any(call.args == ('thread_id','thread') for call in query.eq.call_args_list)


async def test_calendar_edit_scales_saved_values_without_model(client, mock_current_user, fake_sb):
    fake_sb.tables['meal_logs'] = [dict(id='m', user_id=mock_current_user, food_name='밥',
        quantity_g=10, calories=14.6, protein_g=.3, carbs_g=3, fat_g=.1)]
    response = await client.put('/meal/update', json={'meal_id':'m','quantity_g':20})
    assert response.status_code == 200
    assert response.json()['updated']['calories'] == 29.2
    assert (await client.put('/meal/update',json={'meal_id':'m','quantity_g':0})).status_code == 422
