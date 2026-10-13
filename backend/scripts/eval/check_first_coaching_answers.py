"""Check explicitly requested remaining calories, never infer from unrelated numbers."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def remaining_calories(answer):
    text = answer.replace('**','').replace(',','')
    patterns = [
        r'남(?:은|아\s*있는)\s*(?:칼로리|열량|에너지)[^\d\n]{0,30}(\d+(?:\.\d+)?)\s*(?:kcal|칼로리)',
        r'(\d+(?:\.\d+)?)\s*(?:kcal|칼로리)(?:가|의)?\s*(?:그대로\s*)?(?:남아|여유)',
    ]
    values = {float(value) for pattern in patterns for value in re.findall(pattern, text, re.I)}
    return values.pop() if len(values) == 1 else None


def main():
    folder = ROOT/'docs/first_coaching'
    rows = json.loads((folder/'ALTERNATING.json').read_text(encoding='utf-8'))['rows']
    assert len(rows)==18
    checks = [{'level':r['level'],'pair':r['pair'],'expected':r['expected_remaining'],
        'observed':remaining_calories(r['answer']), 'passed':remaining_calories(r['answer'])==r['expected_remaining']} for r in rows]
    result = {'scope':'explicit_remaining_calories_in_synthetic_answers','checks':checks,
        'summary':{p:sum(c['passed'] for c in checks if c['level']==p) for p in sorted({c['level'] for c in checks})}}
    (folder/'FRESHNESS_MODEL.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result['summary']))
    assert all(c['passed'] for c in checks), 'Check raw answer: missing/incorrect remaining calories'


if __name__ == '__main__': main()
