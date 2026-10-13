"""Frozen synthetic parser coverage; not live Agent latency or user outcomes."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.tools.simple_meals import parse_simple_meal, calculate_simple_meal, PORTIONS
from app.tools.food_catalog import FoodCatalog

CASES = ['소보로 빵을 먹었어', '메론빵으 ㄹ먹었어', '도미노피자를 먹었어',
         '냉동피자르 먹었어', '물만두를 머겅써', '군만두를 먹었어',
         '물만두 8개 군만두 3개', '도미노 피자 3조각', '피자 반판',
         '소보루빵 2개 멜론빵 100g', '베이글 크로와상 단팥빵', '만두 김치만두 햄버거']


async def main():
    root = Path(__file__).resolve().parents[3]
    before = {}
    source = subprocess.check_output(['git', 'show', 'ddd82c8:backend/app/tools/simple_meals.py'],
                                     cwd=root).decode('utf-8')
    exec(compile(source, '<baseline-simple-meals>', 'exec'), before)
    catalog = FoodCatalog()
    rows = []
    for message in CASES:
        old = before['parse_simple_meal'](message, allow_unknown=True)
        parsed = parse_simple_meal(message, allow_unknown=True)
        complete = parsed is not None and not any(item.get('unresolved') for item in parsed['items'])
        assert complete, message
        quote = await calculate_simple_meal(parsed, catalog)
        rows.append({'input': message, 'baseline_complete': bool(old and not any(
            item.get('unresolved') for item in old['items'])), 'after_complete': complete,
            'grams': [meal['quantity_g'] for meal in quote['meals']],
            'calories': sum(meal['calories'] for meal in quote['meals'])})
    report = {'scope': 'synthetic_deterministic_parser_and_catalog', 'baseline': 'ddd82c8',
              'cases': len(rows), 'before_complete': sum(row['baseline_complete'] for row in rows),
              'after_complete': sum(row['after_complete'] for row in rows),
              'configured_mappings': len(PORTIONS), 'results': rows,
              'limitations': 'No live Agent latency or actual user success measured. App portions and generic approximations are editable.'}
    (root / 'docs/simple_meals/CATEGORY_EVALUATION.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
