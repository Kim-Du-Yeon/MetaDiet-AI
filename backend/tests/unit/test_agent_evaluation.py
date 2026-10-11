import pytest
from scripts.eval.agent_evaluation import grade_decision, validate_gold, aggregate


def case(**changes):
    return {"id": "a", "group": "g", "split": "dev", "domain": "decision",
            "location": "tools", "allowed_tools": ["read_profile", "read_intake"],
            "acceptable_next": ["read_profile", "read_intake"], "constraints": {}, **changes}


def test_decision_accepts_alternative_valid_paths_but_rejects_forbidden_calls():
    assert grade_decision(case(), [{"name": "read_intake", "args": {}}])["goal_ok"]
    result = grade_decision(case(), [{"name": "search_evidence", "args": {"query": "x"}}])
    assert not result["goal_ok"] and result["policy_violations"] == 1
    assert not grade_decision(case(), [])["goal_ok"]


def test_selected_tool_with_wrong_arguments_is_not_success():
    gold = case(allowed_tools=["nutrition_lookup"], acceptable_next=["nutrition_lookup"],
                constraints={"nutrition_lookup": {"food_id": 0, "quantity_g": 100}})
    assert not grade_decision(gold, [{"name": "nutrition_lookup", "args": {"food_id": 0, "quantity_g": 200}}])["goal_ok"]
    assert grade_decision(gold, [{"name": "nutrition_lookup", "args": {"food_id": 0, "quantity_g": 100}}])["goal_ok"]


def test_gold_rejects_translation_group_leakage_and_missing_review():
    rows = [case(review={"reviewer": "source-scenario-review", "scope": "synthetic"}),
            case(id="b", split="heldout", review={"reviewer": "source-scenario-review", "scope": "synthetic"})]
    with pytest.raises(ValueError, match="group"):
        validate_gold(rows, expected_counts=None)
    with pytest.raises(ValueError, match="review"):
        validate_gold([case()], expected_counts=None)


def test_failed_attempt_stays_in_denominator_and_fallback_is_visible():
    result = aggregate([{"status": "completed", "goal_ok": True, "seconds": 1,
                         "model_calls": 2, "tool_calls": 4, "excess_tool_calls": 1,
                         "fallbacks": 1},
                        {"status": "failed", "seconds": 3, "model_calls": 1,
                         "tool_calls": 2, "excess_tool_calls": 0, "fallbacks": 0}])
    assert result["goal_rate"] == .5 and result["failed"] == 1
    assert result["fallbacks"] == 1 and result["n"] == 2
    assert result["tool_calls"] == 6 and result["excess_tool_calls"] == 1


def test_variant_selection_can_isolate_the_production_gemini_path():
    from scripts.eval.run_agent_comparison import build_parser, minimum_path_excess, select_variants
    assert select_variants('decision', ['gemini']) == ['gemini']
    assert select_variants('flow', ['gemini']) == ['gemini']
    with pytest.raises(ValueError, match='not valid'):
        select_variants('decision', ['jev_tools'])
    args = build_parser().parse_args(['--domain', 'decision', '--split', 'dev',
                                      '--output', 'unused'])
    assert args.dataset.name == 'gold_agent60_v2.json'
    assert minimum_path_excess(
        ['read_intake', 'search_foods', 'nutrition_lookup', 'propose_meal', 'delegate_meal'],
        ['search_foods', 'nutrition_lookup', 'propose_meal']) == 1


def test_safety_runner_uses_selector_loop_on_windows():
    import asyncio
    from scripts.eval.run_agent_safety import event_loop_factory
    assert event_loop_factory('win32') is asyncio.SelectorEventLoop
    assert event_loop_factory('linux') is None


def test_agent_trace_metadata_identifies_the_exact_experiment():
    from scripts.eval.run_agent_comparison import trace_options
    assert trace_options('case-1', 'heldout', 'gemini', 2, 'release-v1') == {
        'metadata': {'case_id': 'case-1', 'split': 'heldout', 'variant': 'gemini',
                     'repeat': 2, 'experiment': 'release-v1',
                     'data_scope': 'public synthetic fixtures'}}


def test_analysis_rejects_changed_gold_and_stale_variants(tmp_path):
    import hashlib
    import json
    from scripts.eval.analyze_agent_comparison import validate_source_identity

    dataset = tmp_path / 'gold.json'
    dataset.write_text('[{"id":"a"}]', encoding='utf8')
    digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    (tmp_path / 'dataset-snapshot.json').write_bytes(dataset.read_bytes())
    (tmp_path / 'identity.json').write_text(json.dumps({
        'dataset_sha': digest, 'variants': ['gemini']}), encoding='utf8')

    assert validate_source_identity(tmp_path, dataset) == {'gemini'}
    dataset.write_text('[{"id":"a","changed":true}]', encoding='utf8')
    with pytest.raises(ValueError, match='dataset SHA'):
        validate_source_identity(tmp_path, dataset)


def test_analysis_rejects_result_variant_outside_frozen_manifest():
    from scripts.eval.analyze_agent_comparison import validate_result_variant
    validate_result_variant('gemini', {'gemini'})
    with pytest.raises(ValueError, match='variant'):
        validate_result_variant('jev', {'gemini'})


async def test_adversarial_replays_execute_boundaries_and_return_feedback():
    from scripts.eval.run_agent_safety import replay
    forbidden = await replay({'scenario': 'write'})
    assert forbidden['writes'] == 0
    assert 'tool_not_allowed' in str(forbidden['feedback'])
    repeated = await replay({'scenario': 'repeat'})
    assert repeated['reason'] == 'repeated_tool_failure'
    recovered = await replay({'scenario': 'recover'})
    assert recovered['executed'] == ['search_evidence']
    assert recovered['feedback'][0]['error'] == 'tool_unavailable'


async def test_empty_model_response_cannot_pass_finish_decision(monkeypatch):
    from langchain_core.messages import AIMessage
    import scripts.eval.run_agent_comparison as runner
    class Model:
        outputs = []
        def __init__(self, **kwargs):
            pass
        async def ainvoke(self, messages, config=None):
            result = AIMessage(content='')
            self.outputs = [{'tool_calls': [], 'usage': {}}]
            return result
    monkeypatch.setattr(runner, 'CapturedModel', Model)
    result = await runner.decision_case(case(location='supervisor', snapshot={}, message='ask',
                                           allowed_tools=[], acceptable_next=['finish']), 'gemini', {})
    assert result['runtime_status'] == 'blocked'
    assert not result['goal_ok']


async def test_capture_wrapper_preserves_unbound_finish_path(monkeypatch):
    from langchain_core.messages import AIMessage
    import scripts.eval.run_agent_comparison as runner
    class Provider:
        def bind_tools(self, schemas):
            class Bound:
                async def ainvoke(self, messages, config=None):
                    return AIMessage(content='bound')
            return Bound()
        async def ainvoke(self, messages, config=None):
            return AIMessage(content='unbound')
    monkeypatch.setattr(runner, 'get_chat_model', Provider)
    model = runner.CapturedModel()
    bound = model.bind_tools([])
    assert (await model.ainvoke([])).content == 'unbound'
    assert (await bound.ainvoke([])).content == 'bound'
    assert len(model.outputs) == 2


def test_quantity_clarification_requires_an_explicit_question_or_request():
    from scripts.eval.agent_evaluation import asks_for_quantity
    assert not asks_for_quantity('밥의 양을 알 수 없어 제안을 보류했습니다.')
    assert not asks_for_quantity('Logging finished.')
    assert asks_for_quantity('밥을 몇 g 드셨나요?')
    assert asks_for_quantity('섭취한 양을 그램으로 알려주세요.')


async def test_structured_validator_tokens_are_captured(monkeypatch):
    from langchain_core.messages import AIMessage
    from app.agents.team import Verdict
    import scripts.eval.run_agent_comparison as runner
    class Provider:
        def with_structured_output(self, schema, include_raw=False):
            class Structured:
                async def ainvoke(self, messages, config=None):
                    parsed = Verdict(passed=True, feedback='ok')
                    raw = AIMessage(content='parsed', usage_metadata={'input_tokens': 12, 'output_tokens': 3, 'total_tokens': 15})
                    return {'raw': raw, 'parsed': parsed, 'parsing_error': None} if include_raw else parsed
            return Structured()
    monkeypatch.setattr(runner, 'get_chat_model', Provider)
    model = runner.CapturedModel()
    verdict = await model.with_structured_output(Verdict).ainvoke([])
    assert verdict.passed
    assert model.outputs[0]['usage']['total_tokens'] == 15
