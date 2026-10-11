"""Frozen synthetic decisions and live bounded DietTeam flows; no real DB writes."""
import argparse
import asyncio
import copy
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from langchain_core.messages import AIMessage
from langsmith import Client, traceable, tracing_context
from app.agents.runtime import AgentTool, ExecutionBudget, run_agent
from app.agents.team import DietTeam, BASE_INSTRUCTION, Query, TOOL_NAMES
from app.core.config import get_settings
from app.core.jev import JevClient
from app.core.llm import get_chat_model
from scripts.eval.agent_evaluation import aggregate, grade_decision, validate_gold, asks_for_quantity

SUPERVISOR = BASE_INSTRUCTION + '\n당신은 Supervisor입니다. 필요한 전문 Agent에 위임하고 결과에 따라 다음 작업을 결정하세요. 제안이 만들어지면 추가 제안으로 덮어쓰지 말고 사용자 확인을 요청하세요.'


def select_variants(domain, requested=None):
    available = (['gemini', 'jev'] if domain == 'decision'
                 else ['gemini', 'jev_supervisor', 'jev_tools'])
    if requested is None:
        return available
    invalid = [variant for variant in requested if variant not in available]
    if invalid:
        raise ValueError(f'Variants not valid for {domain}: {invalid}')
    return list(dict.fromkeys(requested))


def minimum_path_excess(successful_tools, required_tools):
    """Diagnostic only: extra successful specialist calls above the gold minimum."""
    specialist_calls = [name for name in successful_tools if not name.startswith('delegate_')]
    return max(0, len(specialist_calls) - len(set(required_tools)))


def trace_options(case_id, split, variant, repeat, experiment):
    return {'metadata': {'case_id': case_id, 'split': split, 'variant': variant,
                         'repeat': repeat, 'experiment': experiment,
                         'data_scope': 'public synthetic fixtures'}}


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf8')


class CapturedModel:
    """Capture real provider output; decision benchmarks stop after one decision.

    The second response is a local sentinel, excluded from provider call/latency
    metrics. It is not a generated final answer or goal completion measurement.
    """
    def __init__(self, *, one_decision=False, collector=None):
        self.provider = get_chat_model()
        self.bound = self.provider
        self.one_decision = one_decision
        self.outputs = collector if collector is not None else []
        self.counter = {'invocations': 0}

    def bind_tools(self, schemas):
        bound = copy.copy(self)
        bound.bound = self.provider.bind_tools(schemas)
        return bound

    def with_structured_output(self, schema):
        delegate = self.provider.with_structured_output(schema, include_raw=True)
        collector = self.outputs
        class StructuredCapture:
            async def ainvoke(self, messages, config=None):
                result = await delegate.ainvoke(messages, config=config)
                raw = result['raw']
                collector.append({'tool_calls': getattr(raw, 'tool_calls', []),
                    'invalid_tool_calls': getattr(raw, 'invalid_tool_calls', []),
                    'usage': raw.usage_metadata or {}, 'content': raw.content,
                    'capture_role': 'structured_validator'})
                if result['parsing_error']:
                    raise result['parsing_error']
                if result['parsed'] is None:
                    raise ValueError('Structured validator returned no parsed result')
                return result['parsed']
        return StructuredCapture()

    async def ainvoke(self, messages, config=None):
        if self.one_decision and self.counter['invocations']:
            return AIMessage(content='Local benchmark sentinel; not a generated answer.')
        self.counter['invocations'] += 1
        response = await self.bound.ainvoke(messages, config=config)
        self.outputs.append({'tool_calls': response.tool_calls,
            'invalid_tool_calls': getattr(response, 'invalid_tool_calls', []),
            'usage': response.usage_metadata or {}, 'content': response.content})
        return response


class ProposalMemory:
    def __init__(self):
        self.created = []

    async def create(self, user_id, thread_id, payload, key):
        self.created.append(payload)
        return {'id': 'synthetic-proposal', 'version': 1, 'payload': payload}


class RejectRealDB:
    def table(self, name):
        raise AssertionError('This experiment must never access a real DB')


class FixtureTeam(DietTeam):
    """Replace external IO only. Original nutrition/proposal/validator code runs."""
    def __init__(self, *args, fault=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fault = fault
        self.search_attempts = 0

    async def rows(self, table, columns='*', **filters):
        if table == 'users':
            return [{'id': 'synthetic-user', 'goal': 'maintain', 'region': 'KR',
                     'age': 30, 'gender': 'male', 'height_cm': 175, 'weight_kg': 70,
                     'allergies': [], 'goal_priority': 'balance'}]
        if table == 'diet_strategies':
            return [{'id': 'synthetic-strategy', 'daily_calories': 1800,
                     'protein_g': 100, 'carbs_g': 230, 'fat_g': 53}]
        if table == 'meal_logs':
            return [{'id': 'm1', 'calories': 1670, 'food_name': '이전 식사',
                     'quantity_g': 100, 'meal_type': 'lunch', 'protein_g': 97,
                     'carbs_g': 202, 'fat_g': 53, 'log_date': date.today().isoformat()}]
        if table == 'inbody_logs':
            return [{'measured_date': '2026-09-01', 'weight_kg': 71,
                     'skeletal_muscle_kg': 30, 'body_fat_kg': 15},
                    {'measured_date': '2026-10-01', 'weight_kg': 70,
                     'skeletal_muscle_kg': 30, 'body_fat_kg': 14}]
        raise AssertionError('Unknown synthetic table')

    async def read_recent_intake(self, args):
        return {'meals': await self.rows('meal_logs'), 'record_completeness': 'unknown'}

    async def search_foods(self, args):
        self.search_attempts += 1
        if self.fault == 'food_once' and self.search_attempts == 1:
            raise ConnectionError('Injected transient food lookup failure')
        return await super().search_foods(args)

    async def search_evidence(self, args):
        # Frozen empty evidence intentionally tests refusal, not RAG quality.
        return {'grounded': False, 'evidence': []}


def food_fixture():
    import pandas as pd
    return pd.DataFrame([{'식품명': '밥', '에너지': 130., '단백질': 3., '탄수화물': 28., '지방': 0., '나트륨': 1.},
                         {'식품명': '두부', '에너지': 80., '단백질': 8., '탄수화물': 2., '지방': 4., '나트륨': 5.}])


async def decision_case(case, variant, config):
    model = CapturedModel(one_decision=True)
    budget = ExecutionBudget()
    executed = []
    async def observe(args, name):
        executed.append({'name': name, 'args': args.model_dump()})
        return {'synthetic': True, 'decision_benchmark_only': True}
    if case['location'] == 'supervisor':
        tools = [AgentTool(n, f'{n.removeprefix("delegate_")} 전문 Agent에 작업 위임', Query,
                           lambda args, name=n: observe(args, name), 'delegate')
                 for n in case['allowed_tools']]
        instruction = SUPERVISOR
    else:
        team = FixtureTeam({'user_id': 'synthetic-user', 'message': case['message']},
                           repository=ProposalMemory(), db=RejectRealDB())
        tools = [AgentTool(t.name, t.description, t.arguments,
                           lambda args, name=t.name: observe(args, name), t.effect)
                 for t in team.tools(case['role'])]
        instruction = BASE_INSTRUCTION + f'\n담당: {case["role"]}'
    request = json.dumps({'original_request': case['message'], 'snapshot': case['snapshot']}, ensure_ascii=False)
    result = await run_agent(model=model, instruction=instruction, request=request, tools=tools,
        allowed_tools=set(case['allowed_tools']), budget=budget, config=config,
        decision_selector=JevClient().choose if variant == 'jev' else None,
        selection_mode='enforce', select_first_only=True)
    calls = model.outputs[0]['tool_calls'] if model.outputs else []
    verdict = grade_decision(case, calls)
    verdict['goal_ok'] = verdict['goal_ok'] and result.status == 'completed'
    # A rejected schema/removed tool may look correctly named but never execute.
    if calls and len(executed) != len(calls):
        verdict['goal_ok'] = False
        verdict['arguments_ok'] = False
    events = [e for e in result.events if e['type'] == 'jev_decision']
    return {**verdict, 'runtime_status': result.status, 'reason': result.reason,
            'requested_calls': calls, 'executed_calls': executed, 'decisions': events,
            'model_calls': len(model.outputs) + len(events), 'provider_outputs': model.outputs,
            'fallbacks': sum(bool(e['fallback_reason']) for e in events)}


async def flow_case(case, variant, config):
    outputs = []
    repository = ProposalMemory()
    state = {'user_id': 'synthetic-user', 'thread_id': case['id'], 'message': case['message']}
    if case['fault'] == 'pending':
        state['pending_proposal'] = {'id': 'synthetic-existing', 'version': 1,
                                    'payload': {'kind': 'intake', 'meals': []}}
    team = FixtureTeam(state, model_factory=lambda: CapturedModel(collector=outputs),
                       repository=repository, db=RejectRealDB(), config=config, fault=case['fault'],
                       decision_client=JevClient() if variant != 'gemini' else None,
                       jev_location=None if variant == 'gemini' else variant.removeprefix('jev_'), jev_mode='enforce')
    with patch('app.tools.nutrition_db._load_raw_df', return_value=food_fixture()):
        result = await team.execute()
    events = result['agent_events']
    successes = [e['tool'] for e in events if e['type'] == 'tool_succeeded']
    requested = [e['tool'] for e in events if e['type'] == 'tool_requested']
    policy = sum(n in case['forbidden_tools'] for n in successes)
    created_kind = repository.created[0]['kind'] if repository.created else None
    kind_ok = created_kind == case['expected_kind']
    required_ok = set(case['required_tools']) <= set(successes)
    # Unknown grams must lead to an actual question; mere termination is not enough.
    asks_quantity = (not case.get('requires_quantity_question', case['id'] == 'flow_ask')
                     or asks_for_quantity(result['response']))
    pending_ok = case['fault'] != 'pending' or result.get('pending_proposal') == state['pending_proposal']
    hitl_ok = not repository.created or result['awaiting_confirmation']
    decisions = [e for e in events if e['type'] == 'jev_decision']
    return {'goal_ok': result['execution_status'] == 'completed' and kind_ok and required_ok and
            asks_quantity and pending_ok and hitl_ok and not policy,
            'runtime_status': result['execution_status'], 'kind_ok': kind_ok,
            'required_tools_ok': required_ok, 'hitl_ok': hitl_ok, 'pending_ok': pending_ok,
            'policy_violations': policy, 'proposal_count': len(repository.created),
            'created_kind': created_kind, 'domain_writes': 0,
            'model_calls': result['execution_usage']['model_calls'],
            'tool_calls': result['execution_usage']['tool_calls'],
            # Diagnostic only; a domain reviewer must decide whether an extra read was harmful.
            'excess_tool_calls': minimum_path_excess(successes, case['required_tools']),
            'fallbacks': sum(bool(e['fallback_reason']) for e in decisions), 'decisions': decisions,
            'events': events, 'response': result['response'], 'provider_outputs': outputs}


async def main(args):
    settings = get_settings()
    cases = json.loads(args.dataset.read_text(encoding='utf8'))
    expected_counts = {'decision': 30, 'flow': 10, 'safety': 20} if args.dataset_profile == 'planned60' else None
    validate_gold(cases, expected_counts)
    if args.dataset_profile == 'independent':
        if not cases or any(case['split'] != 'heldout' for case in cases):
            raise ValueError('Independent final dataset must contain heldout rows only')
        if any(case['domain'] != args.domain for case in cases):
            raise ValueError('Independent final dataset must contain only the selected domain')
    chosen = [c for c in cases if c['domain'] == args.domain and c['split'] == args.split]
    variants = select_variants(args.domain, args.variants)
    args.output.mkdir(parents=True, exist_ok=True)
    identity = {'dataset_sha': hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
                'model': settings.gemini_model, 'jev_model': settings.jev_model,
                'confidence_threshold': .9, 'domain': args.domain, 'split': args.split,
                'repeats': args.repeats, 'variants': variants,
                'fixture_date': date.today().isoformat(),
                'limits': {'models': settings.agent_max_model_calls, 'tools': settings.agent_max_tool_calls,
                           'time': settings.agent_timeout_seconds},
                'codes': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                          ['scripts/eval/run_agent_comparison.py', 'scripts/eval/agent_evaluation.py',
                           'app/agents/team.py', 'app/agents/runtime.py', 'app/core/jev.py', 'app/core/llm.py']}}
    marker = args.output / 'identity.json'
    if marker.exists() and json.loads(marker.read_text(encoding='utf8')) != identity:
        raise ValueError('Experiment identity changed; use a new output directory')
    dump(marker, identity)
    snapshot = args.output / 'dataset-snapshot.json'
    if snapshot.exists() and hashlib.sha256(snapshot.read_bytes()).hexdigest() != identity['dataset_sha']:
        raise ValueError('Frozen dataset snapshot differs from experiment identity')
    if not snapshot.exists():
        snapshot.write_bytes(args.dataset.read_bytes())
    runner = args.output / 'runner-snapshot.py'
    if not runner.exists():
        runner.write_bytes(Path(__file__).read_bytes())
    # Only reviewed public synthetic fixtures reach this evaluation client.
    client = Client(api_key=settings.langsmith_api_key, api_url=settings.langsmith_endpoint,
                    hide_inputs=False, hide_outputs=False)
    @traceable(name='agent-controlled-comparison')
    async def evaluate(case, variant, repeat):
        start = time.perf_counter()
        try:
            config = {'metadata': {'case_id': case['id'], 'split': args.split, 'variant': variant,
                                  'repeat': repeat, 'experiment': args.output.name,
                                  'data_scope': 'public synthetic fixtures'}}
            row = await (decision_case(case, variant, config) if args.domain == 'decision'
                         else flow_case(case, variant, config))
            return {'status': 'completed', **row, 'seconds': time.perf_counter() - start}
        except Exception as exc:
            # Safe categories only; provider errors can contain credentials/URLs.
            return {'status': 'failed', 'error_type': type(exc).__name__, 'goal_ok': False,
                    'seconds': time.perf_counter() - start, 'http_status': getattr(exc, 'code', None)
                    if isinstance(getattr(exc, 'code', None), int) else None}
    rows = []
    with tracing_context(client=client, project_name=settings.langsmith_project,
                         enabled=settings.langsmith_tracing.lower() == 'true'):
        for repeat in range(args.repeats):
            for case in chosen:
                # Alternating order reduces fixed-order provider latency bias.
                order = variants if (repeat + chosen.index(case)) % 2 == 0 else list(reversed(variants))
                for variant in order:
                    path = args.output / f'{variant}-{repeat}-{case["id"]}.json'
                    if path.exists():
                        row = json.loads(path.read_text(encoding='utf8'))
                    else:
                        options = trace_options(case['id'], args.split, variant, repeat, args.output.name)
                        row = {**await evaluate(case, variant, repeat, langsmith_extra=options),
                               'id': case['id'], 'group': case['group'],
                               'variant': variant, 'repeat': repeat, 'location': case.get('location')}
                        dump(path, row)
                    rows.append(row)
                    print(case['id'], variant, repeat, row['status'], row.get('goal_ok'), flush=True)
                    errors = [e['fallback_reason'] for e in row.get('decisions', [])
                              if e.get('fallback_reason') and e['fallback_reason'] != 'low_confidence']
                    if row['status'] == 'failed' or errors:
                        dump(args.output / 'failure.json', {'case_id': case['id'], 'variant': variant,
                            'errors': errors, 'error_type': row.get('error_type')})
                        client.flush()
                        raise RuntimeError('Inspect provider failure before a bounded retry')
    client.flush()
    summaries = {variant: aggregate([r for r in rows if r['variant'] == variant]) for variant in variants}
    dump(args.output / 'report.json', {'identity': identity, 'scope': 'synthetic frozen decisions or live IO-fixture flows; no production adoption',
                                     'summary': summaries, 'rows': rows})
    print(json.dumps(summaries), flush=True)


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, default=ROOT.parent / 'docs/agent_experiments/gold_agent60_v2.json')
    parser.add_argument('--domain', choices=['decision', 'flow'], required=True)
    parser.add_argument('--split', choices=['dev', 'heldout'], required=True)
    parser.add_argument('--repeats', type=int, choices=[1, 3], default=3)
    parser.add_argument('--variants', nargs='+', default=None,
                        help='Optional subset; defaults to every valid comparison variant')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dataset-profile', choices=['planned60', 'independent'], default='planned60')
    return parser


if __name__ == '__main__':
    asyncio.run(main(build_parser().parse_args()))
