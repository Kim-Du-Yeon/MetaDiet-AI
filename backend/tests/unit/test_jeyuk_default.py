"""The reported mixed meal must not request a hand-entered nutrition label."""
import pytest
from unittest.mock import AsyncMock
from app.tools.simple_meals import parse_simple_meal, calculate_simple_meal
from app.tools.food_catalog import FoodCatalog


@pytest.mark.parametrize('alias',['제육볶음','제육 볶음','돼지고기볶음','매운제육볶음'])
@pytest.mark.parametrize('quantity,grams',[('',200),(' 1인분',200),(' 2인분',400),(' 150g',150),(' 0.5인분',100)])
@pytest.mark.parametrize('prefix',['','오늘 아침에 ','오늘 점심에 ','어제 저녁에 ','오늘 저녁에 계란후라이 4개와 '])
def test_frozen_100_context_alias_quantity_cases(alias,quantity,grams,prefix):
    parsed=parse_simple_meal(prefix+alias+quantity+' 먹었어',allow_unknown=True)
    assert parsed and all(not item.get('unresolved') for item in parsed['items'])
    assert parsed['items'][-1]['quantity_g']==grams
    assert parsed['items'][-1]['portion']['defaulted']==(quantity=='')
    assert parsed['items'][-1]['food_id']=='mfds:D110-465000000-0001'


@pytest.mark.parametrize('text,grams',[
    ('오늘 아침에 계란후라이 4개와 제육볶음 먹었어',[200,200]),
    ('계란후라이 4개 제육 볶음',[200,200]),
    ('제육볶음 300g',[300]),
    ('제육볶음 2인분',[400]),
    ('돼지고기볶음',[200]),
])
@pytest.mark.asyncio
async def test_jeyuk_uses_reviewed_cooked_dish_without_questions(text,grams):
    parsed=parse_simple_meal(text,allow_unknown=True)
    assert parsed and all(not item.get('unresolved') for item in parsed['items'])
    payload=await calculate_simple_meal(parsed,FoodCatalog())
    assert [m['quantity_g'] for m in payload['meals']]==grams
    dish=payload['meals'][-1]
    assert dish['food_id']=='mfds:D110-465000000-0001'
    assert dish['calories']==round(195*grams[-1]/100,1)
    assert dish['nutrition_metadata']['food_kind']=='standard'
    assert dish['nutrition_metadata']['portion']['representative'] is True
    assert dish['nutrition_metadata']['source_date']=='2026-08-28'


@pytest.mark.asyncio
async def test_reported_meal_creates_pending_confirmation_without_model_or_commit():
    from app.agents.team import DietTeam
    repo=AsyncMock()
    repo.create.side_effect=lambda user,thread,payload,key:{
        'id':'test-proposal','version':1,'payload':payload,'kind':'intake','status':'pending'}
    def no_model():raise AssertionError('must not ask for quantities or labels')
    team=DietTeam({'user_id':'test','message':'오늘 아침에 계란후라이 4개와 제육볶음 먹었어',
                   'run_id':'test-run'},model_factory=no_model,repository=repo,db=object())
    result=await team.execute()
    assert result['food_selection'] is None
    assert result['awaiting_confirmation'] is True
    assert len(result['pending_meals'])==2
    assert result['pending_proposal']['status']=='pending'
    assert result['execution_usage']['model_calls']==0
    repo.resolve.assert_not_called()


@pytest.mark.asyncio
async def test_common_lookup_recognizes_the_generic_dish(client,monkeypatch):
    catalog=FoodCatalog()
    monkeypatch.setattr('app.tools.food_catalog.default_catalog',lambda:catalog)
    response=await client.post('/nutrition/lookup',json={'foods':[{'name':'제육볶음','quantity_g':200}]})
    row=response.json()['results'][0]
    assert response.status_code==200 and row['status']=='found'
    assert row['food_id']=='mfds:D110-465000000-0001' and row['calories']==390
