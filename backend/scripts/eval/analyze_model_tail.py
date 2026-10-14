"""Diagnostic associations from immutable public logs; not causal attribution."""
import hashlib
import json
import statistics
from pathlib import Path
from summarize_latency100 import distribution

ROOT = Path(__file__).resolve().parents[3]


def main():
    rows, hashes = [], {}
    for phase in ('before', 'after'):
        path = ROOT / 'docs/budget_public_v2' / (phase + '.json')
        hashes[phase] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.extend({**r, 'phase': phase} for r in json.loads(path.read_text(encoding='utf-8'))['rows'])
    def group(selected):
        return {'n': len(selected), 'model_ms': distribution([r['stage_timings_ms']['model_meal'] for r in selected]),
                'output_tokens': distribution([r['model_tokens']['output_tokens'] for r in selected]),
                'input_tokens': distribution([r['model_tokens']['input_tokens'] for r in selected])}
    timings = [r['stage_timings_ms']['model_meal'] for r in rows]
    outputs = [r['model_tokens']['output_tokens'] for r in rows]
    chars = [len(r['answer']) for r in rows]
    result = {'source_sha256': hashes, 'all': group(rows),
              'correlation_output_tokens_model_ms': statistics.correlation(outputs, timings),
              'output_tokens_semantics': 'LangChain candidates_token_count + thoughts_token_count; NOT visible answer length.',
              'correlation_visible_answer_chars_model_ms': statistics.correlation(chars, timings),
              'visible_answer_chars': distribution(chars),
              'by_case': {case: group([r for r in rows if r['case'] == case]) for case in sorted({r['case'] for r in rows})},
              'slowest': [{k: r.get(k) for k in ('phase', 'pair', 'case', 'total_ms', 'usage', 'model_tokens', 'stage_timings_ms', 'external_failures')}
                          for r in sorted(rows, key=lambda r: r['stage_timings_ms']['model_meal'], reverse=True)[:10]],
              'limitations': ['Model stage includes SDK/network/provider/thinking/decode; historical logs do not split them.',
                              'Combined answer/reasoning token association does not explain the 17.14s outlier.',
                              'No observed retry in these 200 attempts; provider internal root cause unknown.']}
    folder = ROOT / 'docs/model_followup_public'
    folder.mkdir(exist_ok=True)
    path = folder / 'historical_analysis.json'
    assert not path.exists(), 'Refusing to overwrite evidence'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'slowest'}, indent=2))


if __name__ == '__main__': main()
