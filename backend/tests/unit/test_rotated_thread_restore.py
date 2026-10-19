from types import SimpleNamespace
from unittest.mock import AsyncMock


def test_initial_state_uses_actual_rotated_thread():
    import app.api.routes.main as main
    req=main.ChatRequest(message='검토해줘',thread_id='old')
    assert main._initial_state(req,'owner','run',thread_id='new')['thread_id']=='new'


async def test_restore_recovers_completed_turn_from_owner_scoped_checkpoint(monkeypatch,fake_sb):
    import app.api.routes.main as main
    graph=SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={
        'message':'기록 검토','response':'확인된 기록 분석','agent_used':'goal',
        'execution_status':'completed'},next=())))
    monkeypatch.setattr(main,'get_graph',lambda:graph)
    monkeypatch.setattr(main,'_public_stats',AsyncMock(return_value={}))
    fake_sb.tables['chat_history']=[]
    result=await main.restore_session('new','owner')
    assert result['messages']==[{'role':'user','content':'기록 검토'},
        {'role':'assistant','content':'확인된 기록 분석','agent_used':'goal'}]
    assert graph.aget_state.call_args.args[0]['configurable']['thread_id']=='owner_new'


async def test_restore_attaches_basis_only_to_matching_latest_answer(monkeypatch, fake_sb):
    import app.api.routes.main as main
    basis = {'documents': [], 'limitation': 'no search'}
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={
        'message':'question', 'response':'answer', 'agent_used':'meal', 'answer_basis':basis,
        'execution_status':'completed'}, next=())))
    monkeypatch.setattr(main, 'get_graph', lambda:graph)
    monkeypatch.setattr(main, '_public_stats', AsyncMock(return_value={}))
    fake_sb.tables['chat_history'] = []
    result = await main.restore_session('new', 'owner')
    assert result['messages'][-1]['answer_basis'] == basis
    assert 'answer_basis' not in result['messages'][0]
