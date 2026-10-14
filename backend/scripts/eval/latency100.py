"""Frozen 20 cases x5; never discard failed attempts or overwrite evidence."""
import argparse
import hashlib
import json
import os
import random
import time
from pathlib import Path
from uuid import uuid4
from urllib import request
from benchmark_coaching import API, ROOT, load_env, service_api, json_request

CASES = [
    ('first', '점심 추천해줘'), ('first', '저녁 추천해줘'), ('first', '아침 추천해줘'),
    ('first', '오늘 저녁 식단을 추천해줘'),
    ('button', '점심 식단 추천해줘. 오늘 확정된 섭취량과 목표를 반영해줘.'),
    ('button', '저녁 식단 추천해줘. 오늘 확정된 섭취량과 목표를 반영해줘.'),
    ('first', '오늘 점심 메뉴 추천해줘. 조언만 해줘.'),
    ('first', '점심 추천해줘. 오늘 남은 칼로리도 알려줘.'),
    ('first', '아침 추천해줘. 계획 카드는 만들지 말고 조언만 해줘.'),
    ('first', '저녁 추천해줘. 계획 카드는 만들지 말고 조언만 해줘.'),
    ('followup', '그럼 한식뷔페 가서 일반식 한 접시 먹는 건 괜찮아?'),
    ('followup', '그럼 편의점에서 샌드위치 먹어도 괜찮아?'),
    ('followup', '그럼 일반식으로 밥이랑 계란 먹어도 괜찮아?'),
    ('followup', '닭가슴살이랑 샐러드 먹어도 괜찮아?'),
    ('followup', '일반식 먹는 건 그런가?'),
    ('followup', '저녁에 샌드위치 먹어도 괜찮아?'),
    ('complex', '내일 점심 추천해줘. 조언만 해줘.'),
    ('complex', '외식할 때 점심 메뉴 고르는 방법을 두 문장으로 알려줘.'),
    ('complex', '오늘 점심은 편의점에서 먹을 건데 따뜻한 메뉴로 추천해줘. 저장하지 마.'),
    ('complex', '아침을 기록하지 않았는데 안 먹었다고 가정하지 말고 저녁 메뉴만 추천해줘.'),
]
HISTORY = [{'role':'user','content':'점심 추천해줘'},
           {'role':'assistant','content':'밥에 단백질 반찬과 채소를 곁들이세요. 오늘 기록은 아직 없습니다.'}]


def capture(token, payload):
    started = time.perf_counter()
    row = {'status':'failed','first_answer_ms':None,'answer':'','usage':{},'stage_timings_ms':{}}
    req = request.Request(API+'/chat',data=json.dumps(payload).encode(),method='POST',
                          headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with request.urlopen(req,timeout=180) as response:
            for line in response:
                if not line.startswith(b'data:'): continue
                event = json.loads(line[5:])
                if event['type']=='started':
                    row.update(build=event.get('build'), trace_id=event.get('trace_id'))
                if event['type']=='answer_delta':
                    if row['first_answer_ms'] is None: row['first_answer_ms']=(time.perf_counter()-started)*1000
                    row['answer'] += event.get('content','')
                elif event['type'] in ('failed','error'):
                    row['error_type']=event['type']
                    for key in ('external_failures', 'stage_timings_ms', 'build', 'trace_id'):
                        if key in event: row[key] = event[key]
                elif event['type']=='completed':
                    row.update(status=event.get('execution_status','completed'),usage=event.get('execution_usage') or {},
                        stage_timings_ms=event.get('stage_timings_ms') or {},build=event.get('build'),
                        trace_id=event.get('trace_id'),route=event.get('route'))
                    for key in ('model_tokens', 'model_first_token_ms', 'reasoning', 'model_delivery', 'external_failures', 'answer_style', 'model_name'):
                        if key in event: row[key] = event[key]
                    if 'answer' in event: row['answer']=event['answer']
                    if event.get('pending_proposal'):
                        p=event['pending_proposal']
                        json_request(API+'/proposals/decision',token=token,method='POST',payload={
                            'proposal_id':p['id'],'version':p['version'],'action':'cancel'})
                        row['unexpected_proposal']=True
    except Exception as exc:
        row['status']='failed'; row['error_type']=type(exc).__name__
    row['total_ms']=(time.perf_counter()-started)*1000
    if '보류했습니다' in row['answer']: row['status']='blocked'
    return row


def main():
    p=argparse.ArgumentParser(); p.add_argument('--phase',required=True); p.add_argument('--expected-commit'); args=p.parse_args()
    folder=ROOT/'docs/latency100'; folder.mkdir(exist_ok=True)
    output=folder/(args.phase+'.json')
    if output.exists(): raise SystemExit('Refusing to overwrite evidence')
    load_env(ROOT/'backend/.env'); load_env(ROOT/'backend/.env.selection-browser')
    token=service_api('/auth/v1/token?grant_type=password','POST',{'email':os.environ['EMAIL'],'password':os.environ['PASSWORD']})['access_token']
    health=json_request(API+'/health',timeout=90)
    dataset_hash=hashlib.sha256(json.dumps(CASES,ensure_ascii=False).encode()).hexdigest()
    report={'phase':args.phase,'dataset_sha256':dataset_hash,'expected_commit':args.expected_commit,'health':health,
            'scope':'synthetic_public_serial_20_cases_five_repeats','rows':[]}
    order=[(rep,i) for rep in range(5) for i in range(20)]; random.Random(1301).shuffle(order)
    for repeat,index in order:
        group,message=CASES[index]
        row=capture(token,{'message':message,'messages':HISTORY if group=='followup' else [],
            'thread_id':'lat100-'+uuid4().hex,'stream_run_id':str(uuid4()),'after_seq':0,'stream_protocol':2})
        row.update(case=index,repeat=repeat,group=group,question=message)
        report['rows'].append(row)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(args.phase,len(report['rows']),index,row['status'],round(row['total_ms']),flush=True)
    assert len(report['rows'])==100
    if args.expected_commit:
        assert all((r.get('build') or {}).get('commit')==args.expected_commit for r in report['rows'] if r['status']=='completed'), 'build mismatch'


if __name__=='__main__': main()
