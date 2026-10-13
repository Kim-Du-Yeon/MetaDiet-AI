"""Actual messages contract, synthetic public Gemini paired dialogs."""
import argparse,json,os,statistics,sys
from pathlib import Path
from uuid import uuid4
from benchmark_coaching import run,load_env,service_api,json_request,ROOT,API
SCENARIOS=[('lunch_buffet','점심 추천해줘. 계획 카드는 만들지 말고 조언만 해줘.','그럼 한식뷔페 가서 일반식 한 접시 먹는 건 괜찮아?'),
 ('dinner_store','저녁 추천해줘. 계획 카드는 만들지 말고 조언만 해줘.','그럼 편의점에서 샌드위치 먹어도 괜찮아?'),
 ('breakfast_rice','아침 추천해줘. 계획 카드는 만들지 말고 조언만 해줘.','그럼 일반식으로 밥이랑 계란 먹어도 괜찮아?')]
def main():
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=['before','after'],required=True);p.add_argument('--repeats',type=int,default=2);p.add_argument('--output-dir',type=Path,default=ROOT/'docs/answer_delivery');args=p.parse_args()
 args.output_dir.mkdir(parents=True,exist_ok=True)
 load_env(ROOT/'backend/.env');load_env(ROOT/'backend/.env.selection-browser')
 token=service_api('/auth/v1/token?grant_type=password','POST',{'email':os.environ['EMAIL'],'password':os.environ['PASSWORD']})['access_token']
 json_request(API+'/health',timeout=90);rows=[]
 for repeat in range(args.repeats):
  for name,first,follow in SCENARIOS:
   history=[];thread='delivery-'+uuid4().hex
   for turn,message in enumerate([first,follow]):
    row=run(token,{'message':message,'messages':history,'thread_id':thread,'stream_run_id':str(uuid4()),'after_seq':0})
    if not any(e.get('phase')=='coaching_context' for e in row['progress']):raise RuntimeError('verified context missing in actual messages contract')
    row.update(scenario=name,repeat=repeat,turn=turn,history_messages=len(history),delivery_tail_ms=round(row['total_ms']-row['first_answer_ms'],1))
    history += [{'role':'user','content':message},{'role':'assistant','content':row['answer']}];rows.append(row)
    print(args.phase,name,repeat,turn,round(row['total_ms']),flush=True)
    (args.output_dir/f'{args.phase.upper()}_MULTITURN.json').write_text(json.dumps({'scope':'synthetic_public_gemini_with_messages','phase':args.phase,'samples':len(rows),'rows':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 report={'scope':'synthetic_public_gemini_with_messages','phase':args.phase,'dialogs':len(SCENARIOS)*args.repeats,'samples':len(rows),'rows':rows,
  'median_first_answer_ms':statistics.median(r['first_answer_ms'] for r in rows),'median_total_ms':statistics.median(r['total_ms'] for r in rows),
  'median_delivery_tail_ms':statistics.median(r['delivery_tail_ms'] for r in rows),'limitations':'Small actual Gemini synthetic sample; no p95 generalization or actual user outcomes. History is passed explicitly. Tail includes network/public stats, not just pacing.'}
 (args.output_dir/f'{args.phase.upper()}_MULTITURN.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
