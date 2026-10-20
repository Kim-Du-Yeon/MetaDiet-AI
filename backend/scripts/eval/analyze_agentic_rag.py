"""Fail-closed paired analysis; incomplete cost/evaluator data cannot pass."""
from __future__ import annotations
import argparse,collections,json,math,statistics
from pathlib import Path

def keyed(rows):
    result={}
    for row in rows:
        key=(row['attempt_id'],row['condition'])
        if key in result: raise ValueError('Duplicate experiment key')
        result[key]=row
    return result

def analyze(rows,grades):
    attempts=keyed(rows); judges=keyed(grades)
    ids={r['attempt_id'] for r in rows}
    expected={(i,c) for i in ids for c in ('baseline','agentic')}
    if len(ids)<100 or set(attempts)!=expected or set(judges)!=expected:
        raise ValueError('Incomplete matched >=100 comparison')
    result={}
    for condition in ('baseline','agentic'):
        items=[r for r in rows if r['condition']==condition]; n=len(items)
        times=sorted(r['ms'] for r in items)
        serving=lambda r:r['status']=='completed'
        judged=lambda r:judges[(r['attempt_id'],condition)].get('status')=='completed'
        good=lambda r,field:serving(r) and judged(r) and judges[(r['attempt_id'],condition)].get(field,False)
        result[condition]={'attempts':n,'completed':sum(serving(r) for r in items),
            'failure_rate':sum(not serving(r) for r in items)/n,
            'judge_failures':sum(serving(r) and not judged(r) for r in items),
            'correctness':sum(good(r,'correct') for r in items)/n,
            'faithfulness':sum(good(r,'faithful') for r in items)/n,
            'source_page_support':sum(serving(r) and r.get('support',False) for r in items)/n,
            'p50_ms':statistics.median(times),'p95_ms':times[math.ceil(.95*n)-1],
            'known_model_cost_usd':sum(r.get('known_model_cost_usd',0) for r in items),
            'embedding_cost_upper_proxy_usd':sum(r.get('embedding_cost_upper_proxy_usd',0) for r in items),
            'cost_complete':all(r.get('cost_complete',False) for r in items),
            'original_judge_known_cost_usd':sum(r.get('judge_known_cost_usd',0) for r in items),
            'recovered_judge_known_cost_usd':sum(judges[(r['attempt_id'],condition)].get('known_cost_usd',0) for r in items),
            'loop_stops':dict(collections.Counter((r.get('agentic') or {}).get('stop_reason','not_applicable') for r in items)),
            'second_rounds':sum((r.get('agentic') or {}).get('rounds',0)>1 for r in items)}
        group=result[condition]
        group['judge_completed']=sum(serving(r) and judged(r) for r in items)
        group['judge_states']=dict(collections.Counter(judges[(r['attempt_id'],condition)]['status'] for r in items))
        group['correctness_lower_bound']=group['correctness']
        group['faithfulness_lower_bound']=group['faithfulness']
        if group['judge_failures']:
            group['correctness']=None
            group['faithfulness']=None
    b,c=result['baseline'],result['agentic']
    complete_quality=b['correctness'] is not None and c['correctness'] is not None
    checks={'judge_complete':b['judge_failures']==c['judge_failures']==0,
        'quality_minimum':complete_quality and c['correctness']>=.95,
        'quality_improved':complete_quality and c['correctness']-b['correctness']>=.02-1e-10,
        'faithfulness_noninferior':complete_quality and c['faithfulness']>=b['faithfulness'],
        'support_noninferior':c['source_page_support']>=b['source_page_support'],
        'failure_noninferior':c['failure_rate']<=b['failure_rate'],
        'latency_bounded':c['p50_ms']<=b['p50_ms']*1.5 and c['p95_ms']<=b['p95_ms']*1.5,
        'cost_complete':b['cost_complete'] and c['cost_complete'],
        'cost_bounded':c['known_model_cost_usd']+c['embedding_cost_upper_proxy_usd']<=2*(b['known_model_cost_usd']+b['embedding_cost_upper_proxy_usd'])}
    result.update(checks=checks,rollout_gate=all(checks.values()),
        limitations=['100 attempts repeat 40 development questions; not 100 independent user outcomes.',
        'RAG boundary latency excludes auth/DB/queue/browser; not public end-to-end p95.',
        'No latest-user-record reads: freshness is not applicable to this retrieval-only comparison.',
        'Pro rubric is an automated judge, not blind human or Ragas validation.',
        'Embedding SDK metadata=None; UTF8 bytes are conservative proxy, not billed tokens. Cost is incomplete.',
        'Dense-only recipe matches 512MiB dense fallback, not larger-host hybrid mode.'])
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('directory',type=Path); p.add_argument('--grades-name',default='recovered-judges.jsonl'); args=p.parse_args()
    read=lambda name:[json.loads(v) for v in (args.directory/name).read_text(encoding='utf-8').splitlines()]
    report=analyze(read('attempts.jsonl'),read(args.grades_name))
    (args.directory/'summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))
