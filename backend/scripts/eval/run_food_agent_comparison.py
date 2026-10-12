"""Paired live-Gemini/current-Agent catalog ablation. No historical speedup or user outcomes."""
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.agents.team import DietTeam
from app.tools.food_catalog import FoodCatalog
from app.db.food_catalog import FoodRepository
from app.core.service_clock import service_today
from app.core.config import get_settings


class MemoryProposals:
    async def create(self, user, thread, payload, key):
        return {'id': str(uuid4()), 'version': 1, 'status': 'pending', 'payload': payload}


async def main():
    samples = []
    remote = FoodCatalog(repository=FoodRepository())
    cases = [('rice', '멥쌀, 백미, 밥', None), ('ricepaper', '라이스페이퍼', None), ('pigbar', '돼지바', None)]
    selected = []
    for label, query, _ in cases:
        candidates = await remote.search(query)
        assert candidates, query
        candidate = candidates[0]  # Explicit synthetic choice, never pretending it is the user's product.
        selected.append((label, candidate['name'], candidate['food_id']))
    for repetition in range(3):
        for label, name, food_id in selected:
            # Alternate order to reduce systematic warmup/order bias.
            variants = [('csv_only', None), ('csv_mfds', FoodRepository())]
            if repetition % 2:
                variants.reverse()
            for variant, repository in variants:
                started = time.perf_counter()
                team = DietTeam({'message': f'제품 선택: {food_id} / {name} 50g 먹었어. 오늘 간식 기록만 해줘.',
                    'requested_action': 'record_only', 'user_id': str(uuid4()),
                    'thread_id': 'synthetic-catalog-eval', 'today_date': service_today().isoformat()},
                    repository=MemoryProposals(), db=object(),
                    config={'tags': ['synthetic', 'food-catalog-ablation'], 'metadata': {'variant': variant, 'case': label}})
                team.food_catalog = FoodCatalog(repository=repository)
                result = await team.execute()
                proposal = result.get('pending_proposal')
                meals = (proposal or {}).get('payload', {}).get('meals', [])
                sample = {'case': label, 'repetition': repetition + 1, 'variant': variant,
                    'status': result['execution_status'], **result['execution_usage'],
                    'wall_seconds': round(time.perf_counter() - started, 3),
                    'proposal_prepared': bool(proposal), 'exact_selected_product': bool(meals) and all(m.get('food_id') == food_id for m in meals),
                    'sources': sorted({m['source'] for m in meals}),
                    'events': result['agent_events'], 'synthetic_response': result['response']}
                samples.append(sample)
                print(json.dumps(sample), flush=True)
                save(samples, selected)


def save(samples, selected):
    aggregates = []
    for variant in ('csv_only', 'csv_mfds'):
        group = [s for s in samples if s['variant'] == variant]
        if not group:
            continue
        aggregates.append({'variant': variant, 'n': len(group),
            'median_model_calls': statistics.median(s['model_calls'] for s in group),
            'median_tool_calls': statistics.median(s['tool_calls'] for s in group),
            'median_wall_seconds': statistics.median(s['wall_seconds'] for s in group),
            'proposal_count': sum(s['proposal_prepared'] for s in group),
            'exact_product_proposals': sum(s['exact_selected_product'] for s in group)})
    report = {'scope': 'synthetic_live_gemini_current_agent_catalog_only_ablation',
        'model': get_settings().gemini_model, 'domain_writes': 0, 'proposal_repository': 'in_memory',
        'cases': [{'case': label, 'name': name, 'selected_food_id': food_id} for label, name, food_id in selected],
        'samples': samples, 'aggregates': aggregates,
        'limitations': ['3 repetitions per case; no meaningful p95', 'Not an historical 100-second incident comparison',
                        'Catalog-only ablation of current Agent; includes local CSV construction, Gemini, DB reads',
                        'Synthetic explicit product choices; no user outcome or manufactured identity inference']}
    destination = Path(__file__).resolve().parents[3] / 'docs/food_catalog/AGENT_COMPARISON.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
