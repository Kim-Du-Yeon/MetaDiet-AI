from unittest.mock import AsyncMock
import pytest
from langchain_core.messages import AIMessageChunk
from app.agents.model_delivery import invoke_model
from app.agents.execution_stream import set_event_sink, reset_event_sink


async def test_native_chunks_are_buffered_with_usage_and_no_public_deltas():
    class Model:
        async def astream(self, messages, config=None):
            yield AIMessageChunk(content=[{'type': 'text', 'text': 'private thought', 'thought': True}])
            yield AIMessageChunk(content='검증 전 ')
            yield AIMessageChunk(content='후보', usage_metadata={'input_tokens': 5, 'output_tokens': 2, 'total_tokens': 7})
    sink = AsyncMock(); token = set_event_sink(sink)
    try:
        result = await invoke_model(Model(), [], None, buffered_stream=True)
    finally:
        reset_event_sink(token)
    from app.core.llm import response_text
    assert response_text(result) == '검증 전 후보'
    assert result.usage_metadata['total_tokens'] == 7
    names = [call.args[0] for call in sink.call_args_list]
    assert names.count('model_first_token') == 1
    assert 'answer_delta' not in names


async def test_stream_failure_never_falls_back_to_a_second_billable_call():
    class Model:
        ainvoke = AsyncMock()
        async def astream(self, messages, config=None):
            yield AIMessageChunk(content='partial')
            raise ConnectionError('provider-private')
    model = Model()
    with pytest.raises(ConnectionError):
        await invoke_model(model, [], None, buffered_stream=True)
    model.ainvoke.assert_not_awaited()


async def test_fragmented_tool_arguments_and_signature_survive_aggregation():
    class Model:
        async def astream(self, messages, config=None):
            yield AIMessageChunk(content='', tool_call_chunks=[{'name': 'read_intake', 'args': '{"date":',
                'id': 'call1', 'index': 0}], additional_kwargs={'__gemini_function_call_thought_signatures__': {'call1': 'opaque-signature'}})
            yield AIMessageChunk(content='', tool_call_chunks=[{'name': None, 'args': '"today"}',
                'id': None, 'index': 0}])
    result = await invoke_model(Model(), [], None, buffered_stream=True)
    assert result.tool_calls[0]['args'] == {'date': 'today'}
    assert result.additional_kwargs['__gemini_function_call_thought_signatures__']['call1'] == 'opaque-signature'
