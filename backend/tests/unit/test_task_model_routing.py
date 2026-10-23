from types import SimpleNamespace

import pytest

from app.core import llm


@pytest.fixture
def setup_models(monkeypatch):
    settings = SimpleNamespace(gemini_api_key='synthetic', gemini_model='flash-fixture',
        gemini_simple_model='lite-fixture', gemini_vision_model='vision-fixture',
        gemini_eval_model='pro-fixture', model_routing_enabled=True,
        model_timeout_seconds=30, eval_model_timeout_seconds=90, model_max_retries=0)
    made = []
    def provider(**kwargs):
        made.append(kwargs)
        return SimpleNamespace(bind_tools=lambda tools, **kw: tools)
    monkeypatch.setattr(llm, 'get_settings', lambda: settings)
    monkeypatch.setattr(llm, 'ChatGoogleGenerativeAI', provider)
    return settings, made


@pytest.mark.parametrize('task', ['extraction', 'classification', 'query_translation'])
def test_only_bounded_tasks_use_simple_model(setup_models, task):
    settings, made = setup_models
    model = llm.get_chat_model(task=task)
    model.prepare()
    assert made[-1]['model'] == 'lite-fixture'
    settings.model_routing_enabled = False
    llm.get_chat_model(task=task).prepare()
    assert made[-1]['model'] == 'flash-fixture'


@pytest.mark.parametrize('role,expected', [('chat', 'flash-fixture'),
    ('vision', 'vision-fixture'), ('eval', 'pro-fixture')])
def test_agent_vision_and_judge_are_independent(setup_models, role, expected):
    llm.get_chat_model(role=role).prepare()
    assert setup_models[1][-1]['model'] == expected


def test_explicit_model_override_and_tools_keep_native_contract(setup_models):
    model = llm.get_chat_model(task='classification', model_name='explicit-fixture')
    assert model.bind_tools([{'name': 'read_profile'}]).bound == [{'name': 'read_profile'}]
    assert setup_models[1][-1]['model'] == 'explicit-fixture'


def test_unsafe_task_or_role_combination_rejected(setup_models):
    with pytest.raises(ValueError):
        llm.get_chat_model(task='user-supplied-arbitrary-purpose')
    with pytest.raises(ValueError):
        llm.get_chat_model(role='eval', task='classification')


def test_selection_metadata_has_no_credentials(setup_models):
    model = llm.get_chat_model(task='extraction')
    assert model.selection_metadata() == {'model_name': 'lite-fixture',
        'model_task': 'extraction', 'model_routing': True}
    assert 'synthetic' not in str(model.selection_metadata())
