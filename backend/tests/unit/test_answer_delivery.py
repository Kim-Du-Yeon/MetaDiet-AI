import asyncio,json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.api.routes import main

@pytest.mark.parametrize('after_seq',[0,1002])
async def test_answer_delivery_has_no_positive_delay_and_preserves_replay(monkeypatch,after_seq):
    graph=SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={
        'response':'밥 한 공기와 채소를 드세요.','user_id':'u'},next=())))
    monkeypatch.setattr(main,'_public_stats',AsyncMock(return_value={}))
    waits=[];original=asyncio.sleep
    async def sleep(seconds):
        waits.append(seconds);await original(0)
    monkeypatch.setattr(main.asyncio,'sleep',sleep)
    frames=[frame async for frame in main._stream(graph,{'configurable':{'thread_id':'u_t'}},'r',after_seq)]
    events=[json.loads(frame.split('data: ',1)[1]) for frame in frames]
    deltas=[e for e in events if e['type']=='answer_delta']
    assert [e['seq'] for e in deltas]==list(range(max(1001,after_seq+1),1006))
    assert ''.join(e['content'] for e in deltas)==('밥 한 공기와 채소를 드세요. ' if after_seq==0 else '공기와 채소를 드세요. ')
    assert events[-1]['type']=='completed' and events[-1]['seq']==100000
    assert waits and all(seconds==0 for seconds in waits)
    graph.aget_state.assert_awaited_once()
