"""Read-only fixed catalog smoke evaluation, not an Agent/user outcome evaluation."""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from app.tools.food_catalog import FoodCatalog
from app.db.food_catalog import FoodRepository

CASES = ['멥쌀, 백미, 밥', '라이스페이퍼', '돼지바', '미등록_평가용_제품_20261012']


async def main():
    results = []
    for variant, repository in [('csv_only', None), ('csv_mfds', FoodRepository())]:
        catalog = FoodCatalog(repository=repository)
        for name in CASES:
            started = time.perf_counter()
            candidates = await catalog.search(name)
            status = 'not_found' if not candidates else 'found' if len(candidates) == 1 else 'ambiguous'
            quote = await catalog.lookup(candidates[0]['food_id'], 100) if status == 'found' else None
            results.append({'variant': variant, 'query': name, 'status': status,
                'candidate_count_capped': len(candidates), 'sources': sorted({c['source'] for c in candidates}),
                'elapsed_seconds': round(time.perf_counter() - started, 4),
                'quote_available': quote is not None, 'candidates': candidates})
    output = {'scope': 'fixed_read_only_catalog_smoke_not_agent_or_user_results', 'cases': results}
    destination = Path(__file__).resolve().parents[3] / 'docs/food_catalog/LOOKUP_EVALUATION.json'
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps([{k: v for k, v in row.items() if k != 'candidates'} for row in results], ensure_ascii=True))


if __name__ == '__main__':
    asyncio.run(main())
