"""Predeclared single-candidate decision; never drop unsuccessful attempts."""
import hashlib
import json
from pathlib import Path
from summarize_latency100 import summarize, quality, distribution

ROOT = Path(__file__).resolve().parents[3]


def decision(base, candidate, base_quality, candidate_quality):
    a, b = base['total_ms_completed'], candidate['total_ms_completed']
    speed = b['median'] is not None and a['median'] is not None and b['median'] <= .9 * a['median']
    tail = b['p95'] is not None and a['p95'] is not None and b['p95'] <= 1.1 * a['p95']
    safety = all(candidate[k] >= base[k] for k in ('completed', 'fresh', 'no_write'))
    rubric = all(candidate_quality[k] >= base_quality[k] for k in ('judge_completed','relevant','actionable','no_invented_intake','no_false_save_claim','concise'))
    return {'median_10_percent': speed, 'p95_not_10_percent_worse': tail,
            'freshness_and_no_write': safety, 'rubric_nonregression': rubric}


def main():
    folder = ROOT / 'docs/compact_coaching'
    data = json.loads((folder / 'paired.json').read_text(encoding='utf-8'))
    judged = json.loads((folder / 'paired_quality.json').read_text(encoding='utf-8'))
    if judged['source_sha256'] != hashlib.sha256((folder / 'paired.json').read_bytes()).hexdigest():
        raise ValueError('Judge source mismatch')
    groups = {m: sorted([r for r in data['rows'] if r['mode'] == m], key=lambda r:r['pair']) for m in ('baseline', 'compact')}
    assert all(len(g) == 100 and [r['pair'] for r in g] == list(range(100)) for g in groups.values())
    for a,b in zip(groups['baseline'], groups['compact']):
        assert (a['question'],a['case'],a['expected_calories'],a['expected_target']) == (b['question'],b['case'],b['expected_calories'],b['expected_target'])
    measured = {m:summarize(rows) for m,rows in groups.items()}
    grades = {m:quality([r for r in judged['rows'] if r['mode'] == m]) for m in groups}
    base,candidate = (measured[m] for m in groups)
    gates = decision(base, candidate, grades['baseline'], grades['compact'])
    tokens = {m:{k:distribution([r.get('tokens',{}).get(k) for r in rows]) for k in ('input_tokens','output_tokens','total_tokens')} for m,rows in groups.items()}
    result = {'scope': data['scope'], 'measurement': measured, 'quality': grades, 'tokens': tokens,
              'gates': gates, 'adopt': all(gates.values())}
    (folder/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
