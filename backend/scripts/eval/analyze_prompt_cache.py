"""Offline aggregation: keep failed/ungraded attempts in frozen100 denominator."""
import hashlib,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.eval.model_routing_support import estimate_cost

def percentile(values):
    values=sorted(values)
    return values[math.ceil(.95*len(values))-1] if values else None

def analyze(paired,judges):
    grades={}
    completed={(r['case_id'],r['condition']) for r in paired['rows'] if r['status']=='completed'}
    for row in judges['rows']:
        if row['status']=='completed':
            for key,label in row['mapping'].items():
                if (row['case_id'],label) in completed:grades[(row['case_id'],label)]=row['grades'][key]
    output={}
    for label in ['ordinary','explicit']:
        rows=[r for r in paired['rows'] if r['condition']==label]
        if len(rows)!=100 or len({r['case_id'] for r in rows})!=100:raise ValueError('Require100 attempts per condition')
        good=[r for r in rows if r['status']=='completed']
        costs=[r.get('model_cost_usd') for r in rows]
        output[label]={
            'attempts':100,'completed':len(good),'failures':100-len(good),
            'graded':sum((r['case_id'],label) in grades for r in rows),
            'correct':sum(grades.get((r['case_id'],label),{}).get('correct',False) for r in rows),
            'faithful':sum(grades.get((r['case_id'],label),{}).get('faithful',False) for r in rows),
            'mean_ms_all_attempts':sum(r['ms'] for r in rows)/100,
            'p95_ms_all_attempts':percentile([r['ms'] for r in rows]),
            'ttft_p95_ms_observed_only':percentile([r['ttft_ms'] for r in rows if r.get('ttft_ms') is not None]),
            'ttft_observations':sum(r.get('ttft_ms') is not None for r in rows),
            'cached_input_tokens':sum(r.get('cached_input_tokens',0) for r in rows),
            'cache_hit_attempts':sum(r.get('cached_input_tokens',0)>0 for r in rows),
            'known_model_estimate_usd':sum(c for c in costs if c is not None),
            'unknown_cost_attempts':sum(c is None for c in costs),
            'creation_and_full_ttl_upper_usd':sum(r.get('cache_overhead_upper_usd',0) for r in rows),
            'stages':{stage:{'attempts':len(s), 'completed':sum(r['status']=='completed' for r in s),'p95_ms_all_attempts':percentile([r['ms'] for r in s])} for stage in ['first','reuse','ordinary'] if (s:=[r for r in rows if r['cache_stage']==stage])}}
        output[label]['known_total_upper_estimate_usd']=output[label]['known_model_estimate_usd']+output[label]['creation_and_full_ttl_upper_usd']
    a,b=output['ordinary'],output['explicit']
    gates={'correct_noninferiority_2pp':b['correct']>=a['correct']-2,'faithfulness_noninferiority_2pp':b['faithful']>=a['faithful']-2,'failure_noninferiority':b['failures']<=a['failures'],'p95_within_1_1':b['p95_ms_all_attempts']<=a['p95_ms_all_attempts']*1.1,'complete_usage':not a['unknown_cost_attempts'] and not b['unknown_cost_attempts'],'all_pairs_judged':a['graded']==a['completed'] and b['graded']==b['completed'],'saving_at_least_10percent':b['known_total_upper_estimate_usd']<=a['known_total_upper_estimate_usd']*.9}
    return {'scope':paired['scope'],'judge_api_timeout_attempts_retained':sum(r.get('error',{}).get('reason')=='timeout' for row in judges['rows'] for r in [row,*row.get('previous_attempts',[])]),'conditions':output,'gates':gates,'cache_adoption':all(gates.values()),'judge_estimate_usd':sum(estimate_cost(judges['model'],usage) or 0 for r in judges['rows'] for usage in r.get('usage',[])),'denominator_note':'100 each; failed/truncated/ungraded are zero quality; TTFT descriptive observed subset only; costs estimates not invoice; unknown costs retain budget reservation','offline_freshness_isolation':'100 synthetic invocations of cache library; not production mutation hooks','private_cache':'OFF; unique prefixes fail economics; no paired private-cache generation experiment'}

if __name__=='__main__':
    folder=Path(__file__).resolve().parents[3]/'docs/prompt_control/cache-rag'
    paths=[folder/'paired.json',folder/'judges.json']
    result=analyze(*(json.loads(p.read_text(encoding='utf-8')) for p in paths))
    result['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (folder/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
