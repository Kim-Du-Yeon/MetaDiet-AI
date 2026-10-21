"""Offline diagnostic contracts; provider responses and failures are mocked."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.rag import agentic

SECRET = 'private-key-and-prompt-content'


def install_response(monkeypatch, payload):
    class Model:
        def with_structured_output(self, *args, **kwargs):
            return self

        async def ainvoke(self, *args, **kwargs):
            return payload

    from app.core import llm
    monkeypatch.setattr(llm, 'get_chat_model', lambda **kwargs: Model())


def response(*, finish='STOP', parsed=True, error=None, usage=None):
    return {'parsed': agentic.DocumentAssessment(sufficient=True, missing_core=[], supported_document_indices=[]) if parsed else None,
        'parsing_error': error,
        'raw': SimpleNamespace(content=SECRET, response_metadata={'finish_reason': finish},
            usage_metadata=usage)}


@pytest.mark.asyncio
@pytest.mark.parametrize('finish,parsed,error,expected', [
    ('MAX_TOKENS', True, None, 'output_truncated'),
    ('MAX_TOKENS', False, ValueError(SECRET), 'output_truncated'),
    ('STOP', False, ValueError(SECRET), 'parsing_error'),
    ('STOP', False, None, 'missing_parsed'),
])
async def test_output_failures_are_distinct_and_safe(monkeypatch, caplog, finish, parsed, error, expected):
    install_response(monkeypatch, response(finish=finish, parsed=parsed, error=error,
        usage={'input_tokens': 12, 'output_tokens': 9, 'total_tokens': 21,
               'output_token_details': {'reasoning': 4}}))
    with caplog.at_level('INFO'), pytest.raises(ValueError) as caught:
        await agentic.model_assessment(SECRET, {'context': SECRET})
    diagnostic = caught.value.diagnostic
    assert diagnostic['failure_reason'] == expected
    assert diagnostic['finish_reason'] == finish
    assert diagnostic['parsing_error_present'] == bool(error)
    assert diagnostic['usage_status'] == 'complete'
    assert diagnostic['usage']['reasoning_tokens'] == 4
    assert SECRET not in caplog.text + str(caught.value) + json.dumps(diagnostic)
    assert any(getattr(r, 'assessment_diagnostic', None) == diagnostic for r in caplog.records)


@pytest.mark.asyncio
@pytest.mark.parametrize('usage,status', [
    (None, 'missing'), ({}, 'missing'),
    ({'input_tokens': 3}, 'partial'),
    ({'input_tokens': -1}, 'invalid'),
    ({'input_tokens': True}, 'invalid'),
    ({'input_tokens': SECRET}, 'invalid'),
])
async def test_success_logs_usage_without_assuming_zero(monkeypatch, caplog, usage, status):
    install_response(monkeypatch, response(finish=SECRET, usage=usage))
    with caplog.at_level('INFO'):
        result = await agentic.model_assessment(SECRET, {'context': SECRET})
    assert result.sufficient
    diagnostic = next(r.assessment_diagnostic for r in caplog.records
                      if hasattr(r, 'assessment_diagnostic'))
    assert diagnostic['usage_status'] == status
    assert diagnostic['finish_reason'] == 'UNRECOGNIZED'
    assert diagnostic['usage']['output_tokens'] is None
    assert SECRET not in caplog.text + json.dumps(diagnostic)


@pytest.mark.asyncio
async def test_schema_failure_diagnostic_survives_bounded_stop(monkeypatch):
    install_response(monkeypatch, {**response(), 'parsed': {'sufficient': 'invalid', 'missing_core': []}})
    result = await agentic.bounded_retrieve('q', retrieve=AsyncMock(return_value={
        'grounded': True, 'context': SECRET, 'docs': [], 'max_score': .8}))
    assert not result['grounded']
    assert result['agentic']['stop_reason'] == 'controller_error'
    assert result['agentic']['assessment_failure']['failure_reason'] == 'schema_validation_error'
    assert SECRET not in json.dumps(result)


@pytest.mark.asyncio
async def test_raised_parser_exception_is_not_a_provider_failure(monkeypatch, caplog):
    from langchain_core.exceptions import OutputParserException
    class Model:
        def with_structured_output(self, *args, **kwargs):
            return self

        async def ainvoke(self, *args, **kwargs):
            raise OutputParserException(SECRET)

    from app.core import llm
    monkeypatch.setattr(llm, 'get_chat_model', lambda **kwargs: Model())
    with caplog.at_level('INFO'), pytest.raises(ValueError) as caught:
        await agentic.model_assessment('q', {'context': SECRET})
    assert caught.value.diagnostic['failure_reason'] == 'parsing_error'
    assert caught.value.diagnostic['usage_status'] == 'missing'
    assert SECRET not in caplog.text + str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [None, [], 'private-key-and-prompt-content'])
async def test_malformed_envelope_is_safe(monkeypatch, payload):
    install_response(monkeypatch, payload)
    with pytest.raises(ValueError) as caught:
        await agentic.model_assessment('q', {'context': SECRET})
    assert caught.value.diagnostic['failure_reason'] == 'invalid_envelope'
    assert SECRET not in str(caught.value)


@pytest.mark.asyncio
async def test_provider_error_has_safe_log_and_keeps_quota_classification(monkeypatch, caplog):
    class Model:
        def with_structured_output(self, *args, **kwargs):
            return self

        async def ainvoke(self, *args, **kwargs):
            raise RuntimeError('429 ' + SECRET)

    from app.core import llm
    monkeypatch.setattr(llm, 'get_chat_model', lambda **kwargs: Model())
    result = await agentic.bounded_retrieve('q', retrieve=AsyncMock(return_value={
        'grounded': True, 'context': 'evidence', 'max_score': .8, 'docs': []}))
    assert result['agentic']['provider_failure_reason'] == 'quota'
    assert not result['grounded']
    assert any(getattr(r, 'assessment_diagnostic', {}).get('failure_reason') == 'provider_error'
               for r in caplog.records)
    assert SECRET not in caplog.text + json.dumps(result)
