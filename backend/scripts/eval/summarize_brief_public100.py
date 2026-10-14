"""Frozen gates: complete matched evidence, median improvement and no p95 regression."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from summarize_latency100 import distribution, quality, summarize, RUBRIC
from summarize_budget_public100 import complete_missing_grades

ROOT = Path(__file__).resolve().parents[3]


def gates(groups, grades, stages):
    a, b = (groups[p]['duration_ms_all_attempts'] for p in ('before', 'after'))
    return {
        'complete_safe_fresh': all(groups[p][k] == 100 for p in groups for k in ('completed', 'fresh', 'no_write')),
        'no_proposals': all(groups[p]['unexpected_proposals'] == 0 for p in groups),
        'complete_judge': all(grades[p]['judge_completed'] == 100 for p in grades),
        'quality_nonregression': all(grades['after'][k] >= grades['before'][k] for k in RUBRIC),
        'all_attempt_median_5_percent': b['median'] <= .95 * a['median'],
        'all_attempt_p95_nonregression': b['p95'] <= a['p95'],
        'model_median_10_percent': stages['after']['model_meal']['median'] <= .9 * stages['before']['model_meal']['median'],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--complete-missing-judges', action='store_true')
    parser.add_argument('--experiment', choices=['brief', 'model'], default='brief')
    args = parser.parse_args()
    folder = ROOT / ('docs/model_followup_public' if args.experiment == 'model' else 'docs/brief_followup_public')
    reports, measured, grades, stages, primary = {}, {}, {}, {}, {}
    for phase in ('before', 'after'):
        path = folder / (phase + '.json')
        report = json.loads(path.read_text(encoding='utf-8'))
        judged = json.loads((folder / (phase + '_quality.json')).read_text(encoding='utf-8'))
        primary[phase] = quality(judged['rows'])
        supplement = folder / (phase + '_quality_retry.json')
        if args.complete_missing_judges and supplement.exists():
            judged = complete_missing_grades(judged, json.loads(supplement.read_text(encoding='utf-8')))
        assert judged['source_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
        rows = report['rows']
        assert [r['pair'] for r in rows] == list(range(100))
        assert all((r.get('build') or {}).get('commit') == report['expected_commit'] for r in rows)
        assert all(r.get('answer_style') == ('brief' if phase == 'after' and args.experiment == 'brief' else 'default')
                   and 'budget_setup_enqueue' in r['stage_timings_ms'] for r in rows if r['status'] == 'completed')
        assert all((r.get('route'), r.get('reasoning'), r.get('model_delivery'), r.get('model_name')) == (
            'followup_direct', 'low', 'invoke', 'gemini-3.5-flash-lite' if phase == 'after' and args.experiment == 'model'
            else 'gemini-3.8-flash') for r in rows if r['status'] == 'completed')
        assert {r['index'] for r in judged['rows']} == set(range(100))
        reports[phase] = report
        measured[phase] = summarize(rows)
        grades[phase] = quality(judged['rows'])
        grades[phase]['judge_model'] = judged['judge']
        stages[phase] = {k: distribution([r.get('stage_timings_ms', {}).get(k) for r in rows])
                         for k in ('model_meal', 'budget_storage', 'db_read', 'graph_total')}
        stages[phase]['output_tokens'] = distribution([(r.get('model_tokens') or {}).get('output_tokens') for r in rows])
    a, b = reports.values()
    assert a['dataset_sha256'] == b['dataset_sha256']
    if args.experiment == 'brief': assert a['expected_commit'] == b['expected_commit']
    assert grades['before']['judge_model'] == grades['after']['judge_model']
    assert all(all(x[k] == y[k] for k in ('pair', 'case', 'question', 'expected_calories', 'expected_target'))
               for x, y in zip(a['rows'], b['rows']))
    checks = gates(measured, grades, stages)
    checks['complete_finite_timings'] = all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0
        for report in reports.values() for r in report['rows'] for v in
        (r.get('total_ms'), r.get('stage_timings_ms', {}).get('model_meal'))) and all(
        stages[p]['model_meal']['n'] == 100 for p in stages)
    result = dict(experiment=args.experiment, measurement=measured, quality=grades, primary_quality=primary, stages=stages,
                  gates=checks, adopt=all(checks.values()),
                  limitations=['Sequential windows, 20 repeated synthetic cases, not independent users.',
                               'One automated same-provider judge; no clinical correctness claim.'])
    (folder / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
