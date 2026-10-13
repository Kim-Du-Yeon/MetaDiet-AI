"""Frozen adoption rule for a single durable-storage optimization."""
import hashlib
import json
from pathlib import Path
from summarize_latency100 import distribution, quality, summarize

ROOT = Path(__file__).resolve().parents[3]


def decision(base, candidate, storage, grades):
    a, b = base['total_ms_completed'], candidate['total_ms_completed']
    valid = a['median'] is not None and b['median'] is not None
    return {
        'complete_timing_and_judge_evidence': all(storage[m]['n'] == 100 and grades[m]['judge_completed'] == 100 for m in ('baseline','pipeline')),
        'storage_median_20_percent': storage['pipeline']['median'] is not None and storage['baseline']['median'] is not None and storage['pipeline']['median'] <= .8 * storage['baseline']['median'],
        'total_median_5_percent': valid and b['median'] <= .95 * a['median'],
        'p95_not_10_percent_worse': valid and b['p95'] <= 1.1 * a['p95'],
        'completion_freshness_no_write': all(candidate[k] >= base[k] for k in ('completed', 'fresh', 'no_write')),
        'quality_nonregression': all(grades['pipeline'][k] >= grades['baseline'][k] for k in grades['baseline']),
    }


def main():
    folder = ROOT / 'docs/budget_pipeline'
    data = json.loads((folder/'paired.json').read_text(encoding='utf-8'))
    judged = json.loads((folder/'paired_quality.json').read_text(encoding='utf-8'))
    assert data['schema_cleaned'], 'Isolated schema cleanup required'
    expected_safety = {'concurrent_reserved':5, 'concurrent_blocked':7, 'restart_cap':True, 'rollback':True}
    assert all(data['safety'][m] == expected_safety for m in ('baseline','pipeline')), 'Safety evidence incomplete'
    assert judged['source_sha256'] == hashlib.sha256((folder/'paired.json').read_bytes()).hexdigest()
    modes = ('baseline', 'pipeline')
    groups = {m:sorted([r for r in data['rows'] if r['mode'] == m], key=lambda r:r['pair']) for m in modes}
    assert all([r['pair'] for r in group] == list(range(100)) for group in groups.values())
    for a,b in zip(*groups.values()):
        assert all(a[k] == b[k] for k in ('question','case','expected_calories','expected_target'))
    measured = {m:summarize(rows) for m,rows in groups.items()}
    stages = {m:{key:distribution([r.get('stage_timings_ms',{}).get(key) for r in rows])
                 for key in ('budget_storage','budget_connection_wait','budget_pool_checkout','budget_setup',
                             'budget_setup_enqueue','budget_sql','budget_commit','model_meal')}
              for m,rows in groups.items()}
    grades = {m:quality([r for r in judged['rows'] if r['mode'] == m]) for m in modes}
    gates = decision(measured['baseline'], measured['pipeline'], {m:stages[m]['budget_storage'] for m in modes}, grades)
    result = {'scope': data['scope'], 'measurement': measured, 'stages': stages, 'quality': grades,
              'gates': gates, 'adopt': all(gates.values()), 'safety': data['safety']}
    (folder/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
