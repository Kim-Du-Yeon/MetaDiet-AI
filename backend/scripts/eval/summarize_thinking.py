"""Summarize the fixed public dialogs; refuse incomplete/wrong-route samples."""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FOLDER = ROOT/'docs/coaching_thinking'


def main():
    result = {'scope':'small_sequential_public_before_after_not_randomized',
        'before_commit':'41562aa', 'after_commit':'b051f24'}
    keys = []
    for phase in ('before','after'):
        rows = json.loads((FOLDER/f'{phase.upper()}_MULTITURN.json').read_text(encoding='utf-8'))['rows']
        assert len(rows) == 12
        keys.append(sorted((r['scenario'],r['repeat'],r['turn']) for r in rows))
        result[phase] = {}
        for turn, label in ((0,'first'),(1,'followup')):
            group = [r for r in rows if r['turn']==turn]
            assert len(group) == 6 and all(r['answer'].strip() for r in group)
            if turn:
                assert all(r['stage_timings_ms'].get('model_meal',0)>0 and
                    'model_supervisor' not in r['stage_timings_ms'] for r in group)
            result[phase][label] = {
                **{metric:statistics.median(r[metric] for r in group) for metric in ('total_ms','first_answer_ms')},
                **{metric:statistics.median(r['usage'][metric] for r in group) for metric in ('model_calls','tool_calls')},
                'model_meal_ms':statistics.median(r['stage_timings_ms'].get('model_meal',0) for r in group)}
    assert keys[0] == keys[1]
    result['followup_total_reduction_percent'] = 100*(1-result['after']['followup']['total_ms']/result['before']['followup']['total_ms'])
    (FOLDER/'SUMMARY.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__': main()
