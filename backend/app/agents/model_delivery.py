"""Native provider streaming is buffered until the existing final guard passes."""
import time
from langchain_core.messages import message_chunk_to_message
from app.agents.execution_stream import emit_runtime_event
from app.core.llm import response_text


async def invoke_model(model, messages, config, *, buffered_stream=False):
    started = time.perf_counter()
    if not buffered_stream:
        response = await model.ainvoke(messages, config=config)
    else:
        aggregate = None
        first = False
        async for chunk in model.astream(messages, config=config):
            # No text, arguments or thought content goes to the event sink.
            if not first and response_text(chunk).strip():
                first = True
                await emit_runtime_event('model_first_token', elapsed_ms=round((time.perf_counter()-started)*1000, 3))
            aggregate = chunk if aggregate is None else aggregate + chunk
        if aggregate is None:
            raise ValueError('empty_model_stream')
        response = message_chunk_to_message(aggregate)
    usage = getattr(response, 'usage_metadata', None) or {}
    await emit_runtime_event('model_usage', **{
        name: max(0, int(usage.get(name, 0))) for name in ('input_tokens', 'output_tokens', 'total_tokens')})
    return response
