"""Compare matched public requests; nested stages are not additive."""
import json
import statistics
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[3] / 'docs/first_coaching'


def main():
    reports = {phase: json.loads((FOLDER / f'{phase.upper()}_MULTITURN.json').read_text(encoding='utf-8'))['rows']
               for phase in ('before', 'after')}
    keys = lambda rows: sorted((r['scenario'], r['repeat'], r['turn']) for r in rows)
    assert len(reports['before']) == len(reports['after']) == 12
    assert keys(reports['before']) == keys(reports['after'])
    summary = {}
    for phase, rows in reports.items():
        summary[phase] = {}
        for turn, label in ((0, 'first'), (1, 'followup')):
            selected = [r for r in rows if r['turn'] == turn]
            summary[phase][label] = {
                'samples': len(selected),
                **{key: statistics.median(r[key] for r in selected) for key in ('total_ms', 'first_answer_ms')},
                'model_calls': [r['usage']['model_calls'] for r in selected],
                'stages_ms': {key: statistics.median(r['stage_timings_ms'].get(key, 0) for r in selected)
                              for key in ('model_supervisor', 'model_meal', 'budget_storage', 'db_read', 'graph_total')},
            }
    assert all(r['usage']['model_calls'] == 1 and not r['stage_timings_ms'].get('model_supervisor') for r in reports['after'])
    output = {'scope': 'synthetic_public_matched_multiturn', 'summary': summary,
              'limitations': 'Six samples per turn/phase, warm server, sequential deployment comparison. Nested stages are not additive. No p95 or real-user claim.'}
    (FOLDER / 'SUMMARY.json').write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
