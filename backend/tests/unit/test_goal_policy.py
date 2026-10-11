from datetime import date,timedelta
import pytest
from app.core.goal_policy import assess_goal
from app.core.service_clock import service_today


def profile(**changes):
    return {'goal':'diet','region':'KR','weight_kg':70,'height_cm':170,
            'target_weight_kg':65,'target_date':service_today()+timedelta(days=100),**changes}


def test_reviewed_diet_policy_applies_conservative_deficit_to_eligible_adult():
    d=assess_goal(profile(),2400)
    assert d['status']=='adjustment_ready'
    assert d['reason_code']=='reviewed_adult_weight_loss_policy'
    assert d['applied_adjustment_kcal']==-500
    assert d['target_calories']==1900
    assert d['target_change_kg']==-5
    assert d['requested_weekly_change_kg']==pytest.approx(-.35)
    assert d['requested_rate_is_recommendation'] is False
    assert d['source_review']['source']=='guideline2022_vol8.pdf'
    assert d['source_review']['pdf_page']==6
    assert d['source_review']['newer_scope_check']['scope']=='diagnosis_and_pharmacologic_treatment'


def test_diet_policy_defers_normal_bmi_and_insufficient_safe_deficit():
    normal=assess_goal(profile(weight_kg=60,target_weight_kg=55),2100)
    assert normal['status']=='adjustment_deferred'
    assert normal['reason_code']=='weight_loss_population_not_applicable'
    low=assess_goal(profile(),1600)
    assert low['status']=='adjustment_deferred'
    assert low['reason_code']=='minimum_energy_floor_blocks_reviewed_deficit'
    assert low['target_calories']==1600


def test_diet_policy_uses_documented_floor_and_never_creates_vlcd():
    d=assess_goal(profile(weight_kg=114,target_weight_kg=105),2100)
    assert d['minimum_energy_floor_kcal']==1500
    assert d['target_calories']==1600
    assert d['target_calories']>800


def test_four_week_trend_requests_review_without_inventing_calorie_cut():
    from app.core.goal_policy import assess_weight_trend
    slow=assess_weight_trend([
        {'measured_date':'2026-01-01','weight_kg':80},
        {'measured_date':'2026-01-30','weight_kg':79},
    ])
    assert slow['status']=='lifestyle_review_recommended'
    assert slow['weight_loss_pct']==pytest.approx(1.25)
    assert slow['automatic_calorie_adjustment_kcal']==0
    assert slow['requires_human_confirmation'] is True
    adequate=assess_weight_trend([
        {'measured_date':'2026-01-01','weight_kg':80},
        {'measured_date':'2026-01-30','weight_kg':77.5},
    ])
    assert adequate['status']=='continue_current_strategy'
    assert assess_weight_trend([{'measured_date':'2026-01-30','weight_kg':80}])['status']=='insufficient_data'


def test_bulk_does_not_apply_small_training_study_to_everyone():
    d=assess_goal(profile(goal='bulk',target_weight_kg=75),2400)
    assert d['reason_code']=='bulk_applicability_unverified'
    assert d['applied_adjustment_kcal']==0


def test_maintenance_is_ready_without_claiming_weight_change():
    d=assess_goal(profile(goal='maintain',target_weight_kg=None,target_date=None),2400)
    assert d['status']=='maintenance_ready'
    assert d['requested_weekly_change_kg'] is None


@pytest.mark.parametrize('changes',[{'target_weight_kg':75},{'target_weight_kg':70},
    {'target_date':service_today()},{'target_date':'not-a-date'},
    {'target_weight_kg':float('nan')},{'target_date':True},
    {'goal':'bulk','target_weight_kg':65},{'goal':'maintain','target_weight_kg':65}])
def test_inconsistent_goals_rejected(changes):
    with pytest.raises(ValueError): assess_goal(profile(**changes),2400)


def test_goal_receipt_captures_target_and_date():
    from app.core.onboarding import baseline_payload
    from app.core.energy_policy import EnergyInputs
    from app.rag.strategy_evidence import evaluate_strategy,load_claims
    ctx=EnergyInputs(age=30,sex='male',weight_kg=70,height_cm=170,
                    activity='low_active',general_adult_confirmed=True).model_dump()
    u={**profile(),**ctx,'nutrition_policy_context':ctx}
    p=baseline_payload(u,None)
    assert p['evidence_policy']['goal_assessment']['reason_code']=='reviewed_adult_weight_loss_policy'
    assert p['daily_calories']==p['evidence_policy']['goal_assessment']['target_calories']
    assert p['evidence_policy']['goal_assessment']['applied_adjustment_kcal']==-500
    assert '감량' in p['strategy_note']
    u['target_weight_kg']=64
    assert evaluate_strategy(p,u,load_claims())!=p['evidence_policy']


async def test_agent_cannot_label_unconfirmed_adjustment_as_completed_diet():
    from unittest.mock import AsyncMock
    from app.agents.team import DietTeam,StrategyDraft
    from app.core.onboarding import baseline_payload
    from app.core.energy_policy import EnergyInputs
    ctx=EnergyInputs(age=30,sex='male',weight_kg=70,height_cm=170,
                    activity='low_active',general_adult_confirmed=True).model_dump()
    u={**profile(),**ctx,'nutrition_policy_context':ctx,'strategy':None}
    p=baseline_payload(u,None)
    team=DietTeam({'user_id':'u','message':'감량해줘'},repository=AsyncMock(),db=object())
    team.profile=u; team.validate=AsyncMock()
    team.evidence={str(i):e for i,e in enumerate(p['evidence'])}
    draft=StrategyDraft(**{k:p[k] for k in ('daily_calories','protein_g','carbs_g','fat_g')},
                        strategy_note='완료된 맞춤 감량 처방입니다',evidence_ids=list(team.evidence))
    await team.propose_strategy(draft)
    assert '완료된 맞춤 감량' not in team.proposal['strategy_note']
    assert '확정 전' in team.proposal['strategy_note']
