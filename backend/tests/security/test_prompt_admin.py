
async def test_prompt_control_requires_admin(client):
    assert (await client.get('/admin/prompts')).status_code==401
    assert (await client.post('/admin/prompts/refresh')).status_code==401

async def test_prompt_control_never_returns_bodies(client):
    from app.api.routes.main import app
    from app.core.auth import get_current_admin
    app.dependency_overrides[get_current_admin]=lambda:'synthetic-admin'
    try:
        result=await client.get('/admin/prompts')
        assert result.status_code==200 and result.json()['ab_enabled'] is False
        assert 'texts' not in result.json() and 'signature' not in result.json()
    finally:app.dependency_overrides.pop(get_current_admin,None)
