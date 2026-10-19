from app.db.intake_snapshot import record_version, make_snapshot


def test_snapshot_today_and_selected_month_are_separate_and_version_changes():
    rows = [dict(id='a',log_date='2026-10-19',meal_type='lunch',food_name='밥',quantity_g=20,
                 calories=30,protein_g=1,carbs_g=6,fat_g=0),
            dict(id='b',log_date='2026-09-01',meal_type='dinner',food_name='밥',quantity_g=10,
                 calories=15,protein_g=.5,carbs_g=3,fat_g=0)]
    snapshot = make_snapshot(rows,2000,'2026-09-01','2026-10-19',[])
    assert snapshot['today_calories'] == 30
    assert snapshot['calendar']['total']['calories'] == 15
    assert snapshot['calendar_month']['days'][0]['date'] == '2026-09-01'
    assert snapshot['calendar']['meals'][0]['record_version'] == record_version(rows[1])
    assert make_snapshot(rows[:1],2000,'2026-09-01','2026-10-19',[])['version'] != snapshot['version']
    assert make_snapshot(list(reversed(rows)),2000,'2026-09-01','2026-10-19',[])['version'] == snapshot['version']


async def test_snapshot_request_is_validated_and_owner_comes_from_auth(client,mock_current_user,monkeypatch):
    from unittest.mock import AsyncMock
    from app.db import intake_snapshot
    mutate=AsyncMock(return_value={'success':True,'sync':{}})
    monkeypatch.setattr(intake_snapshot,'mutate_meal',mutate)
    meal_id='33333333-3333-4333-8333-333333333333'
    response=await client.put('/meal/update',json={'meal_id':meal_id,'quantity_g':20,'include_snapshot':True,
        'thread_id':'test','expected_record_version':'a'*64,'selected_date':'2026-10-19','user_id':'other'})
    assert response.status_code==200
    assert mutate.call_args.args[:3]==(mock_current_user,meal_id,20)
    response=await client.delete('/meal/delete/'+meal_id,params={'include_snapshot':'true','expected_record_version':'invalid'})
    assert response.status_code==422
    response=await client.put('/meal/update',json={'meal_id':'invalid','quantity_g':20,'include_snapshot':True})
    assert response.status_code==422
