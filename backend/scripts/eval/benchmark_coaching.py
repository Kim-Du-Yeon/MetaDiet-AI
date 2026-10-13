"""Live synthetic coaching measurements; credentials only from ignored env files."""
import argparse,json,sys,time,statistics
from pathlib import Path
from uuid import uuid4
from urllib import request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_render_beta import load_env,service_api,json_request
ROOT=Path(__file__).resolve().parents[3]
API='https://metadiet-api.onrender.com'
def run(token,payload):
    started=time.perf_counter();first=None;answer=None;events=[]
    req=request.Request(API+'/chat',data=json.dumps(payload).encode(),method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with request.urlopen(req,timeout=240) as response:
        for raw in response:
            if not raw.startswith(b'data:'):continue
            event=json.loads(raw[5:]);events.append(event)
            ms=round((time.perf_counter()-started)*1000,1)
            if first is None:first=ms
            if event.get('type')=='answer_delta' and answer is None:answer=ms
    done=next((e for e in events if e.get('type')=='completed'),None)
    if not done:raise RuntimeError('missing_completed_event')
    content=''.join(e.get('content','') for e in events if e.get('type')=='answer_delta')
    if done.get('pending_proposal'):
        p=done['pending_proposal'];json_request(API+'/proposals/decision',token=token,method='POST',payload={'proposal_id':p['id'],'version':p['version'],'action':'cancel'})
    return {'first_event_ms':first,'first_answer_ms':answer,'total_ms':round((time.perf_counter()-started)*1000,1),
        'usage':done.get('execution_usage'),'trace_id':done.get('trace_id'),'answer_chars':len(content),
        'progress':[e for e in events if e.get('type')=='progress'],'answer':content}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['before','after'],required=True);parser.add_argument('--repeats',type=int,default=3);args=parser.parse_args()
    load_env(ROOT/'backend/.env');load_env(ROOT/'backend/.env.selection-browser')
    token=service_api('/auth/v1/token?grant_type=password','POST',{'email':__import__('os').environ['EMAIL'],'password':__import__('os').environ['PASSWORD']})['access_token']
    json_request(API+'/health',timeout=90)
    rows=[]
    for repeat in range(args.repeats):
        thread='perf-'+args.phase+'-'+uuid4().hex
        for index,message in enumerate(['점심 추천해줘. 식단 계획 카드는 만들지 말고 조언만 해줘.','그럼 한식뷔페 가서 일반식 한 접시 먹는 건 괜찮아?']):
            row=run(token,{'message':message,'thread_id':thread,'stream_run_id':str(uuid4()),'after_seq':0})
            if args.phase == 'after' and not any(e.get('phase') == 'coaching_context' for e in row['progress']):
                raise RuntimeError('new_coaching_context_not_observed; stop instead of measuring old deploy')
            row.update(repeat=repeat,turn=index,message=message);rows.append(row)
            print(args.phase,repeat,index,round(row['total_ms']),row['usage'],flush=True)
    report={'scope':'synthetic_public_coaching','phase':args.phase,'samples':len(rows),'rows':rows,
      'median_total_ms':statistics.median(r['total_ms'] for r in rows),'median_first_answer_ms':statistics.median(r['first_answer_ms'] for r in rows),
      'limitations':'Small synthetic sample, no p95 generalization. First event is progress, not answer. No real user outcomes.'}
    (ROOT/'docs/coaching_performance'/f'{args.phase.upper()}_LIVE.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
