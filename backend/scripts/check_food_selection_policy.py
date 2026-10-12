"""Live read-only catalog + Gemini policy check; proposals stay in memory."""
import asyncio, json, sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agents.team import DietTeam
from app.tools.food_catalog import FoodCatalog
from app.db.food_catalog import FoodRepository
from app.core.service_clock import service_today
from eval.run_food_agent_comparison import MemoryProposals

async def main():
    request = '오늘 쌀밥 450g, 삼겹살구이 200g, 고등어구이 300g, 라이스페이퍼 80g 먹었어. 기록만 해줘.'
    async def run(message):
        team = DietTeam({'message': message, 'requested_action': 'record_only', 'user_id': str(uuid4()), 'thread_id': 'synthetic-standard-policy', 'today_date': service_today().isoformat()}, repository=MemoryProposals(), db=object(), config={'tags': ['synthetic', 'standard-policy']})
        team.food_catalog = FoodCatalog(repository=FoodRepository())
        return await team.execute()
    first = await run(request)
    cards = first.get('food_selection')
    assert cards and cards['items'] and not first.get('pending_proposal'), first['response']
    assert all(item['query'] not in ('쌀밥', '삼겹살구이', '고등어구이') for item in cards['items'])
    selections = '\n'.join('제품 선택: ' + item['candidates'][0]['food_id'] + ' / ' + item['candidates'][0]['name'] + ' 80g' for item in cards['items'])
    second = await run(request + '\n' + selections)
    proposal = second.get('pending_proposal')
    assert proposal, second['response']
    meals = proposal['payload']['meals']
    assert len(meals) == 4 and sum(m['source'] == 'csv' for m in meals) == 3 and sum(m['source'] == 'mfds' for m in meals) == 1
    report = {'synthetic': True, 'domain_writes': 0, 'general_standard_count': 3, 'product_card_count': len(cards['items']), 'proposal_meal_count': len(meals), 'stages': [{'execution_status': r['execution_status'], 'usage': r['execution_usage']} for r in (first, second)], 'limitations': ['Synthetic first candidate choice, no assertion of actual consumed manufacturer', 'Local Agent with live Gemini and DB reads; not public browser verification']}
    Path('../docs/food_catalog/SELECTION_POLICY_LIVE.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report))
if __name__ == '__main__':
    if sys.platform == 'win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
