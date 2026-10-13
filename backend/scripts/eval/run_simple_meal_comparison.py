"""Same-version live Gemini ablation: deterministic path on/off; no domain writes."""
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / '.env')
from app.agents.team import DietTeam
from app.tools.food_catalog import FoodCatalog
from app.db.food_catalog import FoodRepository
from app.core.config import get_settings


class MemoryProposals:
    async def create(self, user, thread, payload, key):
        return {'id': str(uuid4()), 'kind': payload['kind'], 'version': 1, 'status': 'pending', 'payload': payload}


async def main():
    cases = [('default', '닭가슴살 밥 한공기 김치', [100, 200, 40]),
             ('counts', '닭가슴살 2개 밥 1.5공기 김치', [200, 300, 40]),
             ('ricepaper', '라이스페이퍼 8장', [80])]
    samples = []
    for repetition in range(3):
        for case, message, grams in cases:
            for enabled in ([False, True] if repetition % 2 == 0 else [True, False]):
                start = time.perf_counter()
                team = DietTeam({'user_id': str(uuid4()), 'message': message, 'requested_action': 'record_only',
                    'thread_id': 'synthetic-simple-eval', 'run_id': str(uuid4())},
                    repository=MemoryProposals(), db=object(), simple_meals_enabled=enabled,
                    config={'tags': ['synthetic', 'simple-meal-ablation']})
                team.food_catalog = FoodCatalog(repository=FoodRepository())
                result = await team.execute()
                meals = (result.get('pending_proposal') or {}).get('payload', {}).get('meals', [])
                samples.append({'case': case, 'repetition': repetition + 1,
                    'variant': 'simple_path' if enabled else 'agent_path',
                    'wall_seconds': round(time.perf_counter() - start, 3),
                    **result['execution_usage'], 'status': result['execution_status'],
                    'proposal_prepared': bool(meals), 'expected_portions': [m['quantity_g'] for m in meals] == grams,
                    'product_selection_required': bool(result.get('food_selection')),
                    'response': result['response']})
                save(samples)
                print(json.dumps({k: v for k, v in samples[-1].items() if k != 'response'}), flush=True)


def save(samples):
    report = {'scope': 'same_version_live_gemini_fast_path_on_off_ablation', 'model': get_settings().gemini_model,
        'domain_writes': 0, 'samples': samples, 'aggregates': [],
        'limitations': ['Synthetic inputs, 3 repetitions per case; not real user outcomes or an historical-version comparison.',
            'Wall time includes local catalog initialization; excludes HTTP, persistent proposals, and Render cold start.',
            'No meaningful p95 from this small sample; approval is not counted as a clarification.']}
    for variant in ('agent_path', 'simple_path'):
        group = [s for s in samples if s['variant'] == variant]
        if group:
            report['aggregates'].append({'variant': variant, 'n': len(group),
                **{f'median_{key}': statistics.median(s[key] for s in group)
                   for key in ('model_calls', 'tool_calls', 'wall_seconds')},
                'proposals': sum(s['proposal_prepared'] for s in group),
                'expected_portions': sum(s['expected_portions'] for s in group),
                'product_selection_required': sum(s['product_selection_required'] for s in group)})
    path = Path(__file__).resolve().parents[3] / 'docs/simple_meals/COMPARISON.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
