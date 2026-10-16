"""Broad representative coverage, separate from nutrient accuracy/live-model eval."""
import json
from pathlib import Path
import pytest
from app.tools.simple_meals import parse_simple_meal, calculate_simple_meal
from app.tools.food_catalog import FoodCatalog

DATA=json.loads((Path(__file__).resolve().parents[3]/'docs/food_catalog/COMMON_FOODS_100.json').read_text(encoding='utf-8'))
FOODS=[food for group in DATA['categories'].values() for food in group]

@pytest.mark.parametrize('food',FOODS)
async def test_frozen_100_distinct_foods_have_editable_server_quote(food):
    parsed=parse_simple_meal(f'오늘 점심에 {food} 먹었어',allow_unknown=True)
    assert parsed and len(parsed['items'])==1,food
    assert not parsed['items'][0].get('unresolved'),food
    payload=await calculate_simple_meal(parsed,FoodCatalog())
    meal=payload['meals'][0]
    assert meal['quantity_g']>0 and meal['calories']>=0
    assert meal['food_id'] and meal['nutrition_metadata']['portion']['defaulted']

@pytest.mark.parametrize('food,expected,forbidden',[
    ('김치볶음밥','김치','새우'),('크림스파게티','크림','미트'),
    ('수육','삶은것','탕수육'),('계란찜','찜','후라이'),('참치김밥','참치','김밥용김'),
])
async def test_no_specific_dish_substituted_with_another(food,expected,forbidden):
    parsed=parse_simple_meal(food,allow_unknown=True)
    assert parsed and not parsed['items'][0].get('unresolved')
    meal=(await calculate_simple_meal(parsed,FoodCatalog()))['meals'][0]
    assert expected in meal['food_name'] and forbidden not in meal['food_name']

@pytest.mark.parametrize('text,grams',[
    ('된장 찌개 150g',150),('김치 볶음밥 2인분',600),('주꾸미 볶음 200g',200),
    ('달걀 말이 0.5인분',50),('수박 200g',200),('돈가스 2인분',400),
])
async def test_aliases_and_explicit_mass_precede_app_serving(text,grams):
    parsed=parse_simple_meal(text,allow_unknown=True)
    assert parsed and not parsed['items'][0].get('unresolved')
    meal=(await calculate_simple_meal(parsed,FoodCatalog()))['meals'][0]
    assert meal['quantity_g']==grams
    assert meal['nutrition_metadata']['portion']['defaulted'] is False

async def test_mfds_generic_standard_is_not_a_brand_selection_gate():
    from unittest.mock import AsyncMock
    from app.agents.team import DietTeam, FoodSearch, FoodLookup
    team=DietTeam({'user_id':'synthetic','message':'된장찌개 먹었어'},repository=AsyncMock(),db=object())
    team.food_catalog=FoodCatalog()
    matches=await team.search_foods(FoodSearch(query='된장찌개',food_kind='standard'))
    assert len(matches)==1 and matches[0]['food_kind']=='standard'
    assert team.food_selection['items']==[]
    quote=await team.nutrition_lookup(FoodLookup(food_id=matches[0]['food_id'],quantity_g=200))
    assert quote['calories']==92

@pytest.mark.parametrize('text,count',[
    ('김밥 한줄 계란말이 먹었어',2),('된장 찌개 한그릇 잡곡 밥 먹었어',2),
    ('닭도리탕 야채샐러드 먹었어',2),('참치 김밥 복숭아 먹었어',2),
])
async def test_mixed_aliases_create_only_pending_proposal(text,count):
    from unittest.mock import AsyncMock
    from app.agents.team import DietTeam
    repo=AsyncMock()
    repo.create.side_effect=lambda user,thread,payload,key:{'id':'test','version':1,
        'kind':'intake','status':'pending','payload':payload}
    def no_model():raise AssertionError('must use reviewed representatives')
    team=DietTeam({'user_id':'synthetic','message':text,'run_id':'test'},
        model_factory=no_model,repository=repo,db=object())
    result=await team.execute()
    assert result['awaiting_confirmation'] and result['food_selection'] is None
    assert len(result['pending_proposal']['payload']['meals'])==count
    assert result['execution_usage']['model_calls']==0
    repo.resolve.assert_not_called()


def test_reviewed_registry_rejects_product_or_missing_macros(tmp_path):
    from copy import deepcopy
    from app.tools.common_representatives import REGISTRY,load_registry
    path=tmp_path/'registry.json'
    data=deepcopy(REGISTRY)
    data['catalog_rows'][0]['manufacturer']='some brand'
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='invalid_representative_source'):load_registry(path)
    data=deepcopy(REGISTRY)
    data['catalog_rows'][0]['nutrients']['protein_g']=None
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='invalid_representative_nutrient'):load_registry(path)

async def test_dish_alias_beats_same_named_raw_ingredient():
    # CSV has a raw fermented-soybean ingredient named 청국장. Intake means the stew.
    catalog=FoodCatalog()
    rows=await catalog.search('청국장',kind='standard')
    assert len(rows)==1 and rows[0]['food_id']=='mfds:D106-297000000-0001'
    quote=await catalog.lookup(rows[0]['food_id'],200)
    assert quote['food_name']=='청국장찌개' and quote['calories']==94

async def test_spaced_stew_alias_uses_same_generic_id_not_legacy_product():
    parsed=parse_simple_meal('김치 찌개 먹었어',allow_unknown=True)
    assert parsed['items'][0]['food_id']=='mfds:D306-266000000-0001'
    meal=(await calculate_simple_meal(parsed,FoodCatalog()))['meals'][0]
    assert meal['nutrition_metadata']['food_kind']=='standard'
    assert not meal['nutrition_metadata']['manufacturer']
