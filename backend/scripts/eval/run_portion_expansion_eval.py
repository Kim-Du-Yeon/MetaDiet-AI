"""Synthetic reviewed portions: real CSV quotes; no LLM or health-data writes."""
import asyncio
import json
import subprocess
import sys
import types
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT / 'backend/.env')
from app.tools.simple_meals import PORTIONS, parse_simple_meal, calculate_simple_meal
from app.tools.food_catalog import FoodCatalog
from app.agents.team import DietTeam
from scripts.eval.run_simple_meal_comparison import MemoryProposals

CASES = [
    ('고구마 사과 우유', [150, 200, 200]),
    ('계란후라이 식빵 두장 플레인 요거트', [50, 60, 100]),
    ('오트밀 바나나 아몬드', [30, 100, 20]),
    ('방울 토마토 다섯개 브로콜리 오이', [75, 80, 150]),
    ('닭 가슴살, 밥 반공기, 깍두기', [100, 100, 40]),
    ('고구마랑 우유 먹었어요', [150, 200]),
    ('삶은계란 2개와 사과 반개', [100, 100]),
    ('고구마 2개 180g 우유 한컵', [180, 200]),
    ('닭가슴살 계란후라이 브로콜리', [100, 50, 80]),
]
NEGATIVE = ['고구마빵 우유', '그릭요거트', '우유 200ml', '사과주스',
            '밥하고 피자', '계란후라이 추천해줘', '아몬드 -2개']


async def main():
    previous_source = subprocess.check_output(['git', 'show',
        'd7f902a:backend/app/tools/simple_meals.py'], cwd=ROOT).decode('utf-8-sig')
    previous = types.ModuleType('previous_portions')
    exec(compile(previous_source, 'baseline-d7f902a-simple_meals.py', 'exec'), previous.__dict__)
    catalog = FoodCatalog()
    samples = []
    for message, grams in CASES:
        def no_model():
            raise AssertionError('expanded simple input must not call a model')
        team = DietTeam({'user_id': str(uuid4()), 'message': message,
            'run_id': str(uuid4()), 'thread_id': 'synthetic-expansion'},
            model_factory=no_model, repository=MemoryProposals(), db=object())
        team.food_catalog = catalog
        result = await team.execute()
        meals = result['pending_proposal']['payload']['meals']
        actual = [m['quantity_g'] for m in meals]
        assert actual == grams
        assert result['execution_usage']['model_calls'] == 0
        samples.append({'message': message, 'previous_simple_supported': previous.parse_simple_meal(message) is not None,
            'grams': actual, 'calories': sum(m['calories'] for m in meals),
            'status': result['execution_status'], 'usage': result['execution_usage']})
    assert all(parse_simple_meal(m) is None for m in NEGATIVE)
    mappings = []
    for aliases, canonical, grams, unit, food_id in PORTIONS:
        if food_id:
            continue  # MFDS representative unchanged; validated separately in the prior release.
        result = await calculate_simple_meal(parse_simple_meal(aliases[0]), catalog)
        meal = result['meals'][0]
        mappings.append({'aliases': aliases, 'canonical': canonical, 'default_g': grams,
            'unit': unit, 'food_id': meal['food_id'], 'calories': meal['calories']})
    report = {'scope': 'synthetic_expansion_csv_release_gate', 'baseline_commit': 'd7f902a',
        'domain_writes': 0, 'samples': samples, 'negative_cases_preserved': NEGATIVE,
        'reviewed_standard_mappings': mappings, 'mapping_count_including_mfds': len(PORTIONS),
        'limitations': ['App serving assumptions, not universal serving sizes.',
            'Baseline support means deterministic parser coverage, not prior Agent failure.',
            'No live HTTP latency or real-user outcomes measured.']}
    target = ROOT / 'docs/simple_meals/EXPANSION_EVALUATION.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'cases': len(samples), 'previous_supported': sum(s['previous_simple_supported'] for s in samples),
        'now_supported': len(samples), 'model_calls': 0, 'logical_tools_per_request': 2,
        'standard_mappings': len(mappings)}))


if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
