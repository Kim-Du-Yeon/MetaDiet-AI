"""Frozen synthetic parser coverage; not live Agent latency or user outcomes."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.tools.simple_meals import parse_simple_meal, calculate_simple_meal, PORTIONS
from app.tools.food_catalog import FoodCatalog

CASES = ['밤크림빵', '버섯피자', '새우만두', '양념치킨', '김치볶음밥', '불고기버거', '수제쿠키', '딸기케이크', '참치샌드위치', '브랜드아이스크림', '망고주스', '탄산음료', '제로콜라', '컵라면', '크림스파게티', '치즈감자튀김', '플레인요거트', '아메리카노']


async def main():
    root = Path(__file__).resolve().parents[3]
    before = {}
    source = subprocess.check_output(['git', 'show', '3d45904:backend/app/tools/simple_meals.py'],
                                     cwd=root, timeout=30).decode('utf-8')
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
    report = {'scope': 'synthetic_deterministic_parser_and_catalog', 'baseline': '3d45904',
              'cases': len(rows), 'before_complete': sum(row['baseline_complete'] for row in rows),
              'after_complete': sum(row['after_complete'] for row in rows),
              'configured_mappings': len(PORTIONS), 'results': rows,
              'limitations': 'No live Agent latency or actual user success measured. App portions and generic approximations are editable.'}
    (root / 'docs/simple_meals/FOOD_GROUP_EVALUATION.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
