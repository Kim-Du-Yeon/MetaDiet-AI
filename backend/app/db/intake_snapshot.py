"""Opt-in transactional meal mutations and a coherent, versioned UI snapshot.

Versions are opaque content fingerprints, NOT globally ordered revision numbers.
"""
import hashlib
import json
import math
from datetime import date

from fastapi import HTTPException
from psycopg.errors import SerializationFailure, DeadlockDetected
from app.core.service_clock import service_today
from app.db.proposals import connection
from app.db.receipt_status import annotate_receipts

NUTRIENTS = ('calories','protein_g','carbs_g','fat_g')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def record_version(row):
    return digest({k: (format(float(row[k]),'.10g') if k in (*NUTRIENTS,'quantity_g','sodium_mg') and row.get(k) is not None
                       else str(row[k]) if row.get(k) is not None else None)
                   for k in ('id','log_date','food_name','meal_type','quantity_g',*NUTRIENTS,'sodium_mg')})


def make_snapshot(rows, target, selected_date, today, messages):
    if not math.isfinite(target) or target <= 0 or any(
            not math.isfinite(float(r.get(k) or 0)) or float(r.get(k) or 0) < 0
            for r in rows for k in NUTRIENTS):
        raise ValueError('invalid_stored_nutrition')
    meals = [{**r,'id':str(r['id']),'log_date':str(r['log_date']),'record_version':record_version(r)} for r in rows]
    selected = [r for r in meals if r['log_date'] == selected_date]
    totals = lambda items: {k:sum(float(r.get(k) or 0) for r in items) for k in NUTRIENTS}
    days = {}
    for row in meals:
        if row['log_date'].startswith(selected_date[:7]):
            day = row['log_date']
            days[day] = days.get(day,0) + float(row.get('calories') or 0)
    return {'protocol':1,'version':digest([sorted(r['record_version'] for r in meals),target,today,selected_date]),
            'today_date':today,'today_calories':totals([r for r in meals if r['log_date']==today])['calories'],
            'target_calories':target,'calendar':{'date':selected_date,'meals':selected,'total':totals(selected)},
            'calendar_month':{'year_month':selected_date[:7],'target_calories':target,
                'days':[{'date':day,'calories':round(value,1),'logged':True,'status':'over' if value>target else 'under'}
                        for day,value in sorted(days.items())]},'messages':messages}


async def mutate_meal(user_id, meal_id, quantity_g=None, *, selected_date=None, thread_id=None,
                      expected_record_version=None, connect=None):
    connect = connect or connection
    today = service_today().isoformat()
    selected_date = str(selected_date or today)
    updated = {}
    try:
        async with connect() as conn:
            await conn.execute('set transaction isolation level serializable')
            # Same lock order as proposal resolution; all reads see own write + one stable snapshot.
            await conn.execute('select id from users where id=%s for update',(user_id,))
            row = await (await conn.execute('select * from meal_logs where id=%s for update',(meal_id,))).fetchone()
            if not row:
                raise HTTPException(404,'기록을 찾을 수 없습니다.')
            if str(row['user_id']) != str(user_id):
                raise HTTPException(403,'본인의 기록만 변경할 수 있습니다.')
            if expected_record_version and expected_record_version != record_version(row):
                raise HTTPException(409,'기록이 다른 곳에서 변경되었습니다. 다시 조회 후 수정해주세요.')
            if quantity_g is None:
                await conn.execute('delete from meal_logs where id=%s and user_id=%s',(meal_id,user_id))
            else:
                old = float(row.get('quantity_g') or 0)
                if old <= 0 or not math.isfinite(old):
                    raise HTTPException(409,'기존 분량을 다시 확인해주세요.')
                if any(row.get(k) is None for k in NUTRIENTS):
                    raise HTTPException(409,'기존 영양정보를 다시 확인해주세요.')
                updated = {k:round(float(row[k])*quantity_g/old,4) for k in (*NUTRIENTS,'sodium_mg') if row.get(k) is not None}
                if not all(math.isfinite(v) and v>=0 for v in updated.values()):
                    raise HTTPException(409,'기존 영양정보를 다시 확인해주세요.')
                # Fixed column allowlist; never interpolate user input as SQL identifiers.
                keys = list(updated)
                await conn.execute('update meal_logs set quantity_g=%s,'+','.join(k+'=%s' for k in keys)
                                   +' where id=%s and user_id=%s',(quantity_g,*[updated[k] for k in keys],meal_id,user_id))
            rows = await (await conn.execute('select * from meal_logs where user_id=%s order by id limit 10001',(user_id,))).fetchall()
            if len(rows)>10000:
                raise HTTPException(409,'기록이 많아 변경 결과를 함께 표시할 수 없습니다. 기존 경로로 다시 확인해주세요.')
            strategy = await (await conn.execute('select daily_calories from diet_strategies where user_id=%s and is_active=true order by created_at desc limit 1',(user_id,))).fetchone()
            if not strategy:
                raise HTTPException(409,'현재 목표를 확인한 뒤 다시 시도해주세요.')
            messages = None
            if thread_id:
                history = await (await conn.execute('select role,content,agent_type from chat_history where user_id=%s and thread_id=%s order by created_at desc,role asc limit 20',(user_id,thread_id))).fetchall()
                messages = [{'role':r['role'],'content':r['content'],'agent_used':r['agent_type']} for r in reversed(history)
                            if r['role'] in ('user','assistant') and r.get('content')]
                proposals = await (await conn.execute("select payload,result from agent_proposals where user_id=%s and thread_id=%s and kind='intake' and status='confirmed' order by resolved_at desc limit 100",(user_id,thread_id))).fetchall()
                messages = annotate_receipts(messages,proposals,rows)
            try:
                snapshot = make_snapshot(rows,float(strategy['daily_calories']),selected_date,today,messages)
            except (ValueError,TypeError):
                raise HTTPException(409,'기존 영양정보나 목표를 다시 확인해주세요.') from None
        # Exiting context commits before any success response is returned.
        return {'success':True,'updated':updated,'sync':snapshot}
    except (SerializationFailure,DeadlockDetected):
        raise HTTPException(409,'동시에 기록이 변경되었습니다. 다시 조회 후 시도해주세요.') from None
