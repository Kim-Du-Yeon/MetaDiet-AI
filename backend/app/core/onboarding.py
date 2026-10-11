"""Transactional profile and pending maintenance baseline creation."""
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal
from uuid import uuid4
from pydantic import Field, field_validator
from psycopg.types.json import Jsonb
from app.core.energy_policy import EnergyInputs,estimate_maintenance
from app.db.proposals import ProposalRepository, connection
from app.rag.strategy_evidence import evaluate_strategy,load_claims
from app.core.goal_policy import assess_goal
from app.core.account_lifecycle import AccountDeletionInProgress, auth_id_hash
from app.core.service_clock import service_today


class OnboardingRequest(EnergyInputs):
    goal: Literal['diet','bulk','maintain']
    region: Literal['KR'] = 'KR'
    target_weight_kg: float | None = Field(default=None,gt=0,le=500)
    target_date: date | None = Field(default=None, strict=False)
    goal_priority: Literal['speed','muscle','balance'] | None = None

    @field_validator('age')
    @classmethod
    def whole_years(cls,value):
        if not value.is_integer(): raise ValueError('온보딩 나이는 만 나이 정수로 입력해주세요.')
        return value


async def onboarding_status(auth_id:str):
    async with connection() as conn:
        user=await (await conn.execute('select id from users where auth_id=%s',(auth_id,))).fetchone()
        if not user: return {}
        active=await (await conn.execute('select * from diet_strategies where user_id=%s and is_active=true order by created_at desc limit 1',(user['id'],))).fetchone()
        # Existing users may continue without re-entering restricted onboarding.
        if active: return {'current_strategy':dict(active)}
        pending=await (await conn.execute("select * from agent_proposals where user_id=%s and thread_id='onboarding' and status='pending' and expires_at>now() order by version desc limit 1",(user['id'],))).fetchone()
        return {'pending_proposal':ProposalRepository.public(pending)} if pending else {}


def baseline_payload(profile, active_id):
    ctx=profile['nutrition_policy_context']
    result=estimate_maintenance(EnergyInputs(**ctx))
    goal_assessment=assess_goal(profile,result['maintenance_kcal'])
    claims=load_claims()
    evidence=[]
    for c in claims:
        e={k:c[k] for k in ('source','page','excerpt','document_sha256')}
        e.update(source_url=c.get('source_url'),edition=str(c['year']),population=c['population'])
        if e not in evidence: evidence.append(e)
    target_kcal=goal_assessment['target_calories']
    macros={'protein_g':round(target_kcal*.20/4,2),
            'carbs_g':round(target_kcal*.55/4,2),
            'fat_g':round(target_kcal*.25/9,2)}
    applied=goal_assessment['status']=='adjustment_ready'
    state_text=('검토된 감량 조정 제안이며 확정 전에는 적용되지 않습니다.' if applied
                else '초기 유지 에너지 기준선이며 목표별 조정은 미적용입니다.')
    p={'kind':'strategy','daily_calories':target_kcal, **macros,
       'strategy_note':f"목표: {profile['goal']}. {state_text} "
                       +goal_assessment['message']+' '+result['message'],
       'evidence':evidence,'policy_version':'evidence-v1',
       'effective_date':service_today().isoformat(),'based_on_strategy_id':active_id}
    p['evidence_policy']=evaluate_strategy(p,profile,claims)
    return p


async def save_onboarding(req:OnboardingRequest,auth_id:str):
    ctx=EnergyInputs(**{k:getattr(req,k) for k in EnergyInputs.model_fields}).model_dump()
    if req.target_date and req.target_date<=service_today():
        raise ValueError('목표일은 오늘 이후로 입력해주세요.')
    async with connection() as conn:
        hashed_auth_id=auth_id_hash(auth_id)
        await conn.execute(
            'select pg_advisory_xact_lock_shared(hashtextextended(%s,0))',
            (f'account-lifecycle:{hashed_auth_id}',),
        )
        deleting=await (await conn.execute(
            'select 1 from account_deletion_tombstones where auth_id_hash=%s',
            (hashed_auth_id,),
        )).fetchone()
        if deleting:
            raise AccountDeletionInProgress('account_deletion_in_progress')
        # Same auth_id serializes even the first concurrent signup (no existing row).
        await conn.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))',(str(auth_id),))
        user=await (await conn.execute('select * from users where auth_id=%s for update',(auth_id,))).fetchone()
        user_id=user['id'] if user else uuid4()
        profile={**(user or {}),'goal':req.goal,'region':req.region,'age':req.age,
                 'weight_kg':req.weight_kg,'height_cm':req.height_cm,'gender':req.sex,
                 'target_weight_kg':req.target_weight_kg,'target_date':req.target_date,
                 'goal_priority':req.goal_priority,
                 'nutrition_policy_context':ctx}
        active=await (await conn.execute('select * from diet_strategies where user_id=%s and is_active=true order by created_at desc limit 1',(user_id,))).fetchone()
        payload=baseline_payload(profile,str(active['id']) if active else None)
        # Existing users keep their confirmed strategy. Profile updates require a new proposal.
        values=(req.goal,req.height_cm,req.age,req.weight_kg,req.target_weight_kg,
                req.target_date,req.goal_priority,req.region,Jsonb(ctx))
        if user:
            await conn.execute('update users set goal=%s,height_cm=%s,age=%s,weight_kg=%s,target_weight_kg=%s,target_date=%s,goal_priority=%s,region=%s,nutrition_policy_context=%s where id=%s',(*values,user_id))
        else:
            await conn.execute("insert into users(goal,height_cm,age,weight_kg,target_weight_kg,target_date,goal_priority,region,nutrition_policy_context,id,auth_id,name) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'')",(*values,user_id,auth_id))
        @asynccontextmanager
        async def same_transaction():
            yield conn
        proposal=await ProposalRepository(same_transaction).create(str(user_id),'onboarding',payload,str(uuid4()))
        assessment=payload['evidence_policy']['goal_assessment']
        message=('검토된 일반 성인 감량 조정 제안입니다. 확인 전에는 활성 전략이 변경되지 않습니다.'
                 if assessment['status']=='adjustment_ready'
                 else '초기 유지 기준선 제안입니다. 확인 전에는 활성 전략이 변경되지 않습니다.')
        return {'pending_proposal':proposal,'strategy_change_requires_confirmation':True,
                'goal_assessment':assessment,
                'current_strategy':dict(active) if active else None,
                'message':message}
