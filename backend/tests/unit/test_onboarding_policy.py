from datetime import date
from unittest.mock import AsyncMock
import pytest
from app.core.energy_policy import EnergyInputs


def energy():
    return EnergyInputs(age=30,sex='male',weight_kg=70,height_cm=170,
                        activity='low_active',general_adult_confirmed=True)


def test_onboarding_age_uses_whole_years():
    from app.core.onboarding import OnboardingRequest
    with pytest.raises(ValueError):
        OnboardingRequest(**{**energy().model_dump(),'age':30.5},goal='maintain')


def test_initial_baseline_has_reviewed_formula_and_no_goal_deficit():
    from app.core.onboarding import baseline_payload
    from app.rag.strategy_evidence import evaluate_strategy,load_claims
    req=energy()
    profile={**req.model_dump(),'gender':req.sex,'goal':'diet','region':'KR',
        'nutrition_policy_context':req.model_dump()}
    p=baseline_payload(profile,None)
    r=evaluate_strategy(p,profile,load_claims())
    assert r==p['evidence_policy']
    assert p['daily_calories']>2000
    assert '유지' in p['strategy_note']
    profile['weight_kg']=71
    with pytest.raises(ValueError): evaluate_strategy(p,profile,load_claims())


def test_complete_diet_goal_creates_hitl_adjustment_not_direct_write():
    from datetime import timedelta
    from app.core.onboarding import baseline_payload
    from app.rag.strategy_evidence import evaluate_strategy,load_claims
    req=energy()
    profile={**req.model_dump(),'gender':req.sex,'goal':'diet','region':'KR',
        'target_weight_kg':65,'target_date':date.today()+timedelta(days=100),
        'nutrition_policy_context':req.model_dump()}
    payload=baseline_payload(profile,None)
    receipt=evaluate_strategy(payload,profile,load_claims())
    assert payload['daily_calories']==receipt['goal_assessment']['target_calories']
    assert receipt['goal_assessment']['applied_adjustment_kcal']==-500
    assert any(item['claim_key']=='weight_loss_adjustment' for item in receipt['decisions'])
    assert '확정 전' in payload['strategy_note']


async def test_legacy_new_signup_cannot_write_strategy(fake_sb,mock_current_user):
    from app.api.routes.main import setup_user
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await setup_user('diet',170,70,30,'male',auth_id=mock_current_user)
    assert not fake_sb.calls


async def test_legacy_missing_strategy_cannot_mutate_profile(fake_sb,mock_current_user):
    from app.api.routes.main import setup_user
    from fastapi import HTTPException
    fake_sb.tables['users']=[{'id':mock_current_user}]
    with pytest.raises(HTTPException):
        await setup_user('diet',170,70,30,'male',auth_id=mock_current_user)
    assert not fake_sb.calls


async def test_onboarding_returns_pending_and_preserves_active(monkeypatch):
    from app.api.routes.main import complete_onboarding
    from app.core.onboarding import OnboardingRequest
    save=AsyncMock(return_value={'pending_proposal':{'status':'pending'},'strategy_change_requires_confirmation':True})
    monkeypatch.setattr('app.core.onboarding.save_onboarding',save)
    req=OnboardingRequest(**energy().model_dump(),goal='diet',region='KR')
    result=await complete_onboarding(req,auth_id='a')
    assert result['pending_proposal']['status']=='pending'
    save.assert_awaited_once()


def test_goal_and_profile_change_invalidates_receipt():
    from app.core.onboarding import baseline_payload
    from app.rag.strategy_evidence import evaluate_strategy,load_claims
    u={**energy().model_dump(),'gender':'male','goal':'maintain','region':'KR',
       'nutrition_policy_context':energy().model_dump()}
    p=baseline_payload(u,None)
    u['goal']='bulk'
    assert evaluate_strategy(p,u,load_claims())!=p['evidence_policy']
