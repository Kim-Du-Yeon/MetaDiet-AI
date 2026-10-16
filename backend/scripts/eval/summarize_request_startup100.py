"""Keep failed/blocked attempts in every denominator; never infer browser paint."""
import collections
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FOLDER = ROOT/'docs/request_startup'


def summarize(report):
    rows = report['rows']
    assert len(rows) == 100 and len({r['index'] for r in rows}) == 100
    assert report['domain_unchanged']
    def metric(key, source=rows):
        values = sorted(r[key] for r in source if r.get(key) is not None)
        return {'observed':len(values), 'missing':len(source)-len(values),
            'median_ms':round(statistics.median(values),3) if values else None,
            'p95_ms':round(values[math.ceil(.95*len(values))-1],3) if values else None,
            'max_ms':round(max(values),3) if values else None}
    return {'attempts':100, 'statuses':dict(collections.Counter(r['status'] for r in rows)),
        'fresh_numeric_match':sum(r['fresh_numeric_match'] for r in rows),
        'no_domain_writes':report['domain_unchanged'],
        'first_progress':metric('first_progress_ms'), 'completion_all_attempts':metric('total_ms'),
        'model_calls_mean':round(statistics.mean(r.get('usage',{}).get('model_calls',0) for r in rows),3),
        'by_case':{str(i):{'statuses':dict(collections.Counter(r['status'] for r in rows if r['case']==i)),
            'completion':metric('total_ms',[r for r in rows if r['case']==i])} for i in range(4)}}


def main():
    before, after = [json.loads((FOLDER/f'{phase}_frozen100.json').read_text(encoding='utf-8')) for phase in ['before','after']]
    assert before['dataset_sha256'] == after['dataset_sha256'] and before['expected'] == after['expected']
    result = {'scope':'public synthetic API4 fixed questions x25; concurrency4; no browser-paint comparison',
        'before':summarize(before), 'after':summarize(after)}
    b, a = result['before'], result['after']
    result['candidate_gate_passed'] = (
        a['completion_all_attempts']['median_ms'] < b['completion_all_attempts']['median_ms']
        and a['completion_all_attempts']['p95_ms'] <= b['completion_all_attempts']['p95_ms']
        and a['fresh_numeric_match'] >= b['fresh_numeric_match']
        and a['statuses'].get('failed',0) <= b['statuses'].get('failed',0)
        and a['statuses'].get('blocked',0) <= b['statuses'].get('blocked',0))
    (FOLDER/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__': main()
