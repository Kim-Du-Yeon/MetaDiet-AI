"""Fixed synthetic interview demo. No DB, no real-user input, explicit --live."""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class NoDatabase:
    def table(self, *args, **kwargs):
        raise RuntimeError('Database access disabled in interview demo')


class MemoryProposals:
    async def create(self, user, thread, payload, key):
        if user != 'synthetic-interview':
            raise ValueError('Only the fixed synthetic identity is allowed')
        return {'id': 'synthetic-proposal', 'version': 1, 'kind': payload['kind'],
                'payload': payload, 'status': 'pending'}


def demo_state():
    return {'user_id': 'synthetic-interview', 'thread_id': 'synthetic-demo',
            'run_id': 'synthetic-'+uuid4().hex,
            'message': '오늘 점심에 조리된 쌀밥 200g을 먹었어. 기록만 해줘. 음식 검색 후 계산해서 확인할 제안을 만들어줘.',
            'requested_action': 'record_only',
            'tool_policy': ['search_foods', 'nutrition_lookup', 'propose_meal']}


async def execute_demo(team_factory=None):
    if team_factory is None:
        from app.agents.team import DietTeam
        team_factory = DietTeam
    return await team_factory(demo_state(), repository=MemoryProposals(), db=NoDatabase(),
                              simple_meals_enabled=False).execute()


def visible_payload(value):
    """Provider signatures stay redacted; conversational content must be visible."""
    def clean(item):
        if isinstance(item, dict):
            return {k:clean(v) for k,v in item.items() if k not in
                    {'signature','__gemini_function_call_thought_signatures__'}}
        if isinstance(item,list): return [clean(v) for v in item]
        return item
    return bool(value) and '[REDACTED]' not in json.dumps(clean(value),ensure_ascii=False)


async def live_demo(output: Path):
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1]/'.env', override=True)
    os.environ.pop('GOOGLE_API_KEY', None)
    if os.getenv('RENDER') or os.getenv('APP_ENV','').lower() in {'production','staging'}:
        raise RuntimeError('Run this synthetic demo in a separate local process')
    os.environ.update(TRACE_DATA_MODE='synthetic', TRACE_SYNTHETIC_ONLY='true',
                      AGENT_MAX_MODEL_CALLS='8', AGENT_MAX_TOOL_CALLS='12',
                      AGENT_TIMEOUT_SECONDS='90')
    from app.core.trace_policy import synthetic_trace_context
    from langsmith import traceable
    from langchain_core.tracers.langchain import wait_for_all_tracers
    root_id=uuid4()
    # The same question appears in the root and the actual Team LLM messages.
    @traceable(name='trace-smoke')
    async def run(question):
        return await execute_demo()
    from langsmith.run_helpers import get_tracing_context
    with synthetic_trace_context('metadiet-synthetic-interview'):
        trace_client=get_tracing_context()['client']
        result=await run(demo_state()['message'],langsmith_extra={'run_id':root_id})
    wait_for_all_tracers()
    trace_client.flush()
    client=trace_client
    await asyncio.sleep(3)
    root=client.read_run(root_id,load_child_runs=True)
    llms=[r for r in root.child_runs or [] if r.run_type=='llm']
    report={'synthetic':True,'database_access':'disabled','production_fast_path':'disabled_for_demo_only',
            'root_run_id':str(root_id),'url':client.get_run_url(run=root),
            'question':demo_state()['message'],'response':result.get('response'),
            'awaiting_confirmation':result.get('awaiting_confirmation'),
            'status':result.get('execution_status'),'agent_events':result.get('agent_events'),
            'usage':result.get('execution_usage'),
            'llms':[{'model':(r.extra or {}).get('metadata',{}).get('ls_model_name'),
                     'tokens':r.total_tokens,'cost':str(r.total_cost),
                     'input_visible':visible_payload(r.inputs),
                     'output_visible':visible_payload(r.outputs)} for r in llms]}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not llms or not all(r['input_visible'] and r['output_visible'] for r in report['llms']):
        raise RuntimeError('Trace visibility check failed; inspect saved report')
    if not result.get('awaiting_confirmation'):
        raise RuntimeError('Proposal did not reach confirmation; inspect saved report')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Call Gemini and send synthetic traces to LangSmith')
    parser.add_argument('--output',type=Path,default=Path('tmp/interview-trace.json'))
    args=parser.parse_args()
    if not args.live:
        print(json.dumps({'preview':demo_state(),'database_access':'disabled','live':False},ensure_ascii=False,indent=2))
        return
    asyncio.run(live_demo(args.output))


if __name__=='__main__': main()
