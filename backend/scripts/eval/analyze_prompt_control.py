"""Analyze frozen saved results. No provider calls or favorable posthoc gate changes."""
import hashlib,json,math,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"backend"))

def percentile(values,p):return sorted(values)[max(0,math.ceil(len(values)*p)-1)] if values else None

def analyze(report,judges):
    if len({r['case_id'] for r in report['rows']})>100:raise ValueError('Unexpected cohort')
    grades={}
    for pair in judges['rows']:
        for position,label in pair['mapping'].items():
            grades[(pair['case_id'],label)]=pair.get('grades',{}).get(position) if pair['status']=='completed' else None
    summary={}
    for label in ['v1','v2']:
        rows=[r for r in report['rows'] if r['condition']==label]
        if len({r['case_id'] for r in rows})!=len(rows):raise ValueError('Duplicate result')
        complete=len(rows)==100 and all(grades.get((r['case_id'],label)) is not None for r in rows)
        good=lambda r:grades.get((r['case_id'],label)) or {}
        summary[label]={'attempts':len(rows),'expected':100,'completed':sum(r['status']=='completed' for r in rows),
            'quality_percent':sum(bool(r['status']=='completed' and r['fresh'] and r['no_write'] and good(r).get('correct') and good(r).get('faithful')) for r in rows),
            'unsupported_sufficiency':sum(bool(good(r).get('unsupported_sufficiency')) for r in rows),
            'fresh_percent':sum(bool(r.get('fresh')) for r in rows),'no_write_percent':sum(bool(r.get('no_write')) for r in rows),
            'mean_ms':statistics.mean([r['ms'] for r in rows]) if rows else None,'p95_ms':percentile([r['ms'] for r in rows],.95),
            'failure_percent':100-sum(r['status']=='completed' for r in rows),
            'generation_estimate_usd':sum(r.get('cost_usd') or 0 for r in rows),
            'usage_complete':all(r.get('cost_usd') is not None for r in rows),'judge_complete':complete,
            'implicit_cache_read_tokens':sum((u or {}).get('input_token_details',{}).get('cache_read',0) for r in rows for u in r.get('usage',[]))}
    from scripts.eval.model_routing_support import estimate_cost
    judge_costs=[estimate_cost('gemini-3.1-pro-preview',u) for row in judges['rows'] for u in row.get('usage',[])]
    judge_usage_complete=len(judges['rows'])==100 and all(row.get('usage') for row in judges['rows']) and all(v is not None for v in judge_costs)
    a,b=summary['v1'],summary['v2']
    passed=all(v['attempts']==100 and v['fresh_percent']==100 and v['no_write_percent']==100 and v['judge_complete'] and v['usage_complete'] for v in summary.values())
    passed=passed and judge_usage_complete and b['quality_percent']>=a['quality_percent']-2 and b['unsupported_sufficiency']<a['unsupported_sufficiency'] and b['p95_ms']<=a['p95_ms']*1.25 and b['generation_estimate_usd']<=a['generation_estimate_usd']*1.25
    return {'judge_usage_complete':bool(judge_usage_complete),'judge_estimate_usd':sum(v or 0 for v in judge_costs),'summary':summary,'candidate_passed':bool(passed),'selection':'v2' if passed else 'v1','denominator':'100 frozen synthetic attempts per condition; incomplete and failures count against success; repeated question templates are not independent actual-user outcomes','judge_cost_note':'Pro evaluator consumption reported separately; generation cost is token estimate, not invoice'}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--folder');args=parser.parse_args()
    folder=Path(args.folder) if args.folder else ROOT/'docs/prompt_control/comparison';report=json.loads((folder/'paired.json').read_text(encoding='utf-8'));judges=json.loads((folder/'judges.json').read_text(encoding='utf-8'))
    result=analyze(report,judges);result['source_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [folder/'paired.json',folder/'judges.json',folder/'frozen.json']}
    (folder/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
