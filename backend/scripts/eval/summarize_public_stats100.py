"""Matched public attempts: separate answer quality from final statistics availability."""
import argparse
import json
import math
import statistics
from pathlib import Path
from summarize_request_startup100 import summarize

ROOT = Path(__file__).resolve().parents[3]


def summary(report):
    result = summarize(report)
    rows = report['rows']
    expected = dict(zip(('today_calories', 'target_calories'), report['expected']))
    result['stats_correct'] = sum(row.get('public_stats') == expected for row in rows)
    result['stats_missing_or_wrong'] = 100 - result['stats_correct']
    result['stats_error_attempts'] = sum(any(e.get('operation') == 'public_stats'
        for e in row.get('external_failures', [])) for row in rows)
    values = sorted(row['stage_timings_ms']['public_stats'] for row in rows
                    if 'public_stats' in row.get('stage_timings_ms', {}))
    result['stats_latency'] = {'observed': len(values), 'missing':100-len(values),
        'median_ms':round(statistics.median(values),3) if values else None,
        'p95_ms':round(values[math.ceil(.95*len(values))-1],3) if values else None}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', default='docs/public_stats_recovery')
    args = parser.parse_args()
    folder = ROOT/args.folder
    before, after = [json.loads((folder/f'{phase}_frozen100.json').read_text(encoding='utf-8'))
                     for phase in ('before', 'after')]
    assert before['dataset_sha256'] == after['dataset_sha256'] and before['expected'] == after['expected']
    result = {'scope':before['scope'], 'dataset_sha256':before['dataset_sha256'],
              'before':summary(before), 'after':summary(after)}
    b, a = result['before'], result['after']
    result['safety_gate_passed'] = (a['stats_correct'] >= b['stats_correct']
        and a['fresh_numeric_match'] >= b['fresh_numeric_match']
        and a['statuses'].get('failed',0) <= b['statuses'].get('failed',0)
        and a['runtime_blocked'] <= b['runtime_blocked']
        and a['no_domain_writes'])
    # Reliability recovery is the objective. Do not label a slower result a speed win.
    result['stats_speed_improved'] = (a['stats_latency']['median_ms'] < b['stats_latency']['median_ms']
                                     and a['stats_latency']['p95_ms'] < b['stats_latency']['p95_ms'])
    (folder/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
