"""Strict model/question/Batch provenance and explicitly bounded timeout accounting."""
import hashlib,json,math,sqlite3
from pathlib import Path
from scripts.eval.clarification_v3 import read
from scripts.eval.clarification_execution import LEDGER_PATH


def trace_templates(groups,label,snapshots,question):
    used=set();question_seen=False
    for group in groups:
        systems=[m['content'] for m in group if m['type']=='system']
        if not systems:raise ValueError('Missing primary system instruction')
        for text in systems:
            matches=[(len(s['texts'][n]),l,n) for l,s in snapshots.items() for n in ['team.base','team.compact_followup'] if text==s['texts'][n] or text.startswith(s['texts'][n]+'\n')]
            if not matches:raise ValueError('Unregistered primary prompt')
            longest=max(x[0] for x in matches);best=[x for x in matches if x[0]==longest]
            if any(l!=label for _,l,_ in best):raise ValueError('Opposite condition primary prompt')
            used.update(n for _,l,n in best)
        for m in group:
            if m['type']!='human' or not isinstance(m['content'],str):continue
            try:payload=json.loads(m['content'])
            except (ValueError,TypeError):continue
            question_seen |= isinstance(payload,dict) and payload.get('message')==question
    if not question_seen:raise ValueError('Actual frozen question absent from trajectory')
    return used


def check_batch(job,wire,expected,entries):
    h=hashlib.sha256(json.dumps(entries,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if job.get('model')!='gemini-3.1-pro-preview' or job.get('state')!='JOB_STATE_SUCCEEDED' or job.get('collected') is not True:raise ValueError('Unconfirmed Pro Batch completion')
    if job.get('entries')!=entries or job.get('entries_sha256')!=h or wire!=expected:raise ValueError('Batch request/model/schema/settings/entry provenance changed')


def reservations():
    with sqlite3.connect(LEDGER_PATH) as db:return {r[0]:{'stage':r[1],'micros':r[2],'settled':r[3]} for r in db.execute('SELECT id,stage,amount,settled FROM costs')}


def bounded_costs(folder,rows):
    p=Path(folder)/'bounded-timeouts.json';saved=read(p)['cases'] if p.exists() else {};result={};actual=reservations()
    for row in rows:
        if row['cost_usd'] is not None:continue
        entry=saved.get(row['case_id'])
        if row['condition']!='v4' or row.get('error',{}).get('reason')!='timeout' or not entry or entry['input_key']!=row['input_key']:raise ValueError('Unknown unaccounted usage')
        tickets=entry['tickets']
        if not tickets or any(actual.get(k)!=v or v['stage']!='comparison' or v['settled'] not in (0,1) or v['micros']<=0 for k,v in tickets.items()):raise ValueError('Unreturned usage reservation changed')
        result[row['case_id']]=sum(v['micros'] for v in tickets.values())/1e6
    if len(result)>2 or set(saved)!=set(result):raise ValueError('Unexpected bounded timeout coverage')
    return result
