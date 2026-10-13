"""Summarize complete evidence only; failed attempts stay in denominators."""
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUBRIC = ('relevant', 'actionable', 'no_invented_intake', 'no_false_save_claim', 'concise')


def distribution(values):
    values = sorted(v for v in values if isinstance(v, (int, float)))
    if not values:
        return {'n': 0, 'median': None, 'p95': None}
    return {'n': len(values), 'median': round(statistics.median(values), 2),
            'p95': round(values[math.ceil(.95 * len(values)) - 1], 2)}


def summarize(rows):
    if len(rows) != 100:
        raise ValueError('Each comparison condition requires exactly 100 attempts')
    completed = [r for r in rows if r.get('status') == 'completed']
    return {'attempts': len(rows), 'completed': len(completed),
            'failed_or_blocked': len(rows) - len(completed),
            'unexpected_proposals': sum(bool(r.get('unexpected_proposal')) for r in rows),
            'first_answer_ms_completed': distribution([r.get('first_answer_ms') for r in completed]),
            'total_ms_completed': distribution([r.get('total_ms') for r in completed]),
            'duration_ms_all_attempts': distribution([r.get('total_ms', r.get('ms')) for r in rows]),
            'model_calls_completed': distribution([(r.get('usage') or {}).get('model_calls') for r in completed]),
            'fresh': sum(r.get('fresh') is True for r in rows) if any('fresh' in r for r in rows) else None,
            'no_write': sum(r.get('no_write') is True for r in rows) if any('no_write' in r for r in rows) else None}


def quality(rows):
    if len(rows) != 100 or len({r['index'] for r in rows}) != 100:
        raise ValueError('Quality requires 100 unique judged attempts')
    return {'attempts': 100, 'judge_completed': sum(r['judge_status'] == 'completed' for r in rows),
            **{key: sum(r.get(key) is True and r['judge_status'] == 'completed' for r in rows) for key in RUBRIC}}


def main():
    folder = ROOT / 'docs/latency100'
    load = lambda name: json.loads((folder / (name + '.json')).read_text(encoding='utf-8'))
    before, after = load('before'), load('after')
    if before['dataset_sha256'] != after['dataset_sha256']:
        raise ValueError('Dataset mismatch')
    if [(r['case'], r['repeat']) for r in before['rows']] != [(r['case'], r['repeat']) for r in after['rows']]:
        raise ValueError('Pair/order mismatch')
    result = {'public': {name: summarize(data['rows']) for name, data in [('before', before), ('after', after)]}}
    result['quality'] = {name: quality(load(name + '_quality')['rows']) for name in ('before', 'after')}
    native, native_quality = load('native_stream'), load('native_stream_quality')
    result['native'] = {mode: summarize([r for r in native['rows'] if r['mode'] == mode]) for mode in ('invoke', 'buffered_stream')}
    result['native_quality'] = {mode: quality([r for r in native_quality['rows'] if r['mode'] == mode]) for mode in ('invoke', 'buffered_stream')}
    result['budget_ms'] = {}
    for mode in ('before', 'after'):
        rows = [r for r in load('budget')['rows'] if r['mode'] == mode]
        if len(rows) != 100:
            raise ValueError('Budget requires 100 attempts per condition')
        result['budget_ms'][mode] = distribution([r['ms'] for r in rows])
    (folder / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
