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
    args = parser.parse_args()
    folder = Path(args.folder)
    phases = ('before',) if args.baseline_only else ('before', 'after')
    measured, timing, grades, reports = {}, {}, {}, {}
    for phase in phases:
        source = folder / (phase + '.json')
        report = json.loads(source.read_text(encoding='utf-8'))
        rows = report['rows']
        assert [r['pair'] for r in rows] == list(range(100))
        assert all((r.get('build') or {}).get('commit') == report['expected_commit'] for r in rows)
        measured[phase] = summarize(rows)
        assert all((r.get('route'), r.get('reasoning'), r.get('model_delivery'), r.get('model_name'),
                    r.get('answer_style'), r.get('tool_policy'), r.get('client_reuse', False)) == (
                   'followup_direct', 'low', 'invoke', 'gemini-3.8-flash', 'default', 'read', phase == 'after')
                   for r in rows if r['status'] == 'completed')
        timing[phase] = {k: distribution([r.get('stage_timings_ms', {}).get(k) for r in rows]) for k in PHASES}
        reports[phase] = report
        if not args.baseline_only:
            judge = json.loads((folder / (phase + '_quality.json')).read_text(encoding='utf-8'))
            assert judge['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
            assert {r['index'] for r in judge['rows']} == set(range(100))
            grades[phase] = quality(judge['rows'])
            grades[phase]['judge_model'] = judge['judge']
    result = {'measurement': measured, 'stages': timing, 'quality': grades,
        'limitations': ['Provider roundtrip includes serialization, transport, generation and parsing.',
                        'Nested timers are not additive; sequential repeated synthetic cases, not real users.']}
    if not args.baseline_only:
        before, after = reports['before'], reports['after']
        assert before['dataset_sha256'] == after['dataset_sha256']
        assert all(all(a[k] == b[k] for k in ('pair', 'case', 'question', 'expected_calories', 'expected_target'))
                   for a, b in zip(before['rows'], after['rows']))
        assert grades['before']['judge_model'] == grades['after']['judge_model']
        checks = gates(measured, grades, timing)
        checks['phase_complete'] = all(timing[p][k]['n'] == 100 for p in phases for k in PHASES)
        checks['finite_phase_timings'] = all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0
            for report in reports.values() for r in report['rows']
            for v in (r.get('stage_timings_ms', {}).get(k) for k in PHASES))
        checks['failure_rate_nonregression'] = measured['after']['failed_or_blocked'] <= measured['before']['failed_or_blocked']
        result.update(gates=checks, adopt=all(checks.values()))
    target = folder / ('baseline_phases.json' if args.baseline_only else 'summary.json')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
