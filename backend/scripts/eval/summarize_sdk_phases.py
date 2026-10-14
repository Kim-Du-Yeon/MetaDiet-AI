"""Report fixed phase labels without treating nested timers as additive."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from summarize_brief_public100 import quality, RUBRIC, gates
from summarize_latency100 import summarize, distribution


PHASES = ('sdk_prepare_meal', 'tool_bind_meal', 'provider_roundtrip',
          'model_meal', 'budget_storage', 'db_read', 'graph_total')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', default='docs/sdk_phase_public')
    parser.add_argument('--baseline-only', action='store_true')
    parser.add_argument('--experiment', choices=['sdk', 'transport'], default='sdk')
    args = parser.parse_args()
    folder = Path(args.folder)
    phases = ('before',) if args.baseline_only else ('before', 'after')
    measured, timing, grades, reports = {}, {}, {}, {}
    phase_labels = PHASES + (('transport_connect', 'transport_tls', 'transport_send_headers',
        'transport_send_body', 'transport_wait_headers', 'transport_receive_body')
        if args.experiment == 'transport' else ())
    for phase in phases:
        source = folder / (phase + '.json')
        report = json.loads(source.read_text(encoding='utf-8'))
        rows = report['rows']
        assert [r['pair'] for r in rows] == list(range(100))
        assert all((r.get('build') or {}).get('commit') == report['expected_commit'] for r in rows)
        measured[phase] = summarize(rows)
        assert all((r.get('route'), r.get('reasoning'), r.get('model_delivery'), r.get('model_name'),
                    r.get('answer_style'), r.get('tool_policy'), r.get('client_reuse', False)) == (
                   'followup_direct', 'low', 'buffered_stream' if args.experiment == 'transport' and phase == 'after' else 'invoke',
                   'gemini-3.8-flash', 'default', 'read', args.experiment == 'sdk' and phase == 'after')
                   for r in rows if r['status'] == 'completed')
        timing[phase] = {k: distribution([r.get('stage_timings_ms', {}).get(k) for r in rows]) for k in phase_labels}
        timing[phase]['model_first_token_ms'] = distribution([r.get('model_first_token_ms') for r in rows])
        reports[phase] = report
        if not args.baseline_only:
            judge = json.loads((folder / (phase + '_quality.json')).read_text(encoding='utf-8'))
            assert judge['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
            assert {r['index'] for r in judge['rows']} == set(range(100))
            grades[phase] = quality(judge['rows'])
            grades[phase]['judge_model'] = judge['judge']
    result = {'measurement': measured, 'stages': timing, 'quality': grades,
        'external_errors': {p: {
            'requests_with_external_error': sum(bool(r.get('external_failures')) for r in report['rows']),
            'recorded_external_errors': sum(len(r.get('external_failures', [])) for r in report['rows']),
        } for p, report in reports.items()},
        'limitations': ['Provider roundtrip includes serialization, transport, generation and parsing.',
                        'Nested timers are not additive; sequential repeated synthetic cases, not real users.']}
    if not args.baseline_only:
        before, after = reports['before'], reports['after']
        assert before['dataset_sha256'] == after['dataset_sha256']
        assert all(all(a[k] == b[k] for k in ('pair', 'case', 'question', 'expected_calories', 'expected_target'))
                   for a, b in zip(before['rows'], after['rows']))
        assert grades['before']['judge_model'] == grades['after']['judge_model']
        checks = gates(measured, grades, timing)
        if args.experiment == 'transport':
            checks.pop('model_median_10_percent')
            a, b = (timing[p]['provider_roundtrip']['median'] for p in phases)
            checks['provider_median_10_percent'] = all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0
                for v in (a, b)) and b <= .9 * a
        checks['phase_complete'] = all(timing[p][k]['n'] == 100 for p in phases for k in PHASES)
        checks['finite_phase_timings'] = all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0
            for report in reports.values() for r in report['rows']
            for v in (r.get('stage_timings_ms', {}).get(k) for k in PHASES))
        checks['failure_rate_nonregression'] = measured['after']['failed_or_blocked'] <= measured['before']['failed_or_blocked']
        if args.experiment == 'transport':
            checks['transport_phase_complete'] = all(timing[p][k]['n'] == 100 for p in phases
                for k in ('transport_wait_headers', 'transport_receive_body'))
        result.update(gates=checks, adopt=all(checks.values()))
    target = folder / ('baseline_phases.json' if args.baseline_only else 'summary.json')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
