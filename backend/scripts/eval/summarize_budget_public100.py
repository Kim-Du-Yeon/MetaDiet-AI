"""Require complete, matched public evidence before changing the default."""
import hashlib
import json
import math
from pathlib import Path
from summarize_latency100 import distribution, quality, summarize
from summarize_budget_pipeline100 import decision

ROOT = Path(__file__).resolve().parents[3]


def public_gates(base, candidate, storage, grades):
    gates = decision(base,candidate,storage,grades)
    gates['all_public_requests_safe_and_fresh'] = all(
        group[key] == 100 for group in (base,candidate) for key in ('completed','fresh','no_write'))
    gates['no_unexpected_proposals'] = all(group['unexpected_proposals']==0 for group in (base,candidate))
    gates['complete_response_timings'] = all(group['total_ms_completed'].get('n')==100 for group in (base,candidate))
    return gates


def main():
    folder = ROOT/'docs/budget_public'
    groups, grades, stages, reports, judges = {}, {}, {}, {}, {}
    for phase,mode in [('before','baseline'),('after','pipeline')]:
        source = folder/(phase+'.json')
        data = json.loads(source.read_text(encoding='utf-8'))
        judged = json.loads((folder/(phase+'_quality.json')).read_text(encoding='utf-8'))
        assert judged['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
        rows = data['rows']
        assert [r['pair'] for r in rows] == list(range(100))
        assert all(r['build']['commit']==data['expected_commit'] for r in rows if r.get('build'))
        assert all(('budget_setup_enqueue' in r['stage_timings_ms'])==(mode=='pipeline') for r in rows if r.get('status')=='completed')
        judges[mode] = judged['judge']
        reports[mode] = data
        groups[mode] = summarize(rows)
        grades[mode] = quality(judged['rows'])
        stages[mode] = {key:distribution([r['stage_timings_ms'].get(key) for r in rows]) for key in (
            'budget_storage','budget_pool_checkout','budget_setup','budget_setup_enqueue','budget_sql',
            'budget_commit','db_read','model_meal','graph_total','terminal_checkpoint','response_snapshot','public_stats')}
    a,b = reports.values()
    assert len(set(judges.values()))==1, 'Judge mismatch'
    assert a['dataset_sha256']==b['dataset_sha256'] and a['expected_commit']==b['expected_commit']
    assert all(all(x[k]==y[k] for k in ('pair','case','question','expected_calories','expected_target'))
               for x,y in zip(a['rows'],b['rows']))
    gates = public_gates(groups['baseline'],groups['pipeline'],{m:stages[m]['budget_storage'] for m in groups},grades)
    gates['valid_build_and_finite_timings'] = all(
        (r.get('build') or {}).get('commit')==data['expected_commit'] and
        all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in
            (r.get('total_ms'),r.get('stage_timings_ms',{}).get('budget_storage')))
        for data in reports.values() for r in data['rows'])
    result = dict(scope='public_serial_synthetic_100_per_condition',measurement=groups,stages=stages,judges=judges,
        quality=grades,gates=gates,adopt=all(gates.values()),
        limitations=['Sequential time windows, not randomized interleaving.',
                     'One synthetic account, one automated same-provider judge.',
                     'Warm serial requests; not cold-start, concurrency, or real-user percentiles.'])
    (folder/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
