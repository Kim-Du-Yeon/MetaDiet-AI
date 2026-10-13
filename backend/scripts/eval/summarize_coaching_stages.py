"""Summarize paired synthetic measurements without double-counting nested spans."""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / 'docs/coaching_stages'


def summarize():
    result = {}
    for phase in ('before', 'after'):
        data = json.loads((ROOT / f'{phase.upper()}_MULTITURN.json').read_text(encoding='utf-8'))
        rows = data['rows']
        assert len(rows) == 12
        assert all(row['stage_timings_ms'].get('budget_storage', 0) > 0 for row in rows)
        def median(fn):
            return round(statistics.median(fn(r) for r in rows), 1)
        result[phase] = {k: median(lambda r: r[k]) for k in ('first_answer_ms', 'total_ms')}
        for stage in ('budget_storage', 'db_read', 'model_supervisor', 'model_meal', 'graph_total', 'public_stats'):
            result[phase][stage] = median(lambda r: r['stage_timings_ms'].get(stage, 0))
        result[phase]['model_total'] = median(lambda r: sum(v for k,v in r['stage_timings_ms'].items() if k.startswith('model_')))
        result[phase]['model_calls'] = median(lambda r: r['usage']['model_calls'])
        result[phase]['tool_calls'] = median(lambda r: r['usage']['tool_calls'])
        result[phase]['turn_median_ms'] = [round(statistics.median(r['total_ms'] for r in rows if r['turn'] == turn),1) for turn in (0,1)]
    result['limitations'] = '12 synthetic requests per version, sequential not randomized. Nested graph spans must not be summed. Missing role span means role not called. No production p95 or causal estimate.'
    (ROOT / 'SUMMARY.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    summarize()
